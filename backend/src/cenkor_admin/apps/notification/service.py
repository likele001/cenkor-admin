"""通知创建服务：写库 + Redis pubsub 推送。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.notification import models
from cenkor_admin.core.redis import redis_client

NOTIFICATION_TYPES = frozenset({"system", "audit", "mention", "task"})


async def create_notification(
    db: AsyncSession,
    *,
    user_id: int,
    type: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    payload: Any = None,
) -> models.Notification:
    """创建通知并推送实时提醒。

    Args:
        db: 数据库会话
        user_id: 接收者（用户 id）
        type: system / audit / mention / task
        title: 标题（必填）
        body: 正文（可选）
        link: 前端路由（可选）
        payload: 附加数据（可选，dict）
    Returns:
        创建的 Notification 实例
    """
    if type not in NOTIFICATION_TYPES:
        raise ValueError(f"Unknown notification type: {type!r}, must be one of {NOTIFICATION_TYPES}")

    n = models.Notification(
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        link=link,
        payload=payload,
    )
    db.add(n)
    await db.flush()
    await db.refresh(n)

    # 推送至 Redis pubsub（实时通知）
    channel = f"notify:user:{user_id}"
    msg = {
        "id": n.id,
        "type": n.type,
        "title": n.title,
        "body": n.body,
        "link": n.link,
        "payload": n.payload,
        "read": False,
        "read_at": None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }
    try:
        await redis_client.publish(channel, json.dumps(msg, ensure_ascii=False))
    except Exception:
        pass  # dev 环境无 redis 时静默失败

    return n


async def create_system_notification_to_all(
    db: AsyncSession,
    *,
    type: str = "system",
    title: str,
    body: str | None = None,
    link: str | None = None,
    payload: Any = None,
) -> list[models.Notification]:
    """向所有用户发送系统通知（逐个创建）。用户数多时应改为批量 insert。"""
    from cenkor_admin.apps.auth.models import User

    users = (await db.execute(select(User.id))).scalars().all()
    created: list[models.Notification] = []
    for uid in users:
        n = await create_notification(db, user_id=uid, type=type, title=title, body=body, link=link, payload=payload)
        created.append(n)
    return created
