"""Webhook 事件投递（M3·P2 3.1 → P2 最后一批加固）。

设计取舍（这一版重写，不是微调）：

1. **先落库再发**。旧实现 ``asyncio.create_task(_post(...))`` 是纯内存任务，
   进程一重启就凭空消失，下游 Agent 收没收到无从查证。现在每次投递先在
   ``system_webhook_deliveries`` 留一条记录，再拿记录去发 —— 这样才能重放。
2. **httpx 异步**。旧实现用 ``urllib.request.urlopen`` 在事件循环里同步阻塞，
   一个慢下游（10s 超时）就能把整个 worker 卡死。现在 ``httpx.AsyncClient``。
3. **重试有退避**。失败按 30s / 2min / 10min / 30min 退避重试，共 5 次；
   后台 worker 每 30s 扫一次到期项，所以进程重启后未投完的会接着投。
4. **签名带时间戳**。``sha256=HMAC(secret, f"{ts}\\n{body}")``，下游校验
   ``X-Cenkor-Timestamp`` 与当前时间差（建议 300s）即可防重放。
5. **事件语义**。新增 ``entry.published``：``entry.saved`` 是「存了一次」
   （草稿也算），下游 Agent 要的是「这篇对外可见了」。

投递是 at-least-once：同一 ``event_id`` 可能被投多次（重试/人工重放），
下游必须按 ``X-Cenkor-Event-Id`` 幂等去重。
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from sqlalchemy import select, update

from cenkor_admin.apps.system import models
from cenkor_admin.apps.system.webhook_models import WebhookDelivery
from cenkor_admin.core.db import AsyncSessionLocal
from cenkor_admin.core.hooks import hook

log = structlog.get_logger()

# 可订阅事件（管理端下拉与此保持一致）
WEBHOOK_EVENTS = (
    "entry.saved",
    "entry.published",
    "entry.deleted",
    "content_type.created",
    "media.uploaded",
    "user.login",
)

TIMEOUT = 10.0          # 单次 HTTP 超时（秒）
MAX_ATTEMPTS = 5        # 含首次
RETRY_BASE = 30         # 首次重试间隔（秒），之后 ×4
RETRY_LOOP_INTERVAL = 30  # 重试 worker 扫描间隔


# ============================================================
# 投递
# ============================================================

def _backoff(attempts: int) -> int:
    """第 attempts 次失败后的等待秒数：30 / 120 / 480 / 1920，上限 1h。"""
    return min(RETRY_BASE * (4 ** max(attempts - 1, 0)), 3600)


def _sign(secret: str, timestamp: str, body: str) -> str:
    msg = f"{timestamp}\n{body}".encode()
    return "sha256=" + hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


async def enqueue(event: str, data: dict[str, Any], *, webhook_ids: list[int] | None = None) -> list[int]:
    """把一次事件写入投递日志，并立即发起投递（异步，不阻塞调用方）。

    - ``webhook_ids`` 非空时只投给指定订阅（测试发送用），跳过事件过滤
    - 返回新建的 delivery id 列表
    """
    try:
        async with AsyncSessionLocal() as db:
            stmt = select(models.Webhook).where(models.Webhook.enabled.is_(True))
            if webhook_ids:
                stmt = stmt.where(models.Webhook.id.in_(webhook_ids))
            rows = (await db.execute(stmt)).scalars().all()

            event_id = str(uuid.uuid4())
            occurred_at = datetime.now(UTC).isoformat()
            payload = {"id": event_id, "event": event, "occurred_at": occurred_at, "data": data}

            created: list[int] = []
            for w in rows:
                if not webhook_ids and event not in (w.events or []):
                    continue
                row = WebhookDelivery(
                    event_id=event_id,
                    webhook_id=w.id,
                    event=event,
                    url=w.url,
                    payload=payload,
                    status="pending",
                    attempts=0,
                    next_retry_at=datetime.now(UTC),
                )
                db.add(row)
                await db.flush()
                created.append(row.id)
            await db.commit()

        for did in created:
            asyncio.create_task(deliver(did))
        return created
    except Exception as e:
        log.warning("webhook.enqueue_failed", evt=event, error=str(e))
        return []


async def deliver(delivery_id: int) -> bool:
    """执行一次投递尝试，并把结果写回日志。返回是否成功。"""
    # 1) 抢占：只有把 next_retry_at 推后的那一个 worker 有权发送
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        claimed = await db.execute(
            update(WebhookDelivery)
            .where(
                WebhookDelivery.id == delivery_id,
                WebhookDelivery.status == "pending",
                (WebhookDelivery.next_retry_at.is_(None)) | (WebhookDelivery.next_retry_at <= now),
            )
            .values(next_retry_at=now + timedelta(seconds=120), updated_at=now)
        )
        await db.commit()
        if claimed.rowcount == 0:
            return False
        obj = await db.get(WebhookDelivery, delivery_id)
        if obj is None:
            return False
        url = obj.url
        payload = obj.payload or {}
        attempts = (obj.attempts or 0) + 1
        webhook_id = obj.webhook_id

    # 2) 拿密钥（订阅可能已被删，密钥也就没了 → 不签名继续投）
    secret = ""
    if webhook_id:
        async with AsyncSessionLocal() as db:
            w = await db.get(models.Webhook, webhook_id)
            if w is not None:
                secret = w.secret or ""
                if not w.enabled:
                    # 订阅被停用：保留记录，标记丢弃，不重试
                    await db.execute(
                        update(WebhookDelivery)
                        .where(WebhookDelivery.id == delivery_id)
                        .values(
                            status="dropped",
                            attempts=attempts,
                            error="订阅已停用",
                            next_retry_at=None,
                            updated_at=datetime.now(UTC),
                        )
                    )
                    await db.commit()
                    return False

    body = json.dumps(payload, ensure_ascii=False, default=str)
    ts = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Cenkor-CMS-Webhook/2",
        "X-Cenkor-Event": str(payload.get("event") or ""),
        "X-Cenkor-Event-Id": str(payload.get("id") or ""),
        "X-Cenkor-Delivery": str(delivery_id),
        "X-Cenkor-Attempt": str(attempts),
        "X-Cenkor-Timestamp": ts,
    }
    if secret:
        headers["X-Cenkor-Signature"] = _sign(secret, ts, body)

    # 3) 发
    status: str
    http_status: int | None = None
    snippet: str | None = None
    err: str | None = None
    duration = 0
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
            resp = await client.post(url, content=body.encode(), headers=headers)
        duration = int((time.perf_counter() - started) * 1000)
        http_status = resp.status_code
        snippet = (resp.text or "")[:500]
        # 2xx 成功；4xx 是下游明确拒绝（配置错），重试无意义 → 直接判失败
        if 200 <= resp.status_code < 300:
            status = "success"
        elif 400 <= resp.status_code < 500 and resp.status_code not in (408, 429):
            status = "failed"
            err = f"HTTP {resp.status_code}（4xx 不重试）"
        else:
            status = "pending" if attempts < MAX_ATTEMPTS else "failed"
            err = f"HTTP {resp.status_code}"
    except Exception as e:
        duration = int((time.perf_counter() - started) * 1000)
        status = "pending" if attempts < MAX_ATTEMPTS else "failed"
        err = f"{type(e).__name__}: {e}"[:1000]

    now = datetime.now(UTC)
    values: dict[str, Any] = {
        "status": status,
        "attempts": attempts,
        "http_status": http_status,
        "response_snippet": snippet,
        "error": err,
        "duration_ms": duration,
        "updated_at": now,
        "delivered_at": now if status == "success" else None,
        "next_retry_at": None if status != "pending" else now + timedelta(seconds=_backoff(attempts)),
    }
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(WebhookDelivery).where(WebhookDelivery.id == delivery_id).values(**values)
        )
        await db.commit()

    if status == "success":
        log.info("webhook.delivered", delivery=delivery_id, evt=payload.get("event"),
                 status=http_status, ms=duration)
    else:
        log.warning("webhook.post_failed", delivery=delivery_id, evt=payload.get("event"),
                    attempts=attempts, status=status, error=err)
    return status == "success"


async def replay(delivery_id: int) -> bool:
    """人工重放：把记录重置为 pending 后立刻投一次（event_id 保持不变，下游可去重）。"""
    async with AsyncSessionLocal() as db:
        obj = await db.get(WebhookDelivery, delivery_id)
        if obj is None:
            raise LookupError("投递记录不存在")
        await db.execute(
            update(WebhookDelivery)
            .where(WebhookDelivery.id == delivery_id)
            .values(
                status="pending",
                attempts=0,
                http_status=None,
                response_snippet=None,
                error=None,
                next_retry_at=datetime.now(UTC),
                delivered_at=None,
                updated_at=datetime.now(UTC),
            )
        )
        await db.commit()
    return await deliver(delivery_id)


async def retry_loop(interval: int = RETRY_LOOP_INTERVAL) -> None:
    """后台重试 worker：扫到期的 pending 记录逐条重投。

    进程重启后这个循环随之重建，未投完的记录会自动续上 —— 这是「落库」换来的。
    """
    log.info("webhook.retry_loop.started", interval=interval)
    while True:
        try:
            await asyncio.sleep(interval)
            now = datetime.now(UTC)
            async with AsyncSessionLocal() as db:
                ids = (await db.execute(
                    select(WebhookDelivery.id)
                    .where(
                        WebhookDelivery.status == "pending",
                        WebhookDelivery.next_retry_at.is_not(None),
                        WebhookDelivery.next_retry_at <= now,
                    )
                    .order_by(WebhookDelivery.next_retry_at)
                    .limit(50)
                )).scalars().all()
            for did in ids:
                await deliver(did)
        except asyncio.CancelledError:
            log.info("webhook.retry_loop.stopped")
            raise
        except Exception as e:
            log.warning("webhook.retry_loop.error", error=str(e))


# ============================================================
# 事件数据构造（下游 Agent 要能只靠这条 payload 干活）
# ============================================================

_HTML_RE = re.compile(r"<[^>]+>")


def _excerpt(content: Any, limit: int = 400) -> str:
    """从 entry.content 里抠一段纯文本摘要，给社媒/CRM 类 Agent 当素材。"""
    parts: list[str] = []
    if isinstance(content, str):
        parts.append(_HTML_RE.sub(" ", content))
    elif isinstance(content, dict):
        for key in ("text", "body", "markdown", "md", "summary", "html"):
            v = content.get(key)
            if isinstance(v, str) and v.strip():
                parts.append(_HTML_RE.sub(" ", v))
    text = re.sub(r"\s+", " ", " ".join(parts)).strip()
    return text[:limit]


async def _entry_data(entry: Any, db: Any = None) -> dict[str, Any]:
    """组装条目事件的数据体。content_type_key 用来拼对外地址。"""
    ct_key: str | None = None
    ct_name: str | None = None
    if db is not None and getattr(entry, "content_type_id", None):
        try:
            from cenkor_admin.apps.cms import models as cms_models

            ct = await db.get(cms_models.ContentType, entry.content_type_id)
            if ct is not None:
                ct_key, ct_name = ct.key, ct.name
        except Exception as e:
            # 查不到类型不影响投递本身：地址字段留空，其余照发
            log.debug("webhook.ct_lookup_failed", error=str(e))

    slug = getattr(entry, "slug", None) or str(entry.id)
    data: dict[str, Any] = {
        "entry_id": entry.id,
        "site_id": getattr(entry, "site_id", None),
        "title": entry.title,
        "slug": getattr(entry, "slug", None),
        "status": entry.status,
        "content_type_id": entry.content_type_id,
        "content_type_key": ct_key,
        "content_type_name": ct_name,
        "seo": getattr(entry, "seo", None) or {},
        "category_id": getattr(entry, "category_id", None),
        "author_id": getattr(entry, "author_id", None),
        "published_at": entry.published_at.isoformat() if getattr(entry, "published_at", None) else None,
        "excerpt": _excerpt(getattr(entry, "content", None)),
        # AI 溯源：下游决定「这篇要不要标注 AI 生成」
        "ai_origin": getattr(entry, "ai_origin", None),
        "ai_generated": bool(getattr(entry, "ai_origin", None)),
    }
    if ct_key:
        data["api_path"] = f"/api/v1/public/site/{ct_key}/{slug}"
        data["public_path"] = f"/{ct_key}/{slug}"
    return data


# ============================================================
# 钩子订阅
# ============================================================

@hook("entry.saved", app_key="core", priority=100)
async def _wh_entry_saved(*, entry=None, db=None, **kwargs) -> None:
    if entry is None:
        return
    await enqueue("entry.saved", await _entry_data(entry, db))


@hook("entry.published", app_key="core", priority=100)
async def _wh_entry_published(*, entry=None, db=None, **kwargs) -> None:
    if entry is None:
        return
    await enqueue("entry.published", await _entry_data(entry, db))


@hook("entry.deleted", app_key="core", priority=100)
async def _wh_entry_deleted(*, entry_id=None, **kwargs) -> None:
    await enqueue("entry.deleted", {"entry_id": entry_id})


@hook("content_type.created", app_key="core", priority=100)
async def _wh_content_type_created(*, content_type=None, **kwargs) -> None:
    if content_type is None:
        return
    await enqueue("content_type.created", {
        "id": content_type.id, "key": content_type.key, "name": content_type.name,
    })


@hook("media.uploaded", app_key="core", priority=100)
async def _wh_media_uploaded(*, media=None, **kwargs) -> None:
    if media is None:
        return
    await enqueue("media.uploaded", {
        "id": media.id, "url": getattr(media, "url", None), "mime": getattr(media, "mime", None),
    })


@hook("user.login", app_key="core", priority=100)
async def _wh_user_login(*, user=None, **kwargs) -> None:
    if user is None:
        return
    await enqueue("user.login", {"user_id": user.id, "username": user.username})
