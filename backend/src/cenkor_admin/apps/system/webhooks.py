"""Webhook 事件推送（M3·P2 3.1）。

- 订阅 core 钩子（entry.saved / entry.deleted / content_type.created / media.uploaded / user.login）
- 命中 system_webhooks 里启用的订阅后，异步 POST JSON（带 HMAC-SHA256 签名头 X-Cenkor-Signature）
- 失败只记日志，绝不影响主流程
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

import structlog
from sqlalchemy import select

from cenkor_admin.core.db import AsyncSessionLocal
from cenkor_admin.core.hooks import hook

log = structlog.get_logger()

WEBHOOK_EVENTS = (
    "entry.saved",
    "entry.deleted",
    "content_type.created",
    "media.uploaded",
    "user.login",
)


async def _notify(event: str, payload: dict) -> None:
    try:
        from cenkor_admin.apps.system.models import Webhook
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(Webhook).where(Webhook.enabled.is_(True))
            )).scalars().all()
        for w in rows:
            if event not in (w.events or []):
                continue
            body = json.dumps(
                {
                    "event": event,
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "payload": payload,
                },
                ensure_ascii=False,
                default=str,
            )
            secret = (w.secret or "").encode()
            sig = hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
            asyncio.create_task(_post(w.url, body, sig))
    except Exception as e:  # noqa: BLE001 - 推送失败不阻塞主流程
        log.warning("webhook.notify_failed", event=event, error=str(e))


async def _post(url: str, body: str, sig: str) -> None:
    req = urllib.request.Request(
        url,
        data=body.encode(),
        headers={
            "Content-Type": "application/json",
            "X-Cenkor-Signature": sig,
            "X-Cenkor-Event": "webhook",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            log.info("webhook.delivered", url=url, status=r.status)
    except Exception as e:  # noqa: BLE001
        log.warning("webhook.post_failed", url=url, error=str(e))


# ---- 钩子订阅 ----

@hook("entry.saved", app_key="core", priority=100)
async def _wh_entry_saved(**kwargs) -> None:
    entry = kwargs.get("entry")
    if entry is None:
        return
    await _notify("entry.saved", {"id": entry.id, "title": entry.title, "status": entry.status})


@hook("entry.deleted", app_key="core", priority=100)
async def _wh_entry_deleted(**kwargs) -> None:
    await _notify("entry.deleted", {"id": kwargs.get("entry_id")})


@hook("content_type.created", app_key="core", priority=100)
async def _wh_content_type_created(**kwargs) -> None:
    ct = kwargs.get("content_type")
    if ct is None:
        return
    await _notify("content_type.created", {"id": ct.id, "key": ct.key, "name": ct.name})


@hook("media.uploaded", app_key="core", priority=100)
async def _wh_media_uploaded(**kwargs) -> None:
    media = kwargs.get("media")
    if media is None:
        return
    await _notify("media.uploaded", {"id": media.id, "url": media.url, "mime": media.mime})


@hook("user.login", app_key="core", priority=100)
async def _wh_user_login(**kwargs) -> None:
    user = kwargs.get("user")
    if user is None:
        return
    await _notify("user.login", {"user_id": user.id, "username": user.username})
