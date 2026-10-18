"""库存管理 — CRUD 路由（由 scripts/gen-app.py 生成）

约定：
  · 每个端点用 require_permission("<key>:<entity>:<action>") 守卫
  · 列表支持 search 模糊搜索 + 指定字段精确过滤 + 分页
  · 删除为软删（写 deleted_at）
  · 生成器不覆盖的地方标了 # TODO(business)，可自行补充业务校验/跨 App 写
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.core.db import get_db
from . import models

router = APIRouter()


def _to_dict_warehouse(obj: models.Warehouse) -> dict:
    return {
        "id": obj.id,
        "code": obj.code,
        "name": obj.name,
        "type": obj.type,
        "enable": obj.enable,
        "remark": obj.remark,
        "creator_id": obj.creator_id,
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
        "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
    }


@router.get("/warehouse")
async def list_warehouse(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("inventory:warehouse:read")),
    search: str | None = None,
    type: str | None = None,
    enable: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    stmt = select(models.Warehouse).where(models.Warehouse.deleted_at.is_(None))
    if search:
        like = f"%{search}%"
        stmt = stmt.where(models.Warehouse.code.ilike(like) | models.Warehouse.name.ilike(like) | models.Warehouse.type.ilike(like))
    if type is not None:
        stmt = stmt.where(models.Warehouse.type == type)
    if enable is not None:
        stmt = stmt.where(models.Warehouse.enable == enable)
    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar() or 0
    stmt = stmt.order_by(models.Warehouse.updated_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return {
        "items": [_to_dict_warehouse(o) for o in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/warehouse/export")
async def export_warehouse(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("inventory:warehouse:export")),
):
    stmt = select(models.Warehouse).where(models.Warehouse.deleted_at.is_(None))
    stmt = stmt.order_by(models.Warehouse.updated_at.desc())
    items = (await db.execute(stmt)).scalars().all()
    header = ["id"] + ['code', 'name', 'type', 'enable', 'remark'] + ["creator_id", "created_at", "updated_at"]
    lines = [",".join(header)]
    for o in items:
        d = _to_dict_warehouse(o)
        lines.append(",".join(str(d.get(k, "")) for k in header))
    csv = "\ufeff" + "\n".join(lines)
    return Response(csv, media_type="text/csv", headers={
        "Content-Disposition": 'attachment; filename="warehouse.csv"'}
    )


@router.post("/warehouse", status_code=201)
async def create_warehouse(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("inventory:warehouse:write")),
):
    # TODO(business): 在此补充跨 App 写 / 业务校验
    obj = models.Warehouse()
    if "code" in body:
        obj.code = body["code"]
    if "name" in body:
        obj.name = body["name"]
    if "type" in body:
        obj.type = body["type"]
    if "enable" in body:
        obj.enable = body["enable"]
    if "remark" in body:
        obj.remark = body["remark"]
    if obj.code in (None, ""):
        raise HTTPException(400, "code is required")
    if obj.name in (None, ""):
        raise HTTPException(400, "name is required")
    obj.creator_id = current.id
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _to_dict_warehouse(obj)


@router.get("/warehouse/{item_id}")
async def get_warehouse(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("inventory:warehouse:read")),
):
    obj = await db.get(models.Warehouse, item_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "not found")
    return _to_dict_warehouse(obj)


@router.patch("/warehouse/{item_id}")
async def update_warehouse(
    item_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("inventory:warehouse:write")),
):
    obj = await db.get(models.Warehouse, item_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "not found")
    # TODO(business): 在此补充业务校验
    for field in ("code", "name", "type", "enable", "remark"):
        if field in body:
            setattr(obj, field, body[field])
    await db.commit()
    await db.refresh(obj)
    return _to_dict_warehouse(obj)


@router.delete("/warehouse/{item_id}", status_code=204)
async def delete_warehouse(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("inventory:warehouse:delete")),
):
    obj = await db.get(models.Warehouse, item_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "not found")
    obj.deleted_at = datetime.now(timezone.utc)
    await db.commit()


def _to_dict_location(obj: models.Location) -> dict:
    return {
        "id": obj.id,
        "code": obj.code,
        "name": obj.name,
        "warehouse_id": obj.warehouse_id,
        "capacity": float(obj.capacity) if obj.capacity is not None else None,
        "creator_id": obj.creator_id,
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
        "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
    }


@router.get("/location")
async def list_location(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("inventory:location:read")),
    search: str | None = None,
    warehouse_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    stmt = select(models.Location).where(models.Location.deleted_at.is_(None))
    if search:
        like = f"%{search}%"
        stmt = stmt.where(models.Location.code.ilike(like))
    if warehouse_id is not None:
        stmt = stmt.where(models.Location.warehouse_id == warehouse_id)
    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar() or 0
    stmt = stmt.order_by(models.Location.updated_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return {
        "items": [_to_dict_location(o) for o in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/location/export")
async def export_location(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("inventory:location:export")),
):
    stmt = select(models.Location).where(models.Location.deleted_at.is_(None))
    stmt = stmt.order_by(models.Location.updated_at.desc())
    items = (await db.execute(stmt)).scalars().all()
    header = ["id"] + ['code', 'name', 'warehouse_id', 'capacity'] + ["creator_id", "created_at", "updated_at"]
    lines = [",".join(header)]
    for o in items:
        d = _to_dict_location(o)
        lines.append(",".join(str(d.get(k, "")) for k in header))
    csv = "\ufeff" + "\n".join(lines)
    return Response(csv, media_type="text/csv", headers={
        "Content-Disposition": 'attachment; filename="location.csv"'}
    )


@router.post("/location", status_code=201)
async def create_location(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("inventory:location:write")),
):
    # TODO(business): 在此补充跨 App 写 / 业务校验
    obj = models.Location()
    if "code" in body:
        obj.code = body["code"]
    if "name" in body:
        obj.name = body["name"]
    if "warehouse_id" in body:
        obj.warehouse_id = body["warehouse_id"]
    if "capacity" in body:
        obj.capacity = body["capacity"]
    if obj.code in (None, ""):
        raise HTTPException(400, "code is required")
    if obj.name in (None, ""):
        raise HTTPException(400, "name is required")
    obj.creator_id = current.id
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _to_dict_location(obj)


@router.get("/location/{item_id}")
async def get_location(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("inventory:location:read")),
):
    obj = await db.get(models.Location, item_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "not found")
    return _to_dict_location(obj)


@router.patch("/location/{item_id}")
async def update_location(
    item_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("inventory:location:write")),
):
    obj = await db.get(models.Location, item_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "not found")
    # TODO(business): 在此补充业务校验
    for field in ("code", "name", "warehouse_id", "capacity"):
        if field in body:
            setattr(obj, field, body[field])
    await db.commit()
    await db.refresh(obj)
    return _to_dict_location(obj)


@router.delete("/location/{item_id}", status_code=204)
async def delete_location(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("inventory:location:delete")),
):
    obj = await db.get(models.Location, item_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "not found")
    obj.deleted_at = datetime.now(timezone.utc)
    await db.commit()
