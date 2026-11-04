"""widget 宿主页路由 —— 沙箱 iframe 里那一层真实文档。

这个路由吐的是**完整 HTML 文档**，不是片段。它有两个和普通公开页完全相反的要求：

1. **不能**带 ``X-Frame-Options``，也**不能**带 ``frame-ancestors``。
   iframe 内是 opaque origin（sandbox 无 allow-same-origin），任何基于 origin
   比较的嵌套校验都会判定「不同源」从而拒绝加载 —— 加了这个头，widget 就永远
   是白的，而且控制台只会说一句含糊的拒绝。
   谁能嵌它由**父页面**的 ``frame-src 'self'`` 决定，不需要它自己再声明一遍。

2. **不能**走 ``csp.html_response()``。那个函数给的是站点级策略（含
   ``script-src 'self'``），而 opaque origin 下 ``'self'`` 匹配不到东西。
   这里必须用 ``widget_sandbox.widget_csp()`` 的哈希白名单。

资源查找**不回落 default 主题**：widget 是主题私有组件，从别的主题借一个
同名 widget 出来，结构、参数、脚本全对不上，比 404 更糟 —— 404 至少能被发现。
"""

from __future__ import annotations

import re

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms import builtin_theme, models, widget_sandbox
from cenkor_admin.apps.cms.render import load_disk_template
from cenkor_admin.core.db import get_db
from cenkor_admin.core.jinja_env import is_safe_template_name

log = structlog.get_logger()
router = APIRouter()

_THEME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

# widget 结构体上限。组件不是页面，超过这个量级说明作者在做别的事。
MAX_STRUCTURE_BYTES = 256 * 1024
MAX_SCRIPT_BYTES = 512 * 1024


async def _site_of(db: AsyncSession, request: Request) -> int:
    from cenkor_admin.apps.cms.public_router import _resolve_site

    site_id, _name, _cfg = await _resolve_site(db, request)
    return int(site_id or 1)


async def _load(db: AsyncSession, site_id: int, theme: str, path: str) -> str | None:
    """磁盘 → DB → 本主题内置。**不回落 default**，理由见模块注释。"""
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
    return builtin_theme.get_builtin_source(theme, path)


@router.get("/theme-widgets/{theme}/{name}", include_in_schema=False)
async def theme_widget(
    theme: str,
    name: str,
    request: Request,
    d: str = "",
    db: AsyncSession = Depends(get_db),
):
    """返回 widget 宿主页（完整文档）。参数 ``d`` 是 base64url 的 JSON。"""
    if not _THEME_RE.match(theme or "") or not widget_sandbox.WIDGET_NAME_RE.match(name or ""):
        raise HTTPException(404, "组件不存在")

    structure_path = f"widgets/{name}.html"
    script_path = f"widgets/{name}.js"
    if not is_safe_template_name(structure_path):
        raise HTTPException(404, "组件不存在")

    site_id = await _site_of(db, request)
    structure = await _load(db, site_id, theme, structure_path)
    if structure is None:
        raise HTTPException(404, "组件不存在")
    if len(structure.encode("utf-8")) > MAX_STRUCTURE_BYTES:
        log.warning("theme_widget.too_large", theme=theme, name=name, part="html")
        raise HTTPException(413, "组件结构过大")

    script = await _load(db, site_id, theme, script_path)
    if script is not None and len(script.encode("utf-8")) > MAX_SCRIPT_BYTES:
        log.warning("theme_widget.too_large", theme=theme, name=name, part="js")
        raise HTTPException(413, "组件脚本过大")

    args = widget_sandbox.decode_args(d)
    html, csp = widget_sandbox.build_host_page(
        structure=structure,
        script=script,
        args=args,
        title=name,
    )

    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={
            # sandbox 在头里，顶层直接打开也受限；哈希锁定唯一可执行的脚本
            "Content-Security-Policy": csp,
            "X-Content-Type-Options": "nosniff",
            # 别把这个地址当正经营业页面收录
            "X-Robots-Tag": "noindex, nofollow",
            # 参数直接进 HTML，缓存住会把 A 页的参数发给 B 页
            "Cache-Control": "no-store",
            # 注意：这里**故意没有** X-Frame-Options
        },
    )
