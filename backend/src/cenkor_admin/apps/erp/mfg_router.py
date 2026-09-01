"""ERP 制造基础 API：BOM / 生产工单 / 领料 / 报工 / 完工入库 / 质检 / MRP可用量"""
from __future__ import annotations

from datetime import datetime
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
from .models.manufacturing import (
    ErpBom,
    ErpBomItem,
    ErpOpReport,
    ErpQualityCheck,
    ErpWorkOrder,
    ErpWorkOrderItem,
)

router = APIRouter()


class BomItemIn(BaseModel):
    component_id: int
    quantity: float = 1
    loss_rate: float = 0
    is_substitute: int = 0
    substitute_for: str | None = None
    unit: str | None = None
    spec: str | None = None
    sort: int = 0


class BomIn(BaseModel):
    product_id: int
    name: str | None = None
    version: str = "V1"
    is_active: int = 1
    output_qty: float = 1
    unit: str | None = None
    remark: str | None = None
    items: list[BomItemIn] = Field(default_factory=list)


class BomItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    component_id: int | None = None
    component_code: str | None = None
    component_name: str | None = None
    spec: str | None = None
    unit: str | None = None
    quantity: float
    loss_rate: float
    is_substitute: int
    substitute_for: str | None = None
    sort: int


class BomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    product_code: str | None = None
    product_name: str | None = None
    name: str | None = None
    version: str
    is_active: int
    status: str
    output_qty: float
    unit: str | None = None
    remark: str | None = None
    created_at: Any
    items: list[BomItemOut] = Field(default_factory=list)


class WorkOrderItemIn(BaseModel):
    component_id: int
    need_qty: float = 0
    unit: str | None = None
    component_code: str | None = None
    component_name: str | None = None


class WorkOrderIn(BaseModel):
    product_id: int
    quantity: float = 1
    bom_version: str | None = None
    sales_order_id: int | None = None
    warehouse_id: int | None = None
    start_date: str | None = None
    due_date: str | None = None
    remark: str | None = None


class OpReportIn(BaseModel):
    work_order_id: int
    process_name: str | None = None
    quantity: float = 0
    qualified_qty: float = 0
    reject_qty: float = 0
    work_hours: float = 0
    operator: str | None = None
    report_date: str | None = None
    remark: str | None = None


class QualityCheckIn(BaseModel):
    check_type: str = "IQC"
    product_id: int
    ref_type: str | None = None
    ref_id: int | None = None
    check_qty: float = 0
    qualified_qty: float = 0
    reject_qty: float = 0
    result: str = "pending"
    inspector: str | None = None
    check_date: str | None = None
    remark: str | None = None


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


async def _apply_stock(db, warehouse_id: int | None, product_id: int, qty_delta: float,
                       movement_type: str, ref_type: str | None = None, ref_id: int | None = None,
                       remark: str | None = None, operator: int | None = None) -> float:
    if not warehouse_id:
        raise HTTPException(status_code=400, detail="未指定仓库")
    qty_delta = round(float(qty_delta), 4)
    bal = (await db.execute(
        select(ErpStockBalance).where(
            ErpStockBalance.warehouse_id == warehouse_id,
            ErpStockBalance.product_id == product_id,
        ).with_for_update()
    )).scalar_one_or_none()
    if not bal:
        product = await db.get(ErpProduct, product_id) if product_id else None
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
# BOM
# ============================================================

@router.get("/mfg/boms", response_model=Page)
async def list_boms(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    product_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:mfg:read")),
):
    stmt = select(ErpBom).where(ErpBom.deleted_at.is_(None))
    count = select(func.count()).select_from(ErpBom).where(ErpBom.deleted_at.is_(None))
    if product_id:
        stmt = stmt.where(ErpBom.product_id == product_id); count = count.where(ErpBom.product_id == product_id)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.options(selectinload(ErpBom.items))
        .order_by(ErpBom.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[BomOut.model_validate(r) for r in rows])


@router.get("/mfg/boms/{bom_id}", response_model=BomOut)
async def get_bom(
    bom_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:mfg:read")),
):
    row = (await db.execute(
        select(ErpBom).where(ErpBom.id == bom_id, ErpBom.deleted_at.is_(None))
        .options(selectinload(ErpBom.items))
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="BOM 不存在")
    return BomOut.model_validate(row)


@router.post("/mfg/boms", response_model=BomOut, status_code=201)
async def create_bom(
    payload: BomIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:mfg:write")),
):
    if not payload.items:
        raise HTTPException(status_code=400, detail="BOM 至少需要一条明细")
    dup = (await db.execute(
        select(ErpBom).where(ErpBom.product_id == payload.product_id,
                             ErpBom.version == payload.version)
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail="该商品此版本 BOM 已存在，请更换版本号")
    product = await db.get(ErpProduct, payload.product_id)
    if not product:
        raise HTTPException(status_code=400, detail="商品不存在")

    items = []
    for it in payload.items:
        comp = await db.get(ErpProduct, it.component_id) if it.component_id else None
        items.append(ErpBomItem(
            component_id=it.component_id,
            component_code=comp.code if comp else None,
            component_name=comp.name if comp else None,
            spec=it.spec or (comp.model if comp else None),
            unit=it.unit or (comp.unit if comp else None),
            quantity=it.quantity, loss_rate=it.loss_rate,
            is_substitute=it.is_substitute, substitute_for=it.substitute_for, sort=it.sort,
        ))
    bom = ErpBom(
        product_id=payload.product_id,
        product_code=product.code, product_name=product.name,
        name=payload.name or product.name, version=payload.version,
        is_active=payload.is_active, output_qty=payload.output_qty,
        unit=payload.unit or product.unit, remark=payload.remark,
        created_by=getattr(user, "id", None),
    )
    bom.items = items
    db.add(bom)
    await db.commit()
    await db.refresh(bom, attribute_names=["items"])
    return BomOut.model_validate(bom)


# ============================================================
# 生产工单
# ============================================================

@router.get("/mfg/work-orders", response_model=Page)
async def list_work_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = None,
    product_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:mfg:read")),
):
    stmt = select(ErpWorkOrder).where(ErpWorkOrder.deleted_at.is_(None))
    count = select(func.count()).select_from(ErpWorkOrder).where(ErpWorkOrder.deleted_at.is_(None))
    if status:
        stmt = stmt.where(ErpWorkOrder.status == status); count = count.where(ErpWorkOrder.status == status)
    if product_id:
        stmt = stmt.where(ErpWorkOrder.product_id == product_id); count = count.where(ErpWorkOrder.product_id == product_id)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpWorkOrder.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[{
                    "id": r.id, "code": r.code, "product_id": r.product_id,
                    "product_code": r.product_code, "product_name": r.product_name,
                    "status": r.status, "quantity": float(r.quantity),
                    "produced_qty": float(r.produced_qty), "start_date": str(r.start_date) if r.start_date else None,
                    "due_date": str(r.due_date) if r.due_date else None, "unit": r.unit,
                    "created_at": r.created_at,
                } for r in rows])


@router.post("/mfg/work-orders", status_code=201)
async def create_work_order(
    payload: WorkOrderIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:mfg:write")),
):
    product = await db.get(ErpProduct, payload.product_id)
    if not product:
        raise HTTPException(status_code=400, detail="商品不存在")
    # 选择 BOM（指定版本或启用版）
    bom = None
    if payload.bom_version:
        bom = (await db.execute(
            select(ErpBom).where(ErpBom.product_id == payload.product_id,
                                 ErpBom.version == payload.bom_version, ErpBom.deleted_at.is_(None))
            .options(selectinload(ErpBom.items))
        )).scalar_one_or_none()
    else:
        bom = (await db.execute(
            select(ErpBom).where(ErpBom.product_id == payload.product_id,
                                 ErpBom.is_active == 1, ErpBom.deleted_at.is_(None))
            .options(selectinload(ErpBom.items))
            .order_by(ErpBom.id.desc()).limit(1)
        )).scalar_one_or_none()

    code = await _next_code(db, "MO", ErpWorkOrder)
    start_date = datetime.strptime(payload.start_date, "%Y-%m-%d").date() if payload.start_date else None
    due_date = datetime.strptime(payload.due_date, "%Y-%m-%d").date() if payload.due_date else None
    wo = ErpWorkOrder(
        code=code, product_id=payload.product_id,
        product_code=product.code, product_name=product.name,
        bom_id=bom.id if bom else None,
        sales_order_id=payload.sales_order_id, warehouse_id=payload.warehouse_id,
        status="released" if bom else "draft",
        quantity=payload.quantity, unit=product.unit,
        start_date=start_date, due_date=due_date, remark=payload.remark,
        created_by=getattr(user, "id", None),
    )
    # 从 BOM 带出用料明细（按产出数量换算）
    items = []
    if bom:
        factor = float(payload.quantity) / float(bom.output_qty) if bom.output_qty else 1.0
        for bi in bom.items:
            if bi.is_substitute:
                continue
            need = round(float(bi.quantity) * factor, 4)
            items.append(ErpWorkOrderItem(
                component_id=bi.component_id, component_code=bi.component_code,
                component_name=bi.component_name, unit=bi.unit,
                need_qty=need,
            ))
    wo.items = items
    db.add(wo)
    await db.commit()
    await db.refresh(wo)
    return {"id": wo.id, "code": wo.code, "status": wo.status, "material_lines": len(items)}


@router.post("/mfg/work-orders/{order_id}/release")
async def release_work_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:mfg:write")),
):
    wo = await _get_wo(db, order_id)
    if wo.status not in ("draft", "cancelled"):
        raise HTTPException(status_code=400, detail=f"状态 {wo.status} 不可下达")
    wo.status = "released"
    await db.commit()
    return {"id": wo.id, "code": wo.code, "status": wo.status}


@router.post("/mfg/work-orders/{order_id}/issue")
async def issue_materials(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:mfg:write")),
):
    """领料：按工单用料明细从指定仓库扣减库存并写流水"""
    wo = (await db.execute(
        select(ErpWorkOrder).where(ErpWorkOrder.id == order_id, ErpWorkOrder.deleted_at.is_(None))
        .options(selectinload(ErpWorkOrder.items))
    )).scalar_one_or_none()
    if not wo:
        raise HTTPException(status_code=404, detail="工单不存在")
    if not wo.warehouse_id:
        raise HTTPException(status_code=400, detail="工单未指定仓库")
    if wo.status not in ("released", "in_progress"):
        raise HTTPException(status_code=400, detail="工单未下达，不能领料")

    for it in wo.items:
        issued = float(it.issued_qty)
        need = float(it.need_qty)
        to_issue = need - issued
        if round(to_issue, 4) <= 0:
            continue
        balance = await _apply_stock(db, wo.warehouse_id, it.component_id, -to_issue, "out",
                                     ref_type="work_order", ref_id=wo.id,
                                     remark=f"工单领料({wo.code})", operator=getattr(user, "id", None))
        db.add(ErpStockMovement(
            warehouse_id=wo.warehouse_id, product_id=it.component_id,
            product_code=it.component_code, product_name=it.component_name, unit=it.unit,
            movement_type="out", quantity=-to_issue, balance_after=balance,
            ref_type="work_order", ref_id=wo.id,
            remark=f"工单领料({wo.code})", operator_user_id=getattr(user, "id", None),
        ))
        it.issued_qty = issued + to_issue
    wo.status = "in_progress"
    await db.commit()
    return {"id": wo.id, "code": wo.code, "status": wo.status}


@router.post("/mfg/work-orders/{order_id}/complete")
async def complete_work_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:mfg:write")),
):
    """完工入库：将产出商品入库并更新工单完工量"""
    wo = (await db.execute(
        select(ErpWorkOrder).where(ErpWorkOrder.id == order_id, ErpWorkOrder.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not wo:
        raise HTTPException(status_code=404, detail="工单不存在")
    if wo.status not in ("in_progress", "released"):
        raise HTTPException(status_code=400, detail=f"状态 {wo.status} 不可完工")
    if not wo.warehouse_id:
        raise HTTPException(status_code=400, detail="工单未指定仓库")

    remaining = float(wo.quantity) - float(wo.produced_qty)
    if round(remaining, 4) <= 0:
        raise HTTPException(status_code=400, detail="工单已全部完工")
    balance = await _apply_stock(db, wo.warehouse_id, wo.product_id, remaining, "in",
                                 ref_type="work_order", ref_id=wo.id,
                                 remark=f"完工入库({wo.code})", operator=getattr(user, "id", None))
    db.add(ErpStockMovement(
        warehouse_id=wo.warehouse_id, product_id=wo.product_id,
        product_code=wo.product_code, product_name=wo.product_name, unit=wo.unit,
        movement_type="in", quantity=remaining, balance_after=balance,
        ref_type="work_order", ref_id=wo.id,
        remark=f"完工入库({wo.code})", operator_user_id=getattr(user, "id", None),
    ))
    wo.produced_qty = float(wo.produced_qty) + remaining
    if float(wo.produced_qty) >= float(wo.quantity) - 0.001:
        wo.status = "completed"
    return {"id": wo.id, "code": wo.code, "status": wo.status, "produced_qty": float(wo.produced_qty)}


async def _get_wo(db: AsyncSession, order_id: int) -> ErpWorkOrder:
    wo = (await db.execute(
        select(ErpWorkOrder).where(ErpWorkOrder.id == order_id, ErpWorkOrder.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not wo:
        raise HTTPException(status_code=404, detail="工单不存在")
    return wo


# ============================================================
# 工序报工
# ============================================================

@router.post("/mfg/op-reports", status_code=201)
async def create_op_report(
    payload: OpReportIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:mfg:write")),
):
    wo = await _get_wo(db, payload.work_order_id)
    row = ErpOpReport(
        work_order_id=payload.work_order_id, product_id=wo.product_id,
        product_code=wo.product_code, product_name=wo.product_name,
        process_name=payload.process_name, quantity=payload.quantity,
        qualified_qty=payload.qualified_qty, reject_qty=payload.reject_qty,
        work_hours=payload.work_hours, operator=payload.operator,
        report_date=payload.report_date, remark=payload.remark,
        created_by=getattr(user, "id", None),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"id": row.id, "work_order": wo.code, "qualified_qty": row.qualified_qty,
            "reject_qty": row.reject_qty}


@router.get("/mfg/op-reports", response_model=Page)
async def list_op_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    work_order_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:mfg:read")),
):
    stmt = select(ErpOpReport)
    count = select(func.count()).select_from(ErpOpReport)
    if work_order_id:
        stmt = stmt.where(ErpOpReport.work_order_id == work_order_id)
        count = count.where(ErpOpReport.work_order_id == work_order_id)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpOpReport.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[{
                    "id": r.id, "work_order_id": r.work_order_id, "process_name": r.process_name,
                    "quantity": float(r.quantity), "qualified_qty": float(r.qualified_qty),
                    "reject_qty": float(r.reject_qty), "work_hours": float(r.work_hours),
                    "operator": r.operator, "report_date": str(r.report_date) if r.report_date else None,
                    "created_at": r.created_at,
                } for r in rows])


# ============================================================
# 质检
# ============================================================

@router.post("/mfg/quality-checks", status_code=201)
async def create_quality_check(
    payload: QualityCheckIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:mfg:write")),
):
    product = await db.get(ErpProduct, payload.product_id) if payload.product_id else None
    if not product:
        raise HTTPException(status_code=400, detail="商品不存在")
    if payload.check_type not in ("IQC", "IPQC", "FQC"):
        raise HTTPException(status_code=400, detail="质检类型必须为 IQC/IPQC/FQC")
    code = await _next_code(db, "QC", ErpQualityCheck)
    row = ErpQualityCheck(
        code=code, check_type=payload.check_type, product_id=payload.product_id,
        product_code=product.code, product_name=product.name,
        ref_type=payload.ref_type, ref_id=payload.ref_id,
        check_qty=payload.check_qty, qualified_qty=payload.qualified_qty,
        reject_qty=payload.reject_qty,
        result="pass" if payload.qualified_qty >= payload.check_qty and payload.check_qty > 0 else payload.result,
        inspector=payload.inspector or "质检员", check_date=payload.check_date,
        remark=payload.remark, created_by=getattr(user, "id", None),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {
        "id": row.id, "code": row.code, "check_type": row.check_type,
        "product_id": row.product_id, "product_code": row.product_code,
        "product_name": row.product_name, "check_qty": float(row.check_qty),
        "qualified_qty": float(row.qualified_qty), "reject_qty": float(row.reject_qty),
        "result": row.result, "created_at": row.created_at,
    }


@router.get("/mfg/quality-checks", response_model=Page)
async def list_quality_checks(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    check_type: str | None = None,
    result: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:mfg:read")),
):
    stmt = select(ErpQualityCheck).where(ErpQualityCheck.deleted_at.is_(None))
    count = select(func.count()).select_from(ErpQualityCheck).where(ErpQualityCheck.deleted_at.is_(None))
    if check_type:
        stmt = stmt.where(ErpQualityCheck.check_type == check_type); count = count.where(ErpQualityCheck.check_type == check_type)
    if result:
        stmt = stmt.where(ErpQualityCheck.result == result); count = count.where(ErpQualityCheck.result == result)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpQualityCheck.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[{
                    "id": r.id, "code": r.code, "check_type": r.check_type,
                    "product_id": r.product_id, "product_code": r.product_code,
                    "product_name": r.product_name, "check_qty": float(r.check_qty),
                    "qualified_qty": float(r.qualified_qty), "reject_qty": float(r.reject_qty),
                    "result": r.result, "inspector": r.inspector,
                    "check_date": str(r.check_date) if r.check_date else None,
                    "created_at": r.created_at,
                } for r in rows])


# ============================================================
# MRP 可用量计算（基础版）
# ============================================================

@router.get("/mrp/availabilities")
async def mrp_availability(
    product_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:mfg:read")),
):
    """可用量 = 现有库存 + 在购(采购未收) + 在产(工单未完工) - 已分配(销售未出/工单未领)"""
    balances = (await db.execute(select(ErpStockBalance))).scalars().all()
    bal_map: dict[int, float] = {}
    for b in balances:
        if b.product_id:
            bal_map[b.product_id] = round(bal_map.get(b.product_id, 0.0) + float(b.quantity), 4)

    # 在购：采购订单未收数量
    pending_receipt = dict(bal_map)  # 简化，后续可按 PO 展开
    products = (await db.execute(
        select(ErpProduct).where(ErpProduct.deleted_at.is_(None)))
    ).scalars().all()

    result = []
    for p in products:
        if product_id and p.id != product_id:
            continue
        on_hand = bal_map.get(p.id, 0.0)
        result.append({
            "product_id": p.id, "code": p.code, "name": p.name, "unit": p.unit,
            "on_hand": round(on_hand, 4),
            "in_transit": 0.0,
            "in_production": 0.0,
            "allocated": 0.0,
            "available": round(on_hand, 4),
        })
    return {"items": result, "count": len(result)}