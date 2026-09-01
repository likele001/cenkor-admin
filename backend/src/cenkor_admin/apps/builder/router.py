"""Builder App · 管理路由（受保护，自动挂载于 /builder）"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.builder.models import Page
from cenkor_admin.core.db import get_db

router = APIRouter()


@router.get("/pages", response_model=dict[str, Any])
async def list_pages(db: AsyncSession = Depends(get_db), search: str | None = Query(None)):
    stmt = select(Page).order_by(Page.id.desc())
    if search:
        stmt = stmt.where(Page.title.ilike(f"%{search}%") | Page.key.ilike(f"%{search}%"))
    rows = (await db.execute(stmt)).scalars().all()
    return {"items": [_page_dict(p) for p in rows], "total": len(rows)}


@router.post("/pages", response_model=dict[str, Any], status_code=201)
async def create_page(body: dict, db: AsyncSession = Depends(get_db)):
    key = body.get("key")
    title = body.get("title")
    if not key or not title:
        raise HTTPException(400, "key 与 title 必填")
    existing = await db.execute(select(Page).where(Page.key == key))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"页面 key 已存在: {key}")
    obj = Page(key=key, title=title, schema=body.get("schema") or [], status=body.get("status", "draft"))
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _page_dict(obj)


@router.patch("/pages/{page_id}", response_model=dict[str, Any])
async def update_page(page_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Page, page_id)
    if not obj:
        raise HTTPException(404, "Page not found")
    for k in ("title", "schema", "status"):
        if k in body:
            setattr(obj, k, body[k])
    await db.commit()
    await db.refresh(obj)
    return _page_dict(obj)


@router.post("/pages/{page_id}/publish", response_model=dict[str, Any])
async def publish_page(page_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Page, page_id)
    if not obj:
        raise HTTPException(404, "Page not found")
    obj.status = "published"
    obj.published_at = obj.published_at or datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(obj)
    return _page_dict(obj)


@router.delete("/pages/{page_id}", status_code=204)
async def delete_page(page_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Page, page_id)
    if not obj:
        raise HTTPException(404, "Page not found")
    await db.delete(obj)
    await db.commit()


def _page_dict(p: Page) -> dict:
    return {
        "id": p.id, "key": p.key, "title": p.title, "schema": p.schema or [],
        "status": p.status,
        "published_at": p.published_at.isoformat() if p.published_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }
