"""ERP 采购 + 仓库模块 API（仓库 + 采购订单 + 收货 + 库存）"""
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

from .models.sales import ErpShipment, ErpShipmentItem
from .models.supplier import ErpSupplier
from .models.purchase import (
    ErpPurchaseOrder,
    ErpPurchaseOrderItem,
    ErpPurchaseReceipt,
    ErpStockBalance,
    ErpStockMovement,
    ErpWarehouse,
)

router = APIRouter()


# ============================================================
# Schemas
# ============================================================

class POrderItemIn(BaseModel):
    product_id: int | None = None
    product_code: str | None = None
    product_name: str | None = None
    spec: str | None = None
    quantity: float = Field(1, gt=0)
    unit: str | None = None
    unit_price: float = 0
    tax_rate: float = 0
    sort: int = 0


class POrderItemOut(POrderItemIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    amount: float
    received_qty: float


class PurchaseOrderIn(BaseModel):
    code: str | None = None
    supplier_id: int
    order_date: str | None = None
    expected_date: str | None = None
    currency: str = "CNY"
    discount: float = 0
    notes: str | None = None
    items: list[POrderItemIn] = []


class PurchaseOrderOut(PurchaseOrderIn):
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
    items: list[POrderItemOut] = []


class PurchaseOrderBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    supplier_id: int
    status: str
    order_date: Any = None
    total_amount: float
    payment_status: str
    owner_user_id: int | None = None
    created_at: Any


class WarehouseIn(BaseModel):
    code: str
    name: str
    location: str | None = None
    manager: str | None = None
    phone: str | None = None
    status: str = "active"
    remarks: str | None = None


class WarehouseOut(WarehouseIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: Any


class StockBalanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    warehouse_id: int
    warehouse_code: str | None = None
    warehouse_name: str | None = None
    product_id: int | None = None
    product_code: str | None = None
    product_name: str | None = None
    unit: str | None = None
    quantity: float
    available_qty: float
    last_movement_at: Any = None


class StockMovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    warehouse_id: int
    product_code: str | None = None
    product_name: str | None = None
    unit: str | None = None
    movement_type: str
    quantity: float
    balance_after: float
    ref_type: str | None = None
    ref_id: int | None = None
    remark: str | None = None
    created_at: Any


class Page(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[Any]


class ReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    purchase_order_id: int | None = None
    supplier_id: int | None = None
    warehouse_id: int | None = None
    status: str
    receipt_date: Any = None
    carrier: str | None = None
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


def _compute(items: list[POrderItemIn]) -> tuple[float, float]:
    subtotal = 0.0
    tax_total = 0.0
    for it in items:
        amount = float(it.quantity) * float(it.unit_price)
        subtotal += amount
        tax_total += amount * float(it.tax_rate or 0) / 100
    return round(subtotal, 2), round(tax_total, 2)


async def _get_order(db: AsyncSession, oid: int) -> ErpPurchaseOrder:
    row = (await db.execute(
        select(ErpPurchaseOrder)
        .where(ErpPurchaseOrder.id == oid, ErpPurchaseOrder.deleted_at.is_(None))
        .options(selectinload(ErpPurchaseOrder.items))
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="采购订单不存在")
    return row


async def _apply_stock(
    db: AsyncSession,
    warehouse_id: int,
    movement_type: str,
    quantity: float,
    product_id: int | None,
    product_code: str | None,
    product_name: str | None,
    unit: str | None,
    ref_type: str | None,
    ref_id: int | None,
    receipt_id: int | None,
    user_id: int | None,
    remark: str | None,
) -> None:
    """更新库存余额并写入流水。movement_type in/out/adjust；out 为负数扣减。"""
    qty = quantity if movement_type == "in" else -quantity
    # 锁定余额行
    bal = (
        await db.execute(
            select(ErpStockBalance)
            .where(
                ErpStockBalance.warehouse_id == warehouse_id,
                ErpStockBalance.product_id == product_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if bal:
        new_qty = float(bal.quantity) + qty
        bal.quantity = new_qty
        bal.available_qty = new_qty
        bal.last_movement_at = func.now()
        bal.product_code = product_code
        bal.product_name = product_name
        bal.unit = unit
    else:
        new_qty = max(qty, 0)
        bal = ErpStockBalance(
            warehouse_id=warehouse_id, product_id=product_id,
            product_code=product_code, product_name=product_name, unit=unit,
            quantity=new_qty, available_qty=new_qty,
        )
        db.add(bal)
    db.add(ErpStockMovement(
        warehouse_id=warehouse_id, product_id=product_id,
        product_code=product_code, product_name=product_name, unit=unit,
        movement_type=movement_type, quantity=qty, balance_after=new_qty,
        ref_type=ref_type, ref_id=ref_id, receipt_id=receipt_id,
        remark=remark, operator_user_id=user_id,
    ))


# ============================================================
# 仓库 API
# ============================================================

@router.get("/warehouses", response_model=Page)
async def list_warehouses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:warehouse:read")),
):
    stmt = select(ErpWarehouse).where(ErpWarehouse.deleted_at.is_(None))
    count = select(func.count()).select_from(ErpWarehouse).where(ErpWarehouse.deleted_at.is_(None))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(ErpWarehouse.name.ilike(like), ErpWarehouse.code.ilike(like)))
        count = count.where(or_(ErpWarehouse.name.ilike(like), ErpWarehouse.code.ilike(like)))
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpWarehouse.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[WarehouseOut.model_validate(r) for r in rows])


@router.post("/warehouses", response_model=WarehouseOut, status_code=201)
async def create_warehouse(
    payload: WarehouseIn,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:warehouse:write")),
):
    exists = (await db.execute(select(ErpWarehouse).where(ErpWarehouse.code == payload.code))).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail=f"仓库编号已存在：{payload.code}")
    row = ErpWarehouse(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return WarehouseOut.model_validate(row)


@router.get("/warehouses/{warehouse_id}", response_model=WarehouseOut)
async def get_warehouse(
    warehouse_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:warehouse:read")),
):
    row = await db.get(ErpWarehouse, warehouse_id)
    if not row or row.deleted_at:
        raise HTTPException(status_code=404, detail="仓库不存在")
    return WarehouseOut.model_validate(row)


@router.put("/warehouses/{warehouse_id}", response_model=WarehouseOut)
async def update_warehouse(
    warehouse_id: int,
    payload: WarehouseIn,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:warehouse:write")),
):
    row = await db.get(ErpWarehouse, warehouse_id)
    if not row or row.deleted_at:
        raise HTTPException(status_code=404, detail="仓库不存在")
    for k, v in payload.model_dump().items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return WarehouseOut.model_validate(row)


# ============================================================
# 采购订单 API
# ============================================================

@router.get("/purchase-orders", response_model=Page)
async def list_purchase_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = None,
    supplier_id: int | None = None,
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:purchase_order:read")),
):
    stmt = select(ErpPurchaseOrder).where(ErpPurchaseOrder.deleted_at.is_(None))
    count = select(func.count()).select_from(ErpPurchaseOrder).where(ErpPurchaseOrder.deleted_at.is_(None))
    if status:
        stmt = stmt.where(ErpPurchaseOrder.status == status); count = count.where(ErpPurchaseOrder.status == status)
    if supplier_id:
        stmt = stmt.where(ErpPurchaseOrder.supplier_id == supplier_id); count = count.where(ErpPurchaseOrder.supplier_id == supplier_id)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(ErpPurchaseOrder.code.ilike(like)); count = count.where(ErpPurchaseOrder.code.ilike(like))
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpPurchaseOrder.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[PurchaseOrderBrief.model_validate(r) for r in rows])


@router.post("/purchase-orders", response_model=PurchaseOrderOut, status_code=201)
async def create_purchase_order(
    payload: PurchaseOrderIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:purchase_order:write")),
):
    sup = await db.get(ErpSupplier, payload.supplier_id)
    if not sup or sup.deleted_at:
        raise HTTPException(status_code=400, detail="供应商不存在")
    subtotal, tax_total = _compute(payload.items)
    total = round(subtotal + tax_total - payload.discount, 2)
    code = payload.code or await _next_code(db, "PO", ErpPurchaseOrder)
    row = ErpPurchaseOrder(
        code=code, supplier_id=payload.supplier_id, order_date=payload.order_date,
        expected_date=payload.expected_date, currency=payload.currency,
        subtotal=subtotal, tax_total=tax_total, discount=payload.discount,
        total_amount=total, owner_user_id=getattr(user, "id", None), notes=payload.notes,
    )
    row.items = [
        ErpPurchaseOrderItem(
            product_id=it.product_id, product_code=it.product_code, product_name=it.product_name,
            spec=it.spec, quantity=it.quantity, unit=it.unit, unit_price=it.unit_price,
            amount=round(float(it.quantity) * float(it.unit_price), 2), tax_rate=it.tax_rate, sort=it.sort,
        ) for it in payload.items
    ]
    db.add(row)
    await db.commit()
    await db.refresh(row, attribute_names=["items"])
    return PurchaseOrderOut.model_validate(row)


@router.get("/purchase-orders/{order_id}", response_model=PurchaseOrderOut)
async def get_purchase_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:purchase_order:read")),
):
    row = await _get_order(db, order_id)
    return PurchaseOrderOut.model_validate(row)


@router.post("/purchase-orders/{order_id}/confirm")
async def confirm_purchase_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:purchase_order:confirm")),
):
    row = await _get_order(db, order_id)
    row.status = "confirmed"
    await db.commit()
    return {"id": row.id, "status": row.status}


# ============================================================
# 收货 API（入库）
# ============================================================

@router.post("/purchase-orders/{order_id}/receive", response_model=ReceiptOut, status_code=201)
async def receive_purchase_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    body: dict | None = None,
    user: auth_models.User = Depends(require_permission("erp:purchase_order:write")),
):
    order = await _get_order(db, order_id)
    if order.status not in ("confirmed", "received"):
        raise HTTPException(status_code=400, detail="采购订单未确认，无法收货")
    body = body or {}
    warehouse_id = body.get("warehouse_id")
    my_user_id = getattr(user, "id", None)
    if not warehouse_id:
        wh = (await db.execute(
            select(ErpWarehouse).where(ErpWarehouse.deleted_at.is_(None)).limit(1)
        )).scalar_one_or_none()
        if not wh:
            raise HTTPException(status_code=400, detail="请先创建仓库")
        warehouse_id = wh.id
    wh = await db.get(ErpWarehouse, warehouse_id)
    if not wh or wh.deleted_at:
        raise HTTPException(status_code=400, detail="仓库不存在")

    code = await _next_code(db, "GR", ErpPurchaseReceipt)
    receipt = ErpPurchaseReceipt(
        code=code, purchase_order_id=order.id, supplier_id=order.supplier_id,
        warehouse_id=warehouse_id, status="received", receipt_date=body.get("receipt_date"),
        carrier=body.get("carrier"), tracking_no=body.get("tracking_no"),
    )
    db.add(receipt)
    await db.flush()

    for it in order.items:
        qty = float(it.quantity) - float(it.received_qty)
        if qty <= 0:
            continue
        it.received_qty = float(it.received_qty) + qty
        await _apply_stock(
            db, warehouse_id=warehouse_id, movement_type="in", quantity=qty,
            product_id=it.product_id, product_code=it.product_code,
            product_name=it.product_name, unit=it.unit,
            ref_type="purchase_receipt", ref_id=receipt.id, receipt_id=receipt.id,
            user_id=my_user_id, remark=f"采购收货 {order.code}",
        )

    order.status = "received"
    order.paid_amount = float(order.paid_amount)
    order.payment_status = "unpaid"
    await db.commit()
    await db.refresh(receipt)
    return ReceiptOut.model_validate(receipt)


@router.post("/shipments/{shipment_id}/confirm")
async def confirm_ship_and_deduct(
    shipment_id: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:warehouse:write")),
):
    """出货确认出库：扣减对应商品库存。"""
    sh = (
        await db.execute(
            select(ErpShipment)
            .where(ErpShipment.id == shipment_id, ErpShipment.deleted_at.is_(None))
            .options(selectinload(ErpShipment.items))
        )
    ).scalar_one_or_none()
    if not sh:
        raise HTTPException(status_code=404, detail="出货单不存在")
    if sh.status != "pending":
        raise HTTPException(status_code=400, detail="出货单状态不允许出库")
    warehouse_id = sh.warehouse_id
    my_user_id = getattr(user, "id", None)
    if not warehouse_id:
        wh = (await db.execute(
            select(ErpWarehouse).where(ErpWarehouse.deleted_at.is_(None)).limit(1)
        )).scalar_one_or_none()
        if not wh:
            raise HTTPException(status_code=400, detail="请先创建仓库")
        warehouse_id = wh.id
    for it in sh.items:
        await _apply_stock(
            db, warehouse_id=warehouse_id, movement_type="out", quantity=float(it.quantity),
            product_id=it.product_id, product_code=it.product_code,
            product_name=it.product_name, unit=it.unit,
            ref_type="shipment", ref_id=sh.id, receipt_id=None,
            user_id=my_user_id, remark=f"销售出货 {sh.code}",
        )
    sh.status = "shipped"
    await db.commit()
    return {"id": sh.id, "code": sh.code, "status": sh.status}


# ============================================================
# 库存 API
# ============================================================

@router.get("/stock/balance", response_model=Page)
async def list_stock_balance(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    warehouse_id: int | None = None,
    product_id: int | None = None,
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:warehouse:read")),
):
    stmt = select(ErpStockBalance)
    count = select(func.count()).select_from(ErpStockBalance)
    if warehouse_id:
        stmt = stmt.where(ErpStockBalance.warehouse_id == warehouse_id)
        count = count.where(ErpStockBalance.warehouse_id == warehouse_id)
    if product_id:
        stmt = stmt.where(ErpStockBalance.product_id == product_id)
        count = count.where(ErpStockBalance.product_id == product_id)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(ErpStockBalance.product_code.ilike(like), ErpStockBalance.product_name.ilike(like)))
        count = count.where(or_(ErpStockBalance.product_code.ilike(like), ErpStockBalance.product_name.ilike(like)))
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpStockBalance.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    wh_ids = {r.warehouse_id for r in rows}
    whs: dict[int, ErpWarehouse] = {}
    if wh_ids:
        whs = {w.id: w for w in (await db.execute(
            select(ErpWarehouse).where(ErpWarehouse.id.in_(wh_ids))
        )).scalars().all()}
    items = []
    for r in rows:
        w = whs.get(r.warehouse_id)
        items.append(StockBalanceOut(
            id=r.id, warehouse_id=r.warehouse_id,
            warehouse_code=getattr(w, "code", None), warehouse_name=getattr(w, "name", None),
            product_id=r.product_id, product_code=r.product_code, product_name=r.product_name,
            unit=r.unit, quantity=float(r.quantity), available_qty=float(r.available_qty),
            last_movement_at=r.last_movement_at,
        ))
    return Page(total=total, page=page, page_size=page_size, items=items)


@router.get("/stock/movements", response_model=Page)
async def list_stock_movements(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    warehouse_id: int | None = None,
    movement_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:warehouse:read")),
):
    stmt = select(ErpStockMovement)
    count = select(func.count()).select_from(ErpStockMovement)
    if warehouse_id:
        stmt = stmt.where(ErpStockMovement.warehouse_id == warehouse_id)
        count = count.where(ErpStockMovement.warehouse_id == warehouse_id)
    if movement_type:
        stmt = stmt.where(ErpStockMovement.movement_type == movement_type)
        count = count.where(ErpStockMovement.movement_type == movement_type)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpStockMovement.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[StockMovementOut.model_validate(r) for r in rows])