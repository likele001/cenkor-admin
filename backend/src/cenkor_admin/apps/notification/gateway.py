"""统一通知网关：业务事件 → 站内信 + 外部渠道（outbox + 30s 重试）。

三条取舍：

1. **不引 Celery**。企业微信 / 飞书 / 钉钉都是普通 HTTPS，站内信是写库，
   一天几十上百条。正确做法是「落库 outbox + scheduler.tick 每 30 秒扫
   pending 重试」，不引入第二个进程和 beat。
2. **先落库再发送**。发送失败不能只写日志 —— 运维事后要能看见「哪条
   没发出去、为什么」，这是 ``notify_outbox`` 唯一的存在理由。
3. **通道复用 ``mon_channels`` 表**。巡检通道是通知渠道的子集，原地扩展
   kind / events，避免线上切表名造成「迁移完成、旧代码查不到表」的空窗。

渠道 kind：
- ``wecom`` / ``wecom_robot``：企业微信群机器人（webhook）
- ``wecom_app``：企业微信自建应用（corpid + secret + agentid）
- ``feishu_robot``：飞书群机器人
- ``dingtalk`` / ``dingtalk_robot``：钉钉群机器人（extra.sign_secret 可选加签）
- ``webhook``：通用 webhook
- ``email``：SMTP 邮件（extra.to 收件人）
- ``sms``：未实现，落 skipped 而不是 failed
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote_plus

import httpx
import structlog
from sqlalchemy import or_, select, update

from cenkor_admin.apps.monitor.models import MonChannel
from cenkor_admin.apps.notification.models import NotificationOutbox
from cenkor_admin.core.db import AsyncSessionLocal
from cenkor_admin.core.secrets import decrypt_secret

log = structlog.get_logger(__name__)

MAX_ATTEMPTS = 3
# 指数退避：第一次失败 30 秒后重试，第二次 2 分钟，第三次 10 分钟
BACKOFF_SECONDS = (30, 120, 600)
BATCH = 20
HTTP_TIMEOUT = 8.0
# sending 状态的租约：进程中途死掉，5 分钟后重新入队
LEASE_SECONDS = 300

WEBHOOK_KINDS = frozenset(
    {"wecom", "wecom_robot", "feishu_robot", "dingtalk", "dingtalk_robot", "webhook"}
)
KNOWN_KINDS = WEBHOOK_KINDS | {"wecom_app", "email", "sms"}

_WECOM_TOKEN: dict[str, tuple[str, float]] = {}
_WECOM_TOKEN_TTL = 7000.0


# ---------------------------------------------------------------- 渲染

def render(event: str, payload: dict[str, Any] | None = None) -> tuple[str, str]:
    """把事件渲染成 (标题, 正文)。调用方也可直接传 title/body 覆盖。"""
    p = payload or {}
    title = str(p.get("title") or p.get("name") or "").strip()
    site = p.get("site_id")
    slug = p.get("slug") or ""
    extra = f"\n站点 {site}" if site is not None else ""
    if slug:
        extra += f"\nslug：{slug}"
    if event == "entry.published":
        return f"内容已发布：{title}", f"{title}{extra}\n状态：published"
    if event == "entry.submitted":
        return f"待审核：{title}", f"{title}{extra}\n提交人：{p.get('submitter') or '未知'}"
    if event == "publish.failed":
        return (
            f"发布失败：{title}",
            f"{title}{extra}\n渠道：{p.get('channel') or '未知'}\n原因：{p.get('error') or '未知'}",
        )
    if event == "monitor.incident":
        return f"站点告警{('：' + title) if title else ''}", str(p.get("text") or "")
    return f"{event}", f"{title}{extra}"


# ---------------------------------------------------------------- 入队

def _subscribed(channel: MonChannel, event: str) -> bool:
    events = channel.events
    if events is None:  # 老通道：订阅全部事件
        return True
    return event in events


async def send(
    event: str,
    *,
    db,
    title: str | None = None,
    body: str | None = None,
    payload: dict[str, Any] | None = None,
    site_id: int | None = None,
    link: str | None = None,
    user_ids: list[int] | None = None,
) -> list[int]:
    """一次业务事件：写站内信 + 给匹配渠道各落一条 outbox。

    - ``user_ids`` 非空时写站内信（type=system），并随 outbox 一起提交。
    - 渠道匹配：启用 + (站点相同 或 全站通用) + 订阅了该 event。
    返回新生成的 outbox 主键，便于调用方立即投递/测试。
    """
    payload = dict(payload or {})
    if site_id is not None:
        payload.setdefault("site_id", site_id)
    if title is None:
        title, body = render(event, payload)
    title = (title or event)[:200]
    body = body or ""

    if user_ids:
        from cenkor_admin.apps.notification.service import create_notification

        for uid in dict.fromkeys(uid for uid in user_ids if uid):
            await create_notification(
                db,
                user_id=uid,
                type="system",
                title=title,
                body=body,
                link=link,
                payload=payload,
            )

    stmt = select(MonChannel).where(
        MonChannel.enabled.is_(True),
        or_(MonChannel.site_id == site_id, MonChannel.site_id.is_(None)),
    )
    channels = [c for c in (await db.execute(stmt)).scalars().all() if _subscribed(c, event)]

    rows = [
        NotificationOutbox(
            event=event,
            site_id=site_id,
            channel_id=c.id,
            status="pending",
            attempts=0,
            title=title,
            body=body,
            payload=payload,
        )
        for c in channels
    ]
    if rows:
        db.add_all(rows)
    await db.commit()
    return [r.id for r in rows]


# ---------------------------------------------------------------- 投递

async def _wecom_app_token(corpid: str, secret: str) -> str:
    key = f"{corpid}:{secret[:8]}"
    hit = _WECOM_TOKEN.get(key)
    now = time.monotonic()
    if hit and now - hit[1] < _WECOM_TOKEN_TTL:
        return hit[0]
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get(
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
            params={"corpid": corpid, "corpsecret": secret},
        )
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"获取 access_token 失败（{data.get('errcode')}）：{data.get('errmsg')}")
    _WECOM_TOKEN[key] = (token, now)
    return token


def _dingtalk_signed_url(url: str, secret: str) -> str:
    ts = str(int(time.time() * 1000))
    digest = hmac.new(secret.encode(), f"{ts}\n{secret}".encode(), hashlib.sha256).digest()
    sign = quote_plus(base64.b64encode(digest))
    joiner = "&" if "?" in url else "?"
    return f"{url}{joiner}timestamp={ts}&sign={sign}"


def _check_response(resp: httpx.Response) -> tuple[str, str]:
    """统一判断：HTTP >= 400 或业务 errcode/code != 0 都算失败。"""
    if resp.status_code >= 400:
        return "failed", f"HTTP {resp.status_code} {resp.text[:180]}"
    try:
        data = resp.json()
    except Exception:
        return "sent", "ok"
    if not isinstance(data, dict):
        return "sent", "ok"
    for key in ("errcode", "code", "StatusCode"):
        if key in data:
            try:
                if int(data[key]) != 0:
                    msg = data.get("errmsg") or data.get("msg") or ""
                    return "failed", f"{key}={data[key]} {msg}".strip()
            except (TypeError, ValueError):
                pass
    return "sent", "ok"


async def _deliver(channel: MonChannel, title: str, body: str, payload: dict | None) -> tuple[str, str]:
    """投递到单个渠道，返回 (sent|skipped|failed, 说明)。"""
    kind = channel.kind
    extra = channel.extra if isinstance(channel.extra, dict) else {}
    text = f"{title}\n{body}" if body else title

    if kind not in KNOWN_KINDS:
        return "skipped", f"未知渠道类型：{kind}"
    if kind == "sms":
        return "skipped", "短信通道未实现"

    if kind == "email":
        to = (extra.get("to") or "").strip()
        if not to:
            return "failed", "邮件渠道没有配置收件人（extra.to）"
        from cenkor_admin.core.mail import send_email_sync

        try:
            res = await asyncio.to_thread(send_email_sync, to, title, body or title)
        except Exception as exc:
            return "failed", f"SMTP 发送异常：{exc}"
        if res.get("transport") == "noop":
            # 未配 SMTP_HOST 时 mail.py 返回假成功，必须记为 skipped 而不是 sent
            return "skipped", "SMTP 未配置，未实际发送"
        return ("sent", "ok") if res.get("ok") else ("failed", str(res.get("reason") or "发送失败"))

    if kind == "wecom_app":
        corpid = (extra.get("corpid") or "").strip()
        agentid = str(extra.get("agentid") or "").strip()
        secret = decrypt_secret(channel.secret) or ""
        if not corpid or not secret or not agentid:
            return "failed", "企业微信自建应用缺少 corpid / secret / agentid"
        try:
            token = await _wecom_app_token(corpid, secret)
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                resp = await client.post(
                    "https://qyapi.weixin.qq.com/cgi-bin/message/send",
                    params={"access_token": token},
                    json={
                        "touser": extra.get("touser") or "@all",
                        "msgtype": "text",
                        "agentid": int(agentid),
                        "text": {"content": text},
                    },
                )
        except Exception as exc:
            return "failed", f"企业微信调用异常：{exc}"
        return _check_response(resp)

    # 其余都是 webhook 形态
    url = decrypt_secret(channel.secret) or ""
    if not url:
        return "failed", "未配置 Webhook 地址"

    if kind == "feishu_robot":
        req = {"msg_type": "text", "content": {"text": text}}
    elif kind in ("dingtalk", "dingtalk_robot"):
        req = {"msgtype": "text", "text": {"content": text}}
        sign_secret = (extra.get("sign_secret") or "").strip()
        if sign_secret:
            url = _dingtalk_signed_url(url, sign_secret)
    elif kind in ("wecom", "wecom_robot"):
        req = {"msgtype": "text", "text": {"content": text}}
    else:  # webhook
        req = {
            "event": payload.get("event") if payload else None,
            "title": title,
            "text": text,
            "payload": payload or {},
        }

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.post(url, json=req)
    except Exception as exc:
        return "failed", f"请求异常：{exc}"
    return _check_response(resp)


async def deliver_pending(limit: int = BATCH) -> dict[str, int]:
    """消费 outbox。SKIP LOCKED 保证多 worker 不会重复投递同一条。"""
    stats = {"sent": 0, "skipped": 0, "failed": 0, "retry": 0}
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        # 进程中途被杀会留下 sending 死行；用 next_retry_at 当租约回收。
        await db.execute(
            update(NotificationOutbox)
            .where(
                NotificationOutbox.status == "sending",
                NotificationOutbox.next_retry_at.is_not(None),
                NotificationOutbox.next_retry_at <= now,
            )
            .values(status="pending", last_error="投递超时，重新入队")
        )

        ids = (
            await db.execute(
                select(NotificationOutbox.id)
                .where(
                    NotificationOutbox.status == "pending",
                    or_(
                        NotificationOutbox.next_retry_at.is_(None),
                        NotificationOutbox.next_retry_at <= now,
                    ),
                )
                .order_by(NotificationOutbox.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        if not ids:
            await db.commit()
            return stats

        # 先置 sending（带 5 分钟租约）并提交，释放行锁；网络 I/O 不能开在事务里
        await db.execute(
            update(NotificationOutbox)
            .where(NotificationOutbox.id.in_(ids))
            .values(status="sending", next_retry_at=now + timedelta(seconds=LEASE_SECONDS))
        )
        await db.commit()

        for oid in ids:
            row = await db.get(NotificationOutbox, oid)
            if row is None:
                continue
            channel = await db.get(MonChannel, row.channel_id)
            if channel is None or not channel.enabled:
                row.status = "skipped"
                row.last_error = "渠道已删除或已停用"
                stats["skipped"] += 1
                continue

            payload = dict(row.payload or {})
            payload.setdefault("event", row.event)
            status, detail = await _deliver(channel, row.title or "", row.body or "", payload)
            row.attempts = int(row.attempts or 0) + 1

            if status == "sent":
                row.status = "sent"
                row.sent_at = datetime.now(UTC)
                row.last_error = None
                stats["sent"] += 1
            elif status == "skipped":
                row.status = "skipped"
                row.last_error = detail[:2000]
                stats["skipped"] += 1
            else:
                row.last_error = detail[:2000]
                if row.attempts >= MAX_ATTEMPTS:
                    row.status = "failed"
                    stats["failed"] += 1
                else:
                    idx = min(row.attempts - 1, len(BACKOFF_SECONDS) - 1)
                    row.next_retry_at = datetime.now(UTC) + timedelta(seconds=BACKOFF_SECONDS[idx])
                    row.status = "pending"
                    stats["retry"] += 1
        await db.commit()

    if any(stats.values()):
        log.info("notify.deliver", **stats)
    return stats


async def drain() -> dict[str, int]:
    """scheduler.tick 的入口：失败只记日志，绝不拖垮调度。"""
    try:
        return await deliver_pending()
    except Exception as exc:
        log.warning("notify.drain_failed", error=str(exc))
        return {}


async def test_channel(channel: MonChannel, title: str = "【测试】Cenkor 通知渠道连通正常") -> dict[str, Any]:
    """发送测试消息，直接返回失败原因（不落 outbox）。"""
    status, detail = await _deliver(channel, title, "", {"event": "test"})
    return {"ok": status == "sent", "status": status, "detail": detail}