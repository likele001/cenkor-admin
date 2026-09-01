"""Forms App · 公共路由（无需鉴权，M4·P3 4.3）"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.forms.models import Form, FormSubmission
from cenkor_admin.core.db import get_db

router = APIRouter()


@router.get("/forms", response_model=dict[str, Any])
async def list_public_forms(db: AsyncSession = Depends(get_db)):
    """公开表单列表（仅启用，含字段定义供前端渲染）。"""
    rows = (await db.execute(
        select(Form).where(Form.enabled.is_(True)).order_by(Form.id)
    )).scalars().all()
    return {"items": [{
        "id": f.id, "key": f.key, "title": f.title, "description": f.description,
        "fields": f.fields or [], "success_message": f.success_message,
    } for f in rows]}


@router.post("/forms/{key}/submit", response_model=dict[str, Any], status_code=201)
async def submit_form(
    key: str,
    body: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """提交表单。body: {values: {field_key: value}}。"""
    form = (await db.execute(
        select(Form).where(Form.key == key, Form.enabled.is_(True))
    )).scalar_one_or_none()
    if not form:
        raise HTTPException(404, "表单不存在或已停用")

    values = body.get("values") or {}
    # 必填校验
    fields = form.fields or []
    missing = []
    for f in fields:
        fk = f.get("key") if isinstance(f, dict) else getattr(f, "key", None)
        if f.get("required") and (fk not in values or values.get(fk) in ("", None)):
            missing.append(fk)
    if missing:
        raise HTTPException(400, f"缺少必填项: {missing}")

    obj = FormSubmission(
        form_id=form.id,
        data=values,
        ip=request.client.host if request.client else None,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {
        "id": obj.id,
        "message": form.success_message or "提交成功",
    }
