"""支付编排服务。

职责边界：
- 通道选路 + 驱动构造（配置解密）
- 订单落库与状态机流转（pending -> paid / closed / failed -> refunded）
- 回调验签结果落库、触发 `payment.paid` / `payment.refunded` 钩子供业务应用订阅
- 驱动只负责与第三方通信，本层不碰第三方协议细节
"""
from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.payment import models
from cenkor_admin.apps.payment.crypto import decrypt_config
from cenkor_admin.apps.payment.drivers import (
    NotifyResult,
    PayError,
    PayRequest,
    PayResult,
    get_driver_class,
)
from cenkor_admin.core.hooks import dispatch

log = structlog.get_logger()

PENDING = "pending"
PAID = "paid"
CLOSED = "closed"
FAILED = "failed"
REFUNDED = "refunded"
PARTIAL_REFUNDED = "partial_refunded"

# 可选支付状态（业务侧查询用）
SETTLED_STATES = (PAID, PARTIAL_REFUNDED, REFUNDED)

# ---------------- 终端识别与通道选路 ----------------
# 背景：同一场景下可能同时存在「扫码」和「跳转」两类收单方式的通道
# （例如虎皮椒 NATIVE 与 MOBILE）。通道本身不含终端信息，
# 必须由调用方把 User-Agent 归一成终端类型，本层再按终端挑一条。

# 扫码类：需要屏幕外设备扫码，只适合 PC
SCAN_PAY_TYPES = frozenset({"NATIVE", "QR", "QRCODE"})
# 跳转/调起类：适合手机浏览器或微信内
MOBILE_PAY_TYPES = frozenset({"MOBILE", "WAP", "WECHAT", "JSAPI", "MWEB"})

_WECHAT_UA_KEYS = ("micromessenger", "wechat")
_MOBILE_UA_KEYS = (
    "android", "iphone", "ipod", "ipad", "mobile", "windows phone",
    "harmony", "blackberry", "opera mini", "micromessenger",
)


def detect_terminal(user_agent: str | None) -> str:
    """把 User-Agent 归类成 ``pc`` / ``mobile`` / ``wechat``。

    归一顺序很重要：微信 UA 里同时含 ``Android``/``iPhone``，
    必须先判微信，否则会被误判成普通手机浏览器。
    """
    ua = (user_agent or "").strip().lower()
    if not ua:
        return "pc"
    if any(k in ua for k in _WECHAT_UA_KEYS):
        return "wechat"
    if any(k in ua for k in _MOBILE_UA_KEYS):
        return "mobile"
    return "pc"


def effective_pay_type(channel: models.PayChannel) -> str:
    """通道实际生效的收单方式：``config.pay_type`` 优先，否则取驱动的默认表。

    驱动若未暴露 ``default_pay_types``，或配置留空且驱动也无默认，返回空串
    （此时无法判断，选路时按中性处理）。
    """
    explicit = str(dict(channel.config or {}).get("pay_type") or "").strip().upper()
    if explicit:
        return explicit
    try:
        cls = get_driver_class(channel.provider)
    except PayError:
        return ""
    table = getattr(cls, "default_pay_types", None) or {}
    return str(table.get(channel.sub_type or "", "")).upper()


def terminal_rank(channel: models.PayChannel, terminal: str) -> int:
    """终端偏好排序键：0 = 匹配当前终端，1 = 不匹配，2 = 无法判断。"""
    pay_type = effective_pay_type(channel)
    if not pay_type:
        return 2
    if terminal == "pc":
        return 0 if pay_type in SCAN_PAY_TYPES else 1
    if terminal in ("mobile", "wechat"):
        return 0 if pay_type in MOBILE_PAY_TYPES else 1
    return 2


def _now() -> datetime:
    return datetime.now(timezone.utc)


def gen_out_trade_no(prefix: str = "P") -> str:
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{prefix}{ts}{random.randint(100000, 999999)}"


def gen_out_refund_no() -> str:
    return gen_out_trade_no("R")


def build_notify_url(base_url: str, scene_key: str, channel_id: int) -> str:
    base = (base_url or "").rstrip("/")
    return f"{base}/api/v1/public/payment/notify/{scene_key}/{channel_id}"


def build_return_url(base_url: str, out_trade_no: str) -> str:
    base = (base_url or "").rstrip("/")
    return f"{base}/api/v1/public/payment/cashier/{out_trade_no}"


async def get_channel(
    db: AsyncSession,
    scene_key: str,
    *,
    channel_id: int | None = None,
    provider: str | None = None,
    sub_type: str | None = None,
    terminal: str | None = None,
    include_disabled: bool = False,
) -> models.PayChannel:
    """按场景挑一条通道。

    排序策略：先按 ``is_default desc, sort asc, id asc`` 取默认序；
    若给了 ``terminal`` 且**未显式指定 channel_id**，再在其中按终端偏好做一次
    **稳定排序**（匹配终端的收单方式优先），同偏好内保持默认序。
    显式传 channel_id 时完全尊重调用方选择，不做终端干预。
    """
    stmt = select(models.PayChannel).where(
        models.PayChannel.deleted_at.is_(None),
        models.PayChannel.scene_key == scene_key,
    )
    if not include_disabled:
        stmt = stmt.where(models.PayChannel.enabled.is_(True))
    if channel_id:
        stmt = stmt.where(models.PayChannel.id == channel_id)
    if provider:
        stmt = stmt.where(models.PayChannel.provider == provider)
    if sub_type:
        stmt = stmt.where(models.PayChannel.sub_type == sub_type)
    stmt = stmt.order_by(
        models.PayChannel.is_default.desc(),
        models.PayChannel.sort.asc(),
        models.PayChannel.id.asc(),
    )
    rows = list((await db.execute(stmt)).scalars().all())
    if not rows:
        raise PayError(
            f"场景「{scene_key}」下没有可用的支付通道",
            detail="请先在支付中心为该业务配置通道",
            code="no_channel",
        )
    if terminal and not channel_id:
        # list.sort 是稳定排序：同 rank 内保留上面的默认序
        rows.sort(key=lambda ch: terminal_rank(ch, terminal))
    return rows[0]


def build_driver(channel: models.PayChannel):
    """按通道配置构造驱动实例（配置在此解密，明文不外流）。"""
    cls = get_driver_class(channel.provider)
    plain = decrypt_config(dict(channel.config or {}), cls.secret_fields())
    return cls(plain, mode=channel.mode, scene_key=channel.scene_key, sub_type=channel.sub_type)


async def create_order(
    db: AsyncSession,
    *,
    scene_key: str,
    amount_cents: int,
    subject: str,
    base_url: str,
    provider: str | None = None,
    sub_type: str | None = None,
    channel_id: int | None = None,
    terminal: str | None = None,
    description: str = "",
    client_ip: str = "",
    return_url: str = "",
    biz_type: str = "",
    biz_id: str = "",
    extra: dict | None = None,
    creator_id: int | None = None,
    prefix: str = "P",
) -> tuple[models.PayOrder, PayResult]:
    if amount_cents <= 0:
        raise PayError("支付金额必须大于 0", code="bad_amount")

    channel = await get_channel(
        db, scene_key, channel_id=channel_id, provider=provider, sub_type=sub_type,
        terminal=terminal,
    )

    out_trade_no = gen_out_trade_no(prefix)
    extra = dict(extra or {})
    notify_url = build_notify_url(base_url, scene_key, channel.id)
    # 业务侧可自带回跳地址，否则回到收银台
    final_return = return_url or build_return_url(base_url, out_trade_no)

    order = models.PayOrder(
        out_trade_no=out_trade_no,
        scene_key=scene_key,
        channel_id=channel.id,
        provider=channel.provider,
        sub_type=channel.sub_type,
        subject=subject[:256],
        description=description[:512] if description else None,
        amount_cents=amount_cents,
        status=PENDING,
        biz_type=biz_type or None,
        biz_id=str(biz_id) if biz_id else None,
        client_ip=client_ip or None,
        return_url=final_return,
        extra=extra or None,
        creator_id=creator_id,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    driver = build_driver(channel)
    req = PayRequest(
        out_trade_no=out_trade_no,
        subject=subject,
        amount_cents=amount_cents,
        scene_key=scene_key,
        description=description,
        client_ip=client_ip,
        notify_url=notify_url,
        return_url=final_return,
        openid=str(extra.get("openid") or ""),
        extra=extra,
    )
    try:
        result = await driver.create_pay(req)
    except PayError as exc:
        order.status = FAILED
        order.pay_mode = ""
        await db.commit()
        log.warning("payment.create_failed", scene=scene_key, out_trade_no=out_trade_no,
                    error=exc.message, detail=exc.detail)
        raise
    except Exception as exc:  # noqa: BLE001
        order.status = FAILED
        await db.commit()
        log.error("payment.create_error", scene=scene_key, out_trade_no=out_trade_no,
                  error=str(exc))
        raise PayError("下单失败，请稍后重试", detail=str(exc), code="create_failed") from exc

    order.pay_mode = result.mode
    order.pay_payload = result.payload
    await db.commit()
    await db.refresh(order)

    log.info("payment.created", scene=scene_key, out_trade_no=out_trade_no,
             provider=channel.provider, channel_id=channel.id,
             pay_type=effective_pay_type(channel), terminal=terminal or "",
             amount_cents=amount_cents, mode=result.mode)
    return order, result


async def mark_paid(
    db: AsyncSession,
    order: models.PayOrder,
    *,
    trade_no: str = "",
    amount_cents: int = 0,
    raw: dict | None = None,
    source: str = "notify",
) -> bool:
    """幂等置为已支付。返回是否发生了状态变化。"""
    if order.status in SETTLED_STATES:
        return False

    order.status = PAID
    order.trade_no = trade_no or order.trade_no
    order.paid_at = _now()
    order.last_notify_at = _now()
    order.notify_count = (order.notify_count or 0) + 1
    if amount_cents:
        order.amount_cents = amount_cents
    await db.commit()
    await db.refresh(order)

    log.info("payment.paid", scene=order.scene_key, out_trade_no=order.out_trade_no,
             amount_cents=order.amount_cents, source=source)

    await _dispatch_paid(order)
    if (order.extra or {}).get("biz_notify_url"):
        await _notify_biz(order)
    return True


async def _dispatch_paid(order: models.PayOrder) -> None:
    payload = {
        "scene_key": order.scene_key,
        "out_trade_no": order.out_trade_no,
        "trade_no": order.trade_no or "",
        "amount_cents": order.amount_cents,
        "provider": order.provider,
        "biz_type": order.biz_type or "",
        "biz_id": order.biz_id or "",
        "extra": order.extra or {},
    }
    try:
        await dispatch("payment.paid", **payload)
    except Exception as exc:  # noqa: BLE001 - 钩子异常不能影响支付主流程
        log.warning("payment.hook_failed", out_trade_no=order.out_trade_no, error=str(exc))


async def _notify_biz(order: models.PayOrder) -> None:
    """业务方自带回调地址时的异步通知（尽力而为，失败不影响主流程）。"""
    url = (order.extra or {}).get("biz_notify_url")
    if not url:
        return
    body = {
        "out_trade_no": order.out_trade_no,
        "trade_no": order.trade_no or "",
        "amount_cents": order.amount_cents,
        "scene_key": order.scene_key,
        "status": order.status,
        "biz_type": order.biz_type or "",
        "biz_id": order.biz_id or "",
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json=body)
    except Exception as exc:  # noqa: BLE001
        log.warning("payment.biz_notify_failed", out_trade_no=order.out_trade_no, error=str(exc))


async def handle_notify(
    db: AsyncSession,
    channel: models.PayChannel,
    headers: dict[str, str],
    body: bytes,
    *,
    client_ip: str = "",
) -> NotifyResult:
    """处理第三方异步回调：验签 -> 落日志 -> 更新订单 -> 钩子。"""
    driver = build_driver(channel)
    try:
        result = await driver.verify_notify(headers, body)
    except Exception as exc:  # noqa: BLE001
        result = NotifyResult(ok=False, error=f"回调处理异常：{exc}", reply="failure")

    db.add(models.PayNotifyLog(
        scene_key=channel.scene_key,
        provider=channel.provider,
        direction="notify",
        out_trade_no=result.out_trade_no or None,
        headers={k: v for k, v in (headers or {}).items() if k.lower() not in ("authorization",)},
        raw=result.raw,
        body_text=body.decode("utf-8", errors="replace")[:20000],
        verified=result.ok,
        processed=False,
        error=result.error or None,
        client_ip=client_ip or None,
    ))
    await db.commit()

    if not result.ok or not result.out_trade_no:
        return result

    order = (await db.execute(
        select(models.PayOrder).where(models.PayOrder.out_trade_no == result.out_trade_no)
    )).scalars().first()
    if order is None:
        log.warning("payment.notify_order_missing", out_trade_no=result.out_trade_no)
        return result

    if result.paid:
        await mark_paid(
            db, order, trade_no=result.trade_no,
            amount_cents=result.amount_cents, raw=result.raw, source="notify",
        )
    elif result.close and order.status == PENDING:
        order.status = CLOSED
        order.closed_at = _now()
        await db.commit()

    # 标记该笔回调已处理
    last_log = (await db.execute(
        select(models.PayNotifyLog)
        .where(models.PayNotifyLog.out_trade_no == result.out_trade_no)
        .order_by(models.PayNotifyLog.id.desc()).limit(1)
    )).scalars().first()
    if last_log is not None:
        last_log.processed = True
        await db.commit()

    return result


async def sync_order(db: AsyncSession, order: models.PayOrder) -> dict[str, Any]:
    """主动查单：以第三方结果为准，必要时补偿本地状态。"""
    if not order.channel_id:
        raise PayError("订单未关联支付通道，无法查单", code="no_channel")
    channel = await get_channel(
        db, order.scene_key, channel_id=order.channel_id, include_disabled=True,
    )
    driver = build_driver(channel)
    info = await driver.query(order.out_trade_no)

    db.add(models.PayNotifyLog(
        scene_key=order.scene_key,
        provider=order.provider,
        direction="query",
        out_trade_no=order.out_trade_no,
        raw=info.get("raw") or info,
        verified=True,
        processed=True,
    ))
    await db.commit()

    if info.get("paid") and order.status == PENDING:
        await mark_paid(
            db, order, trade_no=info.get("trade_no", ""),
            amount_cents=int(info.get("amount_cents") or 0), source="query",
        )
    elif info.get("status") in ("TRADE_CLOSED", "CLOSED", "PAYERROR") and order.status == PENDING:
        order.status = CLOSED if info.get("status") != "PAYERROR" else FAILED
        order.closed_at = _now()
        await db.commit()
    return info


async def refund_order(
    db: AsyncSession,
    order: models.PayOrder,
    *,
    amount_cents: int,
    reason: str = "",
    operator_id: int | None = None,
) -> models.PayRefund:
    if order.status not in SETTLED_STATES:
        raise PayError("只有已支付的订单才能退款", code="not_paid")
    refundable = order.amount_cents - (order.refunded_cents or 0)
    if amount_cents <= 0 or amount_cents > refundable:
        raise PayError(f"退款金额需在 1 ~ {refundable} 分之间", code="bad_amount")
    if not order.channel_id:
        raise PayError("订单未关联支付通道，无法退款", code="no_channel")

    cls = get_driver_class(order.provider)
    if not cls.supports_refund:
        raise PayError(f"{cls.display_name} 暂不支持在线退款", code="refund_unsupported")

    channel = await get_channel(
        db, order.scene_key, channel_id=order.channel_id, include_disabled=True,
    )
    driver = build_driver(channel)

    refund = models.PayRefund(
        out_refund_no=gen_out_refund_no(),
        order_id=order.id,
        out_trade_no=order.out_trade_no,
        scene_key=order.scene_key,
        channel_id=order.channel_id,
        provider=order.provider,
        amount_cents=amount_cents,
        reason=reason[:256] if reason else None,
        status=PENDING,
        operator_id=operator_id,
    )
    db.add(refund)
    await db.commit()
    await db.refresh(refund)

    try:
        res = await driver.refund(
            order.out_trade_no, amount_cents, refund.out_refund_no,
            reason=reason, total_cents=order.amount_cents,
        )
    except PayError as exc:
        refund.status = FAILED
        refund.error = exc.detail or exc.message
        await db.commit()
        raise
    except Exception as exc:  # noqa: BLE001
        refund.status = FAILED
        refund.error = str(exc)
        await db.commit()
        raise PayError("退款请求失败", detail=str(exc), code="refund_failed") from exc

    refund.raw = res.get("raw")
    refund.refund_trade_no = res.get("refund_trade_no") or None
    if res.get("ok"):
        refund.status = "success"
        refund.refunded_at = _now()
        order.refunded_cents = (order.refunded_cents or 0) + amount_cents
        order.status = REFUNDED if order.refunded_cents >= order.amount_cents else PARTIAL_REFUNDED
    else:
        refund.status = FAILED
        refund.error = res.get("message") or "退款失败"
    await db.commit()
    await db.refresh(refund)

    if refund.status == "success":
        log.info("payment.refunded", scene=order.scene_key, out_trade_no=order.out_trade_no,
                 amount_cents=amount_cents)
        try:
            await dispatch(
                "payment.refunded",
                scene_key=order.scene_key,
                out_trade_no=order.out_trade_no,
                amount_cents=amount_cents,
                refund_no=refund.out_refund_no,
                biz_type=order.biz_type or "",
                biz_id=order.biz_id or "",
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("payment.refund_hook_failed", error=str(exc))

    return refund


async def close_order(db: AsyncSession, order: models.PayOrder) -> models.PayOrder:
    if order.status != PENDING:
        raise PayError("只有待支付订单可以关闭", code="bad_status")
    order.status = CLOSED
    order.closed_at = _now()
    await db.commit()
    await db.refresh(order)
    return order


async def stats(db: AsyncSession, scene_key: str | None = None) -> dict[str, Any]:
    """概览统计：各状态订单数与金额、今日成交、通道分布。"""
    base = select(models.PayOrder)
    if scene_key:
        base = base.where(models.PayOrder.scene_key == scene_key)
    sub = base.subquery()

    rows = (await db.execute(
        select(sub.c.status, func.count(), func.coalesce(func.sum(sub.c.amount_cents), 0))
        .group_by(sub.c.status)
    )).all()

    by_status: dict[str, dict[str, int]] = {}
    total_count = 0
    paid_count = 0
    paid_amount = 0
    for status, cnt, amount in rows:
        by_status[status] = {"count": int(cnt), "amount_cents": int(amount or 0)}
        total_count += int(cnt)
        if status in SETTLED_STATES:
            paid_count += int(cnt)
            paid_amount += int(amount or 0)

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_stmt = select(
        func.count(), func.coalesce(func.sum(models.PayOrder.amount_cents), 0),
    ).where(
        models.PayOrder.status.in_(SETTLED_STATES),
        models.PayOrder.paid_at >= today_start,
    )
    if scene_key:
        today_stmt = today_stmt.where(models.PayOrder.scene_key == scene_key)
    today = (await db.execute(today_stmt)).one()

    channels = (await db.execute(
        select(
            models.PayOrder.scene_key,
            models.PayOrder.provider,
            func.count(),
            func.coalesce(func.sum(models.PayOrder.amount_cents), 0),
        )
        .where(models.PayOrder.status.in_(SETTLED_STATES))
        .group_by(models.PayOrder.scene_key, models.PayOrder.provider)
    )).all()

    return {
        "scene_key": scene_key or "",
        "total_count": total_count,
        "paid_count": paid_count,
        "paid_amount_cents": paid_amount,
        "by_status": by_status,
        "today": {"count": int(today[0] or 0), "amount_cents": int(today[1] or 0)},
        "by_channel": [
            {"scene_key": s, "provider": p, "count": int(c), "amount_cents": int(a or 0)}
            for s, p, c, a in channels
        ],
    }
