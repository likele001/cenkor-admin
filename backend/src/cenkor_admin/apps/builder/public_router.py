"""Builder App · 公共路由（无需鉴权，M3·P2 3.2）"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.builder.models import Page
from cenkor_admin.apps.builder.renderer import page_html, render_blocks
from cenkor_admin.core.db import get_db

router = APIRouter()


@router.get("/pages/{key}", response_model=dict[str, Any])
async def get_public_page(key: str, db: AsyncSession = Depends(get_db)):
    """公开页面（JSON：blocks + 渲染好的 html）。"""
    page = (await db.execute(
        select(Page).where(Page.key == key, Page.status == "published")
    )).scalar_one_or_none()
    if not page:
        raise HTTPException(404, "页面不存在或未发布")
    return {
        "key": page.key,
        "title": page.title,
        "blocks": page.schema or [],
        "html": render_blocks(page.schema or []),
        "published_at": page.published_at.isoformat() if page.published_at else None,
    }


@router.get("/pages/{key}/render", response_class=HTMLResponse)
async def render_public_page(key: str, db: AsyncSession = Depends(get_db)):
    """公开页面渲染（完整 HTML 文档）。"""
    page = (await db.execute(
        select(Page).where(Page.key == key, Page.status == "published")
    )).scalar_one_or_none()
    if not page:
        raise HTTPException(404, "页面不存在或未发布")
    return HTMLResponse(content=page_html(page.key, page.title, page.schema or []))
