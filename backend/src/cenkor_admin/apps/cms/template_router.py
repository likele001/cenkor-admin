"""CMS 模板 API（后台）

四件事：
1. validate —— 编译期报错定位到行列，编辑器标红用
2. preview  —— 拿真实内容渲染，支持未保存的跨文件覆盖（改 partial 立刻在页面里生效）
3. files    —— 主题文件的读写，在线编辑器的后端
4. themes   —— 主题增删、切换生效、与内置版逐行对比、zip 导入导出

旧接口 /templates/render 保留原返回结构（rendered/error），前端不用改。
"""
from __future__ import annotations

import asyncio
import difflib
import hashlib
import io
import json
import logging
import re
import zipfile
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms import builtin_theme, models, static_cache
from cenkor_admin.apps.cms.render import (
    KIND_TEMPLATE,
    RENDER_TIMEOUT,
    invalidate_theme_cache,
    make_preview_resolver,
    resolve_theme,
    theme_documents,
)
from cenkor_admin.apps.cms.template_context import TemplateContext, get_session_factory
from cenkor_admin.core import jinja_env
from cenkor_admin.core.db import get_db

router = APIRouter()

logger = logging.getLogger(__name__)

DEFAULT_SITE_ID = 1

# 主题名同时是 URL 片段和磁盘标识，收紧到小写字母数字
_THEME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

# 页面级模板：编辑器里直接渲染自己；其余（partial/macro/asset）挂在宿主页面上预览
PAGE_LEVEL_TEMPLATES = ("layout.html", "list.html", "detail.html", "page.html", "404.html")

# zip 导入的三道体积闸，挡住 zip bomb 与误传的整站包
MAX_ZIP_BYTES = 5 * 1024 * 1024
MAX_ZIP_FILES = 300
MAX_ZIP_FILE_BYTES = 1024 * 1024
_SKIP_PARTS = ("__MACOSX", ".DS_Store", "Thumbs.db", "manifest.json")


async def _invalidate_all(db: AsyncSession, site_id: int | None, theme: str | None = None) -> None:
    """模板/主题变更后统一失效：Jinja 模板缓存 + 已落盘的静态页。

    版式一动，之前落盘的 HTML 全是旧版，不整站撤掉就会出现
    「后台改了模板，线上还是老样子」——这正是静态化最容易被骂的坑。
    site_id 为空表示影响全部站点。
    """
    invalidate_theme_cache(site_id, theme)
    if not static_cache.cache_enabled():
        return
    try:
        if site_id:
            await static_cache.purge_site_by_id(db, site_id)
        else:
            static_cache.purge_all()
    except Exception as exc:
        logger.warning("模板变更后清理静态缓存失败 site_id=%s theme=%s: %s", site_id, theme, exc)


class TemplateRenderRequest(BaseModel):
    template: str = Field(default="", description="模板源码")
    data: dict[str, Any] = Field(default_factory=dict, description="附加数据")


class TemplateValidateRequest(BaseModel):
    template: str = ""
    source: str | None = None

    def text(self) -> str:
        return self.template or self.source or ""


class PreviewRequest(BaseModel):
    """预览：给源码 + 指定一条内容，按主题真实渲染。"""

    source: str = ""
    path: str = "detail.html"
    kind: str = "article"
    slug: str | None = None
    site_id: int = DEFAULT_SITE_ID
    theme: str | None = None
    # 编辑器里其它未保存的文件：{path: source}，让跨文件 include 也能实时看到
    overrides: dict[str, str] = Field(default_factory=dict)


class TemplateSaveRequest(BaseModel):
    theme: str = "default"
    path: str
    content: str
    kind: str | None = None
    site_id: int = DEFAULT_SITE_ID


class ThemeCreateRequest(BaseModel):
    theme: str
    name: str | None = None
    from_theme: str | None = None
    site_id: int = DEFAULT_SITE_ID


class ThemeActiveRequest(BaseModel):
    theme: str
    site_id: int = DEFAULT_SITE_ID


# ---------------------------------------------------------------- 校验 / 渲染


@router.post("/templates/validate")
async def templates_validate(body: TemplateValidateRequest):
    """校验语法。失败时带 line/col，编辑器直接标红。"""
    source = body.text()
    ok, error = jinja_env.validate_source(source)
    return {"valid": ok, "ok": ok, "error": error, "message": (error or {}).get("message")}


@router.post("/templates/render")
async def templates_render(body: TemplateRenderRequest):
    """渲染模板字符串（旧接口，返回结构保持不变）。"""
    if not body.template:
        return {"rendered": "", "html": "", "error": None}
    html, error = await _render_with_data(body.template, body.data)
    if error:
        raise HTTPException(400, f"模板渲染失败: {error}")
    return {"rendered": html, "html": html, "error": None}


@router.post("/templates/preview")
async def templates_preview(body: TemplateRenderRequest):
    """模板预览（与 render 同源，不抛错，专门给编辑器实时预览）。"""
    html, error = await _render_with_data(body.template, body.data)
    return {"rendered": html, "html": html, "error": error, "ok": error is None}


@router.post("/templates/preview-page")
async def templates_preview_page(body: PreviewRequest):
    """按主题上下文预览：能调 content_list / site / nav 等全部数据 API。"""
    html, error = await _preview_page(body)
    return {"html": html, "error": error, "ok": error is None}


async def _render_with_data(source: str, data: dict[str, Any]) -> tuple[str, str | None]:
    try:
        html = await asyncio.wait_for(
            asyncio.to_thread(jinja_env.render_source, source, data),
            timeout=RENDER_TIMEOUT,
        )
        return html, None
    except TimeoutError:
        return "", f"渲染超时（>{RENDER_TIMEOUT:.0f}s）"
    except Exception as exc:
        return "", str(exc)


def _preview_template_name(path: str, kind: str) -> str:
    """编辑 partial/macro 时挂到宿主页面上渲染，改样式不用来回切文件。"""
    name = (path or "").rsplit("/", 1)[-1]
    if name in PAGE_LEVEL_TEMPLATES:
        return name
    return KIND_TEMPLATE.get(kind or "article", "detail.html")


def _preview_page_sync(body: PreviewRequest) -> str:
    """同步渲染（线程里跑，独立 sync session，不碰主事件循环）。"""
    if body.path and not jinja_env.is_safe_template_name(body.path):
        raise ValueError("非法模板路径")

    overrides = {k: v for k, v in (body.overrides or {}).items() if jinja_env.is_safe_template_name(k)}
    if body.path:
        overrides[body.path] = body.source

    factory = get_session_factory()
    session = factory()
    token = None
    try:
        theme = (body.theme or "").strip() or resolve_theme(session, body.site_id)
        resolver = make_preview_resolver(session, body.site_id, theme, overrides)
        ctx = TemplateContext(session, site_id=body.site_id, base="")

        item = ctx.content(body.kind, body.slug) if body.slug else None
        if item is None:
            item = _sample_item(ctx, body.kind)
        title = item.get("title") if item else "预览"
        page = {
            "kind": body.kind,
            "title": title,
            "full_title": f"{title} · 预览",
            "description": (item or {}).get("excerpt") or "",
            "canonical": "",
            "base": "",
            "og": {"type": body.kind, "site_name": (ctx.site_meta("brand.name") or "Cenkor"),
                   "title": title, "description": "", "url": "", "image": "", "video": ""},
            "json_ld": "",
            "published_at": (item or {}).get("published_at"),
            "updated_at": None,
            "item": item,
            "items": ctx.content_list(body.kind, limit=6),
            "pagination": ctx.pagination(1, 12, 6),
        }
        context = {
            **ctx.as_globals(),
            "page": page,
            "item": item,
            "items": page["items"],
            "pagination": page["pagination"],
            "base_url": "",
            "theme_css": resolver("assets/style.css") or "",
            "theme_name": theme,
        }
        token = jinja_env.set_resolver(resolver)
        return jinja_env.render_template_file(_preview_template_name(body.path, body.kind), context)
    finally:
        if token is not None:
            jinja_env.reset_resolver(token)
        session.close()


def _sample_item(ctx: TemplateContext, kind: str) -> dict[str, Any]:
    return {
        "id": 0,
        "type": kind,
        "slug": "preview",
        "title": "预览标题：这是一条示例内容",
        "excerpt": "列表里展示的摘要文字，用来检查折行和截断效果。",
        "cover": "",
        "url": "#",
        "published_at": None,
        "updated_at": None,
        "view_count": 128,
        "ai_generated": False,
        "body_html": "<p>这是正文示例段落。可以放<strong>加粗</strong>、<a href='#'>链接</a>、列表和图片，用来检查排版。</p><h2>小标题</h2><p>第二段正文。</p>",
        "content": {"text": "这是正文示例段落。"},
        "custom_fields": {},
        "seo": {},
        "category": None,
        "tags": ["示例标签", "排版"],
    }


async def _preview_page(body: PreviewRequest) -> tuple[str, str | None]:
    try:
        html = await asyncio.wait_for(
            asyncio.to_thread(_preview_page_sync, body),
            timeout=RENDER_TIMEOUT,
        )
        return html, None
    except TimeoutError:
        return "", f"渲染超时（>{RENDER_TIMEOUT:.0f}s）"
    except Exception as exc:
        return "", str(exc)


# ---------------------------------------------------------------- 主题管理


@router.get("/templates/themes")
async def templates_themes(site_id: int = DEFAULT_SITE_ID, db: AsyncSession = Depends(get_db)):
    """主题列表：内置 + DB 里存在的。"""
    active = await _resolve_theme_async(db, site_id)
    counts: dict[str, int] = {}
    rows = (await db.execute(
        select(models.CmsTemplate.theme).where(models.CmsTemplate.site_id == site_id)
    )).scalars().all()
    for theme in rows:
        counts[theme] = counts.get(theme, 0) + 1

    out = []
    for name in builtin_theme.list_builtin_themes():
        meta = builtin_theme.get_builtin_meta(name) or {}
        out.append({
            "theme": name, "name": meta.get("name") or name,
            "version": meta.get("version"), "author": meta.get("author"),
            "description": meta.get("description"), "source": "builtin",
            "files": len(builtin_theme.BUILTIN_THEMES.get(name, {})),
            "custom_files": counts.get(name, 0),
            "editable": True,
            "deletable": False,
            "active": name == active,
        })
    for name, count in counts.items():
        if name in builtin_theme.BUILTIN_THEMES:
            continue
        out.append({
            "theme": name, "name": name, "version": None, "author": None,
            "description": None, "source": "db", "files": count,
            "custom_files": count, "editable": True,
            "deletable": name != active,
            "active": name == active,
        })
    return {"items": out, "active": active}


@router.post("/templates/themes", status_code=201)
async def templates_theme_create(body: ThemeCreateRequest, db: AsyncSession = Depends(get_db)):
    """新建主题：把基线的有效文件整份复制过来，形成可独立演进的 fork。"""
    theme = (body.theme or "").strip()
    if not _THEME_RE.match(theme):
        raise HTTPException(400, "主题名只能用小写字母、数字、连字符和下划线（2-64 位）")

    exists = (await db.execute(
        select(models.CmsTemplate.id).where(
            models.CmsTemplate.site_id == body.site_id, models.CmsTemplate.theme == theme
        ).limit(1)
    )).scalars().first()
    if exists is not None or theme in builtin_theme.BUILTIN_THEMES:
        raise HTTPException(409, f"主题「{theme}」已存在")

    from_theme = (body.from_theme or builtin_theme.DEFAULT_THEME).strip()
    docs = _theme_documents_sync(body.site_id, from_theme)
    if not docs:
        raise HTTPException(404, f"基线主题「{from_theme}」不存在")

    for path, content in docs.items():
        db.add(models.CmsTemplate(
            site_id=body.site_id, theme=theme, path=path,
            kind=_kind_of(path), content=content, checksum=_md5(content),
        ))
    await db.commit()
    await _invalidate_all(db, body.site_id, theme)
    return {"ok": True, "theme": theme, "from_theme": from_theme, "files": len(docs)}


@router.delete("/templates/themes/{theme}")
async def templates_theme_delete(
    theme: str,
    site_id: int = DEFAULT_SITE_ID,
    db: AsyncSession = Depends(get_db),
):
    """删主题。删内置名等于「还原内置」，当前生效的自定义主题要先切走。"""
    if not _THEME_RE.match(theme):
        raise HTTPException(400, "非法主题名")
    active = await _resolve_theme_async(db, site_id)
    is_builtin = theme in builtin_theme.BUILTIN_THEMES
    if theme == active and not is_builtin:
        raise HTTPException(400, "该主题正在生效，先切换到别的主题再删除")

    result = await db.execute(
        delete(models.CmsTemplate).where(
            models.CmsTemplate.site_id == site_id, models.CmsTemplate.theme == theme
        )
    )
    await db.commit()
    await _invalidate_all(db, site_id, theme)
    return {"ok": True, "theme": theme, "deleted": result.rowcount or 0,
            "reverted_to_builtin": bool(is_builtin)}


@router.put("/templates/themes/active")
async def templates_theme_active(body: ThemeActiveRequest, db: AsyncSession = Depends(get_db)):
    """切换站点生效主题，写 Site.settings['cms.theme']。"""
    theme = (body.theme or "").strip()
    if not _THEME_RE.match(theme):
        raise HTTPException(400, "非法主题名")
    if theme not in builtin_theme.BUILTIN_THEMES:
        exists = (await db.execute(
            select(models.CmsTemplate.id).where(
                models.CmsTemplate.site_id == body.site_id, models.CmsTemplate.theme == theme
            ).limit(1)
        )).scalars().first()
        if exists is None:
            raise HTTPException(404, f"主题「{theme}」不存在")

    row = (await db.execute(select(models.Site).where(models.Site.id == body.site_id))).scalars().first()
    if row is None:
        raise HTTPException(404, "站点不存在")
    settings = dict(row.settings or {})
    settings["cms.theme"] = theme
    row.settings = settings
    await db.commit()
    await _invalidate_all(db, body.site_id)
    return {"ok": True, "active": theme}


# ---------------------------------------------------------------- 主题 / 文件


@router.get("/templates/files")
async def templates_files(
    theme: str = "default",
    site_id: int = DEFAULT_SITE_ID,
    db: AsyncSession = Depends(get_db),
):
    """主题文件树：内置文件 + DB 覆盖标记。自定义主题未覆盖的文件标 inherited。"""
    if not _THEME_RE.match(theme or ""):
        raise HTTPException(400, "非法主题名")
    base_paths = set(builtin_theme.BUILTIN_THEMES.get(builtin_theme.DEFAULT_THEME, {}))
    theme_paths = set(builtin_theme.BUILTIN_THEMES.get(theme, {}))
    rows = (await db.execute(
        select(models.CmsTemplate.path).where(
            models.CmsTemplate.site_id == site_id,
            models.CmsTemplate.theme == theme,
        )
    )).scalars().all()
    custom = set(rows)
    paths = sorted(base_paths | theme_paths | custom)
    return {
        "theme": theme,
        "items": [
            {
                "path": p,
                "kind": _kind_of(p),
                "templatable": p.endswith((".html", ".xml")),
                "overridden": p in custom,
                "builtin": p in theme_paths,
                "inherited": p not in custom and p not in theme_paths and p in base_paths,
                "source": "db" if p in custom else ("builtin" if p in theme_paths else "inherited"),
            }
            for p in paths
        ],
    }


@router.get("/templates/file")
async def templates_file_get(
    path: str = Query(..., description="主题内相对路径"),
    theme: str = "default",
    site_id: int = DEFAULT_SITE_ID,
    db: AsyncSession = Depends(get_db),
):
    if not jinja_env.is_safe_template_name(path):
        raise HTTPException(400, "非法模板路径")
    if not _THEME_RE.match(theme or ""):
        raise HTTPException(400, "非法主题名")
    row = (await db.execute(
        select(models.CmsTemplate).where(
            models.CmsTemplate.site_id == site_id,
            models.CmsTemplate.theme == theme,
            models.CmsTemplate.path == path,
        )
    )).scalars().first()
    if row is not None:
        return {"path": path, "content": row.content, "source": "db",
                "checksum": row.checksum, "updated_at": row.updated_at}
    builtin = _baseline_source(theme, path)
    if builtin is None:
        raise HTTPException(404, "模板不存在")
    return {"path": path, "content": builtin, "source": "builtin", "checksum": None, "updated_at": None}


@router.put("/templates/file")
async def templates_file_save(body: TemplateSaveRequest, db: AsyncSession = Depends(get_db)):
    """保存模板。语法错误直接拒，不留半成品在库里。"""
    if not jinja_env.is_safe_template_name(body.path):
        raise HTTPException(400, "非法模板路径")
    if not _THEME_RE.match(body.theme or ""):
        raise HTTPException(400, "非法主题名")
    ok, error = jinja_env.validate_source(body.content)
    if not ok:
        raise HTTPException(400, {"message": "模板语法错误", "error": error})
    checksum = _md5(body.content)
    row = (await db.execute(
        select(models.CmsTemplate).where(
            models.CmsTemplate.site_id == body.site_id,
            models.CmsTemplate.theme == body.theme,
            models.CmsTemplate.path == body.path,
        )
    )).scalars().first()
    if row is None:
        row = models.CmsTemplate(
            site_id=body.site_id, theme=body.theme, path=body.path,
            kind=body.kind or _kind_of(body.path), content=body.content, checksum=checksum,
        )
        db.add(row)
    else:
        row.content = body.content
        row.checksum = checksum
        if body.kind:
            row.kind = body.kind
    await db.commit()
    await _invalidate_all(db, body.site_id, body.theme)
    return {"ok": True, "path": body.path, "checksum": checksum}


@router.delete("/templates/file")
async def templates_file_delete(
    path: str = Query(...),
    theme: str = "default",
    site_id: int = DEFAULT_SITE_ID,
    db: AsyncSession = Depends(get_db),
):
    """删除覆盖，回落到内置版本。"""
    row = (await db.execute(
        select(models.CmsTemplate).where(
            models.CmsTemplate.site_id == site_id,
            models.CmsTemplate.theme == theme,
            models.CmsTemplate.path == path,
        )
    )).scalars().first()
    if row is None:
        raise HTTPException(404, "没有该覆盖文件")
    await db.delete(row)
    await db.commit()
    await _invalidate_all(db, site_id, theme)
    return {"ok": True, "path": path, "reverted_to": "builtin"}


@router.get("/templates/diff")
async def templates_diff(
    path: str = Query(...),
    theme: str = "default",
    site_id: int = DEFAULT_SITE_ID,
    db: AsyncSession = Depends(get_db),
):
    """当前 DB 版 vs 内置版的逐行差异，用于「我改了什么 / 回滚前确认」。"""
    if not jinja_env.is_safe_template_name(path):
        raise HTTPException(400, "非法模板路径")
    row = (await db.execute(
        select(models.CmsTemplate).where(
            models.CmsTemplate.site_id == site_id,
            models.CmsTemplate.theme == theme,
            models.CmsTemplate.path == path,
        )
    )).scalars().first()
    if row is None:
        return {"path": path, "changed": False, "diff": "", "added": 0, "removed": 0,
                "left": None, "right": None}
    baseline = _baseline_source(theme, path) or ""
    left = baseline.splitlines(keepends=True)
    right = (row.content or "").splitlines(keepends=True)
    diff_lines = list(difflib.unified_diff(
        left, right, fromfile=f"builtin/{path}", tofile=f"{theme}/{path}", n=3
    ))
    added = sum(1 for ln in diff_lines if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in diff_lines if ln.startswith("-") and not ln.startswith("---"))
    return {
        "path": path,
        "changed": bool(diff_lines),
        "diff": "".join(diff_lines),
        "added": added,
        "removed": removed,
        "left": baseline,
        "right": row.content,
        "updated_at": row.updated_at,
    }


# ---------------------------------------------------------------- 主题包导入导出


@router.get("/templates/export")
async def templates_export(
    theme: str = "default",
    site_id: int = DEFAULT_SITE_ID,
    db: AsyncSession = Depends(get_db),
):
    """导出主题包（zip）。内容是「基线 + DB 覆盖」合并后的完整文件，拿去另一站点可直接导入。"""
    if not _THEME_RE.match(theme or ""):
        raise HTTPException(400, "非法主题名")
    docs = _theme_documents_sync(site_id, theme)
    if not docs:
        raise HTTPException(404, "主题没有可导出的文件")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = {
            "theme": theme,
            "files": sorted(docs),
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "site_id": site_id,
        }
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for path, content in sorted(docs.items()):
            zf.writestr(path, content)
    payload = buf.getvalue()
    stamp = datetime.now().strftime("%Y%m%d")
    return Response(
        content=payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{theme}-{stamp}.zip"',
            "X-File-Count": str(len(docs)),
            "X-Byte-Size": str(len(payload)),
        },
    )


@router.post("/templates/import")
async def templates_import(
    file: UploadFile = File(..., description="主题包 zip"),
    theme: str = Form(..., description="导入到哪个主题，不存在则自动创建"),
    site_id: int = Form(DEFAULT_SITE_ID),
    overwrite: bool = Form(True),
    db: AsyncSession = Depends(get_db),
):
    """导入主题包。先全量校验（路径合法性 + Jinja 语法），有一处不合格就整体拒绝。"""
    theme = (theme or "").strip()
    if not _THEME_RE.match(theme):
        raise HTTPException(400, "主题名只能用小写字母、数字、连字符和下划线（2-64 位）")

    raw = await file.read()
    if not raw:
        raise HTTPException(400, "上传文件为空")
    if len(raw) > MAX_ZIP_BYTES:
        raise HTTPException(413, f"主题包不能超过 {MAX_ZIP_BYTES // 1024 // 1024}MB")

    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise HTTPException(400, f"不是合法的 zip 文件：{exc}") from exc

    errors: list[dict[str, Any]] = []
    accepted: dict[str, str] = {}
    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > MAX_ZIP_FILES:
        raise HTTPException(413, f"主题包内文件数上限 {MAX_ZIP_FILES}")

    for info in infos:
        name = info.filename.replace("\\", "/")
        if any(part in name for part in _SKIP_PARTS):
            continue
        if not jinja_env.is_safe_template_name(name):
            errors.append({"path": name, "message": "路径非法或扩展名不在白名单"})
            continue
        if info.file_size > MAX_ZIP_FILE_BYTES:
            errors.append({"path": name, "message": f"单文件超过 {MAX_ZIP_FILE_BYTES // 1024}KB"})
            continue
        try:
            content = zf.read(info).decode("utf-8")
        except UnicodeDecodeError:
            errors.append({"path": name, "message": "不是 UTF-8 文本"})
            continue
        if name.endswith((".html", ".xml")):
            ok, err = jinja_env.validate_source(content, name=name)
            if not ok:
                errors.append({"path": name, **(err or {"message": "语法错误"})})
                continue
        accepted[name] = content

    if errors:
        raise HTTPException(400, {"message": f"{len(errors)} 个文件未通过校验，已整体拒绝", "errors": errors})
    if not accepted:
        raise HTTPException(400, "主题包里没有可导入的文件")

    existing = set((await db.execute(
        select(models.CmsTemplate.path).where(
            models.CmsTemplate.site_id == site_id, models.CmsTemplate.theme == theme
        )
    )).scalars().all())

    written, skipped = 0, 0
    for path, content in accepted.items():
        if path in existing:
            if not overwrite:
                skipped += 1
                continue
            row = (await db.execute(
                select(models.CmsTemplate).where(
                    models.CmsTemplate.site_id == site_id,
                    models.CmsTemplate.theme == theme,
                    models.CmsTemplate.path == path,
                )
            )).scalars().first()
            row.content = content
            row.checksum = _md5(content)
            row.kind = _kind_of(path)
        else:
            db.add(models.CmsTemplate(
                site_id=site_id, theme=theme, path=path,
                kind=_kind_of(path), content=content, checksum=_md5(content),
            ))
        written += 1

    await db.commit()
    await _invalidate_all(db, site_id, theme)
    return {"ok": True, "theme": theme, "written": written, "skipped": skipped,
            "files": sorted(accepted)}


# ---------------------------------------------------------------- 教程数据


@router.get("/templates/context-api")
async def templates_context_api():
    """教程用：列出模板里能调的所有数据 API。"""
    return {
        "apis": [
            {"name": "content_list", "sign": "content_list(type='article', limit=20, offset=0, category=None, tag=None, sort='-published_at', exclude=None)", "desc": "条目列表"},
            {"name": "content", "sign": "content(type='article', slug='')", "desc": "单条详情（含 body_html）"},
            {"name": "related", "sign": "related(item, limit=4)", "desc": "相关推荐"},
            {"name": "search", "sign": "search(kw='', limit=20, page=1)", "desc": "站内搜索"},
            {"name": "categories", "sign": "categories(type='article')", "desc": "分类列表（带文章数）"},
            {"name": "category_tree", "sign": "category_tree(type='article')", "desc": "分类树"},
            {"name": "tags", "sign": "tags(type='article', limit=50)", "desc": "标签列表"},
            {"name": "nav", "sign": "nav(key='main')", "desc": "菜单树"},
            {"name": "site", "sign": "site.name / site['brand.name']", "desc": "站点信息（预注入 dict）"},
            {"name": "site_meta", "sign": "site_meta(key=None)", "desc": "站点配置取值"},
            {"name": "pagination", "sign": "pagination(page=1, total=0, per_page=20)", "desc": "分页对象"},
            {"name": "asset", "sign": "asset(path='')", "desc": "静态资源地址"},
            {"name": "url", "sign": "url(kind='home', slug=None, page=None)", "desc": "生成链接"},
            {"name": "comments", "sign": "comments(target, limit=20)", "desc": "评论（预留）"},
            {"name": "form", "sign": "form(key='contact')", "desc": "表单定义"},
            {"name": "media_list", "sign": "media_list(kind=None, limit=20)", "desc": "媒体资产"},
            {"name": "trans", "sign": "trans(key, lang=None)", "desc": "多语言文案"},
        ],
        "kind_template": KIND_TEMPLATE,
        "page_level": list(PAGE_LEVEL_TEMPLATES),
    }


# ---------------------------------------------------------------- 工具


def _md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def _baseline_source(theme: str, path: str) -> str | None:
    """基线文件：主题自带内置的优先，否则回落到 default 主题。"""
    return builtin_theme.get_builtin_source(theme, path) or builtin_theme.get_builtin_source(
        builtin_theme.DEFAULT_THEME, path
    )


def _theme_documents_sync(site_id: int, theme: str) -> dict[str, str]:
    """同步 session 读「基线 + DB 覆盖」合并后的完整文件表。"""
    factory = get_session_factory()
    session = factory()
    try:
        return theme_documents(session, site_id, theme)
    finally:
        session.close()


def _kind_of(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    if path.startswith("assets/"):
        return "asset"
    if path.startswith("macros/"):
        return "macro"
    if path.startswith("partials/"):
        return "partial"
    if name.endswith((".json", ".txt")):
        return "meta"
    return {
        "layout.html": "layout",
        "list.html": "list",
        "detail.html": "detail",
        "page.html": "page",
    }.get(name, "partial")


async def _resolve_theme_async(db: AsyncSession, site_id: int) -> str:
    """站点设置里 cms.theme 优先，否则 default。"""
    row = (await db.execute(select(models.Site).where(models.Site.id == site_id))).scalars().first()
    if row is not None:
        settings = row.settings or {}
        theme = settings.get("cms.theme") or settings.get("theme")
        if isinstance(theme, str) and theme.strip():
            return theme.strip()
    return builtin_theme.DEFAULT_THEME
