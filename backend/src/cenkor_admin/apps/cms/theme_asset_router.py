"""主题静态资源（``assets/*.css`` / ``*.js``）的对外服务。

## 为什么必须有这条路由

主题体系原本只有一种资源加载方式：``render.py`` 把 ``assets/style.css`` 的**源码**
读出来、内联进 ``<style>``。CSS 这么干没问题，脚本不行 —— 严格 CSP
（``script-src 'self'``，禁内联）下脚本只能是外链文件，而外链需要一个真实可
访问的 URL。没有这条路由，``script()`` 拼出来的地址会 404，"禁内联脚本"
就等于把主题的交互能力整个砍掉。

## 只服务 css / js

路径白名单（``is_safe_template_name``）还允许 html / xml / json，那是给模板和
元数据用的。资源路由**不放行**它们：从这里吐 HTML 等于开了一个同源 XSS 出口，
而且是绕过模板校验的那种。

SVG 也不放行 —— SVG 里可以内嵌 ``<script>``，浏览器执行它时不区分这个文件
是被当"图片"引用的。真要放图，走站点 media 或外链。

## 解析顺序与模板保持一致

磁盘 → DB → 内置（同 ``render._make_resolver``）。顺序不一致会出现
"模板读的是磁盘版、样式读的是 DB 版"这种对不上的怪现象。
"""

from __future__ import annotations

import hashlib
import os
import re

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms import builtin_theme, models
from cenkor_admin.apps.cms.render import load_disk_template
from cenkor_admin.core.db import get_db
from cenkor_admin.core.jinja_env import is_safe_template_name

log = structlog.get_logger()
router = APIRouter()

_THEME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

# 只服务这两种。加新类型前先想清楚它能不能执行代码。
_CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}

MAX_ASSET_BYTES = 1024 * 1024


async def _site_of(db: AsyncSession, request: Request) -> int:
    """按 Host 解析站点。延迟导入避免与 public_router 形成加载环。"""
    from cenkor_admin.apps.cms.public_router import _resolve_site

    site_id, _name, _cfg = await _resolve_site(db, request)
    return int(site_id or 1)


async def _load_source(db: AsyncSession, site_id: int, theme: str, path: str) -> str | None:
    src = load_disk_template(theme, path)
    if src is not None:
        return src

    src = (
        await db.execute(
            select(models.CmsTemplate.content).where(
                models.CmsTemplate.site_id == site_id,
                models.CmsTemplate.theme == theme,
                models.CmsTemplate.path == path,
            )
        )
    ).scalars().first()
    if src is not None:
        return src

    return builtin_theme.get_builtin_source(theme, path) or builtin_theme.get_builtin_source(
        builtin_theme.DEFAULT_THEME, path
    )


@router.get("/theme-assets/{theme}/{path:path}", include_in_schema=False)
async def theme_asset(
    theme: str,
    path: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """返回主题资源文件的原始内容，带 ETag 强缓存。"""
    if not _THEME_RE.match(theme or ""):
        raise HTTPException(404, "资源不存在")

    norm = (path or "").replace("\\", "/").lstrip("/")
    # 白名单挡住 `..`、绝对路径、下划线开头的段（is_safe_template_name 已经覆盖）
    if not norm.startswith("assets/") or not is_safe_template_name(norm):
        raise HTTPException(404, "资源不存在")

    ctype = _CONTENT_TYPES.get(os.path.splitext(norm)[1].lower())
    if ctype is None:
        raise HTTPException(404, "该类型不对外提供（只服务 css / js）")

    site_id = await _site_of(db, request)
    src = await _load_source(db, site_id, theme, norm)
    if src is None:
        raise HTTPException(404, "资源不存在")

    body = src.encode("utf-8")
    if len(body) > MAX_ASSET_BYTES:
        log.warning("theme_asset.too_large", theme=theme, path=norm, size=len(body))
        raise HTTPException(413, "资源超过 1MB 上限")

    etag = '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
    if (request.headers.get("if-none-match") or "").strip() == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "public, max-age=300"})

    return Response(
        content=body,
        media_type=ctype,
        headers={
            "ETag": etag,
            "Cache-Control": "public, max-age=300",
            # 告诉浏览器别猜类型：资源路由只认 css / js，猜错就可能执行
            "X-Content-Type-Options": "nosniff",
        },
    )
