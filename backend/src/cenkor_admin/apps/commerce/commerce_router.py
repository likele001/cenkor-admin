"""应用生态交易 API（P0）：定价 → 下单 → 支付 → 授权 → 激活/心跳 → 云端分发安装

挂在 `/api/v1/store` 下，与 store_router 共用前缀。

鉴权分三类：
1. 买家侧：`require_portal_or_admin`（portal 前台用户或后台用户）
2. 管理侧：`require_permission("rbac:role:write")`
3. 实例侧：免 token，用 `license_key` 自证（激活 / 心跳 / 下载包）

同一份代码在两种部署里跑：
- 授权中心（你的云，`CENKOR_CLOUD_URL` 留空）：签发授权、分发加密包
- 客户实例（`CENKOR_CLOUD_URL` 指向你的云）：激活、心跳、拉包安装
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.commerce import ledger
from cenkor_admin.apps.commerce import license_authority
from cenkor_admin.apps.commerce import models as cm
from cenkor_admin.apps.commerce import pricing
from cenkor_admin.apps.system import store_models
from cenkor_admin.apps.system.models import InstalledApp
from cenkor_admin.apps.system.store_router import require_portal_or_admin
from cenkor_admin.apps.system.versioning import ver_tuple
from cenkor_admin.core import licensing
from cenkor_admin.core.config import get_settings
from cenkor_admin.core.db import get_db

log = structlog.get_logger()
router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _resolve_product(db: AsyncSession, app_key: str, body_product: Any = None) -> str:
    """解析应用的权威 product（实现见 ``pricing.resolve_product``，与全部定价写入点共用）。

    门户下单 / 定价表单常不带 product，若直接走 ``cenkor-admin`` 默认值，会把
    扩展挂到错误的产品轴上：实例按自身 product 拉 ``my-purchases`` 时因
    ``AppLicense.product`` 不匹配而拿不到已购，功能市场永远显示「未持有授权」；
    同一根因还会让定价行定位不到、订单算成 0 元。
    """
    return await pricing.resolve_product(db, app_key, body_product)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


# 「删除」的分层判据，与支付中心 router 同一口径：
#   · 从未收到钱（待支付 / 已取消 / 已过期）且未签发授权 → 允许物理删
#   · 已支付 / 已退款 → 只能作废隐藏（钱、分账、授权都在以它们为凭据）
DELETABLE_STATUSES = {"pending", "cancelled", "expired"}
_STATUS_CN = {
    "pending": "待支付", "paid": "已支付", "cancelled": "已取消",
    "refunded": "已退款", "expired": "已过期",
}


def _archived_at(o: cm.AppOrder) -> str | None:
    return str((o.meta or {}).get("archived_at") or "") or None


def _set_archived(o: cm.AppOrder, operator_id: int | None, reason: str) -> None:
    """作废隐藏（软删除）：只往 meta 里记标记，``status`` 一律不动 —— 市场统计口径不受影响。"""
    meta = dict(o.meta or {})
    meta.update({
        "archived_at": _iso(_now()),
        "archived_by": operator_id,
        "archive_reason": (reason or "未填写")[:200],
    })
    o.meta = meta  # JSON 列要整体替换才会被标记为脏


def _clear_archived(o: cm.AppOrder) -> None:
    meta = dict(o.meta or {})
    for k in ("archived_at", "archived_by", "archive_reason"):
        meta.pop(k, None)
    o.meta = meta


# ============================================================
# 序列化
# ============================================================

def _pricing_dict(p: cm.AppPricing | None, app_key: str) -> dict[str, Any]:
    """定价视图（含原价 / 促销 / 生效价）。统一走 ``pricing.price_view()``。"""
    return pricing.price_view(p, app_key)


def _order_dict(o: cm.AppOrder) -> dict[str, Any]:
    list_cents = int(o.list_unit_price_cents or 0)
    unit = int(o.unit_price_cents or 0)
    percent = pricing.discount_percent(list_cents, unit)
    return {
        "id": o.id, "order_no": o.order_no, "app_key": o.app_key, "app_name": o.app_name,
        "buyer_id": o.buyer_id, "buyer_type": o.buyer_type, "buyer_email": o.buyer_email,
        "buyer_name": o.buyer_name, "model": o.model, "seats": o.seats,
        "unit_price_cents": o.unit_price_cents, "amount_cents": o.amount_cents,
        "amount": f"{o.amount_cents / 100:.2f}", "currency": o.currency,
        # 划线价快照（下单时定死）
        "list_unit_price_cents": list_cents,
        "list_unit_price": f"{list_cents / 100:.2f}",
        "list_amount_cents": list_cents * int(o.seats or 1),
        "is_discounted": percent is not None,
        "discount_percent": percent,
        "discount_label": pricing.discount_label(percent),
        "promo_label": o.promo_label,
        "status": o.status, "channel": o.channel, "trade_no": o.trade_no,
        "paid_at": _iso(o.paid_at), "refunded_at": _iso(o.refunded_at),
        "expires_at": _iso(o.expires_at), "remark": o.remark, "created_at": _iso(o.created_at),
        # 管理台据此决定「删除 / 作废」哪个按钮可点
        "archived_at": _archived_at(o),
        "deletable": (o.status or "") in DELETABLE_STATUSES,
    }


def _license_dict(l: cm.AppLicense, *, with_token: bool = False) -> dict[str, Any]:
    data = {
        "id": l.id, "license_key": l.license_key, "app_key": l.app_key, "app_name": l.app_name,
        "order_id": l.order_id, "buyer_id": l.buyer_id, "buyer_type": l.buyer_type,
        "model": l.model, "seats": l.seats, "status": l.status,
        "bound_domain": l.bound_domain, "instance_fp": l.instance_fp,
        "max_instances": l.max_instances, "max_rebind": l.max_rebind,
        "rebind_count": l.rebind_count, "issued_at": _iso(l.issued_at),
        "activated_at": _iso(l.activated_at), "expires_at": _iso(l.expires_at),
        "last_check_at": _iso(l.last_check_at), "revoked_at": _iso(l.revoked_at),
        "revoke_reason": l.revoke_reason, "notes": l.notes, "created_at": _iso(l.created_at),
    }
    if with_token:
        data["token"] = l.token
    return data


def _license_payload(lic: cm.AppLicense) -> dict[str, Any]:
    now = _now()
    return {
        "v": licensing.TOKEN_VERSION,
        "lic": lic.license_key,
        "app": lic.app_key,
        "sub": lic.buyer_id,
        "typ": lic.buyer_type,
        "seats": lic.seats,
        "model": lic.model,
        "dom": lic.bound_domain,
        "fp": lic.instance_fp,
        "iat": int(now.timestamp()),
        "exp": int(lic.expires_at.timestamp()) if lic.expires_at else None,
    }


async def _resign(db: AsyncSession, lic: cm.AppLicense) -> None:
    lic.token = await license_authority.sign_license_token(db, _license_payload(lic))
    lic.token_issued_at = _now()


# ============================================================
# 定价
# ============================================================

@router.get("/pricing", response_model=dict[str, Any])
async def list_pricing(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:read")),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    stmt = select(cm.AppPricing).order_by(cm.AppPricing.app_key)
    if q:
        stmt = stmt.where(cm.AppPricing.app_key.ilike(f"%{q}%"))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": [_pricing_dict(r, r.app_key) for r in rows], "total": total}


@router.put("/pricing/{app_key}", response_model=dict[str, Any])
async def upsert_pricing(
    app_key: str,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """设置/更新应用定价（含原价与限时促销）。model=free 时价格强制归零。

    扣点不可经此接口修改 —— 走 ``/market/pricing/{app_key}``。
    """
    product = await _resolve_product(db, app_key, body.get("product"))
    price_stmt = select(cm.AppPricing).where(cm.AppPricing.app_key == app_key)
    if product:
        price_stmt = price_stmt.where(cm.AppPricing.product == product)
    row = (await db.execute(price_stmt)).scalar_one_or_none()
    if not row:
        row = cm.AppPricing(app_key=app_key, product=product)
        db.add(row)

    try:
        pricing.apply_price_fields(row, body, touch_fee=False)
    except pricing.PriceRuleError as exc:
        raise HTTPException(400, str(exc)) from None

    await db.commit()
    # UPDATE 之后必须 refresh：``updated_at`` 由数据库生成（onupdate），改动后该属性会被
    # 标记为过期；若在异步上下文里同步访问它，会触发懒加载并抛 MissingGreenlet —— 而它
    # 被包成 BaseExceptionGroup，不是 Exception 子类，会绕过全局异常处理器直接 500。
    # market_router 的两个定价写入端（my_set_pricing / market_set_pricing）已有此步。
    await db.refresh(row)
    log.info("commerce.pricing_updated", app_key=app_key, model=row.model,
             price_cents=row.price_cents, promo_price_cents=row.promo_price_cents,
             by=user.id)
    return _pricing_dict(row, app_key)


@router.get("/apps/{app_key}/pricing", response_model=dict[str, Any])
async def public_app_pricing(app_key: str, db: AsyncSession = Depends(get_db), product: str | None = Query(None)):
    """公开定价（商店详情页展示）。

    不传 product 时回查提交记录拿权威轴 —— 与 ``create_order`` 定位定价行的口径一致。
    早先这里"不传就只按 app_key 查"，会让展示端读到别的轴上的价，出现
    「商店显示 ¥0.10、下单却按免费成交」的分裂。
    """
    axis = product or await pricing.resolve_product(db, app_key)
    row_stmt = select(cm.AppPricing).where(
        cm.AppPricing.app_key == app_key,
        cm.AppPricing.product == axis,
    )
    row = (await db.execute(row_stmt)).scalars().first()
    return _pricing_dict(row, app_key)


# ============================================================
# 订单
# ============================================================

@router.post("/orders", status_code=201, response_model=dict[str, Any])
async def create_order(
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    who: dict = Depends(require_portal_or_admin),
):
    """创建订单。免费应用（定价行 model=free）直接返回 0 元订单并即时签发授权。

    「没有定价行」不等于「免费」：定价行是 (product, app_key) 唯一的数据源，缺行
    只说明平台运营还没给这一轴配过价。把它当免费放行，等于任何一个未配价的 app_key
    都能被下 0 元单并拿到授权 —— 补上定价行是唯一出路，所以缺行即拒单，并留日志。
    """
    app_key = str(body.get("app_key") or "").strip()
    if not app_key:
        raise HTTPException(400, "app_key 必填")
    product = await _resolve_product(db, app_key, body.get("product"))

    price_stmt = select(cm.AppPricing).where(cm.AppPricing.app_key == app_key)
    if product:
        price_stmt = price_stmt.where(cm.AppPricing.product == product)
    price_row = (await db.execute(price_stmt)).scalar_one_or_none()
    if price_row is None:
        log.warning(
            "commerce.order_no_pricing_row",
            app_key=app_key, product=product, buyer=who["user_id"],
        )
        raise HTTPException(400, "该应用尚未配置定价，请联系平台运营确认后再下单")
    if not price_row.enabled:
        raise HTTPException(400, "该应用未上架销售")

    seats = max(int(body.get("seats") or 1), 1)
    if seats < price_row.min_seats:
        seats = price_row.min_seats
    if price_row.max_seats and seats > price_row.max_seats:
        raise HTTPException(400, f"坐席数不能超过 {price_row.max_seats}")

    inst = (await db.execute(
        select(InstalledApp).where(InstalledApp.key == app_key)
    )).scalar_one_or_none()
    app_name = inst.name if inst else app_key

    model = price_row.model
    # 成交单价走「生效价」：促销期内即促销价，到期自动回落售价
    unit = pricing.unit_price_cents(price_row, model)
    amount = unit * seats if model == "seat" else unit
    # 划线价与活动名快照（仅展示，不参与结算）
    list_unit = pricing.list_unit_price_cents(price_row, model)
    promo_label = (price_row.promo_label
                   if pricing.promo_active(price_row) else None)

    buyer = who["user"]
    email = getattr(buyer, "email", None)
    name = getattr(buyer, "nickname", None) or getattr(buyer, "username", None) or email

    # 分账快照：归属与扣点在下单这一刻定死，日后改定价/扣点都不影响本单
    dev_id = price_row.developer_id
    fee_bp = await ledger.resolve_fee_bp(db, price_row, dev_id)
    fee_cents, income_cents = ledger.split_amount(amount, fee_bp)

    order = cm.AppOrder(
        order_no=cm.generate_order_no(),
        app_key=app_key,
        product=product,
        app_name=app_name,
        buyer_id=who["user_id"],
        buyer_type=who["user_type"],
        buyer_email=email,
        buyer_name=name,
        model=model,
        seats=seats,
        unit_price_cents=unit,
        list_unit_price_cents=list_unit,
        promo_label=promo_label,
        amount_cents=amount,
        currency=price_row.currency,
        developer_id=dev_id,
        platform_fee_bp=fee_bp,
        platform_fee_cents=fee_cents,
        developer_income_cents=income_cents,
        status="pending",
        channel=str(body.get("channel") or "manual"),
        expires_at=_now() + timedelta(hours=72),
        remark=body.get("remark"),
    )
    db.add(order)
    await db.commit()

    # 0 元订单即时完成
    if amount <= 0:
        order.status = "paid"
        order.paid_at = _now()
        await db.commit()
        lic = await _issue_license(db, order)
        return {"order": _order_dict(order), "license": _license_dict(lic, with_token=True)}

    log.info("commerce.order_created", order=order.order_no, app=app_key, amount=amount)
    return {"order": _order_dict(order), "license": None}


@router.get("/orders", response_model=dict[str, Any])
async def list_orders(
    db: AsyncSession = Depends(get_db),
    who: dict = Depends(require_portal_or_admin),
    status: str | None = Query(None),
    keyword: str | None = Query(None, description="单号 / 应用 / 买家邮箱名称"),
    app_key: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    include_archived: bool = Query(False, description="含已作废的订单"),
    archived_only: bool = Query(False, description="只看已作废的订单"),
    scope: str | None = Query(None, description="admin 可用 mine 只看自己"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """买家看自己的订单；admin 用户默认看全量（可用 scope=mine 只看自己）。

    作废（软删除）的订单默认不出现，勾上 include_archived 才列出来。
    """
    stmt = select(cm.AppOrder).order_by(cm.AppOrder.id.desc())
    if who["user_type"] != "admin" or scope == "mine":
        stmt = stmt.where(
            cm.AppOrder.buyer_id == who["user_id"],
            cm.AppOrder.buyer_type == who["user_type"],
        )
    if status:
        stmt = stmt.where(cm.AppOrder.status == status)
    if app_key:
        stmt = stmt.where(cm.AppOrder.app_key == app_key)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(
            cm.AppOrder.order_no.ilike(like),
            cm.AppOrder.app_key.ilike(like),
            cm.AppOrder.app_name.ilike(like),
            cm.AppOrder.buyer_email.ilike(like),
            cm.AppOrder.buyer_name.ilike(like),
            cm.AppOrder.trade_no.ilike(like),
        ))
    if date_from:
        stmt = stmt.where(cm.AppOrder.created_at >= date_from)
    if date_to:
        stmt = stmt.where(cm.AppOrder.created_at <= date_to)
    archived = cm.AppOrder.meta["archived_at"].astext
    if archived_only:
        stmt = stmt.where(archived.isnot(None))
    elif not include_archived:
        stmt = stmt.where(archived.is_(None))

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {
        "items": [_order_dict(r) for r in rows], "total": total,
        "scope": "all" if who["user_type"] == "admin" and scope != "mine" else "mine",
        "page": page, "page_size": page_size,
    }


async def _get_order(db: AsyncSession, order_no: str) -> cm.AppOrder:
    row = (await db.execute(
        select(cm.AppOrder).where(cm.AppOrder.order_no == order_no)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "订单不存在")
    return row


@router.get("/orders/{order_no}", response_model=dict[str, Any])
async def get_order_detail(
    order_no: str,
    db: AsyncSession = Depends(get_db),
    who: dict = Depends(require_portal_or_admin),
):
    order = await _get_order(db, order_no)
    if who["user_type"] != "admin" and (
        order.buyer_id != who["user_id"] or order.buyer_type != who["user_type"]
    ):
        raise HTTPException(403, "无权查看该订单")
    lic = (await db.execute(
        select(cm.AppLicense).where(cm.AppLicense.order_id == order.id)
    )).scalars().first()
    return {
        "order": _order_dict(order),
        "license": _license_dict(lic, with_token=True) if lic else None,
        "pay_orders": await _related_pay_orders(db, order.order_no),
    }


async def _related_pay_orders(db: AsyncSession, order_no: str) -> list[dict[str, Any]]:
    """这笔商店订单在支付中心里留下的支付单（装了支付中心才有）。

    走原生 SQL而不是 import 支付中心模型：应用中心对支付中心是**软依赖**，
    没装（或表不存在）时返回空列表，不影响订单本身可读。
    只支持 PG 的 ``->>``；其余方言取不到 archived_at 也不致命（当作未作废）。
    """
    if not (await db.execute(text("select to_regclass('public.pay_orders')"))).scalar():
        return []
    rows = (await db.execute(
        text(
            "select out_trade_no, status, provider, sub_type, pay_mode, amount_cents, "
            "       trade_no, created_at, paid_at, expire_at, "
            "       (extra->>'archived_at') as archived_at "
            "from pay_orders where biz_type = 'app_order' and biz_id = :no "
            "order by id desc limit 20"
        ),
        {"no": order_no},
    )).mappings().all()
    return [{
        **dict(r),
        "created_at": _iso(r["created_at"]), "paid_at": _iso(r["paid_at"]),
        "expire_at": _iso(r["expire_at"]),
        "amount": f"{(r['amount_cents'] or 0) / 100:.2f}",
    } for r in rows]


# ============================================================
# 在线收款（对接「支付中心」应用 · 软依赖）
# ============================================================
#
# 设计：应用中心不实现任何支付协议、不存任何密钥，只在支付中心里「引用」一个场景。
# 装了支付中心 → 下单后可发起在线支付；没装 → 保持原有的对公转账 + 手工确认。
# 两条路最终都汇到同一条授权签发逻辑。

COMMERCE_SETTING_DEFAULTS: dict[str, Any] = {
    "payment_scene_key": "app_store",
    "pay_expire_minutes": 30,
}


async def _commerce_setting(db: AsyncSession, key: str, default: Any = None) -> Any:
    """读 system_settings（该表 value 为 jsonb，走原生 SQL 避开 ORM 类型不匹配）。"""
    try:
        raw = (await db.execute(
            text("select value from system_settings where key = :k"), {"k": key}
        )).scalar()
    except Exception:  # noqa: BLE001
        return default
    if raw is None:
        return default
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:  # noqa: BLE001
            return raw
    return raw


async def _set_setting(db: AsyncSession, key: str, value: Any, user_id: int | None = None) -> None:
    """写 system_settings（UPSERT）。"""
    await db.execute(
        text(
            "insert into system_settings (key, value, description, "
            '"group", updated_by, updated_at) '
            "values (:k, cast(:v as jsonb), :d, 'commerce', :u, now()) "
            "on conflict (key) do update set value = excluded.value, "
            "updated_by = excluded.updated_by, updated_at = now()"
        ),
        {
            "k": key,
            "v": json.dumps(value, ensure_ascii=False),
            "d": "应用中心收款设置",
            "u": user_id,
        },
    )
    await db.commit()


async def _payment_base_url(request: Request, db: AsyncSession) -> str:
    """第三方回调/回跳用的外部可达地址：优先 payment.base_url，其次反代头，最后按请求推导。"""
    configured = await _commerce_setting(db, "payment.base_url", "")
    if configured:
        return str(configured).rstrip("/")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


@router.post("/orders/{order_no}/checkout", response_model=dict[str, Any])
async def checkout_order(
    order_no: str,
    request: Request,
    body: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    who: dict = Depends(require_portal_or_admin),
):
    """发起在线支付：在「支付中心」建单，返回收银台地址与调起参数。

    支付成功后由支付中心派发 `payment.paid`（biz_type=app_order），
    本应用的 hooks.py 接到后自动标记订单已付并签发授权 —— 无需前端回调确认。
    未安装支付中心时返回 503，买家应改用对公转账。
    """
    order = await _get_order(db, order_no)

    if who["user_type"] != "admin" and (
        who["user_type"] != order.buyer_type or who["user_id"] != order.buyer_id
    ):
        raise HTTPException(403, "只能支付自己的订单")

    if order.status != "pending":
        raise HTTPException(400, f"订单当前状态为 {order.status}，无法发起支付")
    if order.amount_cents <= 0:
        raise HTTPException(400, "0 元订单无需支付")

    try:
        from cenkor_admin.apps.payment import service as pay_service
    except ImportError as exc:  # 支付中心未安装
        raise HTTPException(503, "未安装「支付中心」应用，无法在线收款，请改用对公转账") from exc

    scene_key = str(await _commerce_setting(
        db, "commerce.payment_scene_key", COMMERCE_SETTING_DEFAULTS["payment_scene_key"]
    ) or "app_store")
    base_url = await _payment_base_url(request, db)

    # 终端选路：买家在 PC 上 -> 扫码通道；在手机浏览器/微信内 -> 跳转通道。
    # 前端可传 terminal 显式覆盖；传了 channel_id/provider 时选路会跳过终端偏好。
    terminal = (str(body.get("terminal") or "").strip().lower()
                or pay_service.detect_terminal(request.headers.get("user-agent")))

    # 支付完成后的业务回跳地址：默认回门户「我的应用」（授权就在那里生效）。
    # 必须显式传：不传时支付中心会把回跳地址指回收银台自己，收银台支付成功后
    # 再自动跳回去就是无限刷新。门户域名与 API 不同时，用
    # system_settings 里的 commerce.site_base_url 覆盖。
    site_base = (str(await _commerce_setting(db, "commerce.site_base_url", "") or "").rstrip("/")
                 or base_url)
    pay_return_url = f"{site_base}/my/apps?paid_order={order.order_no}"

    try:
        pay_order, result = await pay_service.create_order(
            db,
            scene_key=scene_key,
            amount_cents=order.amount_cents,
            subject=f"{order.app_name} 授权（{order.seats} 席）",
            description=f"应用中心订单 {order.order_no}",
            base_url=base_url,
            provider=(str(body["provider"]) if body.get("provider") else None),
            sub_type=(str(body["sub_type"]) if body.get("sub_type") else None),
            channel_id=(int(body["channel_id"]) if body.get("channel_id") else None),
            terminal=terminal,
            client_ip=(request.client.host if request.client else ""),
            return_url=pay_return_url,
            biz_type="app_order",
            biz_id=order.order_no,
            creator_id=who["user_id"],
            prefix="AS",
        )
    except pay_service.PayError as exc:
        raise HTTPException(400, exc.message) from exc

    order.channel = pay_order.provider or order.channel
    await db.commit()

    log.info("commerce.checkout_created", order=order.order_no,
             pay_order=pay_order.out_trade_no, scene=scene_key, mode=result.mode,
             terminal=terminal, provider=pay_order.provider,
             channel_id=pay_order.channel_id,
             pay_type=result.payload.get("pay_type") or "")
    return {
        "order": _order_dict(order),
        "pay": {
            "out_trade_no": pay_order.out_trade_no,
            "provider": pay_order.provider,
            "sub_type": pay_order.sub_type,
            "channel_id": pay_order.channel_id,
            "pay_type": result.payload.get("pay_type") or "",
            "terminal": terminal,
            "mode": result.mode,
            "payload": result.payload,
            "cashier_url": f"{base_url}/api/v1/public/payment/cashier/{pay_order.out_trade_no}",
            "status_url": f"{base_url}/api/v1/public/payment/status/{pay_order.out_trade_no}",
        },
    }


@router.post("/orders/{order_no}/pay", response_model=dict[str, Any])
async def mark_order_paid(
    order_no: str,
    body: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """确认收款：对公转账 / 线下收款 / 第三方支付回调落库。

    支付成功即签发授权（幂等：重复调用返回已有授权）。
    """
    order = await _get_order(db, order_no)
    if order.status == "refunded":
        raise HTTPException(400, "订单已退款")
    if order.status != "paid":
        order.status = "paid"
        order.paid_at = _now()
        if body.get("channel"):
            order.channel = str(body["channel"])
        if body.get("trade_no"):
            order.trade_no = str(body["trade_no"])
        await db.commit()

    existing = (await db.execute(
        select(cm.AppLicense).where(cm.AppLicense.order_id == order.id)
    )).scalars().first()
    lic = existing or await _issue_license(db, order)
    log.info("commerce.order_paid", order=order.order_no, license=lic.license_key, by=user.id)
    return {"order": _order_dict(order), "license": _license_dict(lic, with_token=True)}


@router.post("/orders/{order_no}/cancel", response_model=dict[str, Any])
async def cancel_order(
    order_no: str,
    db: AsyncSession = Depends(get_db),
    who: dict = Depends(require_portal_or_admin),
):
    order = await _get_order(db, order_no)
    if who["user_type"] != "admin" and order.buyer_id != who["user_id"]:
        raise HTTPException(403, "无权操作该订单")
    if order.status == "paid":
        raise HTTPException(400, "已支付订单需走退款流程")
    order.status = "cancelled"
    await db.commit()
    return _order_dict(order)


@router.post("/orders/{order_no}/refund", response_model=dict[str, Any])
async def refund_order(
    order_no: str,
    body: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """退款：订单置为 refunded，并吊销其授权。"""
    order = await _get_order(db, order_no)
    if order.status != "paid":
        raise HTTPException(400, "只有已支付订单可退款")
    order.status = "refunded"
    order.refunded_at = _now()
    order.remark = (order.remark or "") + f" | 退款：{body.get('reason') or '未填写'}"

    lics = (await db.execute(
        select(cm.AppLicense).where(cm.AppLicense.order_id == order.id)
    )).scalars().all()
    for lic in lics:
        lic.status = "revoked"
        lic.revoked_at = _now()
        lic.revoke_reason = "订单退款"
        await _resign(db, lic)

    # 资金冲正：把开发者已入账的净收入扣回（结算期内扣冻结，已结算扣可用）
    await ledger.debit_refund(db, order)

    await db.commit()
    log.info("commerce.order_refunded", order=order.order_no, by=user.id)
    return {"order": _order_dict(order), "revoked": [l.license_key for l in lics]}


# ============================================================
# 订单治理：作废隐藏 / 删除 / 批量清理（仅后台）
# ============================================================

async def _licensed_order_ids(db: AsyncSession) -> set[int]:
    """已签发过授权的订单 id —— 删订单会撞 app_licenses.order_id 外键，先拦住。"""
    rows = (await db.execute(
        select(cm.AppLicense.order_id).where(cm.AppLicense.order_id.isnot(None)).distinct()
    )).scalars().all()
    return {int(x) for x in rows if x}


async def _live_pay_biz_ids(db: AsyncSession) -> set[str]:
    """还有未过期待支付单的业务单号（删了它们可能弄出「钱到账但单没了」）。"""
    try:
        rows = (await db.execute(text(
            "select biz_id from pay_orders "
            "where biz_type = 'app_order' and status = 'pending' "
            "  and (expire_at is null or expire_at > now())"
        )).scalars().all())
    except Exception:  # noqa: BLE001  支付中心未装 / 非 PG 方言：当作没有活的支付单
        return set()
    return {str(x) for x in rows if x}


@router.post("/orders/{order_no}/archive", response_model=dict[str, Any])
async def archive_order(
    order_no: str,
    body: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """作废隐藏（软删除）：任何状态都可用，已支付订单想用「删除」就走向这里。"""
    order = await _get_order(db, order_no)
    _set_archived(order, user.id, str(body.get("reason") or ""))
    await db.commit()
    await db.refresh(order)  # updated_at 由服务端生成，不刷新会在序列化时踩懒加载
    log.info("commerce.order_archived", order=order.order_no, by=user.id)
    return _order_dict(order)


@router.post("/orders/{order_no}/unarchive", response_model=dict[str, Any])
async def unarchive_order(
    order_no: str,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    order = await _get_order(db, order_no)
    if _archived_at(order) is None:
        raise HTTPException(400, "该订单未作废")
    _clear_archived(order)
    await db.commit()
    await db.refresh(order)
    log.info("commerce.order_unarchived", order=order.order_no, by=user.id)
    return _order_dict(order)


@router.delete("/orders/{order_no}", response_model=dict[str, Any])
async def delete_order(
    order_no: str,
    body: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """物理删除商店订单：只允许从未收到钱、且没签发过授权的单。

    连带清掉它名下的未支付单（同单号重复点结算留下的）：业务单删了而
    支付单还活着，买家事后扫完回调就会「找不到归属订单」，只留告警日志。
    已支付 / 已退款的单请走退款或作废，这里一律 400 拒掉。
    """
    order = await _get_order(db, order_no)
    if order.status not in DELETABLE_STATUSES:
        raise HTTPException(
            400,
            f"{_STATUS_CN.get(order.status, order.status)}的订单不能删除（已入账），"
            "已支付的请先退款，或改用作废隐藏",
        )
    licensed = (await db.execute(
        select(cm.AppLicense).where(cm.AppLicense.order_id == order.id).limit(1)
    )).scalars().first()
    if licensed is not None:
        raise HTTPException(400, f"该订单已签发授权 {licensed.license_key}，不能删除；请先掉授权")

    related = await _related_pay_orders(db, order.order_no)
    open_ones = [r for r in related if r["status"] == "pending" and not r.get("archived_at")]
    if open_ones and not body.get("force"):
        raise HTTPException(
            400,
            f"还有 {len(open_ones)} 笔未关闭的支付单（{open_ones[0]['out_trade_no']}），"
            "买家可能仍在扫码；确认强删请传 force=true",
        )

    removed_pay = 0
    if related:
        try:
            res = await db.execute(text(
                "delete from pay_orders where biz_type = 'app_order' and biz_id = :no "
                "  and status in ('pending', 'closed', 'failed')"
            ), {"no": order.order_no})
            removed_pay = int(res.rowcount or 0)
        except Exception:  # noqa: BLE001  支付中心未装：无连带可清
            removed_pay = 0

    no = order.order_no
    amount = order.amount_cents
    await db.delete(order)
    await db.commit()
    log.warning("commerce.order_deleted", order=no, amount_cents=amount,
                pay_orders_removed=removed_pay, force=bool(body.get("force")), by=user.id)
    return {"ok": True, "order_no": no, "pay_orders_removed": removed_pay}


@router.post("/orders/cleanup", response_model=dict[str, Any])
async def cleanup_orders(
    body: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """批量清理垃圾订单（反复点结算留下的过期未付残单）。

    默认 ``dry_run=true`` 只报命中多少条；一次最多处理 500 条。无论哪种模式，
    已签发授权、已支付、以及还有未过期支付单的单子都会被跳过。
    """
    statuses = [str(s) for s in (body.get("statuses") or ["pending", "cancelled", "expired"])]
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
    stmt = (
        select(cm.AppOrder)
        .where(
            cm.AppOrder.status.in_(statuses),
            cm.AppOrder.created_at <= cutoff,
            cm.AppOrder.meta["archived_at"].astext.is_(None),
        )
        .order_by(cm.AppOrder.id.desc())
        .limit(500)
    )
    rows = (await db.execute(stmt)).scalars().all()
    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar() or 0

    licensed_ids = await _licensed_order_ids(db) if rows else set()
    live_biz = await _live_pay_biz_ids(db) if (rows and mode == "delete") else set()

    candidates = [o for o in rows
                  if o.id not in licensed_ids and o.order_no not in live_biz]
    skipped = len(rows) - len(candidates)
    sample = [{
        "order_no": o.order_no, "status": o.status, "app_name": o.app_name,
        "amount_cents": o.amount_cents, "buyer_email": o.buyer_email,
        "created_at": _iso(o.created_at),
    } for o in candidates[:20]]
    if dry_run:
        return {"dry_run": True, "mode": mode, "matched": int(total),
                "will_process": len(candidates), "skipped": skipped,
                "cutoff": _iso(cutoff), "sample": sample}

    reason = f"批量清理：早于 {cutoff.strftime('%Y-%m-%d %H:%M')}，状态 {'/'.join(statuses)}"
    done = 0
    for o in candidates:
        if mode == "delete":
            await db.delete(o)
        else:
            _set_archived(o, user.id, reason)
        done += 1
    await db.commit()
    log.warning("commerce.orders_cleanup", mode=mode, processed=done, matched=int(total),
                skipped=skipped, cutoff=_iso(cutoff), by=user.id)
    return {"dry_run": False, "mode": mode, "matched": int(total), "processed": done,
            "skipped": skipped, "cutoff": _iso(cutoff)}


# ============================================================
# 授权
# ============================================================

async def _issue_license(db: AsyncSession, order: cm.AppOrder) -> cm.AppLicense:
    """支付完成后签发授权（幂等）。"""
    existing = (await db.execute(
        select(cm.AppLicense).where(cm.AppLicense.order_id == order.id)
    )).scalars().first()
    if existing:
        return existing

    price_stmt = select(cm.AppPricing).where(cm.AppPricing.app_key == order.app_key)
    if order.product:
        price_stmt = price_stmt.where(cm.AppPricing.product == order.product)
    # first() 而非 scalar_one_or_none()：order.product 为空时这里只按 app_key 查，
    # 同一 app_key 在多产品轴各有一行价是合法状态，后者会抛 MultipleResultsFound 把签授权打断。
    price_row = (await db.execute(price_stmt)).scalars().first()
    period_days = price_row.period_days if price_row else 365
    if price_row is None and order.model == "seat":
        # 席位制的授权周期取自定价行；取不到行时静默回落 365 会让"买了 90 天却拿到 365 天"
        # 这类错账无从察觉，必须留痕。
        log.warning("commerce.license_period_fallback", order=order.order_no,
                    app=order.app_key, product=order.product, period_days=period_days)

    expires_at = None
    # 订阅已下线：只有席位制按周期授权；买断（one_time）为永久有效，不设到期
    if order.model == "seat":
        expires_at = _now() + timedelta(days=period_days)

    lic = cm.AppLicense(
        license_key=cm.generate_license_key(),
        app_key=order.app_key,
        product=order.product or "cenkor-admin",
        app_name=order.app_name,
        order_id=order.id,
        buyer_id=order.buyer_id,
        buyer_type=order.buyer_type,
        model=order.model,
        seats=order.seats,
        status="issued",
        expires_at=expires_at,
        max_instances=1 if order.model != "seat" else max(order.seats, 1),
    )
    db.add(lic)
    await db.flush()
    await _resign(db, lic)
    await db.commit()
    log.info("commerce.license_issued", license=lic.license_key, app=lic.app_key, order=order.order_no)
    return lic


@router.get("/licenses", response_model=dict[str, Any])
async def list_licenses(
    db: AsyncSession = Depends(get_db),
    who: dict = Depends(require_portal_or_admin),
    app_key: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    stmt = select(cm.AppLicense).order_by(cm.AppLicense.id.desc())
    if who["user_type"] != "admin":
        stmt = stmt.where(
            cm.AppLicense.buyer_id == who["user_id"],
            cm.AppLicense.buyer_type == who["user_type"],
        )
    if app_key:
        stmt = stmt.where(cm.AppLicense.app_key == app_key)
    if status:
        stmt = stmt.where(cm.AppLicense.status == status)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": [_license_dict(r, with_token=True) for r in rows], "total": total}


@router.post("/licenses", status_code=201, response_model=dict[str, Any])
async def issue_license_manual(
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """手工签发授权（赠送 / 补偿 / 线下大客户）。"""
    app_key = str(body.get("app_key") or "").strip()
    if not app_key:
        raise HTTPException(400, "app_key 必填")
    product = await _resolve_product(db, app_key, body.get("product"))
    model = str(body.get("model") or "one_time")
    if model not in cm.PRICING_MODELS:
        raise HTTPException(400, "model 不合法")
    days = int(body.get("days") or 0)

    lic = cm.AppLicense(
        license_key=cm.generate_license_key(),
        app_key=app_key,
        product=product,
        app_name=str(body.get("app_name") or app_key),
        buyer_id=body.get("buyer_id"),
        buyer_type=str(body.get("buyer_type") or "portal") if body.get("buyer_id") else None,
        model=model,
        seats=max(int(body.get("seats") or 1), 1),
        status="issued",
        expires_at=_now() + timedelta(days=days) if days > 0 else None,
        max_instances=max(int(body.get("max_instances") or 1), 1),
        max_rebind=max(int(body.get("max_rebind") or 3), 0),
        notes=str(body.get("notes") or "") or None,
    )
    db.add(lic)
    await db.flush()
    await _resign(db, lic)
    await db.commit()
    log.info("commerce.license_manual", license=lic.license_key, by=user.id)
    return _license_dict(lic, with_token=True)


async def _get_license(db: AsyncSession, license_key: str) -> cm.AppLicense:
    row = (await db.execute(
        select(cm.AppLicense).where(cm.AppLicense.license_key == license_key.upper())
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "授权码不存在")
    return row


@router.get("/licenses/{license_key}", response_model=dict[str, Any])
async def get_license(
    license_key: str,
    db: AsyncSession = Depends(get_db),
    who: dict = Depends(require_portal_or_admin),
):
    lic = await _get_license(db, license_key)
    if who["user_type"] != "admin" and lic.buyer_id != who["user_id"]:
        raise HTTPException(403, "无权查看该授权")
    bindings = (await db.execute(
        select(cm.AppLicenseBinding).where(cm.AppLicenseBinding.license_id == lic.id)
    )).scalars().all()
    return {
        "license": _license_dict(lic, with_token=True),
        "bindings": [
            {
                "instance_fp": b.instance_fp, "domain": b.domain, "ip": b.ip,
                "version": b.version, "activated_at": _iso(b.activated_at),
                "last_seen_at": _iso(b.last_seen_at), "revoked_at": _iso(b.revoked_at),
            }
            for b in bindings
        ],
    }


# ------------------------------------------------------------
# 实例侧（免 token，用 license_key 自证）
# ------------------------------------------------------------

def _client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


async def _bind_instance(
    db: AsyncSession, lic: cm.AppLicense, instance_fp: str, domain: str | None,
    ip: str | None, version: str | None,
) -> None:
    """绑定实例。已存在的按 fp 更新 last_seen；新 fp 受 max_instances 限制。"""
    binding = (await db.execute(
        select(cm.AppLicenseBinding).where(
            cm.AppLicenseBinding.license_id == lic.id,
            cm.AppLicenseBinding.instance_fp == instance_fp,
        )
    )).scalar_one_or_none()

    if binding:
        binding.last_seen_at = _now()
        if domain:
            binding.domain = domain
        if ip:
            binding.ip = ip
        if version:
            binding.version = version
        return

    active = (await db.execute(
        select(func.count()).select_from(cm.AppLicenseBinding).where(
            cm.AppLicenseBinding.license_id == lic.id,
            cm.AppLicenseBinding.revoked_at.is_(None),
        )
    )).scalar() or 0
    if active >= (lic.max_instances or 1):
        raise HTTPException(
            409,
            f"该授权已绑定 {active} 台实例（上限 {lic.max_instances}），请先解绑或申请换绑",
        )

    db.add(cm.AppLicenseBinding(
        license_id=lic.id, instance_fp=instance_fp, domain=domain, ip=ip,
        version=version, last_seen_at=_now(),
    ))
    if not lic.instance_fp:
        lic.instance_fp = instance_fp
    if domain and not lic.bound_domain:
        lic.bound_domain = domain


def _guard_license(lic: cm.AppLicense) -> None:
    if lic.status in ("revoked", "suspended"):
        raise HTTPException(403, f"授权已{('吊销' if lic.status == 'revoked' else '暂停')}"
                                 f"{'：' + lic.revoke_reason if lic.revoke_reason else ''}")
    if lic.expires_at and lic.expires_at < _now():
        raise HTTPException(403, f"授权已于 {lic.expires_at.date()} 到期，请续费")


@router.post("/licenses/{license_key}/activate", response_model=dict[str, Any])
async def activate_license(
    license_key: str,
    request: Request,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """客户实例激活：提交实例指纹与域名，换取签名授权凭证。"""
    lic = await _get_license(db, license_key)
    _guard_license(lic)

    instance_fp = str(body.get("instance_fp") or "").strip()
    if not instance_fp:
        raise HTTPException(400, "instance_fp 必填")

    st = get_settings()
    try:
        await _bind_instance(
            db, lic, instance_fp, body.get("domain"), _client_ip(request), body.get("version"),
        )
    except HTTPException as e:
        if e.status_code == 409 and lic.max_rebind > lic.rebind_count:
            raise HTTPException(409, "该授权已绑定其他实例，请在授权中心执行换绑") from e
        raise

    lic.status = "active"
    lic.activated_at = lic.activated_at or _now()
    lic.last_check_at = _now()
    if body.get("domain"):
        lic.bound_domain = str(body["domain"])
    await _resign(db, lic)
    await db.commit()

    log.info("commerce.license_activated", license=lic.license_key, fp=instance_fp)
    return {
        "ok": True,
        "app_key": lic.app_key,
        "license_key": lic.license_key,
        "token": lic.token,
        "seats": lic.seats,
        "model": lic.model,
        "expires_at": _iso(lic.expires_at),
        "offline_grace_days": st.LICENSE_OFFLINE_GRACE_DAYS,
        "heartbeat_hours": st.LICENSE_HEARTBEAT_HOURS,
    }


@router.post("/licenses/{license_key}/heartbeat", response_model=dict[str, Any])
async def heartbeat_license(
    license_key: str,
    request: Request,
    body: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
):
    """心跳：返回最新授权状态与新签发的 token。授权失效时 valid=false。"""
    try:
        lic = await _get_license(db, license_key)
    except HTTPException:
        return {"valid": False, "reason": "授权码不存在"}

    if lic.status in ("revoked", "suspended"):
        return {"valid": False, "reason": lic.revoke_reason or "授权已失效"}
    if lic.expires_at and lic.expires_at < _now():
        return {"valid": False, "reason": f"授权已于 {lic.expires_at.date()} 到期"}

    instance_fp = str(body.get("instance_fp") or "").strip()
    if instance_fp:
        try:
            await _bind_instance(
                db, lic, instance_fp, body.get("domain"), _client_ip(request), body.get("version"),
            )
        except HTTPException as e:
            return {"valid": False, "reason": e.detail}

    lic.last_check_at = _now()
    if lic.status == "issued":
        lic.status = "active"
        lic.activated_at = lic.activated_at or _now()
    await _resign(db, lic)
    await db.commit()
    return {
        "valid": True,
        "app_key": lic.app_key,
        "token": lic.token,
        "seats": lic.seats,
        "expires_at": _iso(lic.expires_at),
    }


@router.post("/licenses/{license_key}/rebind", response_model=dict[str, Any])
async def rebind_license(
    license_key: str,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """换绑：解绑旧实例，重签 token。"""
    lic = await _get_license(db, license_key)
    if lic.rebind_count >= lic.max_rebind:
        raise HTTPException(400, f"换绑次数已用尽（上限 {lic.max_rebind}）")

    bindings = (await db.execute(
        select(cm.AppLicenseBinding).where(
            cm.AppLicenseBinding.license_id == lic.id,
            cm.AppLicenseBinding.revoked_at.is_(None),
        )
    )).scalars().all()
    for b in bindings:
        b.revoked_at = _now()

    lic.rebind_count += 1
    lic.instance_fp = None
    lic.bound_domain = None
    if body.get("domain"):
        lic.bound_domain = str(body["domain"])
    if lic.status == "active":
        lic.status = "issued"
    await _resign(db, lic)
    await db.commit()
    log.info("commerce.license_rebound", license=lic.license_key, by=user.id)
    return _license_dict(lic, with_token=True)


@router.post("/licenses/{license_key}/renew", response_model=dict[str, Any])
async def renew_license(
    license_key: str,
    body: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """续期：延长到期时间（从当前到期日或今天起算）。"""
    lic = await _get_license(db, license_key)
    days = int(body.get("days") or 365)
    base = lic.expires_at if (lic.expires_at and lic.expires_at > _now()) else _now()
    lic.expires_at = base + timedelta(days=days)
    if lic.status == "expired":
        lic.status = "issued"
    await _resign(db, lic)
    await db.commit()
    log.info("commerce.license_renewed", license=lic.license_key, days=days, by=user.id)
    return _license_dict(lic, with_token=True)


@router.post("/licenses/{license_key}/revoke", response_model=dict[str, Any])
async def revoke_license(
    license_key: str,
    body: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    lic = await _get_license(db, license_key)
    lic.status = "revoked"
    lic.revoked_at = _now()
    lic.revoke_reason = str(body.get("reason") or "运营吊销")
    await _resign(db, lic)
    await db.commit()
    log.warning("commerce.license_revoked", license=lic.license_key, by=user.id)
    return _license_dict(lic, with_token=True)


# ============================================================
# 授权中心元信息
# ============================================================

@router.get("/licensing/public-key", response_model=dict[str, Any])
async def get_public_key(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:read")),
):
    """取出公钥，回填到 base 代码的 DEFAULT_PUBLIC_KEY_B64，供客户实例验签。"""
    _, pub = await license_authority.get_or_create_keypair(db)
    return {
        "public_key_b64": pub,
        "active_public_key_b64": licensing.DEFAULT_PUBLIC_KEY_B64,
        "cloud_url": get_settings().CENKOR_CLOUD_URL,
        "offline_grace_days": get_settings().LICENSE_OFFLINE_GRACE_DAYS,
        "heartbeat_hours": get_settings().LICENSE_HEARTBEAT_HOURS,
    }


# ============================================================
# 云端分发 & 实例端安装
# ============================================================

async def _fetch_package(
    db: AsyncSession, app_key: str, product: str | None = None
) -> tuple[store_models.AppSubmission, Path]:
    """返回 (发布行, zip 路径)。本机即授权中心时直接用本地包。

    product 非空时按目标产品隔离定位（多产品轴下同名 app_key 不再串包）。

    返回**整行**而不是 (路径, 版本)：下载端点既要把包发出去、又要给这行计下载数、
    还要发发布时的指纹。分两次查询各取一行，会出现「发的是 A 行的字节、计的是
    B 行的次数、签的是 B 行的 hash」—— 定位必须只有一个来源。
    """
    cond = [
        store_models.AppSubmission.app_key == app_key,
        store_models.AppSubmission.status.in_(("approved", "published", "installed")),
        # 撤回上架（yank）只拦新下载：已装客户不受影响，但不能再拿到这一版
        store_models.AppSubmission.yanked_at.is_(None),
    ]
    if product:
        cond.append(store_models.AppSubmission.product == product)
    sub_rows = (await db.execute(
        select(store_models.AppSubmission).where(*cond)
    )).scalars().all()
    if not sub_rows:
        raise HTTPException(404, f"应用 {app_key} 暂无可分发的版本")
    # 与公开目录同一口径：发「版本号最大」的那条，而不是 id 最大的那条。
    # 否则目录上写着 1.9、下载下来是 2.0 的字节，用户拿到的包和自己点开的版本不是一回事。
    sub = max(sub_rows, key=lambda r: (ver_tuple(r.version), r.id or 0))
    if not sub.file_path or not os.path.exists(sub.file_path):
        raise HTTPException(409, f"应用 {app_key} 的包文件缺失，请联系平台")

    s = get_settings()
    cloud = (s.CENKOR_CLOUD_URL or "").rstrip("/")
    if cloud:
        raise HTTPException(409, "外部授权中心模式请在实例侧直接下载安装")

    return sub, Path(sub.file_path)


@router.get("/cloud/packages/{app_key}")
async def download_package(
    app_key: str,
    license_key: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """付费包下载。必须持有该应用的有效授权码。"""
    lic = await _get_license(db, license_key)
    _guard_license(lic)
    if lic.app_key != app_key:
        raise HTTPException(403, f"授权码属于 {lic.app_key}，与请求的 {app_key} 不匹配")

    sub, path = await _fetch_package(db, app_key, product=lic.product)
    version = sub.version
    sub.download_count = (sub.download_count or 0) + 1
    await db.commit()

    # X-App-Schema-Version：包的 manifest.schema_version，实例侧据此判断「要不要跑升级迁移」。
    # 缺值（老包/无此列）即留空，实例按 manifest 兜底。
    headers = {
        "X-App-Version": version,
        "X-App-Product": lic.product or "",
        "X-App-Schema-Version": str(sub.schema_version or ""),
    }
    if sub.file_hash:
        # 实例侧装完之前比对包体指纹；不等说明 hub 落盘的包与发布时不是同一份。
        headers["X-Package-Sha256"] = sub.file_hash
    log.info(
        "commerce.package_served",
        app=app_key,
        version=version,
        license=lic.license_key,
        sha256=sub.file_hash or "",
    )
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"{app_key}-{version}.zip",
        # X-App-Product：把授权轴上的 product 随包下发，实例侧据此拒绝跨产品误装。
        # 走响应头而不是改写 zip：hub 从不重打包（全仓无 ZipFile 'w'）。
        headers=headers,
    )


@router.post("/cloud/install", response_model=dict[str, Any])
async def install_from_cloud(
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """实例端：用授权码从授权中心拉包并安装（解压 → 前端 → 迁移 → 注册路由 → 激活）。"""
    license_key = str(body.get("license_key") or "").strip().upper()
    if not license_key:
        raise HTTPException(400, "license_key 必填")

    s = get_settings()
    cloud = (s.CENKOR_CLOUD_URL or "").rstrip("/")
    tmp_path: str | None = None
    hub_product = ""    # 包所属产品轴；空串 = 上游未下发（老 hub），按「缺值即放行」处理

    # 1. 取得授权信息（外部云走 API，本机授权中心走本地库）
    if cloud:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{cloud}/api/v1/store/licenses/{license_key}/activate",
                    json={
                        "instance_fp": licensing.compute_instance_fp(),
                        "domain": s.PUBLIC_BASE_URL,
                        "version": s.APP_VERSION,
                    },
                )
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"授权中心不可达：{e}") from e
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"授权校验失败：{resp.text[:300]}")
        data = resp.json()
        app_key = data["app_key"]
        token = data["token"]

        # 2. 下载包
        try:
            async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
                pkg = await client.get(
                    f"{cloud}/api/v1/store/cloud/packages/{app_key}",
                    params={"license_key": license_key},
                )
            if pkg.status_code != 200:
                raise HTTPException(pkg.status_code, f"下载应用包失败：{pkg.text[:300]}")
            hub_product = (pkg.headers.get("X-App-Product") or "").strip()
            # 包体指纹校验：授权中心随包下发发布时的 SHA256。缺值（老 hub 无此头）
            # 即放行；有值而不等，就是拿到的字节与发布的那一份不是同一个东西。
            expected_sha = (pkg.headers.get("X-Package-Sha256") or "").strip().lower()
            if expected_sha:
                actual_sha = hashlib.sha256(pkg.content).hexdigest()
                if actual_sha != expected_sha:
                    log.error(
                        "commerce.package_sha256_mismatch",
                        app=app_key,
                        expected=expected_sha,
                        actual=actual_sha,
                        size=len(pkg.content),
                    )
                    raise HTTPException(
                        502,
                        f"应用包校验失败：SHA256 与发布记录不一致（期望 {expected_sha[:12]}…，"
                        f"实得 {actual_sha[:12]}…），已拒绝安装",
                    )
            fd, tmp_path = tempfile.mkstemp(suffix=".zip")
            with os.fdopen(fd, "wb") as f:
                f.write(pkg.content)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"下载应用包异常：{e}") from e
    else:
        lic = await _get_license(db, license_key)
        _guard_license(lic)
        app_key = lic.app_key
        hub_product = lic.product or ""
        sub, path = await _fetch_package(db, app_key)
        fd, tmp_path = tempfile.mkstemp(suffix=".zip")
        shutil.copyfile(path, tmp_path)
        os.close(fd)
        # 本地授权中心：直接激活并拿 token
        await _bind_instance(
            db, lic, licensing.compute_instance_fp(), s.PUBLIC_BASE_URL, None, s.APP_VERSION,
        )
        lic.status = "active"
        lic.activated_at = lic.activated_at or _now()
        lic.last_check_at = _now()
        await _resign(db, lic)
        await db.commit()
        token = lic.token

    # 3. 解压安装
    try:
        from cenkor_admin.apps.system.market_router import SELF_PRODUCT
        from cenkor_admin.apps.system.store_router import install_app_from_zip

        # 跨产品误装闸：上游 hub 随包下发的权威产品轴。缺值（老 hub 无此头）即放行。
        if hub_product and hub_product != SELF_PRODUCT:
            raise HTTPException(
                400,
                f"该应用包属于产品「{hub_product}」，与本实例「{SELF_PRODUCT}」不符",
            )
        result = await install_app_from_zip(db, app_key, Path(tmp_path))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    # 4. 写入本地授权缓存，应用即刻生效
    await licensing.write_cache(db, app_key, {
        "license_key": license_key,
        "token": token,
        "checked_at": _now().isoformat(),
        "cloud_ok": True,
        "invalid_reason": None,
    })

    log.info("commerce.installed_from_cloud", app=app_key, license=license_key, by=user.id)
    return {"ok": True, "app_key": app_key, "license_key": license_key, **result}

# ============================================================
# 收款设置（只存引用，不存密钥）
# ============================================================

async def _build_settings(db: AsyncSession) -> dict[str, Any]:
    scene_key = str(await _commerce_setting(
        db, "commerce.payment_scene_key", COMMERCE_SETTING_DEFAULTS["payment_scene_key"]
    ) or "app_store")
    try:
        expire = int(await _commerce_setting(
            db, "commerce.pay_expire_minutes", COMMERCE_SETTING_DEFAULTS["pay_expire_minutes"]
        ) or 30)
    except (TypeError, ValueError):
        expire = COMMERCE_SETTING_DEFAULTS["pay_expire_minutes"]

    payment_installed = True
    try:
        from cenkor_admin.apps.payment import models as pm  # noqa: F401
    except ImportError:
        payment_installed = False

    scenes: list[dict[str, Any]] = []
    channels: list[dict[str, Any]] = []
    if payment_installed:
        try:
            from cenkor_admin.apps.payment import models as pm
            rows = (await db.execute(
                select(pm.PayChannel.scene_key, pm.PayChannel.provider, pm.PayChannel.sub_type,
                       pm.PayChannel.title, pm.PayChannel.enabled)
                .where(pm.PayChannel.deleted_at.is_(None))
                .order_by(pm.PayChannel.scene_key.asc(), pm.PayChannel.sort.asc())
            )).all()
            index = {s["scene_key"]: s for s in scenes}
            for sk, provider, sub_type, title, enabled in rows:
                node = index.get(sk)
                if node is None:
                    node = {"scene_key": sk, "enabled": False, "channel_count": 0}
                    index[sk] = node
                    scenes.append(node)
                if enabled:
                    node["enabled"] = True
                    node["channel_count"] += 1
                if sk == scene_key and enabled:
                    channels.append({"provider": provider, "sub_type": sub_type,
                                     "title": title or provider})
        except Exception as exc:  # noqa: BLE001
            log.warning("commerce.settings_channels_failed", error=str(exc))

    return {
        "payment_installed": payment_installed,
        "payment_scene_key": scene_key,
        "pay_expire_minutes": expire,
        "scenes": scenes,
        "channels": channels,
    }


@router.get("/settings", response_model=dict[str, Any])
async def get_store_settings(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """应用中心收款设置。密钥类配置请去「支付中心 → 支付通道」维护。"""
    return await _build_settings(db)


@router.put("/settings", response_model=dict[str, Any])
async def update_store_settings(
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """更新收款设置。"""
    if "payment_scene_key" in body:
        scene = str(body["payment_scene_key"] or "").strip() or "app_store"
        await _set_setting(db, "commerce.payment_scene_key", scene, user.id)

    if "pay_expire_minutes" in body:
        try:
            minutes = max(int(body["pay_expire_minutes"]), 1)
        except (TypeError, ValueError):
            raise HTTPException(400, "pay_expire_minutes 必须是整数") from None
        await _set_setting(db, "commerce.pay_expire_minutes", minutes, user.id)

    log.info("commerce.settings_updated", by=user.id, fields=sorted(body.keys()))
    return await _build_settings(db)

# ============================================================
# 应用市场（开发者侧 / 平台侧）—— 共用本前缀的子路由
# ============================================================
from cenkor_admin.apps.commerce import market_router as _market_router  # noqa: E402

router.include_router(_market_router.router)
