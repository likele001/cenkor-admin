"""Webhook 订阅 & URL 重定向 管理路由（M3·P2，受保护）"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.system import models
from cenkor_admin.core.db import get_db

router = APIRouter()

WEBHOOK_EVENTS = (
    "entry.saved",
    "entry.deleted",
    "content_type.created",
    "media.uploaded",
    "user.login",
)


# ============================================================
# Webhook
# ============================================================

@router.get("/webhooks", response_model=dict[str, Any])
async def list_webhooks(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(models.Webhook).order_by(models.Webhook.id.desc())
    )).scalars().all()
    return {"items": [_wh_dict(w) for w in rows], "total": len(rows)}


@router.post("/webhooks", response_model=dict[str, Any], status_code=201)
async def create_webhook(body: dict, db: AsyncSession = Depends(get_db)):
    url = body.get("url")
    events = body.get("events") or []
    if not url:
        raise HTTPException(400, "url required")
    invalid = [e for e in events if e not in WEBHOOK_EVENTS]
    if invalid:
        raise HTTPException(400, f"非法事件: {invalid}，可用: {list(WEBHOOK_EVENTS)}")
    obj = models.Webhook(
        url=url, events=events, secret=body.get("secret"),
        description=body.get("description"), enabled=body.get("enabled", True),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _wh_dict(obj)


@router.patch("/webhooks/{wh_id}", response_model=dict[str, Any])
async def update_webhook(wh_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    obj = await db.get(models.Webhook, wh_id)
    if not obj:
        raise HTTPException(404, "Webhook not found")
    if "events" in body:
        invalid = [e for e in body["events"] if e not in WEBHOOK_EVENTS]
        if invalid:
            raise HTTPException(400, f"非法事件: {invalid}")
    for k in ("url", "events", "secret", "description", "enabled"):
        if k in body:
            setattr(obj, k, body[k])
    await db.commit()
    await db.refresh(obj)
    return _wh_dict(obj)


@router.delete("/webhooks/{wh_id}", status_code=204)
async def delete_webhook(wh_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(models.Webhook, wh_id)
    if not obj:
        raise HTTPException(404, "Webhook not found")
    await db.delete(obj)
    await db.commit()


def _wh_dict(w: models.Webhook) -> dict:
    return {
        "id": w.id, "url": w.url, "events": w.events or [],
        "secret": w.secret, "description": w.description, "enabled": w.enabled,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }


# ============================================================
# URL 重定向
# ============================================================

@router.get("/redirects", response_model=dict[str, Any])
async def list_redirects(db: AsyncSession = Depends(get_db), search: str | None = Query(None)):
    stmt = select(models.Redirect).order_by(models.Redirect.id.desc())
    if search:
        stmt = stmt.where(
            models.Redirect.from_path.ilike(f"%{search}%")
            | models.Redirect.to_path.ilike(f"%{search}%")
        )
    rows = (await db.execute(stmt)).scalars().all()
    return {"items": [_rd_dict(r) for r in rows], "total": len(rows)}


@router.post("/redirects", response_model=dict[str, Any], status_code=201)
async def create_redirect(body: dict, db: AsyncSession = Depends(get_db)):
    from_path = (body.get("from_path") or "").strip()
    to_path = (body.get("to_path") or "").strip()
    if not from_path or not to_path:
        raise HTTPException(400, "from_path 与 to_path 必填")
    existing = await db.execute(
        select(models.Redirect).where(models.Redirect.from_path == from_path)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"from_path 已存在: {from_path}")
    obj = models.Redirect(
        from_path=from_path, to_path=to_path,
        code=body.get("code", 301), enabled=body.get("enabled", True),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    from cenkor_admin.core.redirects import clear_redirect_cache
    clear_redirect_cache()
    return _rd_dict(obj)


@router.patch("/redirects/{rid}", response_model=dict[str, Any])
async def update_redirect(rid: int, body: dict, db: AsyncSession = Depends(get_db)):
    obj = await db.get(models.Redirect, rid)
    if not obj:
        raise HTTPException(404, "Redirect not found")
    for k in ("from_path", "to_path", "code", "enabled"):
        if k in body:
            setattr(obj, k, body[k])
    await db.commit()
    await db.refresh(obj)
    from cenkor_admin.core.redirects import clear_redirect_cache
    clear_redirect_cache()
    return _rd_dict(obj)


@router.delete("/redirects/{rid}", status_code=204)
async def delete_redirect(rid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(models.Redirect, rid)
    if not obj:
        raise HTTPException(404, "Redirect not found")
    await db.delete(obj)
    await db.commit()
    from cenkor_admin.core.redirects import clear_redirect_cache
    clear_redirect_cache()


def _rd_dict(r: models.Redirect) -> dict:
    return {
        "id": r.id, "from_path": r.from_path, "to_path": r.to_path,
        "code": r.code, "enabled": r.enabled,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
