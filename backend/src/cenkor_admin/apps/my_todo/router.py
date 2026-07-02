from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.my_todo import models
from cenkor_admin.core.db import get_db

router = APIRouter()


def _to_dict(item: models.TodoItem) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "done": item.done,
        "note": item.note,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


@router.get("")
async def list_todos(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("my_todo:read")),
    done: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    stmt = select(models.TodoItem).where(models.TodoItem.deleted_at.is_(None))
    if done is not None:
        stmt = stmt.where(models.TodoItem.done == done)
    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery()),
    )).scalar() or 0
    stmt = stmt.order_by(models.TodoItem.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return {
        "items": [_to_dict(i) for i in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("", status_code=201)
async def create_todo(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("my_todo:write")),
):
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "title is required")
    obj = models.TodoItem(
        title=title,
        note=body.get("note"),
        creator_id=current.id,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _to_dict(obj)


@router.patch("/{item_id}")
async def update_todo(
    item_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("my_todo:write")),
):
    obj = await db.get(models.TodoItem, item_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "not found")
    if "title" in body:
        obj.title = body["title"]
    if "done" in body:
        obj.done = body["done"]
    if "note" in body:
        obj.note = body["note"]
    await db.commit()
    await db.refresh(obj)
    return _to_dict(obj)


@router.delete("/{item_id}", status_code=204)
async def delete_todo(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("my_todo:write")),
):
    obj = await db.get(models.TodoItem, item_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "not found")
    obj.deleted_at = datetime.now(timezone.utc)
    await db.commit()
