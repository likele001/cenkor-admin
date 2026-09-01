"""ERP 财务模块 API（销售发票 + 采购发票 + 收付款 + 应收应付）"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.core.db import get_db

from .models.sales import ErpSalesOrder
from .models.purchase import ErpPurchaseOrder
from .models.finance import (
    ErpAccountPayable,
    ErpAccountReceivable,
    ErpInvoice,
    ErpPayment,
    ErpPurchaseInvoice,
)

router = APIRouter()


# ============================================================
# Schemas
# ============================================================

class InvoiceIn(BaseModel):
    sales_order_id: int | None = None
    customer_id: int
    invoice_date: str | None = None
    due_date: str | None = None
    currency: str = "CNY"
    amount: float = 0
    tax_total: float = 0
    total_amount: float = 0
    notes: str | None = None


class InvoiceOut(InvoiceIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    status: str
    paid_amount: float
    created_at: Any


class PurchaseInvoiceIn(BaseModel):
    purchase_order_id: int | None = None
    supplier_id: int
    invoice_date: str | None = None
    due_date: str | None = None
    currency: str = "CNY"
    amount: float = 0
    tax_total: float = 0
    total_amount: float = 0
    notes: str | None = None


class PurchaseInvoiceOut(PurchaseInvoiceIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    status: str
    paid_amount: float
    created_at: Any


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    direction: str
    method: str | None = None
    amount: float
    paid_at: Any = None
    ref_type: str | None = None
    ref_id: int | None = None
    customer_id: int | None = None
    supplier_id: int | None = None
    remark: str | None = None
    created_at: Any


class ReceivableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    customer_id: int | None = None
    invoice_id: int | None = None
    source_type: str | None = None
    amount: float
    paid_amount: float
    balance: float
    due_date: Any = None
    status: str
    created_at: Any


class PayableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    supplier_id: int | None = None
    invoice_id: int | None = None
    source_type: str | None = None
    amount: float
    paid_amount: float
    balance: float
    due_date: Any = None
    status: str
    created_at: Any


class Page(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[Any]


class ShipmentConfirmBody(BaseModel):
    warehouse_id: int | None = None


# ============================================================
# Helpers
# ============================================================

async def _next_code(db: AsyncSession, prefix: str, table) -> str:
    row = (await db.execute(
        select(table.id).order_by(table.id.desc()).limit(1)
    )).scalar_one_or_none()
    n = (row or 0) + 1
    return f"{prefix}{n:04d}"


# 发票创建时同步创建应收/应付
async def _gen_receivable(db, invoice: ErpInvoice) -> None:
    balance = float(invoice.total_amount) - float(invoice.paid_amount)
    db.add(ErpAccountReceivable(
        customer_id=invoice.customer_id, invoice_id=invoice.id,
        source_type="invoice", source_id=invoice.id,
        amount=float(invoice.total_amount), paid_amount=float(invoice.paid_amount),
        balance=round(balance, 2), due_date=invoice.due_date,
        status="settled" if balance <= 0 else "open",
    ))


async def _gen_payable(db, invoice: ErpPurchaseInvoice) -> None:
    balance = float(invoice.total_amount) - float(invoice.paid_amount)
    db.add(ErpAccountPayable(
        supplier_id=invoice.supplier_id, invoice_id=invoice.id,
        source_type="purchase_invoice", source_id=invoice.id,
        amount=float(invoice.total_amount), paid_amount=float(invoice.paid_amount),
        balance=round(balance, 2), due_date=invoice.due_date,
        status="settled" if balance <= 0 else "open",
    ))


async def _refresh_receivable_status(db, invoice_id: int, paid: float, direction: str) -> None:
    if direction == "in":
        ar = (await db.execute(
            select(ErpAccountReceivable).where(
                ErpAccountReceivable.invoice_id == invoice_id,
                ErpAccountReceivable.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        if ar:
            ar.paid_amount = float(ar.paid_amount) + paid
            ar.balance = round(float(ar.amount) - float(ar.paid_amount), 2)
            ar.status = "settled" if ar.balance <= 0 else ("partial" if ar.paid_amount > 0 else "open")


async def _refresh_payable_status(db, invoice_id: int, paid: float, direction: str) -> None:
    if direction == "out":
        ap = (await db.execute(
            select(ErpAccountPayable).where(
                ErpAccountPayable.invoice_id == invoice_id,
                ErpAccountPayable.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        if ap:
            ap.paid_amount = float(ap.paid_amount) + paid
            ap.balance = round(float(ap.amount) - float(ap.paid_amount), 2)
            ap.status = "settled" if ap.balance <= 0 else ("partial" if ap.paid_amount > 0 else "open")


# ============================================================
# 销售发票 API
# ============================================================

@router.get("/finance/invoices", response_model=Page)
async def list_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = None,
    customer_id: int | None = None,
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:finance:read")),
):
    stmt = select(ErpInvoice).where(ErpInvoice.deleted_at.is_(None))
    count = select(func.count()).select_from(ErpInvoice).where(ErpInvoice.deleted_at.is_(None))
    if status:
        stmt = stmt.where(ErpInvoice.status == status); count = count.where(ErpInvoice.status == status)
    if customer_id:
        stmt = stmt.where(ErpInvoice.customer_id == customer_id); count = count.where(ErpInvoice.customer_id == customer_id)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(ErpInvoice.code.ilike(like)); count = count.where(ErpInvoice.code.ilike(like))
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpInvoice.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[InvoiceOut.model_validate(r) for r in rows])


@router.post("/finance/invoices", response_model=InvoiceOut, status_code=201)
async def create_invoice(
    payload: InvoiceIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:finance:write")),
):
    if payload.sales_order_id:
        so = await db.get(ErpSalesOrder, payload.sales_order_id)
        if not so or so.deleted_at:
            raise HTTPException(status_code=400, detail="销售订单不存在")
        if payload.total_amount <= 0:
            payload.total_amount = float(so.total_amount) - float(so.paid_amount)
        if payload.customer_id != so.customer_id:
            payload.customer_id = so.customer_id
    code = await _next_code(db, "INV", ErpInvoice)
    inv = ErpInvoice(
        code=code, sales_order_id=payload.sales_order_id, customer_id=payload.customer_id,
        invoice_date=payload.invoice_date, due_date=payload.due_date, currency=payload.currency,
        amount=payload.amount, tax_total=payload.tax_total, total_amount=payload.total_amount,
        notes=payload.notes,
    )
    db.add(inv)
    await db.flush()
    await _gen_receivable(db, inv)
    await db.commit()
    await db.refresh(inv)
    return InvoiceOut.model_validate(inv)


# ============================================================
# 采购发票 API
# ============================================================

@router.get("/finance/purchase-invoices", response_model=Page)
async def list_purchase_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = None,
    supplier_id: int | None = None,
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:finance:read")),
):
    stmt = select(ErpPurchaseInvoice).where(ErpPurchaseInvoice.deleted_at.is_(None))
    count = select(func.count()).select_from(ErpPurchaseInvoice).where(ErpPurchaseInvoice.deleted_at.is_(None))
    if status:
        stmt = stmt.where(ErpPurchaseInvoice.status == status); count = count.where(ErpPurchaseInvoice.status == status)
    if supplier_id:
        stmt = stmt.where(ErpPurchaseInvoice.supplier_id == supplier_id); count = count.where(ErpPurchaseInvoice.supplier_id == supplier_id)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(ErpPurchaseInvoice.code.ilike(like)); count = count.where(ErpPurchaseInvoice.code.ilike(like))
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpPurchaseInvoice.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[PurchaseInvoiceOut.model_validate(r) for r in rows])


@router.post("/finance/purchase-invoices", response_model=PurchaseInvoiceOut, status_code=201)
async def create_purchase_invoice(
    payload: PurchaseInvoiceIn,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:finance:write")),
):
    if payload.purchase_order_id:
        po = await db.get(ErpPurchaseOrder, payload.purchase_order_id)
        if not po or po.deleted_at:
            raise HTTPException(status_code=400, detail="采购订单不存在")
        if payload.total_amount <= 0:
            payload.total_amount = float(po.total_amount) - float(po.paid_amount)
        if payload.supplier_id != po.supplier_id:
            payload.supplier_id = po.supplier_id
    code = await _next_code(db, "PINV", ErpPurchaseInvoice)
    inv = ErpPurchaseInvoice(
        code=code, purchase_order_id=payload.purchase_order_id, supplier_id=payload.supplier_id,
        invoice_date=payload.invoice_date, due_date=payload.due_date, currency=payload.currency,
        amount=payload.amount, tax_total=payload.tax_total, total_amount=payload.total_amount,
        notes=payload.notes,
    )
    db.add(inv)
    await db.flush()
    await _gen_payable(db, inv)
    await db.commit()
    await db.refresh(inv)
    return PurchaseInvoiceOut.model_validate(inv)


# ============================================================
# 收款 API（应收核销）
# ============================================================

@router.post("/finance/invoices/{invoice_id}/receive")
async def receive_invoice_payment(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    body: dict | None = None,
    user: auth_models.User = Depends(require_permission("erp:finance:write")),
):
    inv = (await db.execute(
        select(ErpInvoice).where(ErpInvoice.id == invoice_id, ErpInvoice.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="发票不存在")
    body = body or {}
    amount = float(body.get("amount") or 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="收款金额必须大于0")
    left = float(inv.total_amount) - float(inv.paid_amount)
    if amount > left:
        raise HTTPException(status_code=400, detail=f"收款金额超过未收余额 {left:.2f}")
    inv.paid_amount = float(inv.paid_amount) + amount
    if float(inv.paid_amount) >= float(inv.total_amount) - 0.001:
        inv.status = "paid"
    code = await _next_code(db, "PMT", ErpPayment)
    db.add(ErpPayment(
        code=code, direction="in", method=body.get("method") or "bank", amount=amount,
        paid_at=body.get("paid_at"), ref_type="invoice", ref_id=inv.id,
        customer_id=inv.customer_id, remark=body.get("remark"),
        operator_user_id=getattr(user, "id", None),
    ))
    await _refresh_receivable_status(db, inv.id, amount, "in")
    # 联动销售订单已收
    if inv.sales_order_id:
        so = await db.get(ErpSalesOrder, inv.sales_order_id)
        if so:
            so.paid_amount = float(so.paid_amount) + amount
            so.payment_status = "paid" if float(so.paid_amount) >= float(so.total_amount) - 0.001 else "partial"
    await db.commit()
    return {"id": inv.id, "code": inv.code, "status": inv.status, "paid_amount": float(inv.paid_amount)}


# ============================================================
# 付款 API（应付核销）
# ============================================================

@router.post("/finance/purchase-invoices/{invoice_id}/pay")
async def pay_purchase_invoice(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    body: dict | None = None,
    user: auth_models.User = Depends(require_permission("erp:finance:write")),
):
    inv = (await db.execute(
        select(ErpPurchaseInvoice).where(ErpPurchaseInvoice.id == invoice_id, ErpPurchaseInvoice.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="采购发票不存在")
    body = body or {}
    amount = float(body.get("amount") or 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="付款金额必须大于0")
    left = float(inv.total_amount) - float(inv.paid_amount)
    if amount > left:
        raise HTTPException(status_code=400, detail=f"付款金额超过未付余额 {left:.2f}")
    inv.paid_amount = float(inv.paid_amount) + amount
    if float(inv.paid_amount) >= float(inv.total_amount) - 0.001:
        inv.status = "paid"
    code = await _next_code(db, "PMT", ErpPayment)
    db.add(ErpPayment(
        code=code, direction="out", method=body.get("method") or "bank", amount=amount,
        paid_at=body.get("paid_at"), ref_type="purchase_invoice", ref_id=inv.id,
        supplier_id=inv.supplier_id, remark=body.get("remark"),
        operator_user_id=getattr(user, "id", None),
    ))
    await _refresh_payable_status(db, inv.id, amount, "out")
    if inv.purchase_order_id:
        po = await db.get(ErpPurchaseOrder, inv.purchase_order_id)
        if po:
            po.paid_amount = float(po.paid_amount) + amount
            po.payment_status = "paid" if float(po.paid_amount) >= float(po.total_amount) - 0.001 else "partial"
    await db.commit()
    return {"id": inv.id, "code": inv.code, "status": inv.status, "paid_amount": float(inv.paid_amount)}


# ============================================================
# 收付款流水 & 应收应付查询
# ============================================================

@router.get("/finance/payments", response_model=Page)
async def list_payments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    direction: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:finance:read")),
):
    stmt = select(ErpPayment)
    count = select(func.count()).select_from(ErpPayment)
    if direction:
        stmt = stmt.where(ErpPayment.direction == direction); count = count.where(ErpPayment.direction == direction)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpPayment.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[PaymentOut.model_validate(r) for r in rows])


@router.get("/finance/receivables", response_model=Page)
async def list_receivables(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = None,
    customer_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:finance:read")),
):
    stmt = select(ErpAccountReceivable).where(ErpAccountReceivable.deleted_at.is_(None))
    count = select(func.count()).select_from(ErpAccountReceivable).where(ErpAccountReceivable.deleted_at.is_(None))
    if status:
        stmt = stmt.where(ErpAccountReceivable.status == status); count = count.where(ErpAccountReceivable.status == status)
    if customer_id:
        stmt = stmt.where(ErpAccountReceivable.customer_id == customer_id); count = count.where(ErpAccountReceivable.customer_id == customer_id)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpAccountReceivable.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[ReceivableOut.model_validate(r) for r in rows])


@router.get("/finance/payables", response_model=Page)
async def list_payables(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = None,
    supplier_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:finance:read")),
):
    stmt = select(ErpAccountPayable).where(ErpAccountPayable.deleted_at.is_(None))
    count = select(func.count()).select_from(ErpAccountPayable).where(ErpAccountPayable.deleted_at.is_(None))
    if status:
        stmt = stmt.where(ErpAccountPayable.status == status); count = count.where(ErpAccountPayable.status == status)
    if supplier_id:
        stmt = stmt.where(ErpAccountPayable.supplier_id == supplier_id); count = count.where(ErpAccountPayable.supplier_id == supplier_id)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpAccountPayable.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[PayableOut.model_validate(r) for r in rows])


@router.get("/finance/overview")
async def finance_overview(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:finance:read")),
):
    """财务总览：应收/应付/已收/已付汇总"""
    async def _sums(table, amount_col, status_col=None):
        stmt = select(
            func.coalesce(func.sum(getattr(table, amount_col)), 0.0),
            func.count(table.id),
        ).where(getattr(table, "deleted_at").is_(None))
        if status_col:
            stmt = stmt.where(getattr(table, status_col) != "settled")
        row = (await db.execute(stmt)).one()
        return float(row[0]), row[1]
    ar_amount, ar_count = await _sums(ErpAccountReceivable, "balance")
    ap_amount, ap_count = await _sums(ErpAccountPayable, "balance")
    paid_row = (await db.execute(
        select(func.coalesce(func.sum(ErpPayment.amount), 0.0)).where(ErpPayment.direction == "in")
    )).scalar_one()
    spent_row = (await db.execute(
        select(func.coalesce(func.sum(ErpPayment.amount), 0.0)).where(ErpPayment.direction == "out")
    )).scalar_one()
    return {
        "receivable_balance": ar_amount,
        "receivable_count": ar_count,
        "payable_balance": ap_amount,
        "payable_count": ap_count,
        "received_total": float(paid_row),
        "paid_total": float(spent_row),
        "net_cash": round(float(paid_row) - float(spent_row), 2),
    }