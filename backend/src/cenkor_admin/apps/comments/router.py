"""Comments App · 管理路由（受保护，自动挂载于 /comments）"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.comments.models import Comment
from cenkor_admin.core.db import get_db

router = APIRouter()


@router.get("", response_model=dict[str, Any])
async def list_comments(
    db: AsyncSession = Depends(get_db),
    content_type_key: str | None = Query(None),
    object_id: int | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    conds = []
    if content_type_key:
        conds.append(Comment.content_type_key == content_type_key)
    if object_id is not None:
        conds.append(Comment.object_id == object_id)
    if status_filter:
        conds.append(Comment.status == status_filter)
    if search:
        conds.append(Comment.content.ilike(f"%{search}%"))
    stmt = select(Comment).where(*conds).order_by(Comment.id.desc())
    total = (await db.execute(select(Comment.id).where(*conds))).scalars().all().__len__()
    rows = (await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {
        "items": [_to_dict(c) for c in rows],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/stats", response_model=dict[str, Any])
async def comment_stats(db: AsyncSession = Depends(get_db)):
    """按状态统计（待审/已审/垃圾）。"""
    from sqlalchemy import func
    rows = (await db.execute(
        select(Comment.status, func.count()).group_by(Comment.status)
    )).all()
    return {"by_status": {s: n for s, n in rows}, "total": sum(n for _, n in rows)}


@router.patch("/{comment_id}", response_model=dict[str, Any])
async def update_comment(comment_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    """审核：body {status: approved|reject(->spam)|deleted, } 或 {content}。"""
    obj = await db.get(Comment, comment_id)
    if not obj:
        raise HTTPException(404, "Comment not found")
    status_map = {"approved": "approved", "reject": "spam", "spam": "spam", "deleted": "deleted"}
    if "status" in body:
        s = body["status"]
        obj.status = status_map.get(s, s)
    if "content" in body:
        obj.content = body["content"]
    await db.commit()
    await db.refresh(obj)
    return _to_dict(obj)


@router.delete("/{comment_id}", status_code=204)
async def delete_comment(comment_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Comment, comment_id)
    if not obj:
        raise HTTPException(404, "Comment not found")
    await db.execute(
        update(Comment).where(Comment.id == comment_id).values(status="deleted")
    )
    await db.commit()


def _to_dict(c: Comment) -> dict:
    return {
        "id": c.id, "content_type_key": c.content_type_key, "object_id": c.object_id,
        "parent_id": c.parent_id, "author_name": c.author_name, "author_email": c.author_email,
        "content": c.content, "status": c.status, "ip": c.ip,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }
