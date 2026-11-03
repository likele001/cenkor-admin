"""应用市场账本：钱包 / 流水 / 结算 / 提现。

三条不变量（任何时刻都必须成立）：
1. 钱包三池（available / pending / frozen）之和 = 该开发者全部在账资金
2. 每一分钱的变动都对应至少一条 ``dev_ledger`` 流水
3. ``dev_ledger`` 只增不改 —— 钱包余额永远可由流水完全重算，这是对账依据

记账口径：金额单位统一「分」，只用整数，不做浮点运算。

事务约定：本模块所有函数 **不自行 commit**，由调用方决定事务边界
（``settle_due`` 由调度器调用，也在调用方 commit）。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.commerce import models as cm

log = structlog.get_logger()

# 平台自营开发者：无归属（None）或归属官方账号（id=1）都算平台自己的应用
PLATFORM_DEVELOPER_ID = 1

POOL_AVAILABLE = "available"
POOL_PENDING = "pending"
POOL_FROZEN = "frozen"
_POOL_COL: dict[str, str] = {
    POOL_AVAILABLE: "available_cents",
    POOL_PENDING: "pending_cents",
    POOL_FROZEN: "frozen_cents",
}

TYPE_SALE = "sale"
TYPE_SETTLE = "settle"
TYPE_REFUND = "refund"
TYPE_WITHDRAW_APPLY = "withdraw_apply"
TYPE_WITHDRAW_PAID = "withdraw_paid"
TYPE_WITHDRAW_REJECT = "withdraw_reject"
TYPE_ADJUST = "adjust"

SETTING_FEE_BP = "commerce.platform_fee_bp"
SETTING_SETTLE_DAYS = "commerce.settle_delay_days"
SETTING_MIN_WITHDRAW = "commerce.min_withdraw_cents"
SETTING_WITHDRAW_FEE_BP = "commerce.withdraw_fee_bp"

SETTING_DEFAULTS: dict[str, Any] = {
    SETTING_FEE_BP: 2000,          # 平台默认扣点 20%
    SETTING_SETTLE_DAYS: 7,        # T+7 转可提
    SETTING_MIN_WITHDRAW: 10000,   # 单笔提现门槛 100 元
    SETTING_WITHDRAW_FEE_BP: 0,    # 提现手续费（万分比），0 = 平台承担
}


def now() -> datetime:
    return datetime.now(timezone.utc)


def is_self_operated(developer_id: int | None) -> bool:
    """平台自营判定：收入全额归平台，不进开发者账、不产生提现。"""
    try:
        did = int(developer_id) if developer_id is not None else 0
    except (TypeError, ValueError):
        did = 0
    return did in (0, PLATFORM_DEVELOPER_ID)


# ============================================================
# 平台结算设置（存 system_settings，value 列实为 jsonb）
# ============================================================


async def get_setting(db: AsyncSession, key: str, default: Any = None) -> Any:
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


async def get_setting_int(db: AsyncSession, key: str, default: int = 0) -> int:
    raw = await get_setting(db, key, None)
    if raw is None:
        raw = SETTING_DEFAULTS.get(key, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return int(default)


async def put_setting(
    db: AsyncSession, key: str, value: Any, *, user_id: int | None = None,
    description: str = "应用市场结算设置",
) -> None:
    await db.execute(
        text(
            "insert into system_settings (key, value, description, \"group\", "
            "updated_by, updated_at) "
            "values (:k, cast(:v as jsonb), :d, 'commerce', :u, now()) "
            "on conflict (key) do update set value = excluded.value, "
            "updated_by = excluded.updated_by, updated_at = now()"
        ),
        {
            "k": key,
            "v": json.dumps(value, ensure_ascii=False),
            "d": description,
            "u": user_id,
        },
    )


async def read_settings(db: AsyncSession) -> dict[str, int]:
    """读全部结算参数（缺失项回落默认值）。"""
    out: dict[str, int] = {}
    for key, default in SETTING_DEFAULTS.items():
        out[key.split(".", 1)[1]] = await get_setting_int(db, key, int(default))
    return out


# ============================================================
# 分账计算
# ============================================================


async def resolve_fee_bp(db: AsyncSession, pricing: cm.AppPricing | None,
                         developer_id: int | None) -> int:
    """扣点万分比：单应用覆盖 > 平台全局默认；平台自营恒为 0。"""
    if is_self_operated(developer_id):
        return 0
    if pricing is not None and pricing.platform_fee_bp is not None:
        return max(0, min(10000, int(pricing.platform_fee_bp)))
    return max(0, min(10000, await get_setting_int(db, SETTING_FEE_BP, 2000)))


def split_amount(amount_cents: int, fee_bp: int) -> tuple[int, int]:
    """按万分比拆分 → (平台抽成, 开发者净收入)。抽成四舍五入到分。"""
    amount_cents = max(0, int(amount_cents))
    fee_bp = max(0, min(10000, int(fee_bp)))
    fee = min((amount_cents * fee_bp + 5000) // 10000, amount_cents)
    return fee, amount_cents - fee


# ============================================================
# 钱包与记账原语
# ============================================================


async def ensure_wallet(db: AsyncSession, developer_id: int) -> cm.DevWallet:
    """取得钱包并**加行锁**（并发记账安全）。不存在则原子创建。"""
    await db.execute(
        text("insert into dev_wallets (developer_id) values (:d) "
             "on conflict (developer_id) do nothing"),
        {"d": int(developer_id)},
    )
    return (await db.execute(
        select(cm.DevWallet)
        .where(cm.DevWallet.developer_id == int(developer_id))
        .with_for_update()
    )).scalar_one()


async def post(
    db: AsyncSession,
    developer_id: int,
    *,
    type_: str,
    pool: str,
    amount_cents: int,
    order_no: str | None = None,
    withdrawal_id: int | None = None,
    app_key: str | None = None,
    available_at: datetime | None = None,
    remark: str | None = None,
    totals: dict[str, int] | None = None,
) -> cm.DevLedger:
    """给某个池记一笔账（正数入、负数出），并落流水。

    调用方负责 commit。``totals`` 用于同步累计字段（如 total_income_cents）。
    """
    if pool not in _POOL_COL:
        raise ValueError(f"未知资金池：{pool}")

    wallet = await ensure_wallet(db, developer_id)
    col = _POOL_COL[pool]
    after = int(getattr(wallet, col) or 0) + int(amount_cents)
    setattr(wallet, col, after)
    wallet.updated_at = now()

    for field, delta in (totals or {}).items():
        setattr(wallet, field, int(getattr(wallet, field) or 0) + int(delta))

    row = cm.DevLedger(
        developer_id=int(developer_id),
        type=type_,
        pool=pool,
        amount_cents=int(amount_cents),
        pool_after_cents=after,
        order_no=order_no,
        withdrawal_id=withdrawal_id,
        app_key=app_key,
        available_at=available_at,
        # 只有「待结算的销售收入」需要被结算任务扫到；其余默认已处理
        settled=not (pool == POOL_PENDING and type_ == TYPE_SALE),
        remark=remark,
    )
    db.add(row)
    await db.flush()
    return row


async def _has_ledger(db: AsyncSession, *, order_no: str, type_: str) -> bool:
    """幂等判据：同一订单同一类型只记一次。"""
    return (await db.execute(
        select(cm.DevLedger.id)
        .where(cm.DevLedger.order_no == order_no, cm.DevLedger.type == type_)
        .limit(1)
    )).first() is not None


# ============================================================
# 业务动作：销售入账 / 退款冲正 / 结算解冻
# ============================================================


async def credit_sale(db: AsyncSession, order: cm.AppOrder) -> cm.DevLedger | None:
    """订单支付成功 → 开发者净收入入账（T+N 内先落 pending）。"""
    if is_self_operated(order.developer_id):
        order.settle_status = "none"
        return None

    income = int(order.developer_income_cents or 0)
    if income <= 0:
        order.settle_status = "none"
        return None

    if await _has_ledger(db, order_no=order.order_no, type_=TYPE_SALE):
        return None

    days = max(0, await get_setting_int(db, SETTING_SETTLE_DAYS, 7))
    immediate = days == 0
    lead = await post(
        db,
        order.developer_id,
        type_=TYPE_SALE,
        pool=POOL_AVAILABLE if immediate else POOL_PENDING,
        amount_cents=income,
        order_no=order.order_no,
        app_key=order.app_key,
        available_at=now() if immediate else now() + timedelta(days=days),
        remark=f"销售收入（净）{income / 100:.2f} 元，平台抽成 {int(order.platform_fee_cents or 0) / 100:.2f} 元",
        totals={"total_income_cents": income},
    )
    order.settle_status = "settled" if immediate else "pending"
    order.settled_at = now() if immediate else None
    log.info("commerce.sale_credited", order_no=order.order_no, developer_id=order.developer_id,
             income_cents=income, fee_cents=order.platform_fee_cents, settle_days=days)
    return lead


async def debit_refund(db: AsyncSession, order: cm.AppOrder) -> int:
    """订单退款 → 冲正开发者收入。

    优先扣 ``pending``（结算期内），不足部分扣 ``available`` —— 若开发者已提现，
    ``available`` 允许变负（等价平台垫付），由后续收入抵扣。
    """
    if is_self_operated(order.developer_id):
        return 0

    income = int(order.developer_income_cents or 0)
    if income <= 0:
        return 0
    if await _has_ledger(db, order_no=order.order_no, type_=TYPE_REFUND):
        return 0

    wallet = await ensure_wallet(db, order.developer_id)
    from_pending = min(int(wallet.pending_cents or 0), income)
    from_available = income - from_pending

    if from_pending:
        await post(db, order.developer_id, type_=TYPE_REFUND, pool=POOL_PENDING,
                   amount_cents=-from_pending, order_no=order.order_no,
                   app_key=order.app_key, remark="退款冲正（结算期内）")
    if from_available:
        await post(db, order.developer_id, type_=TYPE_REFUND, pool=POOL_AVAILABLE,
                   amount_cents=-from_available, order_no=order.order_no,
                   app_key=order.app_key, remark="退款冲正（已结算）",
                   totals={"total_refunded_cents": from_available})
    if from_pending:
        wallet.total_refunded_cents = int(wallet.total_refunded_cents or 0) + from_pending

    order.settle_status = "refunded"
    log.info("commerce.sale_refunded", order_no=order.order_no, developer_id=order.developer_id,
             income_cents=income, from_pending=from_pending, from_available=from_available)
    return income


async def settle_due(db: AsyncSession, *, limit: int = 500) -> int:
    """结算任务：把过期的销售收入从 pending 解冻到 available。

    已退款订单不解冻（直接标记处理完）。调用方负责 commit。
    """
    due = (await db.execute(
        select(cm.DevLedger).where(
            cm.DevLedger.type == TYPE_SALE,
            cm.DevLedger.settled.is_(False),
            cm.DevLedger.available_at.is_not(None),
            cm.DevLedger.available_at <= now(),
        ).order_by(cm.DevLedger.id.asc()).limit(limit)
    )).scalars().all()
    if not due:
        return 0

    done = 0
    for row in due:
        if await _has_ledger(db, order_no=row.order_no or "", type_=TYPE_REFUND):
            row.settled = True
            done += 1
            continue

        wallet = await ensure_wallet(db, row.developer_id)
        amount = min(int(row.amount_cents), int(wallet.pending_cents or 0))
        if amount > 0:
            await post(db, row.developer_id, type_=TYPE_SETTLE, pool=POOL_PENDING,
                       amount_cents=-amount, order_no=row.order_no, app_key=row.app_key,
                       remark="结算解冻：转入可提现")
            await post(db, row.developer_id, type_=TYPE_SETTLE, pool=POOL_AVAILABLE,
                       amount_cents=amount, order_no=row.order_no, app_key=row.app_key,
                       remark="结算解冻：转入可提现")
            if row.order_no:
                await db.execute(
                    update(cm.AppOrder)
                    .where(cm.AppOrder.order_no == row.order_no)
                    .values(settle_status="settled", settled_at=now())
                )
        row.settled = True
        done += 1

    if done:
        log.info("commerce.settle_due", processed=done)
    return done


# ============================================================
# 提现
# ============================================================


async def request_withdraw(
    db: AsyncSession,
    *,
    developer_id: int,
    amount_cents: int,
    account_type: str = "alipay",
    account_no: str | None = None,
    account_name: str | None = None,
    bank_name: str | None = None,
    remark: str | None = None,
) -> cm.DevWithdrawal:
    """提现申请：可提余额划入冻结池，等平台审核打款。抛 ValueError 表示业务拒绝。"""
    amount_cents = int(amount_cents or 0)
    if amount_cents <= 0:
        raise ValueError("提现金额必须大于 0")
    if not account_no:
        raise ValueError("请先填写收款账户")
    if not account_name:
        raise ValueError("请先填写收款人姓名")

    wallet = await ensure_wallet(db, developer_id)
    available = int(wallet.available_cents or 0)
    min_cents = await get_setting_int(db, SETTING_MIN_WITHDRAW, 10000)
    if amount_cents < min_cents:
        raise ValueError(f"单笔提现不得低于 {min_cents / 100:.2f} 元")
    if amount_cents > available:
        raise ValueError(f"可提现余额不足，当前 {available / 100:.2f} 元")

    fee_bp = max(0, await get_setting_int(db, SETTING_WITHDRAW_FEE_BP, 0))
    fee = (amount_cents * fee_bp + 5000) // 10000

    wd = cm.DevWithdrawal(
        developer_id=int(developer_id),
        amount_cents=amount_cents,
        fee_cents=fee,
        actual_cents=amount_cents - fee,
        account_type=account_type or "alipay",
        account_no=account_no,
        account_name=account_name,
        bank_name=bank_name,
        status="pending",
        remark=remark,
    )
    db.add(wd)
    await db.flush()

    await post(db, developer_id, type_=TYPE_WITHDRAW_APPLY, pool=POOL_AVAILABLE,
               amount_cents=-amount_cents, withdrawal_id=wd.id, remark="提现申请：划入冻结")
    await post(db, developer_id, type_=TYPE_WITHDRAW_APPLY, pool=POOL_FROZEN,
               amount_cents=amount_cents, withdrawal_id=wd.id, remark="提现申请：划入冻结")
    log.info("commerce.withdraw_requested", withdrawal_id=wd.id, developer_id=developer_id,
             amount_cents=amount_cents)
    return wd


async def reject_withdraw(db: AsyncSession, wd: cm.DevWithdrawal, *,
                          reviewer_id: int | None = None, remark: str | None = None) -> None:
    """驳回提现：冻结金额原路退回可提余额。调用方 commit。"""
    if wd.status == "paid":
        raise ValueError("已打款的提现不能驳回")
    if wd.status == "rejected":
        return
    await post(db, wd.developer_id, type_=TYPE_WITHDRAW_REJECT, pool=POOL_FROZEN,
               amount_cents=-int(wd.amount_cents), withdrawal_id=wd.id, remark="提现驳回：解冻")
    await post(db, wd.developer_id, type_=TYPE_WITHDRAW_REJECT, pool=POOL_AVAILABLE,
               amount_cents=int(wd.amount_cents), withdrawal_id=wd.id, remark="提现驳回：退回可提现")
    wd.status = "rejected"
    wd.reviewed_by = reviewer_id
    wd.reviewed_at = now()
    wd.review_remark = remark
    log.info("commerce.withdraw_rejected", withdrawal_id=wd.id, by=reviewer_id)


async def mark_withdraw_paid(db: AsyncSession, wd: cm.DevWithdrawal, *,
                             voucher: str | None = None, remark: str | None = None,
                             reviewer_id: int | None = None) -> None:
    """标记已打款：冻结池出账并累计已提现。调用方 commit。"""
    if wd.status == "paid":
        return
    if wd.status == "rejected":
        raise ValueError("已驳回的提现不能标记打款")
    await post(db, wd.developer_id, type_=TYPE_WITHDRAW_PAID, pool=POOL_FROZEN,
               amount_cents=-int(wd.amount_cents), withdrawal_id=wd.id,
               remark=f"提现打款{'（凭证：%s）' % voucher if voucher else ''}",
               totals={"total_withdrawn_cents": int(wd.amount_cents)})
    wd.status = "paid"
    wd.paid_at = now()
    wd.pay_voucher = voucher
    if remark:
        wd.remark = ((wd.remark + " | ") if wd.remark else "") + remark
    if reviewer_id:
        wd.reviewed_by = wd.reviewed_by or reviewer_id
        wd.reviewed_at = wd.reviewed_at or now()
    log.info("commerce.withdraw_paid", withdrawal_id=wd.id, amount_cents=wd.amount_cents, by=reviewer_id)


async def adjust(db: AsyncSession, *, developer_id: int, amount_cents: int,
                 pool: str = POOL_AVAILABLE, remark: str) -> cm.DevLedger:
    """平台手工调整（补偿 / 扣罚）。调用方 commit。"""
    return await post(db, developer_id, type_=TYPE_ADJUST, pool=pool,
                      amount_cents=int(amount_cents), remark=remark)


# ============================================================
# 序列化
# ============================================================


def wallet_dict(w: cm.DevWallet | None, developer_id: int | None = None) -> dict[str, Any]:
    if w is None:
        return {
            "developer_id": developer_id,
            "available_cents": 0, "pending_cents": 0, "frozen_cents": 0,
            "total_cents": 0,
            "available": "0.00", "pending": "0.00", "frozen": "0.00", "total": "0.00",
            "total_income_cents": 0, "total_withdrawn_cents": 0, "total_refunded_cents": 0,
            "total_income": "0.00", "total_withdrawn": "0.00", "total_refunded": "0.00",
        }
    avail = int(w.available_cents or 0)
    pend = int(w.pending_cents or 0)
    frozen = int(w.frozen_cents or 0)
    return {
        "developer_id": w.developer_id,
        "available_cents": avail, "pending_cents": pend, "frozen_cents": frozen,
        "total_cents": avail + pend + frozen,
        "available": f"{avail / 100:.2f}", "pending": f"{pend / 100:.2f}",
        "frozen": f"{frozen / 100:.2f}", "total": f"{(avail + pend + frozen) / 100:.2f}",
        "total_income_cents": int(w.total_income_cents or 0),
        "total_withdrawn_cents": int(w.total_withdrawn_cents or 0),
        "total_refunded_cents": int(w.total_refunded_cents or 0),
        "total_income": f"{int(w.total_income_cents or 0) / 100:.2f}",
        "total_withdrawn": f"{int(w.total_withdrawn_cents or 0) / 100:.2f}",
        "total_refunded": f"{int(w.total_refunded_cents or 0) / 100:.2f}",
    }


LEDGER_TYPE_LABEL: dict[str, str] = {
    TYPE_SALE: "销售收入",
    TYPE_SETTLE: "结算解冻",
    TYPE_REFUND: "退款冲正",
    TYPE_WITHDRAW_APPLY: "提现冻结",
    TYPE_WITHDRAW_PAID: "提现打款",
    TYPE_WITHDRAW_REJECT: "提现驳回",
    TYPE_ADJUST: "平台调整",
}


def ledger_dict(row: cm.DevLedger) -> dict[str, Any]:
    return {
        "id": row.id,
        "type": row.type,
        "type_label": LEDGER_TYPE_LABEL.get(row.type, row.type),
        "pool": row.pool,
        "amount_cents": int(row.amount_cents or 0),
        "amount": f"{int(row.amount_cents or 0) / 100:.2f}",
        "pool_after_cents": int(row.pool_after_cents or 0),
        "pool_after": f"{int(row.pool_after_cents or 0) / 100:.2f}",
        "order_no": row.order_no,
        "withdrawal_id": row.withdrawal_id,
        "app_key": row.app_key,
        "available_at": row.available_at.isoformat() if row.available_at else None,
        "settled": bool(row.settled),
        "remark": row.remark,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def withdrawal_dict(wd: cm.DevWithdrawal) -> dict[str, Any]:
    return {
        "id": wd.id,
        "developer_id": wd.developer_id,
        "amount_cents": int(wd.amount_cents or 0),
        "amount": f"{int(wd.amount_cents or 0) / 100:.2f}",
        "fee_cents": int(wd.fee_cents or 0),
        "fee": f"{int(wd.fee_cents or 0) / 100:.2f}",
        "actual_cents": int(wd.actual_cents or 0),
        "actual": f"{int(wd.actual_cents or 0) / 100:.2f}",
        "account_type": wd.account_type,
        "account_no": wd.account_no,
        "account_name": wd.account_name,
        "bank_name": wd.bank_name,
        "status": wd.status,
        "reviewed_by": wd.reviewed_by,
        "reviewed_at": wd.reviewed_at.isoformat() if wd.reviewed_at else None,
        "review_remark": wd.review_remark,
        "paid_at": wd.paid_at.isoformat() if wd.paid_at else None,
        "pay_voucher": wd.pay_voucher,
        "remark": wd.remark,
        "created_at": wd.created_at.isoformat() if wd.created_at else None,
    }
