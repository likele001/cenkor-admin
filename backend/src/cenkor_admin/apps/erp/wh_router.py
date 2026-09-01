"""ERP 仓储深度 API：库位 / 批次 / 序列号 / 盘点 / 安全库存预警"""
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

from .models.product import ErpProduct
from .models.purchase import ErpStockBalance, ErpStockMovement
from .models.warehouse_ext import (
    ErpBatch,
    ErpSerial,
    ErpStockLocation,
    ErpStocktake,
    ErpStocktakeItem,
)

router = APIRouter()


class LocationIn(BaseModel):
    warehouse_id: int
    code: str
    name: str | None = None
    area: str | None = None
    status: str = "active"
    remarks: str | None = None


class LocationOut(LocationIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: Any


class StocktakeItemIn(BaseModel):
    product_id: int
    actual_qty: float = 0
    remark: str | None = None


class StocktakeIn(BaseModel):
    warehouse_id: int | None = None
    location_id: int | None = None
    take_date: str | None = None
    remark: str | None = None
    items: list[StocktakeItemIn] = Field(default_factory=list)


class Page(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[Any]


async def _next_code(db: AsyncSession, prefix: str, table) -> str:
    row = (await db.execute(
        select(table.id).order_by(table.id.desc()).limit(1)
    )).scalar_one_or_none()
    n = (row or 0) + 1
    return f"{prefix}{n:04d}"


async def _apply_stock(db, warehouse_id: int, product_id: int, qty_delta: float,
                       movement_type: str, ref_type: str | None = None, ref_id: int | None = None,
                       remark: str | None = None, operator: int | None = None) -> float:
    """调整库存余额（支持负向扣减），返回调整后的余额"""
    qty_delta = round(float(qty_delta), 4)
    bal = (await db.execute(
        select(ErpStockBalance).where(
            ErpStockBalance.warehouse_id == warehouse_id,
            ErpStockBalance.product_id == product_id,
        ).with_for_update()
    )).scalar_one_or_none()
    if not bal:
        product = None
        if product_id:
            product = await db.get(ErpProduct, product_id)
        bal = ErpStockBalance(
            warehouse_id=warehouse_id, product_id=product_id,
            product_code=product.code if product else None,
            product_name=product.name if product else None,
            unit=product.unit if product else None,
            quantity=0, available_qty=0,
        )
        db.add(bal)
        await db.flush()
    bal.quantity = round(float(bal.quantity) + qty_delta, 4)
    bal.available_qty = bal.quantity
    bal.last_movement_at = func.now()
    await db.flush()
    return bal.quantity


# ============================================================
# 库位
# ============================================================

@router.get("/warehouse/locations", response_model=Page)
async def list_locations(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    warehouse_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:warehouse:read")),
):
    stmt = select(ErpStockLocation)
    count = select(func.count()).select_from(ErpStockLocation)
    if warehouse_id:
        stmt = stmt.where(ErpStockLocation.warehouse_id == warehouse_id)
        count = count.where(ErpStockLocation.warehouse_id == warehouse_id)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpStockLocation.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[LocationOut.model_validate(r) for r in rows])


@router.post("/warehouse/locations", response_model=LocationOut, status_code=201)
async def create_location(
    payload: LocationIn,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:warehouse:write")),
):
    dup = (await db.execute(
        select(ErpStockLocation).where(
            ErpStockLocation.warehouse_id == payload.warehouse_id,
            ErpStockLocation.code == payload.code,
        )
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail=f"库位编码已存在：{payload.code}")
    row = ErpStockLocation(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return LocationOut.model_validate(row)


# ============================================================
# 批次
# ============================================================

class BatchIn(BaseModel):
    batch_no: str
    product_id: int
    quantity: float = 0
    production_date: str | None = None
    expiry_date: str | None = None
    supplier_id: int | None = None
    status: str = "active"


class BatchOut(BatchIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_code: str | None = None
    product_name: str | None = None
    created_at: Any


@router.get("/warehouse/batches", response_model=Page)
async def list_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    product_id: int | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:warehouse:read")),
):
    stmt = select(ErpBatch)
    count = select(func.count()).select_from(ErpBatch)
    if product_id:
        stmt = stmt.where(ErpBatch.product_id == product_id); count = count.where(ErpBatch.product_id == product_id)
    if status:
        stmt = stmt.where(ErpBatch.status == status); count = count.where(ErpBatch.status == status)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpBatch.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[BatchOut.model_validate(r) for r in rows])


@router.post("/warehouse/batches", response_model=BatchOut, status_code=201)
async def create_batch(
    payload: BatchIn,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:warehouse:write")),
):
    dup = (await db.execute(select(ErpBatch).where(ErpBatch.batch_no == payload.batch_no))).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail=f"批次号已存在：{payload.batch_no}")
    product = await db.get(ErpProduct, payload.product_id) if payload.product_id else None
    if not product:
        raise HTTPException(status_code=400, detail="商品不存在")
    row = ErpBatch(
        batch_no=payload.batch_no, product_id=payload.product_id,
        product_code=product.code, product_name=product.name,
        quantity=payload.quantity, production_date=payload.production_date,
        expiry_date=payload.expiry_date, supplier_id=payload.supplier_id, status=payload.status,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return BatchOut.model_validate(row)


# ============================================================
# 序列号
# ============================================================

class SerialIn(BaseModel):
    serial_no: str
    product_id: int
    batch_id: int | None = None
    warehouse_id: int | None = None
    location_id: int | None = None
    status: str = "in_stock"


class SerialOut(SerialIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_code: str | None = None
    product_name: str | None = None
    created_at: Any


@router.get("/warehouse/serials", response_model=Page)
async def list_serials(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    product_id: int | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:warehouse:read")),
):
    stmt = select(ErpSerial)
    count = select(func.count()).select_from(ErpSerial)
    if product_id:
        stmt = stmt.where(ErpSerial.product_id == product_id); count = count.where(ErpSerial.product_id == product_id)
    if status:
        stmt = stmt.where(ErpSerial.status == status); count = count.where(ErpSerial.status == status)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpSerial.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[SerialOut.model_validate(r) for r in rows])


@router.post("/warehouse/serials", response_model=SerialOut, status_code=201)
async def create_serial(
    payload: SerialIn,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:warehouse:write")),
):
    dup = (await db.execute(select(ErpSerial).where(ErpSerial.serial_no == payload.serial_no))).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail=f"序列号已存在：{payload.serial_no}")
    product = await db.get(ErpProduct, payload.product_id) if payload.product_id else None
    if not product:
        raise HTTPException(status_code=400, detail="商品不存在")
    row = ErpSerial(
        serial_no=payload.serial_no, product_id=payload.product_id,
        product_code=product.code, product_name=product.name,
        batch_id=payload.batch_id, warehouse_id=payload.warehouse_id,
        location_id=payload.location_id, status=payload.status,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return SerialOut.model_validate(row)


# ============================================================
# 盘点
# ============================================================

class StocktakeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    warehouse_id: int | None = None
    location_id: int | None = None
    status: str
    take_date: Any = None
    remark: str | None = None
    created_at: Any
    items: list[Any] = Field(default_factory=list)


@router.get("/warehouse/stocktakes", response_model=Page)
async def list_stocktakes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:warehouse:read")),
):
    stmt = select(ErpStocktake).where(ErpStocktake.deleted_at.is_(None))
    count = select(func.count()).select_from(ErpStocktake).where(ErpStocktake.deleted_at.is_(None))
    if status:
        stmt = stmt.where(ErpStocktake.status == status); count = count.where(ErpStocktake.status == status)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpStocktake.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[StocktakeOut.model_validate(r) for r in rows])


@router.post("/warehouse/stocktakes", response_model=StocktakeOut, status_code=201)
async def create_stocktake(
    payload: StocktakeIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:warehouse:write")),
):
    if not payload.warehouse_id:
        raise HTTPException(status_code=400, detail="请选择盘点仓库")
    code = await _next_code(db, "STK", ErpStocktake)
    stocktake = ErpStocktake(
        code=code, warehouse_id=payload.warehouse_id, location_id=payload.location_id,
        take_date=payload.take_date, remark=payload.remark,
        created_by=getattr(user, "id", None),
    )
    # 按明细带出账面数量与差异
    items = []
    for it in payload.items:
        bal = None
        if payload.warehouse_id:
            bal = (await db.execute(
                select(ErpStockBalance).where(
                    ErpStockBalance.warehouse_id == payload.warehouse_id,
                    ErpStockBalance.product_id == it.product_id,
                )
            )).scalar_one_or_none()
        book = float(bal.quantity) if bal else 0.0
        product = await db.get(ErpProduct, it.product_id) if it.product_id else None
        items.append(ErpStocktakeItem(
            product_id=it.product_id,
            product_code=product.code if product else None,
            product_name=product.name if product else None,
            unit=product.unit if product else None,
            book_qty=book, actual_qty=it.actual_qty,
            diff_qty=round(it.actual_qty - book, 4),
            remark=it.remark,
        ))
    stocktake.items = items
    db.add(stocktake)
    await db.commit()
    await db.refresh(stocktake, attribute_names=["items"])
    return StocktakeOut.model_validate(stocktake)


@router.post("/warehouse/stocktakes/{stocktake_id}/confirm")
async def confirm_stocktake(
    stocktake_id: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:warehouse:write")),
):
    """确认盘点：按盘点差异调整库存并生成流水"""
    row = (await db.execute(
        select(ErpStocktake).where(ErpStocktake.id == stocktake_id, ErpStocktake.deleted_at.is_(None))
        .options(selectinload(ErpStocktake.items))
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="盘点单不存在")
    if row.status == "done":
        raise HTTPException(status_code=400, detail="盘点单已完成")

    for it in row.items:
        diff = float(it.diff_qty)
        if abs(diff) < 0.0001:
            continue
        balance = await _apply_stock(
            db, row.warehouse_id, it.product_id, diff, "adjust",
            ref_type="stocktake", ref_id=row.id,
            remark=f"盘点调整({row.code})", operator=getattr(user, "id", None),
        )
        db.add(ErpStockMovement(
            warehouse_id=row.warehouse_id, product_id=it.product_id,
            product_code=it.product_code, product_name=it.product_name, unit=it.unit,
            movement_type="adjust", quantity=diff, balance_after=balance,
            ref_type="stocktake", ref_id=row.id,
            remark=f"盘点调整({row.code})", operator_user_id=getattr(user, "id", None),
        ))
    row.status = "done"
    await db.commit()
    return {"id": row.id, "code": row.code, "status": "done"}


# ============================================================
# 安全库存 & 预警
# ============================================================

@router.get("/warehouse/alerts")
async def stock_alerts(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:warehouse:read")),
):
    """低于安全库存的商品预警"""
    products = (await db.execute(
        select(ErpProduct).where(ErpProduct.deleted_at.is_(None), ErpProduct.status == "active")
    )).scalars().all()
    balances = (await db.execute(select(ErpStockBalance))).scalars().all()
    bal_map: dict[int, float] = {}
    for b in balances:
        if b.product_id:
            bal_map[b.product_id] = round(bal_map.get(b.product_id, 0.0) + float(b.quantity), 4)
    alerts = []
    for p in products:
        qty = bal_map.get(p.id, 0.0)
        min_stock = float(p.min_stock or 0)
        if qty < min_stock:
            alerts.append({
                "product_id": p.id, "code": p.code, "name": p.name, "unit": p.unit,
                "quantity": qty, "min_stock": min_stock, "shortage": round(min_stock - qty, 4),
            })
    return {"count": len(alerts), "items": alerts}