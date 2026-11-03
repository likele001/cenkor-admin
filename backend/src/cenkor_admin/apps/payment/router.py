"""支付中心管理接口。

挂在 /api/v1/payment（由 api/v1/__init__.py 的应用路由自动发现挂载）。
免登录回调与收银台在 public_router.py。
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.payment import models, service
from cenkor_admin.apps.payment.crypto import encrypt_value, mask_config
from cenkor_admin.apps.payment.drivers import (
    PayError,
    get_driver_class,
    list_providers,
)
from cenkor_admin.core.db import get_db

log = structlog.get_logger()
router = APIRouter()


# ---------- 工具 ----------

def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


async def _setting(db: AsyncSession, key: str) -> str:
    """读 system_settings（该表 value 为 jsonb，走原生 SQL 避开 ORM 类型不匹配）。"""
    try:
        raw = (await db.execute(
            text("select value from system_settings where key = :k"), {"k": key}
        )).scalar()
    except Exception:
        return ""
    if raw is None:
        return ""
    if isinstance(raw, str):
        try:
            return str(json.loads(raw))
        except Exception:
            return raw
    return str(raw)


async def _base_url(request: Request, db: AsyncSession) -> str:
    configured = await _setting(db, "payment.base_url")
    if configured:
        return configured.rstrip("/")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def _channel_out(ch: models.PayChannel) -> dict[str, Any]:
    try:
        cls = get_driver_class(ch.provider)
        provider_name = cls.display_name
        secret_fields = cls.secret_fields()
    except PayError:
        provider_name = ch.provider
        secret_fields = ()
    return {
        "id": ch.id,
        "scene_key": ch.scene_key,
        "provider": ch.provider,
        "provider_name": provider_name,
        "sub_type": ch.sub_type,
        "title": ch.title,
        "mode": ch.mode,
        "config": mask_config(dict(ch.config or {}), secret_fields),
        "enabled": ch.enabled,
        "is_default": ch.is_default,
        "sort": ch.sort,
        "remark": ch.remark,
        "created_at": _iso(ch.created_at),
        "updated_at": _iso(ch.updated_at),
    }


def _order_out(o: models.PayOrder, *, with_payload: bool = False) -> dict[str, Any]:
    out = {
        "id": o.id,
        "out_trade_no": o.out_trade_no,
        "scene_key": o.scene_key,
        "channel_id": o.channel_id,
        "provider": o.provider,
        "sub_type": o.sub_type,
        "subject": o.subject,
        "description": o.description,
        "amount_cents": o.amount_cents,
        "amount": f"{o.amount_cents / 100:.2f}",
        "refunded_cents": o.refunded_cents or 0,
        "currency": o.currency,
        "status": o.status,
        "pay_mode": o.pay_mode,
        "trade_no": o.trade_no,
        "biz_type": o.biz_type,
        "biz_id": o.biz_id,
        "client_ip": o.client_ip,
        "return_url": o.return_url,
        "paid_at": _iso(o.paid_at),
        "closed_at": _iso(o.closed_at),
        "expire_at": _iso(o.expire_at),
        "notify_count": o.notify_count,
        "last_notify_at": _iso(o.last_notify_at),
        "created_at": _iso(o.created_at),
        "updated_at": _iso(o.updated_at),
        # 管理台据此决定「删除 / 作废」按钮哪个能点
        "archived_at": _archived_at(o),
        "deletable": (o.status or "") in DELETABLE_STATUSES,
    }
    if with_payload:
        out["pay_payload"] = o.pay_payload or {}
        out["extra"] = o.extra or {}
    return out


def _refund_out(r: models.PayRefund) -> dict[str, Any]:
    return {
        "id": r.id,
        "out_refund_no": r.out_refund_no,
        "order_id": r.order_id,
        "out_trade_no": r.out_trade_no,
        "scene_key": r.scene_key,
        "provider": r.provider,
        "amount_cents": r.amount_cents,
        "amount": f"{r.amount_cents / 100:.2f}",
        "reason": r.reason,
        "status": r.status,
        "refund_trade_no": r.refund_trade_no,
        "error": r.error,
        "operator_id": r.operator_id,
        "refunded_at": _iso(r.refunded_at),
        "created_at": _iso(r.created_at),
    }


def _bad(exc: PayError, code: int = 400) -> HTTPException:
    return HTTPException(code, exc.message)


# 「删除」的分层判据：只有从未收到钱的单子才允许抹掉痕迹。
# 已支付 / 已退款 / 部分退款牵涉资金、对账与第三方交易号，只能作废隐藏（软删除），
# 真删会让账单与网关记录断链，事后无法自证清白。
DELETABLE_STATUSES = {"pending", "closed", "failed"}
_STATUS_CN = {
    "pending": "待支付", "paid": "已支付", "closed": "已关闭",
    "failed": "失败", "refunded": "已退款", "partial_refunded": "部分退款",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _archived_at(o: models.PayOrder) -> str | None:
    return str((o.extra or {}).get("archived_at") or "") or None


def _set_archived(o: models.PayOrder, operator_id: int | None, reason: str) -> None:
    """作废隐藏（软删除）：写进 extra，状态字段不动 —— 统计口径不受影响。"""
    extra = dict(o.extra or {})
    extra.update({
        "archived_at": _iso(_now()),
        "archived_by": operator_id,
        "archive_reason": (reason or "未填写")[:200],
    })
    o.extra = extra  # JSON 列要整体替换才会被标记为脏


def _clear_archived(o: models.PayOrder) -> None:
    extra = dict(o.extra or {})
    for k in ("archived_at", "archived_by", "archive_reason"):
        extra.pop(k, None)
    o.extra = extra


# ---------- 元数据 ----------

@router.get("/providers")
async def list_payment_providers(
    _: auth_models.User = Depends(require_permission("payment:read")),
):
    """可用通道驱动及其表单字段声明（前端渲染新增/编辑表单用）。"""
    return {"items": list_providers()}


@router.get("/scenes")
async def list_scenes(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("payment:read")),
):
    """可作为 scene 的业务应用清单（每个应用一套独立的支付配置）。"""
    scenes: dict[str, dict[str, Any]] = {}
    try:
        rows = (await db.execute(text(
            "select key, name from platform_apps where status = 'installed' order by key"
        ))).all()
        for key, name in rows:
            scenes[key] = {"scene_key": key, "name": name or key, "source": "app"}
    except Exception as exc:
        log.warning("payment.scene_query_failed", error=str(exc))

    keys = (await db.execute(
        select(models.PayChannel.scene_key).where(models.PayChannel.deleted_at.is_(None)).distinct()
    )).scalars().all()
    for key in keys:
        scenes.setdefault(key, {"scene_key": key, "name": key, "source": "channel"})

    # 应用中心（commerce）无 manifest、不在 platform_apps 里，固定补一个内置项，
    # 否则配置通道时下拉看不到它，只能手打 app_store。
    scenes.setdefault("app_store", {"scene_key": "app_store", "name": "应用中心", "source": "builtin"})
    scenes.setdefault("default", {"scene_key": "default", "name": "默认场景", "source": "builtin"})
    return {"items": sorted(scenes.values(), key=lambda x: x["scene_key"])}


# ---------- 通道配置 ----------

@router.get("/channels")
async def list_channels(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("payment:read")),
    scene_key: str | None = None,
    provider: str | None = None,
):
    stmt = select(models.PayChannel).where(models.PayChannel.deleted_at.is_(None))
    if scene_key:
        stmt = stmt.where(models.PayChannel.scene_key == scene_key)
    if provider:
        stmt = stmt.where(models.PayChannel.provider == provider)
    stmt = stmt.order_by(
        models.PayChannel.scene_key.asc(),
        models.PayChannel.sort.asc(),
        models.PayChannel.id.asc(),
    )
    items = (await db.execute(stmt)).scalars().all()
    return {"items": [_channel_out(c) for c in items], "total": len(items)}


@router.get("/channels/{channel_id}")
async def get_channel_detail(
    channel_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("payment:read")),
):
    ch = await db.get(models.PayChannel, channel_id)
    if ch is None or ch.deleted_at is not None:
        raise HTTPException(404, "通道不存在")
    return _channel_out(ch)


def _merge_config(
    cls, old: dict, incoming: dict, *, is_update: bool,
) -> tuple[dict, list[str]]:
    """合并配置：脱敏占位保留旧值，其余加密存储。返回 (config, 缺失字段)。"""
    merged: dict[str, Any] = {} if not is_update else dict(old or {})
    missing: list[str] = []
    for f in cls.config_fields:
        key = f["key"]
        if key not in incoming:
            if not is_update and f.get("required") and not merged.get(key):
                missing.append(f["label"])
            continue
        raw = incoming.get(key)
        if f.get("secret"):
            text_val = "" if raw is None else str(raw)
            if not text_val or "****" in text_val:
                continue  # 保持旧密文不动
            merged[key] = encrypt_value(text_val)
        else:
            merged[key] = raw
    if not is_update:
        for f in cls.config_fields:
            if (
                f.get("required")
                and not merged.get(f["key"])
                and f["label"] not in missing
            ):
                missing.append(f["label"])
    return merged, missing


async def _clear_other_defaults(db: AsyncSession, scene_key: str, keep_id: int | None):
    stmt = select(models.PayChannel).where(
        models.PayChannel.scene_key == scene_key,
        models.PayChannel.is_default.is_(True),
        models.PayChannel.deleted_at.is_(None),
    )
    if keep_id:
        stmt = stmt.where(models.PayChannel.id != keep_id)
    for row in (await db.execute(stmt)).scalars().all():
        row.is_default = False


@router.post("/channels", status_code=201)
async def create_channel(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("payment:write")),
):
    provider = (body.get("provider") or "").strip()
    if not provider:
        raise HTTPException(400, "provider 必填")
    try:
        cls = get_driver_class(provider)
    except PayError as exc:
        raise _bad(exc) from exc

    sub_type = (body.get("sub_type") or "").strip()
    if cls.sub_types and not sub_type:
        sub_type = cls.sub_types[0][0]
    if cls.sub_types and sub_type not in [v for v, _ in cls.sub_types]:
        raise HTTPException(400, f"sub_type 需为 {[v for v, _ in cls.sub_types]}")

    scene_key = (body.get("scene_key") or "default").strip() or "default"
    config, missing = _merge_config(cls, {}, body.get("config") or {}, is_update=False)
    if missing:
        raise HTTPException(400, f"缺少必填配置：{'、'.join(missing)}")

    ch = models.PayChannel(
        scene_key=scene_key,
        provider=provider,
        sub_type=sub_type,
        title=(body.get("title") or cls.display_name)[:100],
        mode=(body.get("mode") or "live"),
        config=config,
        enabled=bool(body.get("enabled", True)),
        is_default=bool(body.get("is_default", False)),
        sort=int(body.get("sort") or 0),
        remark=body.get("remark"),
    )
    db.add(ch)
    await db.commit()
    await db.refresh(ch)
    if ch.is_default:
        await _clear_other_defaults(db, scene_key, ch.id)
        await db.commit()

    log.info("payment.channel_created", scene=scene_key, provider=provider,
              channel_id=ch.id, by=current.id)
    return _channel_out(ch)


@router.put("/channels/{channel_id}")
async def update_channel(
    channel_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("payment:write")),
):
    ch = await db.get(models.PayChannel, channel_id)
    if ch is None or ch.deleted_at is not None:
        raise HTTPException(404, "通道不存在")
    try:
        cls = get_driver_class(ch.provider)
    except PayError as exc:
        raise _bad(exc) from exc

    if "sub_type" in body and cls.sub_types:
        sub_type = (body.get("sub_type") or "").strip()
        if sub_type not in [v for v, _ in cls.sub_types]:
            raise HTTPException(400, f"sub_type 需为 {[v for v, _ in cls.sub_types]}")
        ch.sub_type = sub_type

    if "config" in body:
        merged, _ = _merge_config(cls, dict(ch.config or {}), body.get("config") or {}, is_update=True)
        ch.config = merged
    if "title" in body:
        ch.title = (body.get("title") or ch.title)[:100]
    if "mode" in body:
        ch.mode = body.get("mode") or ch.mode
    if "enabled" in body:
        ch.enabled = bool(body.get("enabled"))
    if "sort" in body:
        ch.sort = int(body.get("sort") or 0)
    if "remark" in body:
        ch.remark = body.get("remark")
    if "scene_key" in body and (body.get("scene_key") or "").strip():
        ch.scene_key = body["scene_key"].strip()
    if "is_default" in body:
        ch.is_default = bool(body.get("is_default"))

    await db.commit()
    await db.refresh(ch)
    if ch.is_default:
        await _clear_other_defaults(db, ch.scene_key, ch.id)
        await db.commit()

    log.info("payment.channel_updated", channel_id=ch.id, by=current.id)
    return _channel_out(ch)


@router.delete("/channels/{channel_id}")
async def delete_channel(
    channel_id: int,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("payment:write")),
):
    ch = await db.get(models.PayChannel, channel_id)
    if ch is None or ch.deleted_at is not None:
        raise HTTPException(404, "通道不存在")
    ch.deleted_at = datetime.now(UTC)
    ch.enabled = False
    await db.commit()
    log.info("payment.channel_deleted", channel_id=channel_id, by=current.id)
    return {"ok": True}


@router.post("/channels/{channel_id}/test")
async def test_channel(
    channel_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("payment:write")),
):
    """连通性与签名自检：拿一个不存在的单号去查，能拿到第三方业务响应即算通。"""
    ch = await db.get(models.PayChannel, channel_id)
    if ch is None or ch.deleted_at is not None:
        raise HTTPException(404, "通道不存在")
    driver = service.build_driver(ch)
    probe = f"CKPROBE{datetime.now().strftime('%Y%m%d%H%M%S')}"
    try:
        info = await driver.query(probe)
    except PayError as exc:
        return {"ok": False, "message": exc.message, "detail": exc.detail}
    except Exception as exc:
        return {"ok": False, "message": "自检失败", "detail": str(exc)}

    return {
        "ok": True,
        "message": "配置可用（签名与网络均正常）",
        "detail": f"探测单号 {probe} 返回：{info.get('status') or info.get('message') or '无业务数据'}",
        "raw": info.get("raw") or {},
    }


# ---------- 订单 ----------

@router.post("/orders", status_code=201)
async def create_order(
    body: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("payment:write")),
):
    """手工建单（联调用）。业务系统集成请走 service.create_order 或开放接口。"""
    try:
        amount_cents = int(body.get("amount_cents") or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "amount_cents 需为整数（分）") from exc

    base = await _base_url(request, db)
    # 终端选路：PC -> 扫码通道，手机/微信 -> 跳转通道。
    # 调用方可在 body 里传 terminal 覆盖（联调用），显式 channel_id 优先级更高。
    terminal = (body.get("terminal") or "").strip().lower() or service.detect_terminal(
        request.headers.get("user-agent")
    )
    try:
        order, result = await service.create_order(
            db,
            scene_key=(body.get("scene_key") or "default").strip() or "default",
            amount_cents=amount_cents,
            subject=body.get("subject") or "测试订单",
            base_url=base,
            provider=body.get("provider"),
            sub_type=body.get("sub_type"),
            channel_id=body.get("channel_id"),
            terminal=terminal,
            description=body.get("description") or "",
            client_ip=request.client.host if request.client else "",
            return_url=body.get("return_url") or "",
            biz_type=body.get("biz_type") or "",
            biz_id=body.get("biz_id") or "",
            extra=body.get("extra") or {},
            creator_id=current.id,
        )
    except PayError as exc:
        raise _bad(exc) from exc

    out = _order_out(order, with_payload=True)
    out["pay_result"] = {"mode": result.mode, "payload": result.payload}
    out["cashier_url"] = f"{base}/api/v1/public/payment/cashier/{order.out_trade_no}"
    return out


@router.get("/orders")
async def list_orders(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("payment:read")),
    scene_key: str | None = None,
    status: str | None = None,
    provider: str | None = None,
    keyword: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    include_archived: bool = Query(False, description="含已作废的单"),
    archived_only: bool = Query(False, description="只看已作废的单"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    conds = []
    if scene_key:
        conds.append(models.PayOrder.scene_key == scene_key)
    if status:
        conds.append(models.PayOrder.status == status)
    if provider:
        conds.append(models.PayOrder.provider == provider)
    if keyword:
        like = f"%{keyword.strip()}%"
        conds.append(or_(
            models.PayOrder.out_trade_no.ilike(like),
            models.PayOrder.trade_no.ilike(like),
            models.PayOrder.subject.ilike(like),
            models.PayOrder.biz_id.ilike(like),
        ))
    if date_from:
        conds.append(models.PayOrder.created_at >= date_from)
    if date_to:
        conds.append(models.PayOrder.created_at <= date_to)
    # 作废的单默认从列表里消失（免得管理台被垃圾单刷满），勾上才显示
    archived = models.PayOrder.extra["archived_at"].astext
    if archived_only:
        conds.append(archived.isnot(None))
    elif not include_archived:
        conds.append(archived.is_(None))

    total = (await db.execute(
        select(func.count()).select_from(models.PayOrder).where(*conds)
    )).scalar() or 0
    stmt = select(models.PayOrder).where(*conds).order_by(models.PayOrder.id.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return {
        "items": [_order_out(o) for o in items],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


async def _get_order(db: AsyncSession, out_trade_no: str) -> models.PayOrder:
    order = (await db.execute(
        select(models.PayOrder).where(models.PayOrder.out_trade_no == out_trade_no)
    )).scalars().first()
    if order is None:
        raise HTTPException(404, "订单不存在")
    return order


@router.get("/orders/{out_trade_no}")
async def get_order(
    out_trade_no: str,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("payment:read")),
):
    order = await _get_order(db, out_trade_no)
    out = _order_out(order, with_payload=True)
    refunds = (await db.execute(
        select(models.PayRefund).where(models.PayRefund.order_id == order.id)
        .order_by(models.PayRefund.id.desc())
    )).scalars().all()
    logs = (await db.execute(
        select(models.PayNotifyLog).where(models.PayNotifyLog.out_trade_no == out_trade_no)
        .order_by(models.PayNotifyLog.id.desc()).limit(20)
    )).scalars().all()
    out["refunds"] = [_refund_out(r) for r in refunds]
    out["notify_logs"] = [
        {
            "id": lg.id,
            "direction": lg.direction,
            "provider": lg.provider,
            "verified": lg.verified,
            "processed": lg.processed,
            "error": lg.error,
            "created_at": _iso(lg.created_at),
        }
        for lg in logs
    ]
    return out


@router.post("/orders/{out_trade_no}/sync")
async def sync_order(
    out_trade_no: str,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("payment:write")),
):
    order = await _get_order(db, out_trade_no)
    try:
        info = await service.sync_order(db, order)
    except PayError as exc:
        raise _bad(exc) from exc
    await db.refresh(order)
    return {"order": _order_out(order), "gateway": info}


@router.post("/orders/{out_trade_no}/close")
async def close_order(
    out_trade_no: str,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("payment:write")),
):
    order = await _get_order(db, out_trade_no)
    try:
        order = await service.close_order(db, order)
    except PayError as exc:
        raise _bad(exc) from exc
    return _order_out(order)


@router.post("/orders/{out_trade_no}/archive")
async def archive_order(
    out_trade_no: str,
    body: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("payment:write")),
):
    """作废隐藏（软删除）：任何状态都能用，不碰资金状态，只把它从列表里拿掉。"""
    order = await _get_order(db, out_trade_no)
    _set_archived(order, current.id, str(body.get("reason") or ""))
    await db.commit()
    await db.refresh(order)  # updated_at 是服务端生成的，不刷新会在序列化时踩到懒加载
    log.info("payment.order_archived", out_trade_no=out_trade_no, by=current.id)
    return _order_out(order)


@router.post("/orders/{out_trade_no}/unarchive")
async def unarchive_order(
    out_trade_no: str,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("payment:write")),
):
    order = await _get_order(db, out_trade_no)
    if _archived_at(order) is None:
        raise HTTPException(400, "该订单未作废")
    _clear_archived(order)
    await db.commit()
    await db.refresh(order)
    log.info("payment.order_unarchived", out_trade_no=out_trade_no, by=current.id)
    return _order_out(order)


@router.delete("/orders/{out_trade_no}")
async def delete_order(
    out_trade_no: str,
    body: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("payment:write")),
):
    """物理删除支付单：只允许从未收到钱的（待支付 / 已关闭 / 失败）。

    回调日志（pay_notify_logs）按单号关联且不阻断删除，故保留 —— 真出了
    「单已删但钱到账」的纠纷，日志就是唯一证据。
    """
    order = await _get_order(db, out_trade_no)
    if order.status not in DELETABLE_STATUSES:
        raise HTTPException(
            400,
            f"{_STATUS_CN.get(order.status, order.status)}的订单不能删除（已有资金记录），"
            "请改用作废或在通道里退款",
        )
    if not body.get("force") and order.status == service.PENDING and (
        order.expire_at is None or order.expire_at > _now()
    ):
        raise HTTPException(400, "该单还在有效期内，买家仍可能完成支付；请先关闭，或确认强删（force=true）")

    no = order.out_trade_no
    status, amount_cents = order.status, order.amount_cents  # 删完再读会踩已删除实例的懒加载
    await db.delete(order)
    await db.commit()
    log.warning("payment.order_deleted", out_trade_no=no, amount_cents=amount_cents,
                status=status, force=bool(body.get("force")), by=current.id)
    return {"ok": True, "out_trade_no": no}


@router.post("/orders/cleanup")
async def cleanup_orders(
    body: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("payment:write")),
):
    """批量清理垃圾支付单（反复点结算留下的过期未付残单）。

    默认 ``dry_run=true``：只报命中多少条、不动数据。一次最多处理 500 条，
    剩下的翻页再来 —— 宁可让操作员多点几次，也不要一键抹掉全库。
    """
    statuses = [str(s) for s in (body.get("statuses") or ["pending", "closed", "failed"])]
    if not statuses:
        raise HTTPException(400, "statuses 不能为空")
    risky = [s for s in statuses if s not in DELETABLE_STATUSES]
    if risky:
        raise HTTPException(400, f"状态 {'、'.join(_STATUS_CN.get(s, s) for s in risky)} 涉及资金，不允许清理")

    mode = str(body.get("mode") or "archive")
    if mode not in ("archive", "delete"):
        raise HTTPException(400, "mode 只能是 archive（作废隐藏）或 delete（真删）")
    try:
        minutes = int(body.get("older_than_minutes") or 1440)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "older_than_minutes 需为整数（分钟）") from exc
    if minutes < 0:
        raise HTTPException(400, "older_than_minutes 不能为负")
    dry_run = bool(body.get("dry_run", True))

    cutoff = _now() - timedelta(minutes=minutes)
    conds = [
        models.PayOrder.status.in_(statuses),
        models.PayOrder.created_at <= cutoff,
        models.PayOrder.extra["archived_at"].astext.is_(None),
    ]
    matched = (await db.execute(
        select(func.count()).select_from(models.PayOrder).where(*conds)
    )).scalar() or 0
    rows = (await db.execute(
        select(models.PayOrder).where(*conds).order_by(models.PayOrder.id.desc()).limit(500)
    )).scalars().all()

    sample = [{
        "out_trade_no": o.out_trade_no, "status": o.status,
        "amount_cents": o.amount_cents, "subject": o.subject,
        "created_at": _iso(o.created_at), "biz_id": o.biz_id,
    } for o in rows[:20]]
    if dry_run:
        return {"dry_run": True, "mode": mode, "matched": int(matched),
                "will_process": len(rows), "cutoff": _iso(cutoff), "sample": sample}

    reason = f"批量清理：早于 {cutoff.strftime('%Y-%m-%d %H:%M')}，状态 {'/'.join(statuses)}"
    done = 0
    for o in rows:
        # 待支付且在有效期内的不碰：删了它可能把刚扫出去的单弄成孤儿
        if o.status == service.PENDING and (o.expire_at is None or o.expire_at > _now()):
            continue
        if mode == "delete":
            await db.delete(o)
        else:
            _set_archived(o, current.id, reason)
        done += 1
    await db.commit()
    log.warning("payment.orders_cleanup", mode=mode, processed=done, matched=int(matched),
                cutoff=_iso(cutoff), by=current.id)
    return {"dry_run": False, "mode": mode, "matched": int(matched), "processed": done,
            "skipped": len(rows) - done, "cutoff": _iso(cutoff)}


@router.post("/orders/{out_trade_no}/refund")
async def refund_order(
    out_trade_no: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("payment:write")),
):
    order = await _get_order(db, out_trade_no)
    amount = body.get("amount_cents")
    if amount in (None, ""):
        amount = order.amount_cents - (order.refunded_cents or 0)
    try:
        amount_cents = int(amount)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "amount_cents 需为整数（分）") from exc

    try:
        refund = await service.refund_order(
            db, order, amount_cents=amount_cents,
            reason=body.get("reason") or "", operator_id=current.id,
        )
    except PayError as exc:
        raise _bad(exc) from exc
    if refund.status != "success":
        raise HTTPException(400, refund.error or "退款失败")
    return _refund_out(refund)


@router.get("/refunds")
async def list_refunds(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("payment:read")),
    scene_key: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    conds = []
    if scene_key:
        conds.append(models.PayRefund.scene_key == scene_key)
    if status:
        conds.append(models.PayRefund.status == status)
    total = (await db.execute(
        select(func.count()).select_from(models.PayRefund).where(*conds)
    )).scalar() or 0
    stmt = select(models.PayRefund).where(*conds).order_by(models.PayRefund.id.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return {
        "items": [_refund_out(r) for r in items],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


@router.get("/notify-logs")
async def list_notify_logs(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("payment:read")),
    scene_key: str | None = None,
    out_trade_no: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    conds = []
    if scene_key:
        conds.append(models.PayNotifyLog.scene_key == scene_key)
    if out_trade_no:
        conds.append(models.PayNotifyLog.out_trade_no == out_trade_no)
    total = (await db.execute(
        select(func.count()).select_from(models.PayNotifyLog).where(*conds)
    )).scalar() or 0
    stmt = select(models.PayNotifyLog).where(*conds).order_by(models.PayNotifyLog.id.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return {
        "items": [
            {
                "id": lg.id,
                "scene_key": lg.scene_key,
                "provider": lg.provider,
                "direction": lg.direction,
                "out_trade_no": lg.out_trade_no,
                "verified": lg.verified,
                "processed": lg.processed,
                "error": lg.error,
                "created_at": _iso(lg.created_at),
            }
            for lg in items
        ],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


@router.get("/stats")
async def payment_stats(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("payment:read")),
    scene_key: str | None = None,
):
    return await service.stats(db, scene_key)
