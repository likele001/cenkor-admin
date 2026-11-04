"""模板渲染入口

职责：
1. 解析站点当前主题（DB 覆盖内置）
2. 在 executor 线程里同步渲染（同步 DB session，不碰主事件循环）
3. 渲染失败逐级回退：用户主题 → 内置主题 → 极简 HTML，保证页面永远不白屏

模板来源优先级：磁盘主题目录 → 数据库 → 内置主题。
磁盘目录（var/themes/<主题>/）面向习惯「建文件改文件」的开发者：
文件即事实源，删掉文件自动落回 DB/内置版本，不会 404。
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from cenkor_admin.apps.cms import builtin_theme, models, theme_package
from cenkor_admin.apps.cms.template_context import TemplateContext, get_session_factory
from cenkor_admin.core import jinja_env

logger = logging.getLogger(__name__)

__all__ = [
    "KIND_TEMPLATE",
    "disk_theme_paths",
    "invalidate_theme_cache",
    "load_disk_template",
    "make_preview_resolver",
    "render_page",
    "render_source",
    "resolve_theme",
    "theme_documents",
]

# 一页渲染的总时限。超过就放弃等待、走回退，避免拖垮整个请求。
RENDER_TIMEOUT = 8.0

KIND_TEMPLATE = {
    "article": "detail.html",
    "product": "detail.html",
    "news": "detail.html",
    "case": "detail.html",
    "page": "page.html",
    "list": "list.html",
    "404": "404.html",
}

# 主题文件缓存：key=(site_id, theme, path) -> (expire_ts, content|None)
_TPL_CACHE: dict[tuple[int, str, str], tuple[float, str | None]] = {}
_TPL_TTL = 30.0
_TPL_LOCK = threading.Lock()

# 磁盘主题目录：backend/var/themes/<主题>/<模板路径>
_THEMES_ROOT = Path(__file__).resolve().parents[4] / "var" / "themes"
# 主题名白名单：只允许字母数字下划线连字符，杜绝路径穿越
_THEME_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# 磁盘层独立缓存：key=(theme, path) -> (expire_ts, content|None, mtime|None)
# 与 DB 层分开，因为磁盘文件是开发者手改的 —— mtime 一变就要立刻生效，
# 还得连带清 Jinja 编译缓存（编译缓存按模板名缓存、不含源码指纹，
# 源码变了它不会自愈，不清前台就永远拿旧编译版）。
_DISK_CACHE: dict[tuple[str, str], tuple[float, str | None, float | None]] = {}


def _load_disk_template(theme: str, path: str) -> str | None:
    """读磁盘主题文件；不存在/主题名/路径不安全返回 None，渲染层自然落到下一级。

    每次调用都 stat 一次（微秒级）比对新 mtime：TTL 内命中缓存省掉 read_text，
    但文件一被手改立刻重新读取并清编译缓存，改动下一次渲染即生效。
    """
    if not _THEME_NAME_RE.match(theme or "") or not jinja_env.is_safe_template_name(path):
        return None
    key = (theme, path)
    fp = _THEMES_ROOT / theme / path
    now = time.time()
    try:
        st = fp.stat()
        mtime = st.st_mtime if st.st_size > 0 else None
    except OSError:
        mtime = None
    with _TPL_LOCK:
        hit = _DISK_CACHE.get(key)
        if hit and hit[0] > now and hit[2] == mtime:
            return hit[1]
    content: str | None = None
    if mtime is not None:
        try:
            resolved = fp.resolve()
            # resolve 后再校验一次前缀，双保险防符号链接/相对路径逃逸
            if resolved.is_relative_to(_THEMES_ROOT.resolve()) and resolved.is_file():
                text = fp.read_text(encoding="utf-8")
                if text.strip():
                    content = text
        except Exception:
            logger.debug("磁盘主题文件读取失败：%s/%s", theme, path, exc_info=True)
            content = None
    changed = hit is not None and hit[1] != content
    with _TPL_LOCK:
        _DISK_CACHE[key] = (now + _TPL_TTL, content, mtime)
    if changed:
        jinja_env.clear_template_cache()
        logger.info("磁盘主题文件变更，已清除模板编译缓存：%s/%s", theme, path)
    return content


# ---------------------------------------------------------------- 主题解析


def resolve_theme(session, site_id: int) -> str:
    """站点设置里 cms.theme 优先，否则 default。"""
    row = session.execute(select(models.Site).where(models.Site.id == site_id)).scalars().first()
    if row is not None:
        settings = row.settings or {}
        theme = settings.get("cms.theme") or settings.get("theme")
        if isinstance(theme, str) and theme.strip():
            return theme.strip()
    return builtin_theme.DEFAULT_THEME


def _load_db_template(session, site_id: int, theme: str, path: str) -> str | None:
    if not jinja_env.is_safe_template_name(path):
        return None
    key = (site_id, theme, path)
    now = time.time()
    with _TPL_LOCK:
        hit = _TPL_CACHE.get(key)
        if hit and hit[0] > now:
            return hit[1]
    content: str | None = None
    try:
        row = session.execute(
            select(models.CmsTemplate).where(
                models.CmsTemplate.site_id == site_id,
                models.CmsTemplate.theme == theme,
                models.CmsTemplate.path == path,
            )
        ).scalars().first()
        if row is not None:
            content = row.content
    except Exception:
        logger.debug("cms_templates 查询失败，回退内置主题", exc_info=True)
        content = None
    with _TPL_LOCK:
        _TPL_CACHE[key] = (now + _TPL_TTL, content)
    return content


def invalidate_theme_cache(site_id: int | None = None, theme: str | None = None) -> None:
    """后台保存模板后调用，立刻让改动生效。"""
    with _TPL_LOCK:
        for key in list(_TPL_CACHE):
            if (site_id is None or key[0] == site_id) and (theme is None or key[1] == theme):
                _TPL_CACHE.pop(key, None)
    jinja_env.clear_template_cache()


def disk_theme_paths(theme: str) -> set[str]:
    """磁盘主题目录下已有的模板文件集合（递归，含 assets/ 等）。"""
    if not _THEME_NAME_RE.match(theme or ""):
        return set()
    root = _THEMES_ROOT / theme
    if not root.is_dir():
        return set()
    try:
        return {
            str(p.relative_to(root)).replace("\\", "/")
            for p in root.rglob("*")
            if p.is_file()
        }
    except Exception:
        logger.debug("枚举磁盘主题文件失败：%s", theme, exc_info=True)
        return set()


def theme_documents(session, site_id: int, theme: str) -> dict[str, str]:
    """合并磁盘 + DB + 内置的完整主题文件表（磁盘优先），用于导出主题包。"""
    # 先铺 default 基线，再盖本主题 —— 顺序反了的话 blog 导出时 layout.html
    # 还是 default 那一份（它的自有文件永远盖不上去），包拿出来就是另一个主题。
    merged: dict[str, str] = dict(builtin_theme.BUILTIN_THEMES.get(builtin_theme.DEFAULT_THEME, {}))
    merged.update(builtin_theme.BUILTIN_THEMES.get(theme, {}))
    try:
        rows = session.execute(
            select(models.CmsTemplate).where(
                models.CmsTemplate.site_id == site_id,
                models.CmsTemplate.theme == theme,
            )
        ).scalars().all()
        for row in rows:
            merged[row.path] = row.content
    except Exception:
        logger.debug("导出主题时读取 cms_templates 失败", exc_info=True)
    for path in disk_theme_paths(theme):
        content = _load_disk_template(theme, path)
        if content is not None:
            merged[path] = content
    return merged


# 对外名字：theme_asset_router 取资源时用「磁盘 → DB → 内置」同一套顺序，
# 复用这份实现，避免两处逻辑漂移（尤其缓存与安全检查那部分）。
load_disk_template = _load_disk_template


def _make_resolver(session, site_id: int, theme: str, *, builtin_only: bool = False):
    def resolve(name: str) -> str | None:
        if not builtin_only:
            # 磁盘优先：开发者建了文件就以文件为准（builtin_only 回退渲染时
            # 刻意跳过磁盘层 —— 磁盘文件写坏了才触发回退，回退不能再被它污染）
            src = _load_disk_template(theme, name)
            if src is not None:
                return src
            src = _load_db_template(session, site_id, theme, name)
            if src is not None:
                return src
        # 用户主题只覆盖了部分文件时，其余回落到内置 default
        return builtin_theme.get_builtin_source(theme, name) or builtin_theme.get_builtin_source(
            builtin_theme.DEFAULT_THEME, name
        )

    return resolve


def make_preview_resolver(
    session, site_id: int, theme: str, overrides: dict[str, str] | None = None
):
    """预览用解析器：DB 覆盖 → 内置 → default 回落，可再叠一层未保存的编辑内容。

    overrides 让编辑器在没点保存时也能看到跨文件 include 的效果
    （改 partials/header.html，detail.html 的预览立刻跟着变）。
    """
    base = _make_resolver(session, site_id, theme)
    if not overrides:
        return base

    def resolve(name: str) -> str | None:
        if name in overrides:
            return overrides[name]
        return base(name)

    return resolve


# ---------------------------------------------------------------- 上下文


def _theme_manifest_text(session, site_id: int, theme: str) -> str | None:
    """取本主题的 theme.json 原文。

    查找范围**严格限定在本主题**：磁盘 → DB → 本主题内置，到此为止。
    不走 default 回落 —— 借来的清单会让站长的设置项变成另一个主题的 key。
    """
    raw = _load_disk_template(theme, theme_package.MANIFEST_NAME)
    if raw is None:
        raw = _load_db_template(session, site_id, theme, theme_package.MANIFEST_NAME)
    if raw is None:
        raw = builtin_theme.get_builtin_source(theme, theme_package.MANIFEST_NAME)
    return raw


def _theme_settings(session, site_id: int, theme: str, site_settings: dict[str, Any] | None) -> dict[str, Any]:
    """主题设置 = 清单默认值 + 站点覆盖。没有清单就是空 dict。

    清单解析失败不让渲染挂掉 —— 配置是元数据，坏了顶多设置项不生效，页面照出。
    """
    raw = _theme_manifest_text(session, site_id, theme)
    if not raw:
        return {}
    try:
        manifest = theme_package.manifest_from_json(raw, legacy_key=theme)
    except ValueError as exc:
        logger.warning("主题 %s 的 theme.json 解析失败：%s", theme, exc)
        return {}
    return theme_package.resolve_settings(manifest, site_settings)


def _is_home(model: dict[str, Any]) -> bool:
    """这一页是不是站点首页。

    列表页的 kind 一律是 "list"（首页 / 分类 / 标签 / 搜索都走同一个模型），
    模板没法靠 kind 分出首页。canonical 是三类页面都有的字段，
    首页的 path 恒为 "/"，从它判断最稳。
    """
    canonical = model.get("canonical") or ""
    if not canonical:
        return False
    try:
        from urllib.parse import urlparse

        return urlparse(canonical).path in ("", "/")
    except Exception:  # pragma: no cover - urlparse 几乎不抛
        return False


def _build_context(
    model: dict[str, Any],
    ctx: TemplateContext,
    base: str,
    css: str,
    theme: str,
    session=None,
) -> dict[str, Any]:
    data = ctx.as_globals()
    data.update({
        "page": model,
        "item": model.get("item"),
        "items": model.get("items") or [],
        "pagination": model.get("pagination") or ctx.pagination(1, 0, 20),
        "base_url": base,
        "theme_css": css,
        "theme_name": theme,
        # 主题设置：清单里的默认值 + 站长改过的值。
        # 模板里写 {{ theme.brand_color }}，永远有值 —— 不会因为站长没配过
        # 就渲染出 None。默认值兜底这件事必须在渲染时做，不能在模板里做，
        # 否则每个设置项都要写一遍 if。
        "theme": _theme_settings(session, ctx.site_id, theme, ctx.site_meta()) if session else {},
        # 模板里判断首页用：{% if is_home %} 放 Hero / 大标题
        "is_home": _is_home(model),
        "now": datetime.now(),
    })
    return data


def _render_sync(
    model: dict[str, Any],
    *,
    site_id: int,
    base: str,
    theme: str | None = None,
    builtin_only: bool = False,
) -> str:
    factory = get_session_factory()
    session = factory()
    token = None
    try:
        active_theme = theme or (builtin_theme.DEFAULT_THEME if builtin_only else resolve_theme(session, site_id))
        resolver = _make_resolver(session, site_id, active_theme, builtin_only=builtin_only)
        token = jinja_env.set_resolver(resolver)
        ctx = TemplateContext(session, site_id=site_id, base=base, theme=active_theme)
        css = resolver("assets/style.css") or ""
        context = _build_context(model, ctx, base, css, active_theme, session)
        tpl_name = KIND_TEMPLATE.get(model.get("kind") or "article", "detail.html")
        # 栏目级模板覆盖：栏目配了 template 且主题里真有这个文件才启用，
        # 否则回退按 kind 的默认模板 —— 不会因为填错文件名整页 500。
        custom = (model.get("tpl") or "").strip() if isinstance(model.get("tpl"), str) else None
        if custom and custom != tpl_name and resolver(custom):
            tpl_name = custom
        return jinja_env.render_template_file(tpl_name, context)
    finally:
        if token is not None:
            jinja_env.reset_resolver(token)
        session.close()


def _minimal_html(model: dict[str, Any]) -> str:
    """最后一道兜底：连内置主题都渲染失败时，至少给出可读页面。"""
    import html as _h

    title = _h.escape(str(model.get("title") or "页面"))
    desc = _h.escape(str(model.get("description") or ""))
    canonical = _h.escape(str(model.get("canonical") or ""))
    body = ""
    item = model.get("item") or {}
    if isinstance(item, dict) and item.get("body_html"):
        body = str(item["body_html"])
    elif isinstance(item, dict):
        body = _h.escape(str((item.get("content") or {}).get("text") or ""))
    return (
        "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"UTF-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        f"<title>{title}</title><meta name=\"description\" content=\"{desc}\">"
        f"<link rel=\"canonical\" href=\"{canonical}\">"
        "<style>body{max-width:760px;margin:0 auto;padding:32px 20px;font:16px/1.8 -apple-system,'PingFang SC',sans-serif;color:#1a1d23}"
        "h1{font-size:26px;line-height:1.4}img{max-width:100%}</style></head>"
        f"<body><h1>{title}</h1><div>{body}</div></body></html>"
    )


# ---------------------------------------------------------------- 对外接口


async def render_page(
    model: dict[str, Any],
    *,
    site_id: int = 1,
    base: str = "",
    theme: str | None = None,
    timeout: float = RENDER_TIMEOUT,
) -> str:
    """渲染一页。永不让异常冒到路由层。"""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                _render_sync, model, site_id=site_id, base=base, theme=theme
            ),
            timeout=timeout,
        )
    except TimeoutError:
        logger.warning("模板渲染超时（>%.1fs），回退内置主题 site=%s kind=%s", timeout, site_id, model.get("kind"))
    except Exception as exc:
        logger.warning("用户主题渲染失败，回退内置主题：%s", exc, exc_info=True)

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                _render_sync, model, site_id=site_id, base=base, builtin_only=True
            ),
            timeout=timeout,
        )
    except Exception as exc:
        logger.error("内置主题渲染也失败，使用极简兜底：%s", exc, exc_info=True)

    return _minimal_html(model)


async def render_source(source: str, context: dict[str, Any], *, name: str = "<preview>") -> tuple[str, str | None]:
    """渲染任意模板源码（后台预览用）。返回 (html, error)。"""
    try:
        out = await asyncio.wait_for(
            asyncio.to_thread(jinja_env.render_source, source, context, name=name),
            timeout=RENDER_TIMEOUT,
        )
        return out, None
    except TimeoutError:
        return "", f"渲染超时（>{RENDER_TIMEOUT:.0f}s）"
    except Exception as exc:
        return "", str(exc)
