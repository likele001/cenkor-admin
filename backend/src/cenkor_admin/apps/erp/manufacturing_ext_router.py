"""ERP 制造深化 API：工作中心 / 工艺路线 / 工艺步骤 / 生产排程（由工单自动生成）"""
from __future__ import annotations

from datetime import datetime

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.core.db import get_db

from .models.product import ErpProduct
from .models.manufacturing import ErpWorkOrder
from .models.routing import (
    ErpProductionSchedule,
    ErpRouting,
    ErpRoutingStep,
    ErpWorkCenter,
)

router = APIRouter()


# ============================================================
# Schemas
# ============================================================

class WorkCenterIn(BaseModel):
    code: str
    name: str
    wc_type: str = "machine"
    location: str | None = None
    capacity: float = 8
    unit: str | None = None
    labor_count: int = 1
    status: str = "active"
    remark: str | None = None


class WorkCenterOut(WorkCenterIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: Any


class StepIn(BaseModel):
    seq: int = 1
    process_code: str | None = None
    process_name: str
    work_center_id: int | None = None
    work_center_name: str | None = None
    std_time: float = 0
    setup_minutes: float = 0
    time_type: str = "per_unit"
    yield_rate: float = 100
    is_last: int = 0
    description: str | None = None
    sort: int = 0


class RoutingIn(BaseModel):
    product_id: int
    name: str | None = None
    version: str = "V1"
    is_active: int = 1
    output_qty: float = 1
    unit: str | None = None
    lead_time_hours: float = 0
    remark: str | None = None
    steps: list[StepIn] = []


class StepOut(StepIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    routing_id: int


class RoutingOut(BaseModel):
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
    lead_time_hours: float
    remark: str | None = None
    created_at: Any
    steps: list[StepOut] = Field(default_factory=list)


class ScheduleIn(BaseModel):
    work_order_id: int
    routing_id: int | None = None
    plan_date: str | None = None


class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    work_order_id: int | None = None
    work_order_code: str | None = None
    product_code: str | None = None
    product_name: str | None = None
    step_seq: int | None = None
    process_name: str | None = None
    work_center_id: int | None = None
    work_center_name: str | None = None
    plan_date: Any = None
    plan_qty: float
    done_qty: float
    plan_hours: float
    status: str
    remark: str | None = None


class LoadResult(BaseModel):
    work_order_id: int
    work_order_code: str
    routing_id: int
    routing_name: str | None = None
    rows: list[ScheduleOut]
    total_steps: int


class Page(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[Any]


# ============================================================
# Helpers
# ============================================================

async def _next_code(db: AsyncSession, prefix: str, table) -> str:
    row = (await db.execute(
        select(table.id).order_by(table.id.desc()).limit(1)
    )).scalar_one_or_none()
    n = (row or 0) + 1
    return f"{prefix}{n:04d}"


async def _get_routing(db: AsyncSession, routing_id: int) -> ErpRouting:
    row = (await db.execute(
        select(ErpRouting).where(ErpRouting.id == routing_id, ErpRouting.deleted_at.is_(None))
        .options(selectinload(ErpRouting.steps))
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="工艺路线不存在")
    return row


# ============================================================
# 工作中心
# ============================================================

@router.get("/mfge/work-centers", response_model=Page)
async def list_work_centers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:mfg:read")),
):
    stmt = select(ErpWorkCenter).where(ErpWorkCenter.deleted_at.is_(None))
    count = select(func.count()).select_from(ErpWorkCenter).where(ErpWorkCenter.deleted_at.is_(None))
    if keyword:
        like = f"%{keyword}%"
        cond = func.concat(ErpWorkCenter.code, " ", ErpWorkCenter.name).ilike(like)
        stmt = stmt.where(cond); count = count.where(cond)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpWorkCenter.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[WorkCenterOut.model_validate(r) for r in rows])


@router.post("/mfge/work-centers", response_model=WorkCenterOut, status_code=201)
async def create_work_center(
    payload: WorkCenterIn,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:mfg:write")),
):
    dup = (await db.execute(select(ErpWorkCenter).where(ErpWorkCenter.code == payload.code))).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail=f"工作中心编码已存在：{payload.code}")
    wc = ErpWorkCenter(**payload.model_dump())
    db.add(wc)
    await db.commit()
    await db.refresh(wc)
    return WorkCenterOut.model_validate(wc)


@router.put("/mfge/work-centers/{wc_id}", response_model=WorkCenterOut)
async def update_work_center(
    wc_id: int,
    payload: WorkCenterIn,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:mfg:write")),
):
    wc = (await db.execute(
        select(ErpWorkCenter).where(ErpWorkCenter.id == wc_id, ErpWorkCenter.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not wc:
        raise HTTPException(status_code=404, detail="工作中心不存在")
    for field, val in payload.model_dump().items():
        setattr(wc, field, val)
    await db.commit()
    await db.refresh(wc)
    return WorkCenterOut.model_validate(wc)


@router.delete("/mfge/work-centers/{wc_id}", status_code=204)
async def delete_work_center(
    wc_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:mfg:delete")),
):
    wc = (await db.execute(
        select(ErpWorkCenter).where(ErpWorkCenter.id == wc_id, ErpWorkCenter.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not wc:
        raise HTTPException(status_code=404, detail="工作中心不存在")
    wc.deleted_at = func.now()
    await db.commit()
    return None


# ============================================================
# 工艺路线
# ============================================================

@router.get("/mfge/routings", response_model=Page)
async def list_routings(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    product_id: int | None = None,
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:mfg:read")),
):
    stmt = select(ErpRouting).where(ErpRouting.deleted_at.is_(None))
    count = select(func.count()).select_from(ErpRouting).where(ErpRouting.deleted_at.is_(None))
    if product_id:
        stmt = stmt.where(ErpRouting.product_id == product_id); count = count.where(ErpRouting.product_id == product_id)
    if keyword:
        like = f"%{keyword}%"
        cond = func.concat(ErpRouting.product_code, " ", ErpRouting.product_name, " ", ErpRouting.name, " ", ErpRouting.version).ilike(like)
        stmt = stmt.where(cond); count = count.where(cond)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpRouting.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    items2 = []
    for r in rows:
        n = (await db.execute(
            select(func.count()).select_from(ErpRoutingStep).where(ErpRoutingStep.routing_id == r.id)
        )).scalar_one()
        items2.append({
            "id": r.id, "product_id": r.product_id, "product_code": r.product_code,
            "product_name": r.product_name, "version": r.version, "is_active": r.is_active,
            "status": r.status, "lead_time_hours": float(r.lead_time_hours), "step_count": n,
        })
    return Page(total=total, page=page, page_size=page_size, items=items2)


@router.get("/mfge/routings/{routing_id}", response_model=RoutingOut)
async def get_routing(
    routing_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:mfg:read")),
):
    return RoutingOut.model_validate(await _get_routing(db, routing_id))


@router.post("/mfge/routings", response_model=RoutingOut, status_code=201)
async def create_routing(
    payload: RoutingIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:mfg:write")),
):
    if not payload.steps:
        raise HTTPException(status_code=400, detail="工艺路线至少需要一道工序")
    dup = (await db.execute(
        select(ErpRouting).where(ErpRouting.product_id == payload.product_id,
                                 ErpRouting.version == payload.version)
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail="该商品此版本工艺路线已存在，请更换版本号")
    product = await db.get(ErpProduct, payload.product_id)
    if not product:
        raise HTTPException(status_code=400, detail="商品不存在")

    steps = []
    for st in payload.steps:
        wc = await db.get(ErpWorkCenter, st.work_center_id) if st.work_center_id else None
        steps.append(ErpRoutingStep(
            seq=st.seq, process_code=st.process_code, process_name=st.process_name,
            work_center_id=st.work_center_id,
            work_center_name=st.work_center_name or (wc.name if wc else None),
            std_time=st.std_time, setup_minutes=st.setup_minutes, time_type=st.time_type,
            yield_rate=st.yield_rate, is_last=st.is_last, description=st.description, sort=st.sort,
        ))
    routing = ErpRouting(
        product_id=payload.product_id, product_code=product.code, product_name=product.name,
        name=payload.name or f"{product.name} 工艺", version=payload.version,
        is_active=payload.is_active, output_qty=payload.output_qty,
        unit=payload.unit or product.unit, lead_time_hours=payload.lead_time_hours,
        remark=payload.remark, created_by=getattr(user, "id", None),
    )
    routing.steps = steps
    db.add(routing)
    await db.commit()
    await db.refresh(routing, attribute_names=["steps"])
    return RoutingOut.model_validate(routing)


@router.put("/mfge/routings/{routing_id}", response_model=RoutingOut)
async def update_routing(
    routing_id: int,
    payload: RoutingIn,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:mfg:write")),
):
    routing = await _get_routing(db, routing_id)
    if not payload.steps:
        raise HTTPException(status_code=400, detail="工艺路线至少需要一道工序")
    product = await db.get(ErpProduct, payload.product_id)
    if not product:
        raise HTTPException(status_code=400, detail="商品不存在")
    routing.product_id = payload.product_id
    routing.product_code = product.code
    routing.product_name = product.name
    routing.name = payload.name or f"{product.name} 工艺"
    routing.version = payload.version
    routing.is_active = payload.is_active
    routing.output_qty = payload.output_qty
    routing.unit = payload.unit or product.unit
    routing.lead_time_hours = payload.lead_time_hours
    routing.remark = payload.remark
    routing.steps = []
    for st in payload.steps:
        wc = await db.get(ErpWorkCenter, st.work_center_id) if st.work_center_id else None
        routing.steps.append(ErpRoutingStep(
            seq=st.seq, process_code=st.process_code, process_name=st.process_name,
            work_center_id=st.work_center_id,
            work_center_name=st.work_center_name or (wc.name if wc else None),
            std_time=st.std_time, setup_minutes=st.setup_minutes, time_type=st.time_type,
            yield_rate=st.yield_rate, is_last=st.is_last, description=st.description, sort=st.sort,
        ))
    await db.commit()
    await db.refresh(routing, attribute_names=["steps"])
    return RoutingOut.model_validate(routing)


@router.delete("/mfge/routings/{routing_id}", status_code=204)
async def delete_routing(
    routing_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:mfg:delete")),
):
    routing = (await db.execute(
        select(ErpRouting).where(ErpRouting.id == routing_id, ErpRouting.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not routing:
        raise HTTPException(status_code=404, detail="工艺路线不存在")
    routing.deleted_at = func.now()
    await db.commit()
    return None


# ============================================================
# 生产排程
# ============================================================

@router.post("/mfge/schedules/load", response_model=LoadResult)
async def load_schedule(
    payload: ScheduleIn,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:mfg:write")),
):
    """按工单产品加载工艺路线，为每道工序生成排程记录（可重复加载以刷新）"""
    wo = (await db.execute(
        select(ErpWorkOrder).where(ErpWorkOrder.id == payload.work_order_id, ErpWorkOrder.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not wo:
        raise HTTPException(status_code=404, detail="生产工单不存在")

    routing = None
    if payload.routing_id:
        routing = await _get_routing(db, payload.routing_id)
    else:
        routing = (await db.execute(
            select(ErpRouting).where(
                ErpRouting.product_id == wo.product_id,
                ErpRouting.is_active == 1, ErpRouting.deleted_at.is_(None),
            ).options(selectinload(ErpRouting.steps))
            .order_by(ErpRouting.id.desc()).limit(1)
        )).scalar_one_or_none()
    if not routing:
        raise HTTPException(status_code=400, detail="未找到可用的工艺路线，请先为产品维护工艺路线")

    # 删除该工单原有排程后重建
    old = (await db.execute(
        select(ErpProductionSchedule).where(ErpProductionSchedule.work_order_id == wo.id)
    )).scalars().all()
    for o in old:
        o.deleted_at = func.now()

    plan_qty = float(wo.quantity)
    created: list[ErpProductionSchedule] = []
    yield_carry = 1.0
    for st in sorted(routing.steps, key=lambda s: (s.seq or s.sort or 0)):
        yield_carry *= float(st.yield_rate or 100) / 100
        hours = 0.0
        if float(st.std_time) > 0:
            if st.time_type == "per_lot":
                hours = float(st.setup_minutes) / 60 + float(st.std_time)
            else:
                hours = (float(st.setup_minutes) / 60) + (plan_qty * float(st.std_time))
        sched = ErpProductionSchedule(
            code=await _next_code(db, "SC", ErpProductionSchedule),
            work_order_id=wo.id, work_order_code=wo.code,
            product_id=wo.product_id, product_code=wo.product_code, product_name=wo.product_name,
            routing_id=routing.id, step_id=st.id, step_seq=st.seq,
            process_name=st.process_name,
            work_center_id=st.work_center_id, work_center_name=st.work_center_name,
            plan_date=payload.plan_date, plan_qty=round(plan_qty / yield_carry, 4),
            plan_hours=round(hours, 2),
            status="planned",
        )
        created.append(sched)
        db.add(sched)

    routing.lead_time_hours = round(sum(float(s.plan_hours) for s in created), 2) or routing.lead_time_hours
    await db.commit()

    out_rows = []
    for s in created:
        await db.refresh(s)
        out_rows.append(ScheduleOut.model_validate(s))
    return LoadResult(
        work_order_id=wo.id, work_order_code=wo.code,
        routing_id=routing.id, routing_name=routing.name,
        rows=self_sorted(out_rows), total_steps=len(out_rows),
    )


def self_sorted(rows: list[ScheduleOut]) -> list[ScheduleOut]:
    return sorted(rows, key=lambda s: s.step_seq or 0)


@router.get("/mfge/schedules", response_model=Page)
async def list_schedules(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    work_order_id: int | None = None,
    work_center_id: int | None = None,
    status: str | None = None,
    plan_date: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:mfg:read")),
):
    stmt = select(ErpProductionSchedule).where(ErpProductionSchedule.deleted_at.is_(None))
    count = select(func.count()).select_from(ErpProductionSchedule).where(ErpProductionSchedule.deleted_at.is_(None))
    if work_order_id:
        stmt = stmt.where(ErpProductionSchedule.work_order_id == work_order_id); count = count.where(ErpProductionSchedule.work_order_id == work_order_id)
    if work_center_id:
        stmt = stmt.where(ErpProductionSchedule.work_center_id == work_center_id); count = count.where(ErpProductionSchedule.work_center_id == work_center_id)
    if status:
        stmt = stmt.where(ErpProductionSchedule.status == status); count = count.where(ErpProductionSchedule.status == status)
    if plan_date:
        stmt = stmt.where(ErpProductionSchedule.plan_date == plan_date); count = count.where(ErpProductionSchedule.plan_date == plan_date)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpProductionSchedule.plan_date.asc().nullsfirst(),
                      ErpProductionSchedule.step_seq.asc().nullsfirst(),
                      ErpProductionSchedule.id.asc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[ScheduleOut.model_validate(r) for r in rows])


@router.put("/mfge/schedules/{sched_id}", response_model=ScheduleOut)
async def update_schedule(
    sched_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:mfg:write")),
):
    sched = (await db.execute(
        select(ErpProductionSchedule).where(ErpProductionSchedule.id == sched_id, ErpProductionSchedule.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not sched:
        raise HTTPException(status_code=404, detail="排程记录不存在")
    for key in ("plan_date", "plan_qty", "plan_hours", "work_center_id", "work_center_name", "remark"):
        if key in payload:
            setattr(sched, key, payload[key])
    if "status" in payload and payload["status"] in ("planned", "in_progress", "completed", "skipped"):
        sched.status = payload["status"]
    await db.commit()
    await db.refresh(sched)
    return ScheduleOut.model_validate(sched)