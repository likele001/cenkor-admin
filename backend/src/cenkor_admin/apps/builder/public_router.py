"""Builder App · 公共路由（无需鉴权）

两套路径：
- `/public/pages/{key}` 老接口，返回 JSON blocks（内部预览/嵌入用）
- `/public/lp/{key}` 与 `/public/lp/{site_key}/{page_key}` 落地页整页 HTML，
  nginx 把 `www.cenkor.cn/lp/*` 反代到这里，对外就是干净的 `/lp/xxx`。

为什么整页由后端出而不是前端渲染：落地页要投广告、要被搜索引擎收录、
要分享到微信。这些场景都需要**首屏就是完整 HTML**（标题、描述、og 图、
结构化数据都在源码里），不能让爬虫跑一遍 JS 才看到内容。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.builder.models import Page
from cenkor_admin.apps.builder.renderer import render_page
from cenkor_admin.apps.forms.models import Form
from cenkor_admin.core.db import get_db

router = APIRouter()


def _form_keys(blocks: list[dict[str, Any]]) -> list[str]:
    return [
        str((b.get("data") or {}).get("form_key") or "")
        for b in blocks or []
        if b.get("type") == "form"
    ]


async def _forms_for(db: AsyncSession, blocks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    keys = [k for k in _form_keys(blocks) if k]
    if not keys:
        return {}
    rows = (
        await db.execute(select(Form).where(Form.key.in_(keys), Form.enabled.is_(True)))
    ).scalars().all()
    return {
        f.key: {"fields": f.fields or [], "success_message": f.success_message} for f in rows
    }


def _page_dict(p: Page) -> dict[str, Any]:
    return {
        "id": p.id,
        "key": p.key,
        "title": p.title,
        "schema": p.schema or [],
        "seo": p.seo or {},
        "kind": p.kind or "page",
        "site_key": p.site_key,
        "nav": p.nav or [],
        "status": p.status,
        "published_at": p.published_at.isoformat() if p.published_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


async def _render(db: AsyncSession, page: Page, *, path: str, preview: bool = False) -> HTMLResponse:
    forms = await _forms_for(db, page.schema or [])
    html = render_page(
        {
            "key": page.key,
            "title": page.title,
            "schema": page.schema or [],
            "seo": page.seo or {},
            "nav": page.nav or [],
            "kind": page.kind,
            "site_key": page.site_key,
        },
        forms=forms,
        canonical=path,
        track=not preview,
        noindex=preview,
    )
    return HTMLResponse(
        content=html,
        headers={
            # 已发布的落地页可以被 CDN 缓存一小段时间；草稿一律不缓存
            "Cache-Control": "no-store" if preview else "public, max-age=60",
            "X-Robots-Tag": "noindex" if preview else "all",
        },
    )


# ---------------------------------------------------------------------------
# 老接口
# ---------------------------------------------------------------------------
@router.get("/pages/{key}", response_model=dict[str, Any])
async def get_public_page(key: str, db: AsyncSession = Depends(get_db)):
    """公开页面（JSON：blocks + 渲染好的 html）。"""
    page = (
        await db.execute(select(Page).where(Page.key == key, Page.status == "published"))
    ).scalar_one_or_none()
    if not page:
        raise HTTPException(404, "页面不存在或未发布")
    data = _page_dict(page)
    data["html"] = render_page(data, forms=await _forms_for(db, data["schema"]))
    return data


@router.get("/pages/{key}/render", response_class=HTMLResponse)
async def render_public_page(key: str, db: AsyncSession = Depends(get_db)):
    page = (
        await db.execute(select(Page).where(Page.key == key, Page.status == "published"))
    ).scalar_one_or_none()
    if not page:
        raise HTTPException(404, "页面不存在或未发布")
    return await _render(db, page, path=f"/pages/{key}")


# ---------------------------------------------------------------------------
# 落地页（对外干净路径）
# ---------------------------------------------------------------------------
@router.get("/lp/{key}", response_class=HTMLResponse, include_in_schema=False)
async def landing_page(
    key: str,
    preview: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    """单页落地页。草稿要带 ?preview=1 才能看（运营自测用）。"""
    stmt = select(Page).where(Page.key == key)
    if not preview:
        stmt = stmt.where(Page.status == "published")
    page = (await db.execute(stmt)).scalar_one_or_none()
    if not page:
        raise HTTPException(404, "页面不存在或未发布")
    return await _render(db, page, path=f"/lp/{key}", preview=preview)


@router.get("/lp/{site_key}/{page_key}", response_class=HTMLResponse, include_in_schema=False)
async def landing_site_page(
    site_key: str,
    page_key: str,
    preview: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    """子站内页。key 在库里是 `site_key/page_key`，这里拼回去查。"""
    full = f"{site_key}/{page_key}"
    stmt = select(Page).where(Page.key == full)
    if not preview:
        stmt = stmt.where(Page.status == "published")
    page = (await db.execute(stmt)).scalar_one_or_none()
    if not page:
        raise HTTPException(404, "页面不存在或未发布")
    return await _render(db, page, path=f"/lp/{full}", preview=preview)
