from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from . import models
from cenkor_admin.core.db import get_db

router = APIRouter()


def _to_dict(n: models.Note) -> dict:
    return {
        "id": n.id,
        "title": n.title,
        "content": n.content,
        "color": n.color,
        "creator_id": n.creator_id,
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "updated_at": n.updated_at.isoformat() if n.updated_at else None,
    }


@router.get("")
async def list_notes(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("quick_notes:read")),
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    stmt = select(models.Note).where(models.Note.deleted_at.is_(None))
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            (models.Note.title.ilike(like)) | (models.Note.content.ilike(like))
        )
    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar() or 0
    stmt = stmt.order_by(models.Note.updated_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return {
        "items": [_to_dict(n) for n in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("", status_code=201)
async def create_note(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("quick_notes:write")),
):
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "title is required")
    obj = models.Note(
        title=title,
        content=body.get("content"),
        color=body.get("color", "default"),
        creator_id=current.id,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _to_dict(obj)


@router.patch("/{note_id}")
async def update_note(
    note_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("quick_notes:write")),
):
    obj = await db.get(models.Note, note_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "not found")
    for field in ("title", "content", "color"):
        if field in body:
            setattr(obj, field, body[field])
    await db.commit()
    await db.refresh(obj)
    return _to_dict(obj)


@router.delete("/{note_id}", status_code=204)
async def delete_note(
    note_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("quick_notes:write")),
):
    obj = await db.get(models.Note, note_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "not found")
    obj.deleted_at = datetime.now(timezone.utc)
    await db.commit()
