"""ERP 总账（GL）API：会计科目 / 记账凭证 / 会计期间 / 期末结转 / 三大报表"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.core.db import get_db

from .models.gl import (
    ErpAccount,
    ErpAccountingPeriod,
    ErpVoucher,
    ErpVoucherEntry,
)

router = APIRouter()

# 默认科目表（新增会计初始化的标准科目）
DEFAULT_ACCOUNTS = [
    # 资产类
    ("1001", "库存现金", "asset", "debit", 1),
    ("1002", "银行存款", "asset", "debit", 2),
    ("1122", "应收账款", "asset", "debit", 3),
    ("1405", "库存商品", "asset", "debit", 4),
    ("1601", "固定资产", "asset", "debit", 5),
    # 负债类
    ("2202", "应付账款", "liability", "credit", 6),
    ("2203", "预收账款", "liability", "credit", 7),
    ("2211", "应付职工薪酬", "liability", "credit", 8),
    # 权益类
    ("4001", "实收资本", "equity", "credit", 9),
    ("4104", "利润分配", "equity", "credit", 10),
    ("4103", "本年利润", "equity", "credit", 11),
    # 收入类
    ("6001", "主营业务收入", "revenue", "credit", 12),
    ("6051", "其他业务收入", "revenue", "credit", 13),
    # 费用类
    ("6401", "主营业务成本", "expense", "debit", 14),
    ("6602", "管理费用", "expense", "debit", 15),
    ("6603", "财务费用", "expense", "debit", 16),
    ("6601", "销售费用", "expense", "debit", 17),
    ("6604", "其他业务成本", "expense", "debit", 18),
]


# ============================================================
# Schemas
# ============================================================

class AccountIn(BaseModel):
    code: str
    name: str
    category: str = "asset"
    direction: str = "debit"
    parent_id: int | None = None
    is_leaf: int = 1
    status: str = "active"
    initial_balance: float = 0.0
    seq: int = 0


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    category: str
    direction: str
    parent_id: int | None = None
    is_leaf: int
    status: str
    initial_balance: float
    seq: int
    created_at: Any


class VoucherEntryIn(BaseModel):
    account_id: int
    summary: str | None = None
    debit: float = 0
    credit: float = 0


class VoucherIn(BaseModel):
    voucher_date: str
    word: str | None = "记"
    source_type: str | None = "manual"
    remark: str | None = None
    entries: list[VoucherEntryIn] = Field(default_factory=list)


class VoucherEntryOut(VoucherEntryIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_code: str | None = None
    account_name: str | None = None


class VoucherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    period: str
    voucher_date: Any
    word: str | None = None
    source_type: str | None = None
    status: str
    total_debit: float
    total_credit: float
    remark: str | None = None
    created_at: Any
    entries: list[VoucherEntryOut] = Field(default_factory=list)


class Page(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[Any]


class PeriodIn(BaseModel):
    period: str  # YYYY-MM


class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int | None = None
    account_code: str | None = None
    account_name: str | None = None
    summary: str | None = None
    debit: float
    credit: float


# ============================================================
# Helpers
# ============================================================

async def _next_code(db: AsyncSession, prefix: str, table) -> str:
    row = (await db.execute(
        select(table.id).order_by(table.id.desc()).limit(1)
    )).scalar_one_or_none()
    n = (row or 0) + 1
    return f"{prefix}{n:04d}"


async def _get_period(db: AsyncSession, period_str: str) -> ErpAccountingPeriod:
    row = (await db.execute(
        select(ErpAccountingPeriod).where(ErpAccountingPeriod.period == period_str)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail=f"会计期间 {period_str} 不存在")
    return row


# ============================================================
# 会计科目 API
# ============================================================

@router.get("/gl/accounts", response_model=Page)
async def list_accounts(
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=500),
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:gl:read")),
):
    stmt = select(ErpAccount)
    count = select(func.count()).select_from(ErpAccount)
    if category:
        stmt = stmt.where(ErpAccount.category == category)
        count = count.where(ErpAccount.category == category)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpAccount.seq, ErpAccount.code).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[AccountOut.model_validate(r) for r in rows])


@router.post("/gl/accounts", response_model=AccountOut, status_code=201)
async def create_account(
    payload: AccountIn,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:gl:write")),
):
    dup = (await db.execute(select(ErpAccount).where(ErpAccount.code == payload.code))).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail=f"科目编码已存在：{payload.code}")
    row = ErpAccount(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return AccountOut.model_validate(row)


@router.post("/gl/accounts/seed")
async def seed_accounts(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:gl:write")),
):
    """初始化默认科目表"""
    existing = (await db.execute(select(func.count()).select_from(ErpAccount))).scalar_one()
    added = 0
    if existing == 0:
        for code, name, category, direction, seq in DEFAULT_ACCOUNTS:
            db.add(ErpAccount(code=code, name=name, category=category,
                              direction=direction, seq=seq))
            added += 1
        await db.commit()
    return {"seeded": added, "total": existing + added}


# ============================================================
# 记账凭证 API
# ============================================================

@router.get("/gl/vouchers", response_model=Page)
async def list_vouchers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = None,
    period: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:gl:read")),
):
    stmt = select(ErpVoucher).where(ErpVoucher.deleted_at.is_(None))
    count = select(func.count()).select_from(ErpVoucher).where(ErpVoucher.deleted_at.is_(None))
    if status:
        stmt = stmt.where(ErpVoucher.status == status); count = count.where(ErpVoucher.status == status)
    if period:
        stmt = stmt.where(ErpVoucher.period == period); count = count.where(ErpVoucher.period == period)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.options(selectinload(ErpVoucher.entries)).order_by(ErpVoucher.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[VoucherOut.model_validate(r) for r in rows])


@router.get("/gl/vouchers/{voucher_id}", response_model=VoucherOut)
async def get_voucher(
    voucher_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:gl:read")),
):
    row = (await db.execute(
        select(ErpVoucher).where(ErpVoucher.id == voucher_id, ErpVoucher.deleted_at.is_(None))
        .options(selectinload(ErpVoucher.entries))
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="凭证不存在")
    return VoucherOut.model_validate(row)


@router.post("/gl/vouchers", response_model=VoucherOut, status_code=201)
async def create_voucher(
    payload: VoucherIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:gl:write")),
):
    if not payload.entries:
        raise HTTPException(status_code=400, detail="凭证至少需要一条分录")
    total_debit = round(sum(e.debit for e in payload.entries), 2)
    total_credit = round(sum(e.credit for e in payload.entries), 2)
    if abs(total_debit - total_credit) > 0.001:
        raise HTTPException(status_code=400, detail=f"借贷不平衡：借 {total_debit} ≠ 贷 {total_credit}")
    if total_debit <= 0:
        raise HTTPException(status_code=400, detail="凭证金额必须大于0")

    # 解析日期与会计期间
    v_date = datetime.strptime(payload.voucher_date, "%Y-%m-%d").date()
    period_str = v_date.strftime("%Y-%m")
    await _get_period(db, period_str)

    code = await _next_code(db, "VCH", ErpVoucher)
    voucher = ErpVoucher(
        code=code, period=period_str, voucher_date=v_date, word=payload.word,
        source_type=payload.source_type, status="posted",
        total_debit=total_debit, total_credit=total_credit, remark=payload.remark,
        created_by=getattr(user, "id", None),
    )
    entries = []
    for e in payload.entries:
        acct = None
        if e.account_id:
            acct = await db.get(ErpAccount, e.account_id)
        entries.append(ErpVoucherEntry(
            account_id=e.account_id,
            account_code=acct.code if acct else None,
            account_name=acct.name if acct else None,
            summary=e.summary, debit=e.debit, credit=e.credit,
        ))
    voucher.entries = entries
    db.add(voucher)
    await db.commit()
    await db.refresh(voucher, attribute_names=["entries"])
    return VoucherOut.model_validate(voucher)


# ============================================================
# 账簿（科目余额汇总 + 分录流水）
# ============================================================

@router.get("/gl/ledger")
async def account_ledger(
    account_id: int | None = None,
    period: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:gl:read")),
):
    """按科目汇总期初+期间借贷+余额；可按科目或期间过滤"""
    entry = select(ErpVoucherEntry)
    if account_id:
        entry = entry.where(ErpVoucherEntry.account_id == account_id)
    if period:
        entry = entry.join(ErpVoucher).where(
            ErpVoucher.period == period, ErpVoucher.status == "posted",
            ErpVoucher.deleted_at.is_(None),
        )
    entries = (await db.execute(entry)).scalars().all()

    totals: dict[int, dict] = {}
    for e in entries:
        acc = e.account_id or 0
        d = totals.setdefault(acc, {"account_id": acc, "account_code": e.account_code,
                                    "account_name": e.account_name, "debit": 0.0, "credit": 0.0})
        d["debit"] = round(d["debit"] + float(e.debit or 0), 2)
        d["credit"] = round(d["credit"] + float(e.credit or 0), 2)

    result = []
    for d in totals.values():
        account = None
        if d["account_id"]:
            account = await db.get(ErpAccount, d["account_id"])
        initial_balance = float(account.initial_balance) if account else 0.0
        direction = account.direction if account else "debit"
        net = d["debit"] - d["credit"]
        if direction == "credit":
            balance = initial_balance - net
        else:
            balance = initial_balance + net
        d["initial_balance"] = initial_balance
        d["balance"] = round(balance, 2)
        result.append(d)
    result.sort(key=lambda x: str(x["account_code"] or ""))
    return {"items": result, "count": len(result)}


@router.get("/gl/entries")
async def list_gl_entries(
    account_id: int | None = None,
    period: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:gl:read")),
):
    stmt = select(ErpVoucherEntry).join(ErpVoucher).where(
        ErpVoucher.status == "posted", ErpVoucher.deleted_at.is_(None))
    count = select(func.count()).select_from(ErpVoucherEntry).join(ErpVoucher).where(
        ErpVoucher.status == "posted", ErpVoucher.deleted_at.is_(None))
    if account_id:
        stmt = stmt.where(ErpVoucherEntry.account_id == account_id)
        count = count.where(ErpVoucherEntry.account_id == account_id)
    if period:
        stmt = stmt.where(ErpVoucher.period == period)
        count = count.where(ErpVoucher.period == period)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpVoucherEntry.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[EntryOut.model_validate(r) for r in rows])


# ============================================================
# 会计期间 API
# ============================================================

@router.get("/gl/periods", response_model=Page)
async def list_periods(
    page: int = Query(1, ge=1),
    page_size: int = Query(60, ge=1, le=120),
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:gl:read")),
):
    stmt = select(ErpAccountingPeriod)
    count = select(func.count()).select_from(ErpAccountingPeriod)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpAccountingPeriod.period.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[{
                    "id": r.id, "period": r.period, "status": r.status,
                    "start_date": str(r.start_date), "end_date": str(r.end_date),
                    "closed_at": r.closed_at,
                } for r in rows])


@router.post("/gl/periods", status_code=201)
async def create_period(
    payload: PeriodIn,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:gl:write")),
):
    dup = (await db.execute(
        select(ErpAccountingPeriod).where(ErpAccountingPeriod.period == payload.period)
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail=f"会计期间已存在：{payload.period}")
    y, m = payload.period.split("-")
    year, month = int(y), int(m)
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="月份不合法")
    # 该月首日与末日
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        import calendar
        end = date(year, month, calendar.monthrange(year, month)[1])
    row = ErpAccountingPeriod(period=payload.period, start_date=start, end_date=end)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"id": row.id, "period": row.period, "status": row.status,
            "start_date": str(start), "end_date": str(end)}


@router.post("/gl/periods/{period}/close")
async def close_period(
    period: str,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:gl:write")),
):
    """期末结转：将当期损益类科目余额结转到本年利润，并关闭期间"""
    row = await _get_period(db, period)
    if row.status == "closed":
        raise HTTPException(status_code=400, detail=f"期间 {period} 已关闭")

    entries = (await db.execute(
        select(ErpVoucherEntry).join(ErpVoucher).where(
            ErpVoucher.period == period, ErpVoucher.status == "posted",
            ErpVoucher.deleted_at.is_(None),
        )
    )).scalars().all()

    # 汇总损益类科目净额：收入(credit)减费用(debit)
    pl_totals: dict[int, dict] = {}
    account_objs: dict[int, ErpAccount | None] = {}
    for e in entries:
        if not e.account_id:
            continue
        acc = await db.get(ErpAccount, e.account_id)
        account_objs[e.account_id] = acc
        if not acc or acc.category not in ("revenue", "expense"):
            continue
        d = pl_totals.setdefault(e.account_id, {"net": 0.0, "category": acc.category})
        d["net"] = round(d["net"] + float(e.debit or 0) - float(e.credit or 0), 2)

    # 结转当期损益到"本年利润"(4103)
    # 收入结转：借收入贷本年利润；费用结转：借本年利润贷费用
    code = await _next_code(db, "YEE", ErpVoucher)
    pl_acct = (await db.execute(select(ErpAccount).where(ErpAccount.code == "4103"))).scalar_one_or_none()
    if not pl_acct:
        raise HTTPException(status_code=400, detail="缺少本年利润科目(4103)，请先初始化科目表")

    closing_entries = []
    total = 0.0
    for acc_id, d in pl_totals.items():
        acc = account_objs.get(acc_id)
        if not acc:
            continue
        if d["category"] == "revenue" and d["net"] != 0:
            # 借收入 贷本年利润
            closing_entries.append(ErpVoucherEntry(
                account_id=acc_id, account_code=acc.code, account_name=acc.name,
                summary="期末结转收入", debit=round(-d["net"], 2), credit=0))
            closing_entries.append(ErpVoucherEntry(
                account_id=pl_acct.id, account_code=pl_acct.code, account_name=pl_acct.name,
                summary="期末结转收入", debit=0, credit=round(-d["net"], 2)))
            total += round(-d["net"], 2)
        elif d["category"] == "expense" and d["net"] != 0:
            closing_entries.append(ErpVoucherEntry(
                account_id=pl_acct.id, account_code=pl_acct.code, account_name=pl_acct.name,
                summary="期末结转费用", debit=round(d["net"], 2), credit=0))
            closing_entries.append(ErpVoucherEntry(
                account_id=acc_id, account_code=acc.code, account_name=acc.name,
                summary="期末结转费用", debit=0, credit=round(d["net"], 2)))
            total += round(d["net"], 2)

    if closing_entries:
        voucher = ErpVoucher(
            code=code, period=period, voucher_date=row.end_date, word="转",
            source_type="period_close", status="posted",
            total_debit=round(total, 2), total_credit=round(total, 2),
            remark=f"期末结转 {period} 损益",
        )
        voucher.entries = closing_entries
        db.add(voucher)

    row.status = "closed"
    row.closed_at = func.now()
    await db.commit()
    return {"period": period, "status": "closed", "closing_entries": len(closing_entries)}


# ============================================================
# 三大报表
# ============================================================

async def _period_balances(db: AsyncSession, period: str) -> dict[int, dict]:
    """统计某会计期间各科目的借贷发生额与余额（考虑期初）"""
    entries = (await db.execute(
        select(ErpVoucherEntry).join(ErpVoucher).where(
            ErpVoucher.period <= period, ErpVoucher.status == "posted",
            ErpVoucher.deleted_at.is_(None),
        )
    )).scalars().all()
    cur = (await db.execute(
        select(ErpVoucherEntry).join(ErpVoucher).where(
            ErpVoucher.period == period, ErpVoucher.status == "posted",
            ErpVoucher.deleted_at.is_(None),
        )
    )).scalars().all()

    accounts = (await db.execute(select(ErpAccount))).scalars().all()
    acct_map = {a.id: a for a in accounts}

    agg: dict[int, dict] = {}
    for a in accounts:
        agg.setdefault(a.id, {
            "cum_debit": 0.0, "cum_credit": 0.0,
            "per_debit": 0.0, "per_credit": 0.0,
            "initial": float(a.initial_balance), "direction": a.direction,
            "category": a.category, "code": a.code, "name": a.name,
        })
    for e in entries:
        d = agg.get(e.account_id)
        if d:
            d["cum_debit"] = round(d["cum_debit"] + float(e.debit or 0), 2)
            d["cum_credit"] = round(d["cum_credit"] + float(e.credit or 0), 2)
    for e in cur:
        d = agg.get(e.account_id)
        if d:
            d["per_debit"] = round(d["per_debit"] + float(e.debit or 0), 2)
            d["per_credit"] = round(d["per_credit"] + float(e.credit or 0), 2)
    for d in agg.values():
        net = d["cum_debit"] - d["cum_credit"]
        d["balance"] = round(d["initial"] + net if d["direction"] == "debit" else d["initial"] - net, 2)
    return agg


@router.get("/gl/balance-sheet")
async def balance_sheet(
    period: str,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:gl:read")),
):
    """资产负债表（简化）：资产 = 负债 + 权益；列示余额与期末余额"""
    await _get_period(db, period)
    agg = await _period_balances(db, period)
    groups = {"asset": [], "liability": [], "equity": [], "revenue": [], "expense": []}
    totals = {"asset": 0.0, "liability": 0.0, "equity": 0.0, "revenue": 0.0, "expense": 0.0}
    for d in agg.values():
        cat = d["category"]
        if cat in groups:
            groups[cat].append(d)
            totals[cat] = round(totals[cat] + d["balance"], 2)
    return {
        "period": period,
        "asset_total": totals["asset"],
        "liability_total": totals["liability"],
        "equity_total": totals["equity"],
        "assets": groups["asset"],
        "liabilities": groups["liability"],
        "equities": groups["equity"],
        "balanced": abs(totals["asset"] - (totals["liability"] + totals["equity"])) < 0.01,
    }


@router.get("/gl/income-statement")
async def income_statement(
    period: str,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:gl:read")),
):
    """利润表（本期发生额）"""
    await _get_period(db, period)
    agg = await _period_balances(db, period)
    revenue_items, expense_items = [], []
    revenue_total = expense_total = 0.0
    for d in agg.values():
        if d["category"] == "revenue":
            amt = d["per_credit"] - d["per_debit"]
            revenue_items.append({**d, "amount": round(amt, 2)})
            revenue_total += amt
        elif d["category"] == "expense":
            amt = d["per_debit"] - d["per_credit"]
            expense_items.append({**d, "amount": round(amt, 2)})
            expense_total += amt
    profit = round(revenue_total - expense_total, 2)
    return {
        "period": period,
        "revenue_items": revenue_items,
        "expense_items": expense_items,
        "revenue_total": round(revenue_total, 2),
        "expense_total": round(expense_total, 2),
        "net_profit": profit,
    }


@router.get("/gl/cash-flow")
async def cash_flow_statement(
    period: str,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:gl:read")),
):
    """现金流量表（简化，基于现/银行账户收付）"""
    await _get_period(db, period)
    cash_accounts = (await db.execute(
        select(ErpAccount).where(ErpAccount.code.in_(["1001", "1002"]))
    )).scalars().all()
    cash_ids = [a.id for a in cash_accounts]
    entries = (await db.execute(
        select(ErpVoucherEntry).join(ErpVoucher).where(
            ErpVoucher.period == period, ErpVoucher.status == "posted",
            ErpVoucher.deleted_at.is_(None),
            ErpVoucherEntry.account_id.in_(cash_ids) if cash_ids else ErpVoucherEntry.account_id == -1,
        )
    )).scalars().all()
    inflow = sum(float(e.debit or 0) for e in entries)
    outflow = sum(float(e.credit or 0) for e in entries)
    return {
        "period": period,
        "cash_inflow": round(inflow, 2),
        "cash_outflow": round(outflow, 2),
        "net_cash": round(inflow - outflow, 2),
    }