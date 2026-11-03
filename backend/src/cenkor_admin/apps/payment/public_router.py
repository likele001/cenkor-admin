"""支付公开路由：第三方异步回调 + 同步跳转 + 收银台 + 状态轮询。

挂载在 /api/v1/public/payment（见 api/v1/__init__.py）。
本模块所有接口**不校验登录态** —— 回调来自第三方，收银台面向付款人。
安全边界：
- 回调一律走驱动验签，验签失败只落日志不改状态
- 收银台/状态查询只暴露单笔订单的非敏感字段
"""
from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.payment import models, service
from cenkor_admin.apps.payment.cashier import render_cashier
from cenkor_admin.core.db import get_db

log = structlog.get_logger()
router = APIRouter()

PAID_STATES = service.SETTLED_STATES

# 收银台二维码生成库：自托管在应用目录里，不依赖第三方 CDN
# （支付页一旦依赖外网，随时可能因 CDN 不可达而渲染不出二维码）。
_QR_LIB = Path(__file__).resolve().parent / "static" / "qrcode.min.js"


async def _load_channel(
    db: AsyncSession, scene_key: str, channel_id: int,
) -> models.PayChannel:
    ch = await db.get(models.PayChannel, channel_id)
    if ch is None or ch.deleted_at is not None or ch.scene_key != scene_key:
        raise HTTPException(404, "支付通道不存在")
    return ch


@router.post("/notify/{scene_key}/{channel_id}")
async def payment_notify(
    scene_key: str,
    channel_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """第三方异步回调入口。"""
    channel = await _load_channel(db, scene_key, channel_id)
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    client_ip = request.client.host if request.client else ""

    result = await service.handle_notify(
        db, channel, headers, body, client_ip=client_ip,
    )
    reply = result.reply or "failure"
    media = result.content_type or "text/plain"
    log.info(
        "payment.notify_received", scene=scene_key, provider=channel.provider,
        out_trade_no=result.out_trade_no, ok=result.ok, paid=result.paid,
    )
    return PlainTextResponse(reply, media_type=media)


@router.api_route("/return/{scene_key}/{channel_id}", methods=["GET", "POST"])
async def payment_return(
    scene_key: str,
    channel_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """第三方同步回跳：统一收口，再转回订单自己的 return_url 或收银台。"""
    await _load_channel(db, scene_key, channel_id)
    params = dict(request.query_params)
    if request.method == "POST":
        try:
            form = await request.form()
            params.update({k: str(v) for k, v in form.items()})
        except Exception:
            pass

    out_trade_no = (
        params.get("out_trade_no")
        or params.get("trade_order_id")
        or params.get("out_trade_order")
        or ""
    )
    if not out_trade_no:
        return HTMLResponse(
            "<meta charset='utf-8'><p style='font-family:sans-serif;padding:40px'>"
            "支付流程已结束，可关闭本页。</p>"
        )

    order = (await db.execute(
        select(models.PayOrder).where(models.PayOrder.out_trade_no == out_trade_no)
    )).scalars().first()
    if order is None:
        raise HTTPException(404, "订单不存在")

    # 顺手同步一次，避免同步回跳早于异步通知
    try:
        if order.status == "pending":
            await service.sync_order(db, order)
            await db.refresh(order)
    except Exception as exc:
        log.warning("payment.return_sync_failed", out_trade_no=out_trade_no, error=str(exc))

    target = order.return_url or f"/api/v1/public/payment/cashier/{out_trade_no}"
    return RedirectResponse(target, status_code=302)


@router.get("/assets/qrcode.min.js")
async def cashier_qr_lib():
    """收银台用的二维码生成库（qrcode-generator v1.4.4，MIT，文件头有出处）。"""
    if not _QR_LIB.is_file():
        raise HTTPException(404, "二维码组件缺失")
    return FileResponse(
        _QR_LIB, media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@router.get("/cashier/{out_trade_no}", response_class=HTMLResponse)
async def cashier(
    out_trade_no: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """收银台页面。"""
    order = (await db.execute(
        select(models.PayOrder).where(models.PayOrder.out_trade_no == out_trade_no)
    )).scalars().first()
    if order is None:
        raise HTTPException(404, "订单不存在")
    in_wechat = service.detect_terminal(request.headers.get("user-agent")) == "wechat"
    return HTMLResponse(render_cashier(order, scene_name=order.scene_key, in_wechat=in_wechat))


@router.get("/status/{out_trade_no}")
async def order_status(
    out_trade_no: str,
    db: AsyncSession = Depends(get_db),
):
    """收银台轮询用：只暴露非敏感字段。"""
    order = (await db.execute(
        select(models.PayOrder).where(models.PayOrder.out_trade_no == out_trade_no)
    )).scalars().first()
    if order is None:
        raise HTTPException(404, "订单不存在")
    return {
        "out_trade_no": order.out_trade_no,
        "status": order.status,
        "paid": order.status in PAID_STATES,
        "amount_cents": order.amount_cents,
        "subject": order.subject,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
    }
