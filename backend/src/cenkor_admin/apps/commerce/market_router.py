"""应用市场：开发者侧（定价 / 销售 / 收入 / 提现）+ 平台侧（配置 / 审核 / 报表）。

挂载方式：由 ``commerce_router`` 末尾 ``include_router`` 引入，共用 `/api/v1/store` 前缀。
本模块**不 import commerce_router**（避免循环依赖），需要的序列化自己实现。

鉴权两套：
- 开发者侧 ``/my/*``：``require_portal_or_admin`` + **归属校验**（只能操作自己提交过的应用）
- 平台侧 ``/market/*``：``require_permission("rbac:role:write")``

安全边界：扣点比例（``platform_fee_bp``）**只能平台侧改**，开发者定价接口会忽略该字段。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.commerce import ledger
from cenkor_admin.apps.commerce import models as cm
from cenkor_admin.apps.commerce import pricing
from cenkor_admin.apps.system import store_models
from cenkor_admin.apps.system.models import InstalledApp
from cenkor_admin.apps.system.store_router import require_portal_or_admin
from cenkor_admin.core.db import get_db

log = structlog.get_logger()
router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: datetime | None) -> str | None:
    return v.isoformat() if v else None


def _yuan(c: Any) -> str:
    return f"{int(c or 0) / 100:.2f}"


def _page(page: int, page_size: int) -> tuple[int, int]:
    page = max(int(page or 1), 1)
    size = min(max(int(page_size or 20), 1), 100)
    return (page - 1) * size, size


# ============================================================
# 身份与归属
# ============================================================


async def _developer_of(db: AsyncSession, who: dict) -> store_models.Developer:
    """把鉴权结果解析成开发者。开发者身份只挂在门户账号（portal_users）上。"""
    if who.get("user_type") != "portal":
        raise HTTPException(403, "请使用开发者账号（门户账号）访问，管理后台请走「应用市场」模块")
    dev = (await db.execute(
        select(store_models.Developer).where(
            store_models.Developer.user_id == int(who["user_id"])
        )
    )).scalar_one_or_none()
    if dev is None:
        raise HTTPException(403, "当前账号尚未注册为开发者")
    if (dev.status or "active") != "active":
        raise HTTPException(403, "开发者账号已被停用，请联系平台")
    return dev


async def _assert_owned(db: AsyncSession, app_key: str, developer_id: int) -> None:
    """归属校验：以该 app_key 最新一条提交记录的归属为准。"""
    owner = (await db.execute(
        select(store_models.AppSubmission.developer_id)
        .where(store_models.AppSubmission.app_key == app_key)
        .order_by(store_models.AppSubmission.id.desc())
        .limit(1)
    )).scalar()
    if owner is None:
        raise HTTPException(404, f"应用 {app_key} 没有任何提交记录")
    if int(owner) != int(developer_id):
        raise HTTPException(403, "该应用不属于当前开发者，无法操作")


async def _pricing_row(db: AsyncSession, app_key: str,
                       product: str | None = None) -> cm.AppPricing | None:
    """按 ``(product, app_key)`` 定位定价行 —— 这是 ``AppPricing`` 的唯一键。

    ``product`` 缺省时先回查提交记录拿权威轴：只按 app_key 查并用 ``scalar_one_or_none()``
    在历史上被写歪到 ``cenkor-admin`` 的行、与正确轴的行并存时会抛
    ``MultipleResultsFound``（定价页 500）。
    """
    axis = product or await pricing.resolve_product(db, app_key)
    return (await db.execute(
        select(cm.AppPricing).where(
            cm.AppPricing.app_key == app_key,
            cm.AppPricing.product == axis,
        )
    )).scalars().first()


def _pricing_view(p: cm.AppPricing | None, app_key: str) -> dict[str, Any]:
    """定价视图 = 通用定价视图（含原价/促销/生效价）+ 市场归属与扣点。

    通用部分由 ``pricing.price_view()`` 产出，避免与 commerce_router 的序列化漂移。
    """
    view = pricing.price_view(p, app_key)
    view.update({
        "developer_id": p.developer_id if p else None,
        "owner_self_operated": ledger.is_self_operated(p.developer_id) if p else False,
        "platform_fee_bp": p.platform_fee_bp if p else None,
        "listed": (bool(p.enabled) and p.model != "free") if p else False,
    })
    return view


async def _owner_name(db: AsyncSession, developer_id: int | None) -> str:
    """归属展示名：平台自营 / 开发者名。"""
    if ledger.is_self_operated(developer_id):
        return "平台自营"
    dev = await db.get(store_models.Developer, int(developer_id))
    return dev.display_name if dev else f"开发者 #{developer_id}"


async def _wallet_of(db: AsyncSession, developer_id: int) -> cm.DevWallet | None:
    return (await db.execute(
        select(cm.DevWallet).where(cm.DevWallet.developer_id == developer_id)
    )).scalar_one_or_none()


async def _set_pricing(db: AsyncSession, app_key: str, body: dict, *,
                       developer_id: int | None, touch_fee: bool) -> cm.AppPricing:
    """写入定价。``developer_id`` 为归属（钉死）；``touch_fee`` 决定是否允许改扣点。

    字段校验与落库统一交给 ``pricing.apply_price_fields()``（含原价 / 促销）。
    行按 ``(product, app_key)`` 定位，product 取提交记录的权威轴 —— ``apply_price_fields``
    只管价格字段、从不碰轴，所以新建行必须在这里显式 stamp，否则吃列默认值
    ``cenkor-admin``，实例按自身产品轴下单会匹配不到行而算成 0 元。
    """
    axis = await pricing.resolve_product(db, app_key)
    row = await _pricing_row(db, app_key, axis)
    if row is None:
        row = cm.AppPricing(app_key=app_key, product=axis)
        db.add(row)

    try:
        pricing.apply_price_fields(row, body, touch_fee=touch_fee)
    except pricing.PriceRuleError as exc:
        raise HTTPException(400, str(exc)) from None

    row.developer_id = developer_id
    return row


# ============================================================
# 开发者侧 · 我的应用与定价
# ============================================================


@router.get("/my/apps", response_model=dict[str, Any])
async def my_apps(
    db: AsyncSession = Depends(get_db),
    who: dict = Depends(require_portal_or_admin),
):
    """我的应用：提交状态 + 定价 + 销量 + 收入。"""
    dev = await _developer_of(db, who)

    subs = (await db.execute(
        select(store_models.AppSubmission)
        .where(store_models.AppSubmission.developer_id == dev.id)
        .order_by(store_models.AppSubmission.id.desc())
    )).scalars().all()
    latest: dict[str, store_models.AppSubmission] = {}
    for s in subs:
        latest.setdefault(s.app_key, s)

    keys = list(latest.keys())
    pricing: dict[str, cm.AppPricing] = {}
    sales: dict[str, dict[str, int]] = {}
    installs: dict[str, str] = {}
    if keys:
        # 定价行按 (product, app_key) 配对：同一 app_key 允许在不同产品轴上各有一条价，
        # 只按 app_key 建字典会让后读到的那条覆盖前者，列表显示的价格随查询顺序漂移。
        price_map = {(p.product, p.app_key): p for p in (await db.execute(
            select(cm.AppPricing).where(cm.AppPricing.app_key.in_(keys))
        )).scalars().all()}

        for k, cnt, gross, income in (await db.execute(
            select(cm.AppOrder.app_key,
                   func.count(cm.AppOrder.id),
                   func.coalesce(func.sum(cm.AppOrder.amount_cents), 0),
                   func.coalesce(func.sum(cm.AppOrder.developer_income_cents), 0))
            .where(cm.AppOrder.app_key.in_(keys), cm.AppOrder.status == "paid")
            .group_by(cm.AppOrder.app_key)
        )).all():
            sales[k] = {"order_count": int(cnt), "gross_cents": int(gross), "income_cents": int(income)}

        installs = {
            k: v for k, v in (await db.execute(
                select(InstalledApp.key, InstalledApp.status).where(InstalledApp.key.in_(keys))
            )).all()
        }

    items = []
    for key, sub in latest.items():
        s = sales.get(key, {"order_count": 0, "gross_cents": 0, "income_cents": 0})
        items.append({
            "app_key": key,
            "name": sub.name,
            "version": sub.version,
            "category": sub.category,
            "submission_status": sub.status,
            "submission_id": sub.id,
            "product": sub.product,
            "installed": installs.get(key) == "installed",
            "pricing": _pricing_view(price_map.get((sub.product, key)), key),
            "order_count": s["order_count"],
            "gross_cents": s["gross_cents"],
            "income_cents": s["income_cents"],
            "gross": _yuan(s["gross_cents"]),
            "income": _yuan(s["income_cents"]),
        })
    return {
        "developer": {"id": dev.id, "display_name": dev.display_name, "status": dev.status},
        "wallet": ledger.wallet_dict(await _wallet_of(db, dev.id), dev.id),
        "items": items,
        "total": len(items),
    }


@router.get("/my/apps/{app_key}/pricing", response_model=dict[str, Any])
async def my_get_pricing(
    app_key: str,
    db: AsyncSession = Depends(get_db),
    who: dict = Depends(require_portal_or_admin),
):
    dev = await _developer_of(db, who)
    await _assert_owned(db, app_key, dev.id)
    row = await _pricing_row(db, app_key)
    view = _pricing_view(row, app_key)
    view["effective_fee_bp"] = await ledger.resolve_fee_bp(db, row, dev.id)
    return view


@router.put("/my/apps/{app_key}/pricing", response_model=dict[str, Any])
async def my_set_pricing(
    app_key: str,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    who: dict = Depends(require_portal_or_admin),
):
    """开发者自主定价，即时生效。归属自动钉死为本开发者，扣点不可改。"""
    dev = await _developer_of(db, who)
    await _assert_owned(db, app_key, dev.id)

    row = await _set_pricing(db, app_key, body, developer_id=dev.id, touch_fee=False)
    await db.commit()
    await db.refresh(row)
    log.info("commerce.dev_pricing_updated", app_key=app_key, developer_id=dev.id,
             model=row.model, price_cents=row.price_cents)
    view = _pricing_view(row, app_key)
    view["effective_fee_bp"] = await ledger.resolve_fee_bp(db, row, dev.id)
    return view


@router.get("/my/apps/{app_key}/sales", response_model=dict[str, Any])
async def my_app_sales(
    app_key: str,
    db: AsyncSession = Depends(get_db),
    who: dict = Depends(require_portal_or_admin),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """某应用的销售记录（含分账明细）。"""
    dev = await _developer_of(db, who)
    await _assert_owned(db, app_key, dev.id)

    cond = (cm.AppOrder.app_key == app_key, cm.AppOrder.developer_id == dev.id)
    total = (await db.execute(
        select(func.count(cm.AppOrder.id)).where(*cond)
    )).scalar() or 0
    offset, limit = _page(page, page_size)
    rows = (await db.execute(
        select(cm.AppOrder).where(*cond).order_by(cm.AppOrder.id.desc())
        .offset(offset).limit(limit)
    )).scalars().all()

    agg = (await db.execute(
        select(func.count(cm.AppOrder.id),
               func.coalesce(func.sum(cm.AppOrder.amount_cents), 0),
               func.coalesce(func.sum(cm.AppOrder.platform_fee_cents), 0),
               func.coalesce(func.sum(cm.AppOrder.developer_income_cents), 0))
        .where(*cond, cm.AppOrder.status == "paid")
    )).one()

    return {
        "app_key": app_key,
        "total": int(total),
        "summary": {
            "paid_count": int(agg[0]), "gross_cents": int(agg[1]),
            "platform_fee_cents": int(agg[2]), "income_cents": int(agg[3]),
            "gross": _yuan(agg[1]), "platform_fee": _yuan(agg[2]), "income": _yuan(agg[3]),
        },
        "items": [{
            "order_no": o.order_no, "app_name": o.app_name,
            "buyer_name": o.buyer_name or o.buyer_email,
            "amount_cents": int(o.amount_cents or 0), "amount": _yuan(o.amount_cents),
            "unit_price_cents": int(o.unit_price_cents or 0),
            "list_unit_price_cents": int(o.list_unit_price_cents or 0),
            "list_unit_price": _yuan(o.list_unit_price_cents),
            "is_discounted": pricing.discount_percent(
                int(o.list_unit_price_cents or 0), int(o.unit_price_cents or 0)) is not None,
            "discount_label": pricing.discount_label(pricing.discount_percent(
                int(o.list_unit_price_cents or 0), int(o.unit_price_cents or 0))),
            "promo_label": o.promo_label,
            "platform_fee_cents": int(o.platform_fee_cents or 0),
            "developer_income_cents": int(o.developer_income_cents or 0),
            "income": _yuan(o.developer_income_cents),
            "seats": o.seats, "model": o.model, "status": o.status,
            "settle_status": o.settle_status, "channel": o.channel,
            "paid_at": _iso(o.paid_at), "refunded_at": _iso(o.refunded_at),
            "created_at": _iso(o.created_at),
        } for o in rows],
    }


# ============================================================
# 开发者侧 · 收入与流水
# ============================================================


@router.get("/my/income", response_model=dict[str, Any])
async def my_income(
    db: AsyncSession = Depends(get_db),
    who: dict = Depends(require_portal_or_admin),
):
    """我的收入：钱包三池 + 累计值 + 每月销售趋势（近 12 个月）。"""
    dev = await _developer_of(db, who)
    wallet = await _wallet_of(db, dev.id)

    monthly = (await db.execute(
        select(func.to_char(cm.AppOrder.paid_at, "YYYY-MM").label("ym"),
               func.count(cm.AppOrder.id),
               func.coalesce(func.sum(cm.AppOrder.developer_income_cents), 0))
        .where(cm.AppOrder.developer_id == dev.id, cm.AppOrder.status == "paid",
               cm.AppOrder.paid_at.is_not(None))
        .group_by(text("ym")).order_by(text("ym desc")).limit(12)
    )).all()

    app_rows = (await db.execute(
        select(cm.AppOrder.app_key,
               func.count(cm.AppOrder.id),
               func.coalesce(func.sum(cm.AppOrder.developer_income_cents), 0))
        .where(cm.AppOrder.developer_id == dev.id, cm.AppOrder.status == "paid")
        .group_by(cm.AppOrder.app_key)
        .order_by(func.coalesce(func.sum(cm.AppOrder.developer_income_cents), 0).desc())
    )).all()

    return {
        "wallet": ledger.wallet_dict(wallet, dev.id),
        "settings": {
            "settle_delay_days": await ledger.get_setting_int(db, ledger.SETTING_SETTLE_DAYS, 7),
            "min_withdraw_cents": await ledger.get_setting_int(db, ledger.SETTING_MIN_WITHDRAW, 10000),
            "min_withdraw": _yuan(await ledger.get_setting_int(db, ledger.SETTING_MIN_WITHDRAW, 10000)),
        },
        "monthly": [{"month": m, "order_count": int(c), "income_cents": int(v),
                     "income": _yuan(v)} for m, c, v in monthly],
        "by_app": [{"app_key": k, "order_count": int(c), "income_cents": int(v),
                    "income": _yuan(v)} for k, c, v in app_rows],
    }


@router.get("/my/ledger", response_model=dict[str, Any])
async def my_ledger(
    db: AsyncSession = Depends(get_db),
    who: dict = Depends(require_portal_or_admin),
    type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """资金流水（只增不改，可完全重算余额）。"""
    dev = await _developer_of(db, who)
    cond = [cm.DevLedger.developer_id == dev.id]
    if type:
        cond.append(cm.DevLedger.type == type)

    total = (await db.execute(select(func.count(cm.DevLedger.id)).where(*cond))).scalar() or 0
    offset, limit = _page(page, page_size)
    rows = (await db.execute(
        select(cm.DevLedger).where(*cond).order_by(cm.DevLedger.id.desc())
        .offset(offset).limit(limit)
    )).scalars().all()

    return {
        "total": int(total),
        "wallet": ledger.wallet_dict(await _wallet_of(db, dev.id), dev.id),
        "types": [{"value": k, "label": v} for k, v in ledger.LEDGER_TYPE_LABEL.items()],
        "items": [ledger.ledger_dict(r) for r in rows],
    }


# ============================================================
# 开发者侧 · 提现与收款账户
# ============================================================


@router.get("/my/withdrawals", response_model=dict[str, Any])
async def my_withdrawals(
    db: AsyncSession = Depends(get_db),
    who: dict = Depends(require_portal_or_admin),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    dev = await _developer_of(db, who)
    cond = [cm.DevWithdrawal.developer_id == dev.id]
    if status:
        cond.append(cm.DevWithdrawal.status == status)

    total = (await db.execute(select(func.count(cm.DevWithdrawal.id)).where(*cond))).scalar() or 0
    offset, limit = _page(page, page_size)
    rows = (await db.execute(
        select(cm.DevWithdrawal).where(*cond).order_by(cm.DevWithdrawal.id.desc())
        .offset(offset).limit(limit)
    )).scalars().all()

    agg = (await db.execute(
        select(func.coalesce(func.sum(cm.DevWithdrawal.amount_cents), 0))
        .where(cm.DevWithdrawal.developer_id == dev.id, cm.DevWithdrawal.status == "paid")
    )).scalar() or 0

    return {
        "total": int(total),
        "withdrawn_cents": int(agg),
        "withdrawn": _yuan(agg),
        "wallet": ledger.wallet_dict(await _wallet_of(db, dev.id), dev.id),
        "items": [ledger.withdrawal_dict(w) for w in rows],
    }


@router.post("/my/withdrawals", status_code=201, response_model=dict[str, Any])
async def my_request_withdrawal(
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    who: dict = Depends(require_portal_or_admin),
):
    """发起提现。未传账户信息时取默认收款账户。"""
    dev = await _developer_of(db, who)
    amount = int(body.get("amount_cents") or 0)

    acct = (await db.execute(
        select(cm.DevPayoutAccount).where(cm.DevPayoutAccount.developer_id == dev.id)
    )).scalar_one_or_none()

    try:
        wd = await ledger.request_withdraw(
            db, developer_id=dev.id, amount_cents=amount,
            account_type=str(body.get("account_type") or (acct.account_type if acct else "alipay")),
            account_no=body.get("account_no") or (acct.account_no if acct else None),
            account_name=body.get("account_name") or (acct.account_name if acct else None),
            bank_name=body.get("bank_name") or (acct.bank_name if acct else None),
            remark=body.get("remark"),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    await db.commit()
    return ledger.withdrawal_dict(wd)


@router.get("/my/account", response_model=dict[str, Any])
async def my_get_account(
    db: AsyncSession = Depends(get_db),
    who: dict = Depends(require_portal_or_admin),
):
    dev = await _developer_of(db, who)
    acct = (await db.execute(
        select(cm.DevPayoutAccount).where(cm.DevPayoutAccount.developer_id == dev.id)
    )).scalar_one_or_none()
    return {
        "developer_id": dev.id,
        "account_type": acct.account_type if acct else "alipay",
        "account_no": acct.account_no if acct else None,
        "account_name": acct.account_name if acct else None,
        "bank_name": acct.bank_name if acct else None,
        "updated_at": _iso(acct.updated_at) if acct else None,
    }


@router.put("/my/account", response_model=dict[str, Any])
async def my_set_account(
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    who: dict = Depends(require_portal_or_admin),
):
    dev = await _developer_of(db, who)
    acct = (await db.execute(
        select(cm.DevPayoutAccount).where(cm.DevPayoutAccount.developer_id == dev.id)
    )).scalar_one_or_none()
    if acct is None:
        acct = cm.DevPayoutAccount(developer_id=dev.id)
        db.add(acct)

    acc_type = str(body.get("account_type") or "alipay")
    if acc_type not in ("alipay", "wechat", "bank"):
        raise HTTPException(400, "account_type 必须是 alipay / wechat / bank")
    acct.account_type = acc_type
    acct.account_no = (body.get("account_no") or "").strip() or None
    acct.account_name = (body.get("account_name") or "").strip() or None
    acct.bank_name = (body.get("bank_name") or "").strip() or None
    await db.commit()
    await db.refresh(acct)
    return {
        "developer_id": dev.id, "account_type": acct.account_type,
        "account_no": acct.account_no, "account_name": acct.account_name,
        "bank_name": acct.bank_name, "updated_at": _iso(acct.updated_at),
    }


# ============================================================
# 平台侧 · 报表与结算配置
# ============================================================


@router.get("/market/overview", response_model=dict[str, Any])
async def market_overview(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """平台收入总览。

    三块口径互不重叠：
    - 自营收入 = 平台自己应用的订单**全额**
    - 抽成收入 = 第三方应用订单中平台抽走的部分
    - 开发者应结 = 第三方应用订单中归开发者的净收入（按池细分）
    """
    self_cond = or_(cm.AppOrder.developer_id.is_(None),
                    cm.AppOrder.developer_id == ledger.PLATFORM_DEVELOPER_ID)
    third_cond = (cm.AppOrder.developer_id.is_not(None),
                  cm.AppOrder.developer_id != ledger.PLATFORM_DEVELOPER_ID)

    self_rev = (await db.execute(
        select(func.coalesce(func.sum(cm.AppOrder.amount_cents), 0))
        .where(cm.AppOrder.status == "paid", self_cond)
    )).scalar() or 0
    fee_rev = (await db.execute(
        select(func.coalesce(func.sum(cm.AppOrder.platform_fee_cents), 0))
        .where(cm.AppOrder.status == "paid", *third_cond)
    )).scalar() or 0

    pools = (await db.execute(
        select(func.coalesce(func.sum(cm.DevWallet.pending_cents), 0),
               func.coalesce(func.sum(cm.DevWallet.available_cents), 0),
               func.coalesce(func.sum(cm.DevWallet.frozen_cents), 0),
               func.coalesce(func.sum(cm.DevWallet.total_withdrawn_cents), 0),
               func.coalesce(func.sum(cm.DevWallet.total_refunded_cents), 0))
    )).one()

    paid_cnt, paid_amt = (await db.execute(
        select(func.count(cm.AppOrder.id),
               func.coalesce(func.sum(cm.AppOrder.amount_cents), 0))
        .where(cm.AppOrder.status == "paid")
    )).one()
    refund_cnt = (await db.execute(
        select(func.count(cm.AppOrder.id)).where(cm.AppOrder.status == "refunded")
    )).scalar() or 0
    wd_pending_cnt, wd_pending_amt = (await db.execute(
        select(func.count(cm.DevWithdrawal.id),
               func.coalesce(func.sum(cm.DevWithdrawal.amount_cents), 0))
        .where(cm.DevWithdrawal.status == "pending")
    )).one()
    dev_cnt = (await db.execute(
        select(func.count(store_models.Developer.id))
        .where(store_models.Developer.status == "active")
    )).scalar() or 0

    return {
        "platform_self_revenue_cents": int(self_rev),
        "platform_self_revenue": _yuan(self_rev),
        "platform_commission_cents": int(fee_rev),
        "platform_commission": _yuan(fee_rev),
        "platform_total_cents": int(self_rev) + int(fee_rev),
        "platform_total": _yuan(int(self_rev) + int(fee_rev)),
        "developer_pending_cents": int(pools[0]),
        "developer_available_cents": int(pools[1]),
        "developer_frozen_cents": int(pools[2]),
        "developer_withdrawn_cents": int(pools[3]),
        "developer_refunded_cents": int(pools[4]),
        "developer_pending": _yuan(pools[0]),
        "developer_available": _yuan(pools[1]),
        "developer_frozen": _yuan(pools[2]),
        "paid_order_count": int(paid_cnt),
        "paid_amount_cents": int(paid_amt),
        "paid_amount": _yuan(paid_amt),
        "refunded_order_count": int(refund_cnt),
        "withdrawal_pending_count": int(wd_pending_cnt),
        "withdrawal_pending_cents": int(wd_pending_amt),
        "withdrawal_pending": _yuan(wd_pending_amt),
        "developer_count": int(dev_cnt),
        "settings": await ledger.read_settings(db),
    }


@router.get("/market/settings", response_model=dict[str, Any])
async def market_get_settings(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:read")),
):
    s = await ledger.read_settings(db)
    return {
        **s,
        "platform_fee_percent": f"{s['platform_fee_bp'] / 100:.2f}",
        "min_withdraw": _yuan(s["min_withdraw_cents"]),
        "defaults": {k.split(".", 1)[1]: v for k, v in ledger.SETTING_DEFAULTS.items()},
    }


@router.put("/market/settings", response_model=dict[str, Any])
async def market_set_settings(
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """改全局结算参数。只接受已知键，未知键忽略。"""
    mapping = {
        "platform_fee_bp": (ledger.SETTING_FEE_BP, 0, 10000),
        "settle_delay_days": (ledger.SETTING_SETTLE_DAYS, 0, 365),
        "min_withdraw_cents": (ledger.SETTING_MIN_WITHDRAW, 0, 100_000_00),
        "withdraw_fee_bp": (ledger.SETTING_WITHDRAW_FEE_BP, 0, 10000),
    }
    changed = []
    for field, (key, lo, hi) in mapping.items():
        if field not in body:
            continue
        try:
            val = int(body[field])
        except (TypeError, ValueError):
            raise HTTPException(400, f"{field} 必须是整数")
        if not (lo <= val <= hi):
            raise HTTPException(400, f"{field} 取值范围 {lo} ~ {hi}")
        await ledger.put_setting(db, key, val, user_id=user.id)
        changed.append(field)
    await db.commit()
    log.info("commerce.market_settings_updated", fields=changed, by=user.id)
    s = await ledger.read_settings(db)
    return {**s, "changed": changed}


# ============================================================
# 平台侧 · 商品与扣点
# ============================================================


@router.get("/market/pricing", response_model=dict[str, Any])
async def market_list_pricing(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:read")),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """全量商品：定价 + 归属 + 生效扣点 + 销量。"""
    stmt = select(cm.AppPricing).order_by(cm.AppPricing.app_key.asc())
    if q:
        stmt = stmt.where(cm.AppPricing.app_key.ilike(f"%{q}%"))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    offset, limit = _page(page, page_size)
    rows = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()

    keys = [r.app_key for r in rows]
    sales: dict[str, dict[str, int]] = {}
    names: dict[str, str] = {}
    dev_names: dict[int, str] = {}
    if keys:
        for k, cnt, amt, income in (await db.execute(
            select(cm.AppOrder.app_key, func.count(cm.AppOrder.id),
                   func.coalesce(func.sum(cm.AppOrder.amount_cents), 0),
                   func.coalesce(func.sum(cm.AppOrder.developer_income_cents), 0))
            .where(cm.AppOrder.app_key.in_(keys), cm.AppOrder.status == "paid")
            .group_by(cm.AppOrder.app_key)
        )).all():
            sales[k] = {"order_count": int(cnt), "paid_cents": int(amt), "income_cents": int(income)}
        names = {
            k: n for k, n in (await db.execute(
                select(InstalledApp.key, InstalledApp.name).where(InstalledApp.key.in_(keys))
            )).all()
        }
        dev_ids = {r.developer_id for r in rows if r.developer_id}
        if dev_ids:
            dev_names = {
                i: n for i, n in (await db.execute(
                    select(store_models.Developer.id, store_models.Developer.display_name)
                    .where(store_models.Developer.id.in_(dev_ids))
                )).all()
            }

    default_bp = await ledger.get_setting_int(db, ledger.SETTING_FEE_BP, 2000)
    items = []
    for r in rows:
        s = sales.get(r.app_key, {"order_count": 0, "paid_cents": 0, "income_cents": 0})
        eff = await ledger.resolve_fee_bp(db, r, r.developer_id)
        items.append({
            **_pricing_view(r, r.app_key),
            "app_name": names.get(r.app_key) or r.app_key,
            "owner": "平台自营" if ledger.is_self_operated(r.developer_id)
                     else (dev_names.get(r.developer_id) or f"开发者 #{r.developer_id}"),
            "effective_fee_bp": eff,
            "effective_fee_percent": f"{eff / 100:.2f}",
            "fee_overridden": r.platform_fee_bp is not None,
            **s,
        })
    return {"items": items, "total": int(total), "default_fee_bp": default_bp}


@router.put("/market/pricing/{app_key}", response_model=dict[str, Any])
async def market_set_pricing(
    app_key: str,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """平台侧改定价：可同时设置归属（developer_id）与单应用扣点覆盖。

    ``platform_fee_bp`` 传 null 表示清除覆盖、回落全局默认。
    ``developer_id`` 不传则保留原归属；传 0 / null 表示收归平台自营。
    """
    existing = await _pricing_row(db, app_key)
    if existing is not None and "developer_id" not in body:
        dev_id = existing.developer_id
    elif "developer_id" in body:
        raw = body.get("developer_id")
        dev_id = None if raw in (None, "", 0, "0") else int(raw)
    else:
        dev_id = None

    row = await _set_pricing(db, app_key, body, developer_id=dev_id, touch_fee=True)
    await db.commit()
    await db.refresh(row)
    eff = await ledger.resolve_fee_bp(db, row, row.developer_id)
    log.info("commerce.market_pricing_updated", app_key=app_key, developer_id=row.developer_id,
             price_cents=row.price_cents, fee_bp=row.platform_fee_bp, by=user.id)
    return {
        **_pricing_view(row, app_key),
        "owner": await _owner_name(db, row.developer_id),
        "effective_fee_bp": eff,
        "effective_fee_percent": f"{eff / 100:.2f}",
        "fee_overridden": row.platform_fee_bp is not None,
    }


# ============================================================
# 平台侧 · 开发者与提现
# ============================================================


@router.get("/market/developers", response_model=dict[str, Any])
async def market_list_developers(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:read")),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """开发者列表（含钱包余额与上架应用数）。"""
    stmt = select(store_models.Developer).order_by(store_models.Developer.id.asc())
    if q:
        stmt = stmt.where(store_models.Developer.display_name.ilike(f"%{q}%"))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    offset, limit = _page(page, page_size)
    devs = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()

    ids = [d.id for d in devs]
    wallets: dict[int, cm.DevWallet] = {}
    app_counts: dict[int, int] = {}
    if ids:
        wallets = {w.developer_id: w for w in (await db.execute(
            select(cm.DevWallet).where(cm.DevWallet.developer_id.in_(ids))
        )).scalars().all()}
        for did, cnt in (await db.execute(
            select(store_models.AppSubmission.developer_id, func.count(func.distinct(
                store_models.AppSubmission.app_key)))
            .where(store_models.AppSubmission.developer_id.in_(ids))
            .group_by(store_models.AppSubmission.developer_id)
        )).all():
            app_counts[did] = int(cnt)

    user_ids = [d.user_id for d in devs]
    emails: dict[int, str | None] = {}
    if user_ids:
        try:
            from cenkor_admin.apps.portal import models as portal_models

            emails = {
                uid: mail for uid, mail in (await db.execute(
                    select(portal_models.PortalUser.id, portal_models.PortalUser.email)
                    .where(portal_models.PortalUser.id.in_(user_ids))
                )).all()
            }
        except Exception as e:  # noqa: BLE001 - 邮箱只是展示字段，取不到不影响主流程
            log.warning("commerce.dev_emails_failed", error=str(e))

    items = []
    for d in devs:
        w = wallets.get(d.id)
        items.append({
            "id": d.id, "user_id": d.user_id, "display_name": d.display_name,
            "email": emails.get(d.user_id),
            "status": d.status, "website": d.website,
            "app_count": app_counts.get(d.id, 0),
            "wallet": ledger.wallet_dict(w, d.id),
            "created_at": _iso(d.created_at),
        })
    return {"items": items, "total": int(total)}


@router.get("/market/withdrawals", response_model=dict[str, Any])
async def market_list_withdrawals(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:read")),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    cond = []
    if status:
        cond.append(cm.DevWithdrawal.status == status)
    total = (await db.execute(
        select(func.count(cm.DevWithdrawal.id)).where(*cond) if cond
        else select(func.count(cm.DevWithdrawal.id))
    )).scalar() or 0
    offset, limit = _page(page, page_size)
    stmt = select(cm.DevWithdrawal).order_by(cm.DevWithdrawal.id.desc()).offset(offset).limit(limit)
    if cond:
        stmt = stmt.where(*cond)
    rows = (await db.execute(stmt)).scalars().all()

    names = {}
    ids = {w.developer_id for w in rows}
    if ids:
        names = {
            i: n for i, n in (await db.execute(
                select(store_models.Developer.id, store_models.Developer.display_name)
                .where(store_models.Developer.id.in_(ids))
            )).all()
        }
    return {
        "total": int(total),
        "items": [{**ledger.withdrawal_dict(w),
                   "developer_name": names.get(w.developer_id) or f"#{w.developer_id}"}
                  for w in rows],
    }


@router.post("/market/withdrawals/{wid}/review", response_model=dict[str, Any])
async def market_review_withdrawal(
    wid: int,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """审核提现：approve 通过（待打款）/ reject 驳回（金额退回可提现）。"""
    action = str(body.get("action") or "").strip().lower()
    remark = body.get("remark")
    wd = await db.get(cm.DevWithdrawal, wid)
    if wd is None:
        raise HTTPException(404, "提现单不存在")

    if action == "reject":
        try:
            await ledger.reject_withdraw(db, wd, reviewer_id=user.id, remark=remark)
        except ValueError as e:
            raise HTTPException(400, str(e))
    elif action in ("approve", "pass"):
        if wd.status != "pending":
            raise HTTPException(400, f"当前状态 {wd.status} 不能通过")
        wd.status = "approved"
        wd.reviewed_by = user.id
        wd.reviewed_at = _now()
        wd.review_remark = remark
    else:
        raise HTTPException(400, "action 必须是 approve 或 reject")

    await db.commit()
    await db.refresh(wd)
    log.info("commerce.withdraw_reviewed", withdrawal_id=wid, action=action, by=user.id)
    return ledger.withdrawal_dict(wd)


@router.post("/market/withdrawals/{wid}/pay", response_model=dict[str, Any])
async def market_pay_withdrawal(
    wid: int,
    body: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """标记已打款：记打款凭证，冻结金额出账，计入累计提现。"""
    wd = await db.get(cm.DevWithdrawal, wid)
    if wd is None:
        raise HTTPException(404, "提现单不存在")
    try:
        await ledger.mark_withdraw_paid(db, wd, voucher=body.get("voucher"),
                                        remark=body.get("remark"), reviewer_id=user.id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await db.commit()
    await db.refresh(wd)
    return ledger.withdrawal_dict(wd)


@router.post("/market/developers/{developer_id}/adjust", response_model=dict[str, Any])
async def market_adjust_developer(
    developer_id: int,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """手工调整开发者余额（补偿 / 扣罚）。正数加、负数减，必填备注。"""
    try:
        amount = int(body.get("amount_cents") or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "amount_cents 必须是整数")
    if amount == 0:
        raise HTTPException(400, "调整金额不能为 0")
    pool = str(body.get("pool") or ledger.POOL_AVAILABLE)
    if pool not in (ledger.POOL_AVAILABLE, ledger.POOL_PENDING, ledger.POOL_FROZEN):
        raise HTTPException(400, "pool 必须是 available / pending / frozen")
    remark = (body.get("remark") or "").strip()
    if not remark:
        raise HTTPException(400, "必须填写调整备注")

    dev = await db.get(store_models.Developer, developer_id)
    if dev is None:
        raise HTTPException(404, "开发者不存在")

    await ledger.adjust(db, developer_id=developer_id, amount_cents=amount, pool=pool,
                        remark=f"{remark}（by {user.username or user.id}）")
    await db.commit()
    w = await _wallet_of(db, developer_id)
    log.info("commerce.developer_adjusted", developer_id=developer_id, amount_cents=amount,
             pool=pool, by=user.id)
    return {"developer_id": developer_id, "wallet": ledger.wallet_dict(w, developer_id)}
