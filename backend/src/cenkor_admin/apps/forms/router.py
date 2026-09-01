"""Forms App · 管理路由（受保护，自动挂载于 /forms）"""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.forms.models import Form, FormSubmission
from cenkor_admin.core.db import get_db

router = APIRouter()


# ============================================================
# 表单定义
# ============================================================

@router.get("", response_model=dict[str, Any])
async def list_forms(db: AsyncSession = Depends(get_db), search: str | None = Query(None)):
    stmt = select(Form).order_by(Form.id.desc())
    if search:
        stmt = stmt.where(Form.title.ilike(f"%{search}%") | Form.key.ilike(f"%{search}%"))
    rows = (await db.execute(stmt)).scalars().all()
    result = []
    for f in rows:
        d = _form_dict(f)
        d["submissions"] = (await db.execute(
            select(func.count()).select_from(FormSubmission).where(FormSubmission.form_id == f.id)
        )).scalar() or 0
        result.append(d)
    return {"items": result, "total": len(result)}


@router.post("", response_model=dict[str, Any], status_code=201)
async def create_form(body: dict, db: AsyncSession = Depends(get_db)):
    key = body.get("key")
    title = body.get("title")
    if not key or not title:
        raise HTTPException(400, "key 与 title 必填")
    existing = await db.execute(select(Form).where(Form.key == key))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"表单 key 已存在: {key}")
    obj = Form(
        key=key, title=title, description=body.get("description"),
        fields=body.get("fields") or [], success_message=body.get("success_message"),
        enabled=body.get("enabled", True),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _form_dict(obj)


@router.patch("/{form_id}", response_model=dict[str, Any])
async def update_form(form_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Form, form_id)
    if not obj:
        raise HTTPException(404, "Form not found")
    for k in ("title", "description", "fields", "success_message", "enabled", "key"):
        if k in body:
            setattr(obj, k, body[k])
    await db.commit()
    await db.refresh(obj)
    return _form_dict(obj)


@router.delete("/{form_id}", status_code=204)
async def delete_form(form_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Form, form_id)
    if not obj:
        raise HTTPException(404, "Form not found")
    await db.delete(obj)
    await db.commit()


# ============================================================
# 提交记录
# ============================================================

@router.get("/{form_id}/submissions", response_model=dict[str, Any])
async def list_submissions(
    form_id: int,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    form = await db.get(Form, form_id)
    if not form:
        raise HTTPException(404, "Form not found")
    stmt = select(FormSubmission).where(FormSubmission.form_id == form_id).order_by(FormSubmission.id.desc())
    total = (await db.execute(
        select(func.count()).select_from(FormSubmission).where(FormSubmission.form_id == form_id)
    )).scalar() or 0
    rows = (await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {
        "items": [{
            "id": s.id, "data": s.data or {}, "ip": s.ip,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        } for s in rows],
        "total": total, "page": page, "page_size": page_size,
        "fields": form.fields or [],
    }


@router.get("/{form_id}/submissions/export")
async def export_submissions(form_id: int, db: AsyncSession = Depends(get_db)):
    """导出提交记录为 CSV。"""
    form = await db.get(Form, form_id)
    if not form:
        raise HTTPException(404, "Form not found")
    rows = (await db.execute(
        select(FormSubmission).where(FormSubmission.form_id == form_id).order_by(FormSubmission.id.desc())
    )).scalars().all()
    keys: list[str] = []
    for f in form.fields or []:
        k = f.get("key") if isinstance(f, dict) else getattr(f, "key", None)
        if k and k not in keys:
            keys.append(k)

    def gen():
        yield "\ufeff"
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "created_at", "ip"] + keys)
        yield buf.getvalue()
        for s in rows:
            buf = io.StringIO()
            w = csv.writer(buf)
            data = s.data or {}
            w.writerow([s.id, s.created_at.isoformat() if s.created_at else "", s.ip or ""] + [data.get(k, "") for k in keys])
            yield buf.getvalue()

    return StreamingResponse(
        gen(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="form_{form.key}.csv"'},
    )


def _form_dict(f: Form) -> dict:
    return {
        "id": f.id, "key": f.key, "title": f.title, "description": f.description,
        "fields": f.fields or [], "success_message": f.success_message, "enabled": f.enabled,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }
