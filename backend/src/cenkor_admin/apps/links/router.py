"""链接收集 App 路由"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.links import models
from cenkor_admin.core.db import get_db

router = APIRouter()


@router.get("", response_model=dict[str, Any])
async def list_links(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("links:read")),
    search: str | None = None,
    category: str | None = None,
    is_favorite: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    stmt = select(models.Link).where(models.Link.deleted_at.is_(None))
    if search:
        like = f"%{search}%"
        stmt = stmt.where(models.Link.title.ilike(like) | models.Link.url.ilike(like))
    if category:
        stmt = stmt.where(models.Link.category == category)
    if is_favorite is not None:
        stmt = stmt.where(models.Link.is_favorite == is_favorite)

    count = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    stmt = stmt.order_by(models.Link.is_favorite.desc(), models.Link.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()

    return {
        "items": [
            {
                "id": l.id, "url": l.url, "title": l.title, "description": l.description,
                "category": l.category, "favicon": l.favicon,
                "is_favorite": l.is_favorite, "click_count": l.click_count,
                "creator_id": l.creator_id,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in items
        ],
        "total": count, "page": page, "page_size": page_size,
    }


@router.get("/{link_id}", response_model=dict[str, Any])
async def get_link(
    link_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("links:read")),
):
    obj = await db.get(models.Link, link_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "链接不存在")
    return {
        "id": obj.id, "url": obj.url, "title": obj.title, "description": obj.description,
        "category": obj.category, "favicon": obj.favicon,
        "is_favorite": obj.is_favorite, "click_count": obj.click_count,
        "creator_id": obj.creator_id,
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
        "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
    }


@router.post("", status_code=201)
async def create_link(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("links:write")),
):
    url = (body.get("url") or "").strip()
    if not url:
        raise HTTPException(400, "url 必填")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    obj = models.Link(
        url=url,
        title=body.get("title") or url,
        description=body.get("description"),
        category=body.get("category", "general"),
        favicon=body.get("favicon"),
        is_favorite=body.get("is_favorite", False),
        creator_id=current.id,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "title": obj.title}


@router.patch("/{link_id}")
async def update_link(
    link_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("links:write")),
):
    obj = await db.get(models.Link, link_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "链接不存在")
    for k in ("url", "title", "description", "category", "favicon", "is_favorite"):
        if k in body:
            setattr(obj, k, body[k])
    await db.commit()
    return {"id": obj.id}


@router.delete("/{link_id}", status_code=204)
async def delete_link(
    link_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("links:write")),
):
    obj = await db.get(models.Link, link_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "链接不存在")
    obj.deleted_at = datetime.now(timezone.utc)
    await db.commit()
