"""Comments App · 公共路由（无需鉴权，M4·P3 4.2）"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.comments.models import Comment
from cenkor_admin.core.db import get_db

router = APIRouter()


@router.get("/comments", response_model=dict[str, Any])
async def list_public_comments(
    db: AsyncSession = Depends(get_db),
    content_type_key: str = Query(...),
    object_id: int = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """公开评论列表（仅已通过审核的）。"""
    conds = [
        Comment.content_type_key == content_type_key,
        Comment.object_id == object_id,
        Comment.status == "approved",
    ]
    stmt = select(Comment).where(*conds).order_by(Comment.id.asc())
    total = len((await db.execute(select(Comment.id).where(*conds))).scalars().all())
    rows = (await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {
        "items": [{
            "id": c.id, "parent_id": c.parent_id, "author_name": c.author_name,
            "content": c.content,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        } for c in rows],
        "total": total, "page": page, "page_size": page_size,
    }


@router.post("/comments", response_model=dict[str, Any], status_code=201)
async def create_public_comment(
    body: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """发表评论（默认进入待审核）。"""
    content_type_key = body.get("content_type_key")
    object_id = body.get("object_id")
    content = (body.get("content") or "").strip()
    author_name = (body.get("author_name") or "").strip()
    if not content_type_key or object_id is None:
        raise HTTPException(400, "content_type_key 与 object_id 必填")
    if not content:
        raise HTTPException(400, "评论内容不能为空")
    if not author_name:
        raise HTTPException(400, "请填写昵称")
    if len(content) > 2000:
        raise HTTPException(400, "评论过长（≤2000 字）")
    parent_id = body.get("parent_id")
    if parent_id is not None:
        parent = await db.get(Comment, parent_id)
        if not parent or parent.status != "approved":
            raise HTTPException(400, "父评论不存在或未通过审核")
    obj = Comment(
        content_type_key=content_type_key,
        object_id=object_id,
        parent_id=parent_id,
        author_name=author_name,
        author_email=body.get("author_email"),
        content=content,
        status="pending",
        ip=request.client.host if request.client else None,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "status": obj.status, "message": "评论已提交，待审核"}
