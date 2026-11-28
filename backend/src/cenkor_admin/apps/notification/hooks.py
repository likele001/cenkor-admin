"""通知网关的事件接线。

只做「事件 → 网关」，渲染与投递都在 ``gateway`` 里。订阅了哪些事件由
渠道自己的 ``events`` 决定，所以同一条事件可以同时进审核群和运维群，
也可以只进其中一个。

同时挂 ``scheduler.tick`` 消费 outbox —— 和巡检、发布任务共用同一个
30 秒循环，不新增进程。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from cenkor_admin.apps.notification import gateway
from cenkor_admin.core.hooks import hook


def _entry_payload(entry: Any, user: Any = None) -> dict[str, Any]:
    submitter = ""
    if user is not None:
        submitter = getattr(user, "nickname", "") or getattr(user, "username", "") or ""
    return {
        "entry_id": getattr(entry, "id", None),
        "title": getattr(entry, "title", ""),
        "slug": getattr(entry, "slug", ""),
        "site_id": getattr(entry, "site_id", None),
        "status": getattr(entry, "status", ""),
        "submitter": submitter,
    }


async def _reviewer_ids(db) -> list[int]:
    """拥有内容审核权限的用户 —— 提交审核的站内信只该给他们。"""
    from cenkor_admin.apps.rbac.models import Permission, RolePermission, UserRole

    rows = (
        await db.execute(
            select(UserRole.user_id)
            .join(RolePermission, RolePermission.role_id == UserRole.role_id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(Permission.code == "cms:entry:review")
            .distinct()
        )
    ).scalars().all()
    return [int(uid) for uid in rows]


@hook("entry.published", app_key="notification", priority=60)
async def _on_entry_published(*, entry: Any = None, db=None, user: Any = None, **_: Any) -> None:
    if entry is None or db is None:
        return
    payload = _entry_payload(entry, user)
    author = getattr(entry, "author_id", None)
    await gateway.send(
        "entry.published",
        db=db,
        payload=payload,
        site_id=getattr(entry, "site_id", None),
        link=f"/cms/entries/{getattr(entry, 'id', '')}",
        user_ids=[author] if author else None,
    )


@hook("entry.submitted", app_key="notification", priority=60)
async def _on_entry_submitted(*, entry: Any = None, db=None, user: Any = None, **_: Any) -> None:
    if entry is None or db is None:
        return
    payload = _entry_payload(entry, user)
    recipients = await _reviewer_ids(db)
    await gateway.send(
        "entry.submitted",
        db=db,
        payload=payload,
        site_id=getattr(entry, "site_id", None),
        link=f"/cms/entries/{getattr(entry, 'id', '')}",
        user_ids=recipients,
    )


@hook("publish.failed", app_key="notification", priority=60)
async def _on_publish_failed(
    *, entry: Any = None, db=None, user: Any = None, channel: Any = None,
    error: str | None = None, **_: Any,
) -> None:
    if entry is None or db is None:
        return
    payload = _entry_payload(entry, user)
    payload["channel"] = (
        getattr(channel, "name", None) or getattr(channel, "channel_key", None) or ""
    )
    payload["error"] = error or ""
    recipients = await _reviewer_ids(db)
    author = getattr(entry, "author_id", None)
    if author:
        recipients.append(author)
    await gateway.send(
        "publish.failed",
        db=db,
        payload=payload,
        site_id=getattr(entry, "site_id", None),
        link=f"/cms/entries/{getattr(entry, 'id', '')}",
        user_ids=recipients,
    )


@hook("scheduler.tick", app_key="notification", priority=20)
async def _drain_outbox() -> None:
    """每 30 秒消费一次 outbox；优先级高于巡检，先清掉上一轮的积压。"""
    await gateway.drain()