"""工单系统 App 路由（含通知触发）"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.notification.service import create_notification
from cenkor_admin.apps.tickets import models
from cenkor_admin.core.db import get_db

router = APIRouter()

STATUS_LABEL = {"open": "待处理", "in_progress": "处理中", "resolved": "已解决", "closed": "已关闭"}


@router.get("", response_model=dict[str, Any])
async def list_tickets(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("tickets:read")),
    search: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    assignee_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    stmt = select(models.Ticket).where(models.Ticket.deleted_at.is_(None))
    if search:
        like = f"%{search}%"
        stmt = stmt.where(models.Ticket.title.ilike(like) | models.Ticket.description.ilike(like))
    if status:
        stmt = stmt.where(models.Ticket.status == status)
    if priority:
        stmt = stmt.where(models.Ticket.priority == priority)
    if category:
        stmt = stmt.where(models.Ticket.category == category)
    if assignee_id is not None:
        stmt = stmt.where(models.Ticket.assignee_id == assignee_id)

    count = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    stmt = stmt.order_by(models.Ticket.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()

    return {
        "items": [
            {
                "id": t.id, "title": t.title, "description": t.description,
                "status": t.status, "priority": t.priority, "category": t.category,
                "creator_id": t.creator_id, "assignee_id": t.assignee_id,
                "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in items
        ],
        "total": count, "page": page, "page_size": page_size,
    }


@router.get("/{ticket_id}", response_model=dict[str, Any])
async def get_ticket(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("tickets:read")),
):
    obj = await db.get(models.Ticket, ticket_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "工单不存在")
    comments = (await db.execute(
        select(models.TicketComment)
        .where(models.TicketComment.ticket_id == ticket_id)
        .order_by(models.TicketComment.created_at)
    )).scalars().all()
    return {
        "id": obj.id, "title": obj.title, "description": obj.description,
        "status": obj.status, "priority": obj.priority, "category": obj.category,
        "creator_id": obj.creator_id, "assignee_id": obj.assignee_id,
        "resolved_at": obj.resolved_at.isoformat() if obj.resolved_at else None,
        "closed_at": obj.closed_at.isoformat() if obj.closed_at else None,
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
        "comments": [
            {"id": c.id, "user_id": c.user_id, "content": c.content,
             "created_at": c.created_at.isoformat() if c.created_at else None}
            for c in comments
        ],
    }


@router.post("", status_code=201)
async def create_ticket(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("tickets:write")),
):
    obj = models.Ticket(
        title=body.get("title", ""),
        description=body.get("description"),
        status=body.get("status", "open"),
        priority=body.get("priority", "normal"),
        category=body.get("category", "general"),
        creator_id=current.id,
        assignee_id=body.get("assignee_id"),
    )
    db.add(obj)
    await db.flush()
    await db.refresh(obj)

    # 通知：有分配人 → 通知被分配人
    if obj.assignee_id and obj.assignee_id != current.id:
        await create_notification(
            db, user_id=obj.assignee_id, type="task",
            title=f"新工单分配给你：#{obj.id} {obj.title}",
            body=f"优先级：{obj.priority}，分类：{obj.category}",
            link=f"/tickets",
        )

    await db.commit()
    return {"id": obj.id, "title": obj.title}


@router.patch("/{ticket_id}")
async def update_ticket(
    ticket_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("tickets:write")),
):
    obj = await db.get(models.Ticket, ticket_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "工单不存在")

    old_assignee = obj.assignee_id
    old_status = obj.status

    for k in ("title", "description", "status", "priority", "category", "assignee_id"):
        if k in body:
            setattr(obj, k, body[k])
    if "status" in body:
        if body["status"] == "resolved":
            obj.resolved_at = datetime.now(timezone.utc)
        elif body["status"] == "closed":
            obj.closed_at = datetime.now(timezone.utc)

    await db.flush()

    # 通知：分配给新的人
    new_assignee = obj.assignee_id
    if new_assignee and new_assignee != old_assignee and new_assignee != current.id:
        await create_notification(
            db, user_id=new_assignee, type="task",
            title=f"工单分配给你：#{obj.id} {obj.title}",
            body=f"优先级：{obj.priority}，分类：{obj.category}",
            link=f"/tickets",
        )

    # 通知：状态变更 → 通知创建者
    new_status = obj.status
    if new_status != old_status and obj.creator_id != current.id:
        await create_notification(
            db, user_id=obj.creator_id, type="task",
            title=f"工单 #{obj.id} 状态变更",
            body=f"「{obj.title}」从 {STATUS_LABEL.get(old_status, old_status)} 变为 {STATUS_LABEL.get(new_status, new_status)}",
            link=f"/tickets",
        )

    await db.commit()
    return {"id": obj.id}


@router.delete("/{ticket_id}", status_code=204)
async def delete_ticket(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("tickets:write")),
):
    obj = await db.get(models.Ticket, ticket_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "工单不存在")
    obj.deleted_at = datetime.now(timezone.utc)
    await db.commit()


@router.post("/{ticket_id}/comments", status_code=201)
async def add_comment(
    ticket_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("tickets:write")),
):
    obj = await db.get(models.Ticket, ticket_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "工单不存在")

    content = body.get("content", "")
    comment = models.TicketComment(
        ticket_id=ticket_id,
        user_id=current.id,
        content=content,
    )
    db.add(comment)
    await db.flush()
    await db.refresh(comment)

    # 通知：评论者不是工单创建者 → 通知创建者
    if obj.creator_id and obj.creator_id != current.id:
        await create_notification(
            db, user_id=obj.creator_id, type="task",
            title=f"工单 #{obj.id} 有新评论",
            body=f"{current.nickname or current.username}：{content[:100]}",
            link=f"/tickets",
        )

    # 通知：评论者不是被分配人 → 通知被分配人
    if obj.assignee_id and obj.assignee_id != current.id and obj.assignee_id != obj.creator_id:
        await create_notification(
            db, user_id=obj.assignee_id, type="task",
            title=f"工单 #{obj.id} 有新评论",
            body=f"{current.nickname or current.username}：{content[:100]}",
            link=f"/tickets",
        )

    # 通知：@提及 — 从评论内容中检测 @username
    mentioned = set(re.findall(r"@(\w+)", content))
    if mentioned:
        users_result = await db.execute(
            select(auth_models.User).where(auth_models.User.username.in_(mentioned))
        )
        mentioned_users = users_result.scalars().all()
        for mu in mentioned_users:
            if mu.id != current.id:
                await create_notification(
                    db, user_id=mu.id, type="mention",
                    title=f"你在工单 #{obj.id} 被提及",
                    body=f"{current.nickname or current.username}：{content[:100]}",
                    link=f"/tickets",
                )

    await db.commit()
    return {"id": comment.id}
