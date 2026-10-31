"""模板渲染入口

职责：
1. 解析站点当前主题（DB 覆盖内置）
2. 在 executor 线程里同步渲染（同步 DB session，不碰主事件循环）
3. 渲染失败逐级回退：用户主题 → 内置主题 → 极简 HTML，保证页面永远不白屏
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime
from typing import Any

from sqlalchemy import select

from cenkor_admin.apps.cms import builtin_theme, models
from cenkor_admin.apps.cms.template_context import TemplateContext, get_session_factory
from cenkor_admin.core import jinja_env

logger = logging.getLogger(__name__)

__all__ = [
    "KIND_TEMPLATE",
    "invalidate_theme_cache",
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


def theme_documents(session, site_id: int, theme: str) -> dict[str, str]:
    """合并内置 + DB 后的完整主题文件表，用于导出主题包。"""
    merged: dict[str, str] = dict(builtin_theme.BUILTIN_THEMES.get(builtin_theme.DEFAULT_THEME, {}))
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
    return merged


def _make_resolver(session, site_id: int, theme: str, *, builtin_only: bool = False):
    def resolve(name: str) -> str | None:
        if not builtin_only:
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


def _build_context(model: dict[str, Any], ctx: TemplateContext, base: str, css: str, theme: str) -> dict[str, Any]:
    data = ctx.as_globals()
    data.update({
        "page": model,
        "item": model.get("item"),
        "items": model.get("items") or [],
        "pagination": model.get("pagination") or ctx.pagination(1, 0, 20),
        "base_url": base,
        "theme_css": css,
        "theme_name": theme,
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
        ctx = TemplateContext(session, site_id=site_id, base=base)
        css = resolver("assets/style.css") or ""
        context = _build_context(model, ctx, base, css, active_theme)
        tpl_name = KIND_TEMPLATE.get(model.get("kind") or "article", "detail.html")
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
