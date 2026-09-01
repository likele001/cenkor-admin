"""ERP 销售订单模块 API（报价单 + 销售订单 + 出货）"""
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

from .models.customer import ErpCustomer
from .models.sales import (
    ErpQuotation,
    ErpQuotationItem,
    ErpSalesOrder,
    ErpSalesOrderItem,
    ErpShipment,
    ErpShipmentItem,
)

router = APIRouter()


# ============================================================
# Schemas
# ============================================================

class SOrderItemIn(BaseModel):
    product_id: int | None = None
    product_code: str | None = None
    product_name: str | None = None
    spec: str | None = None
    quantity: float = Field(1, gt=0)
    unit: str | None = None
    unit_price: float = 0
    tax_rate: float = 0
    sort: int = 0


class SOrderItemOut(SOrderItemIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    amount: float
    tax_amount: float = 0


class QuotationIn(BaseModel):
    code: str | None = None
    customer_id: int
    contact_id: int | None = None
    quote_date: str | None = None
    valid_until: str | None = None
    currency: str = "CNY"
    discount: float = 0
    notes: str | None = None
    items: list[SOrderItemIn] = []


class QuotationOut(QuotationIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    subtotal: float
    tax_total: float
    total_amount: float
    owner_user_id: int | None = None
    created_at: Any
    items: list[SOrderItemOut] = []


class QuotationBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    customer_id: int
    status: str
    quote_date: Any = None
    total_amount: float
    owner_user_id: int | None = None
    created_at: Any


class SalesOrderIn(BaseModel):
    code: str | None = None
    customer_id: int
    contact_id: int | None = None
    quotation_id: int | None = None
    order_date: str | None = None
    delivery_date: str | None = None
    currency: str = "CNY"
    discount: float = 0
    notes: str | None = None
    items: list[SOrderItemIn] = []


class SalesOrderOut(SalesOrderIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    subtotal: float
    tax_total: float
    total_amount: float
    paid_amount: float
    payment_status: str
    owner_user_id: int | None = None
    created_at: Any
    items: list[SOrderItemOut] = []


class SalesOrderBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    customer_id: int
    status: str
    order_date: Any = None
    total_amount: float
    payment_status: str
    owner_user_id: int | None = None
    created_at: Any


class Page(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[Any]


class ShipmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    sales_order_id: int
    status: str
    ship_date: Any = None
    receiver: str | None = None
    tracking_no: str | None = None
    created_at: Any


# ============================================================
# Helpers
# ============================================================

async def _next_code(db: AsyncSession, prefix: str, table) -> str:
    row = (await db.execute(
        select(table.id).order_by(table.id.desc()).limit(1)
    )).scalar_one_or_none()
    n = (row or 0) + 1
    return f"{prefix}{n:04d}"


def _compute(items: list[SOrderItemIn]) -> tuple[float, float]:
    subtotal = 0.0
    tax_total = 0.0
    for it in items:
        amount = float(it.quantity) * float(it.unit_price)
        subtotal += amount
        tax_total += amount * float(it.tax_rate or 0) / 100
    return round(subtotal, 2), round(tax_total, 2)


def _item_out(row) -> SOrderItemOut:
    amount = round(float(row.quantity) * float(row.unit_price), 2)
    tax_amount = round(amount * float(row.tax_rate or 0) / 100, 2)
    return SOrderItemOut(
        id=row.id, product_id=row.product_id, product_code=row.product_code,
        product_name=row.product_name, spec=row.spec, quantity=row.quantity,
        unit=row.unit, unit_price=row.unit_price, tax_rate=row.tax_rate, sort=row.sort,
        amount=amount, tax_amount=tax_amount,
    )


def _build_quotation_out(row: ErpQuotation) -> QuotationOut:
    subtotal, tax_total = _compute(
        [type("I", (), {"quantity": it.quantity, "unit_price": it.unit_price, "tax_rate": it.tax_rate}) for it in row.items]
    )
    return QuotationOut(
        id=row.id, code=row.code, customer_id=row.customer_id, contact_id=row.contact_id,
        quote_date=row.quote_date, valid_until=row.valid_until, currency=row.currency,
        discount=row.discount, notes=row.notes, status=row.status, subtotal=subtotal,
        tax_total=tax_total, total_amount=row.total_amount, owner_user_id=row.owner_user_id,
        created_at=row.created_at, items=[_item_out(it) for it in row.items],
    )


async def _get_quotation(db: AsyncSession, qid: int) -> ErpQuotation:
    row = (await db.execute(
        select(ErpQuotation)
        .where(ErpQuotation.id == qid, ErpQuotation.deleted_at.is_(None))
        .options(selectinload(ErpQuotation.items))
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="报价单不存在")
    return row


async def _get_order(db: AsyncSession, oid: int) -> ErpSalesOrder:
    row = (await db.execute(
        select(ErpSalesOrder)
        .where(ErpSalesOrder.id == oid, ErpSalesOrder.deleted_at.is_(None))
        .options(selectinload(ErpSalesOrder.items))
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="销售订单不存在")
    return row


# ============================================================
# 报价单 API
# ============================================================

@router.get("/quotations", response_model=Page)
async def list_quotations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = None,
    customer_id: int | None = None,
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:quotation:read")),
):
    stmt = select(ErpQuotation).where(ErpQuotation.deleted_at.is_(None))
    count = select(func.count()).select_from(ErpQuotation).where(ErpQuotation.deleted_at.is_(None))
    if status:
        stmt = stmt.where(ErpQuotation.status == status); count = count.where(ErpQuotation.status == status)
    if customer_id:
        stmt = stmt.where(ErpQuotation.customer_id == customer_id); count = count.where(ErpQuotation.customer_id == customer_id)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(ErpQuotation.code.ilike(like)); count = count.where(ErpQuotation.code.ilike(like))
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpQuotation.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[QuotationBrief.model_validate(r) for r in rows])


@router.post("/quotations", response_model=QuotationOut, status_code=201)
async def create_quotation(
    payload: QuotationIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:quotation:write")),
):
    cust = await db.get(ErpCustomer, payload.customer_id)
    if not cust or cust.deleted_at:
        raise HTTPException(status_code=400, detail="客户不存在")
    subtotal, tax_total = _compute(payload.items)
    total = round(subtotal + tax_total - payload.discount, 2)
    code = payload.code or await _next_code(db, "QT", ErpQuotation)
    row = ErpQuotation(
        code=code, customer_id=payload.customer_id, contact_id=payload.contact_id,
        quote_date=payload.quote_date, valid_until=payload.valid_until, currency=payload.currency,
        subtotal=subtotal, tax_total=tax_total, discount=payload.discount,
        total_amount=total, owner_user_id=getattr(user, "id", None), notes=payload.notes,
    )
    row.items = [
        ErpQuotationItem(
            product_id=it.product_id, product_code=it.product_code, product_name=it.product_name,
            spec=it.spec, quantity=it.quantity, unit=it.unit, unit_price=it.unit_price,
            amount=round(it.quantity * it.unit_price, 2), tax_rate=it.tax_rate, sort=it.sort,
        ) for it in payload.items
    ]
    db.add(row)
    await db.commit()
    await db.refresh(row, attribute_names=["items"])
    return _build_quotation_out(row)


@router.get("/quotations/{quotation_id}", response_model=QuotationOut)
async def get_quotation(
    quotation_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:quotation:read")),
):
    row = await _get_quotation(db, quotation_id)
    return _build_quotation_out(row)


@router.get("/sales-orders", response_model=Page)
async def list_sales_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = None,
    customer_id: int | None = None,
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:sales_order:read")),
):
    stmt = select(ErpSalesOrder).where(ErpSalesOrder.deleted_at.is_(None))
    count = select(func.count()).select_from(ErpSalesOrder).where(ErpSalesOrder.deleted_at.is_(None))
    if status:
        stmt = stmt.where(ErpSalesOrder.status == status); count = count.where(ErpSalesOrder.status == status)
    if customer_id:
        stmt = stmt.where(ErpSalesOrder.customer_id == customer_id); count = count.where(ErpSalesOrder.customer_id == customer_id)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(ErpSalesOrder.code.ilike(like)); count = count.where(ErpSalesOrder.code.ilike(like))
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpSalesOrder.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[SalesOrderBrief.model_validate(r) for r in rows])


@router.post("/sales-orders", response_model=SalesOrderOut, status_code=201)
async def create_sales_order(
    payload: SalesOrderIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:sales_order:write")),
):
    cust = await db.get(ErpCustomer, payload.customer_id)
    if not cust or cust.deleted_at:
        raise HTTPException(status_code=400, detail="客户不存在")
    subtotal, tax_total = _compute(payload.items)
    total = round(subtotal + tax_total - payload.discount, 2)
    code = payload.code or await _next_code(db, "SO", ErpSalesOrder)
    row = ErpSalesOrder(
        code=code, customer_id=payload.customer_id, contact_id=payload.contact_id,
        quotation_id=payload.quotation_id, order_date=payload.order_date,
        delivery_date=payload.delivery_date, currency=payload.currency,
        subtotal=subtotal, tax_total=tax_total, discount=payload.discount,
        total_amount=total, owner_user_id=getattr(user, "id", None), notes=payload.notes,
    )
    row.items = [
        ErpSalesOrderItem(
            product_id=it.product_id, product_code=it.product_code, product_name=it.product_name,
            spec=it.spec, quantity=it.quantity, unit=it.unit, unit_price=it.unit_price,
            amount=round(it.quantity * it.unit_price, 2), tax_rate=it.tax_rate, sort=it.sort,
        ) for it in payload.items
    ]
    db.add(row)
    await db.commit()
    await db.refresh(row, attribute_names=["items"])
    return SalesOrderOut.model_validate(row)


@router.get("/sales-orders/{order_id}", response_model=SalesOrderOut)
async def get_sales_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:sales_order:read")),
):
    row = await _get_order(db, order_id)
    return SalesOrderOut.model_validate(row)


@router.post("/sales-orders/{order_id}/confirm")
async def confirm_sales_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:sales_order:confirm")),
):
    row = await _get_order(db, order_id)
    row.status = "confirmed"
    await db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/quotations/{quotation_id}/convert", response_model=SalesOrderOut, status_code=201)
async def convert_quotation_to_order(
    quotation_id: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:sales_order:write")),
):
    q = await _get_quotation(db, quotation_id)
    code = await _next_code(db, "SO", ErpSalesOrder)
    order = ErpSalesOrder(
        code=code, customer_id=q.customer_id, contact_id=q.contact_id, quotation_id=q.id,
        currency=q.currency, subtotal=q.subtotal, tax_total=q.tax_total,
        discount=q.discount, total_amount=q.total_amount,
        owner_user_id=getattr(user, "id", None),
    )
    order.items = [
        ErpSalesOrderItem(
            product_id=it.product_id, product_code=it.product_code, product_name=it.product_name,
            spec=it.spec, quantity=it.quantity, unit=it.unit, unit_price=it.unit_price,
            amount=it.amount, tax_rate=it.tax_rate, sort=it.sort,
        ) for it in q.items
    ]
    db.add(order)
    q.status = "converted"
    await db.commit()
    await db.refresh(order, attribute_names=["items"])
    return SalesOrderOut.model_validate(order)


@router.post("/sales-orders/{order_id}/ship", response_model=ShipmentOut, status_code=201)
async def ship_sales_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    body: dict | None = None,
    _: auth_models.User = Depends(require_permission("erp:sales_order:write")),
):
    order = await _get_order(db, order_id)
    if order.status not in ("confirmed", "fulfilled"):
        raise HTTPException(status_code=400, detail="订单未确认，无法出货")
    body = body or {}
    code = await _next_code(db, "SH", ErpShipment)
    sh = ErpShipment(
        code=code, sales_order_id=order.id, status="pending",
        ship_date=body.get("ship_date"), receiver=body.get("receiver"),
        phone=body.get("phone"), address=body.get("address"),
    )
    sh.items = [
        ErpShipmentItem(
            product_id=it.product_id, product_code=it.product_code,
            product_name=it.product_name, quantity=it.quantity, unit=it.unit,
        ) for it in order.items
    ]
    db.add(sh)
    await db.commit()
    await db.refresh(sh)
    return ShipmentOut.model_validate(sh)


@router.get("/shipments", response_model=Page)
async def list_shipments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:warehouse:read")),
):
    stmt = select(ErpShipment).where(ErpShipment.deleted_at.is_(None))
    count = select(func.count()).select_from(ErpShipment).where(ErpShipment.deleted_at.is_(None))
    if status:
        stmt = stmt.where(ErpShipment.status == status); count = count.where(ErpShipment.status == status)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpShipment.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[ShipmentOut.model_validate(r) for r in rows])