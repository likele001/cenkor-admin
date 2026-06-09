"""Notification App · 路由（站内信）"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.notification import models
from cenkor_admin.core.db import get_db

router = APIRouter()


@router.get("", response_model=dict[str, Any])
async def list_notifications(
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("notification:read")),
    unread_only: bool = Query(False, description="只返回未读"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """当前用户的通知列表（按时间倒序）"""
    stmt = select(models.Notification).where(models.Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(models.Notification.read_at.is_(None))
    count = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar() or 0
    stmt = stmt.order_by(models.Notification.created_at.desc(), models.Notification.id.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return {
        "items": [_to_dict(n) for n in items],
        "total": int(count),
        "page": page,
        "page_size": page_size,
    }


@router.get("/unread-count")
async def unread_count(
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("notification:read")),
):
    """未读数量（用于铃铛角标）"""
    cnt = (await db.execute(
        select(func.count())
        .select_from(models.Notification)
        .where(models.Notification.user_id == user.id, models.Notification.read_at.is_(None))
    )).scalar() or 0
    return {"unread": int(cnt)}


@router.post("/{nid}/read", status_code=200)
async def mark_read(
    nid: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("notification:read")),
):
    """标记单条已读"""
    result = await db.execute(
        select(models.Notification).where(
            models.Notification.id == nid, models.Notification.user_id == user.id
        )
    )
    n = result.scalar_one_or_none()
    if not n:
        raise HTTPException(404, "通知不存在")
    if not n.read_at:
        n.read_at = datetime.now(timezone.utc)
        await db.commit()
    return {"id": n.id, "read_at": n.read_at.isoformat()}


@router.post("/read-all", status_code=200)
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("notification:read")),
):
    """全部标记已读"""
    await db.execute(
        update(models.Notification)
        .where(models.Notification.user_id == user.id, models.Notification.read_at.is_(None))
        .values(read_at=func.now())
    )
    await db.commit()
    return {"ok": True}


@router.delete("/{nid}", status_code=204)
async def delete_notification(
    nid: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("notification:read")),
):
    """删除单条通知（仅自己可见的通知可删）"""
    result = await db.execute(
        select(models.Notification).where(
            models.Notification.id == nid, models.Notification.user_id == user.id
        )
    )
    n = result.scalar_one_or_none()
    if not n:
        raise HTTPException(404, "通知不存在")
    await db.delete(n)
    await db.commit()


def _to_dict(n: models.Notification) -> dict:
    return {
        "id": n.id,
        "type": n.type,
        "title": n.title,
        "body": n.body,
        "link": n.link,
        "payload": n.payload,
        "read": n.read_at is not None,
        "read_at": n.read_at.isoformat() if n.read_at else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }
