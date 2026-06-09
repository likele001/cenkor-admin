"""系统设置路由（独立于 cms_site_config）。"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.api.deps import require_permission
from cenkor_admin.core.db import get_db

router = APIRouter()


class SettingUpdate(BaseModel):
    value: Any
    description: str | None = None


def _to_dict(s: auth_models.SystemSetting) -> dict:
    raw = s.value
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        parsed = raw
    return {
        "key": s.key,
        "value": parsed,
        "description": s.description,
        "group": s.group,
        "updated_by": s.updated_by,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@router.get("", response_model=dict[str, Any])
async def list_settings(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("settings:read")),
    group: str | None = None,
):
    stmt = select(auth_models.SystemSetting)
    if group:
        stmt = stmt.where(auth_models.SystemSetting.group == group)
    stmt = stmt.order_by(auth_models.SystemSetting.group, auth_models.SystemSetting.key)
    result = await db.execute(stmt)
    items = [_to_dict(s) for s in result.scalars().all()]
    return {"items": items, "total": len(items)}


@router.get("/{key}", response_model=dict[str, Any])
async def get_setting(
    key: str,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("settings:read")),
):
    s = await db.get(auth_models.SystemSetting, key)
    if not s:
        raise HTTPException(404, "设置不存在")
    return _to_dict(s)


@router.put("/{key}", response_model=dict[str, Any])
async def upsert_setting(
    key: str,
    body: SettingUpdate,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("settings:write")),
):
    s = await db.get(auth_models.SystemSetting, key)
    value_str = json.dumps(body.value) if not isinstance(body.value, str) else body.value
    if s:
        s.value = value_str
        if body.description is not None:
            s.description = body.description
        s.updated_by = user.id
    else:
        s = auth_models.SystemSetting(
            key=key, value=value_str, description=body.description,
            group="custom", updated_by=user.id,
        )
        db.add(s)
    await db.commit()
    await db.refresh(s)
    return _to_dict(s)
