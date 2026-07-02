"""公告管理 App 路由"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.announcements import models
from cenkor_admin.core.db import get_db

router = APIRouter()


@router.get("", response_model=dict[str, Any])
async def list_announcements(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("announcements:read")),
    search: str | None = None,
    category: str | None = None,
    is_published: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    stmt = select(models.Announcement).where(models.Announcement.deleted_at.is_(None))
    if search:
        like = f"%{search}%"
        stmt = stmt.where(models.Announcement.title.ilike(like) | models.Announcement.content.ilike(like))
    if category:
        stmt = stmt.where(models.Announcement.category == category)
    if is_published is not None:
        stmt = stmt.where(models.Announcement.is_published == is_published)

    count = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    stmt = stmt.order_by(models.Announcement.is_pinned.desc(), models.Announcement.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()

    return {
        "items": [
            {
                "id": a.id, "title": a.title, "summary": a.summary,
                "category": a.category, "priority": a.priority,
                "is_pinned": a.is_pinned, "is_published": a.is_published,
                "publish_at": a.publish_at.isoformat() if a.publish_at else None,
                "expire_at": a.expire_at.isoformat() if a.expire_at else None,
                "view_count": a.view_count, "author_id": a.author_id,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in items
        ],
        "total": count, "page": page, "page_size": page_size,
    }


@router.get("/{announcement_id}", response_model=dict[str, Any])
async def get_announcement(
    announcement_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("announcements:read")),
):
    obj = await db.get(models.Announcement, announcement_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "公告不存在")
    return {
        "id": obj.id, "title": obj.title, "content": obj.content, "summary": obj.summary,
        "category": obj.category, "priority": obj.priority,
        "is_pinned": obj.is_pinned, "is_published": obj.is_published,
        "publish_at": obj.publish_at.isoformat() if obj.publish_at else None,
        "expire_at": obj.expire_at.isoformat() if obj.expire_at else None,
        "view_count": obj.view_count, "author_id": obj.author_id,
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
        "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
    }


@router.post("", status_code=201)
async def create_announcement(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("announcements:write")),
):
    obj = models.Announcement(
        title=body.get("title", ""),
        content=body.get("content", ""),
        summary=body.get("summary"),
        category=body.get("category", "general"),
        priority=body.get("priority", "normal"),
        is_pinned=body.get("is_pinned", False),
        is_published=body.get("is_published", False),
        publish_at=_parse_dt(body.get("publish_at")),
        expire_at=_parse_dt(body.get("expire_at")),
        author_id=current.id,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "title": obj.title}


@router.patch("/{announcement_id}")
async def update_announcement(
    announcement_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("announcements:write")),
):
    obj = await db.get(models.Announcement, announcement_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "公告不存在")
    for k in ("title", "content", "summary", "category", "priority", "is_pinned", "is_published"):
        if k in body:
            setattr(obj, k, body[k])
    if "publish_at" in body:
        obj.publish_at = _parse_dt(body["publish_at"])
    if "expire_at" in body:
        obj.expire_at = _parse_dt(body["expire_at"])
    await db.commit()
    return {"id": obj.id}


@router.delete("/{announcement_id}", status_code=204)
async def delete_announcement(
    announcement_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("announcements:write")),
):
    obj = await db.get(models.Announcement, announcement_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "公告不存在")
    obj.deleted_at = datetime.now(timezone.utc)
    await db.commit()


def _parse_dt(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val)
    except (ValueError, TypeError):
        return None
