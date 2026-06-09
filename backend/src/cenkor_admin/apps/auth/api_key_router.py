"""API Key 路由：生成、列出、撤销。"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.api.deps import get_current_user, require_permission
from cenkor_admin.core.db import get_db

router = APIRouter()


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scopes: list[str] = Field(default_factory=list)
    expires_days: int | None = Field(None, ge=1, le=3650)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _to_dict(k: auth_models.ApiKey, *, include_token: str | None = None) -> dict:
    return {
        "id": k.id,
        "name": k.name,
        "prefix": k.prefix,
        "scopes": (k.scopes or "").split(",") if k.scopes else [],
        "expires_at": k.expires_at.isoformat() if k.expires_at else None,
        "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        "revoked": k.revoked_at is not None,
        "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
        "created_at": k.created_at.isoformat() if k.created_at else None,
        "token": include_token,  # 仅在创建时一次性返回
    }


@router.get("", response_model=dict[str, Any])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("apikey:read")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """当前用户的 API Key 列表（仅自己可见）"""
    stmt = (
        select(auth_models.ApiKey)
        .where(auth_models.ApiKey.user_id == user.id)
        .order_by(auth_models.ApiKey.created_at.desc(), auth_models.ApiKey.id.desc())
    )
    from cenkor_admin.core.repository import paginate
    data = await paginate(db, stmt, page=page, page_size=page_size)
    return {
        "items": [_to_dict(k) for k in data["items"]],
        "total": data["total"],
        "page": data["page"],
        "page_size": data["page_size"],
    }


@router.post("", status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("apikey:write")),
):
    """创建 API Key。

    **token 字段仅在创建时一次性返回**，之后无法再查询，请妥善保存。
    """
    # 生成 token: ck_<random 32 字节 base32>
    raw = "ck_" + secrets.token_urlsafe(32)
    prefix = raw[:8]  # "ck_xxxx"
    token_hash = _hash_token(raw)
    expires = None
    if body.expires_days:
        expires = datetime.now(timezone.utc).timestamp() + body.expires_days * 86400
        expires_dt = datetime.fromtimestamp(expires, tz=timezone.utc)
    else:
        expires_dt = None
    k = auth_models.ApiKey(
        user_id=user.id,
        name=body.name,
        prefix=prefix,
        hash=token_hash,
        scopes=",".join(body.scopes) if body.scopes else None,
        expires_at=expires_dt,
    )
    db.add(k)
    await db.commit()
    await db.refresh(k)
    return _to_dict(k, include_token=raw)


@router.post("/{key_id}/revoke", status_code=200)
async def revoke_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("apikey:write")),
):
    """撤销 API Key（仅自己）"""
    k = await db.get(auth_models.ApiKey, key_id)
    if not k or k.user_id != user.id:
        raise HTTPException(404, "API Key 不存在")
    if k.revoked_at:
        return {"ok": True, "already_revoked": True}
    k.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True}


@router.delete("/{key_id}", status_code=204)
async def delete_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("apikey:write")),
):
    """删除 API Key（仅自己）"""
    k = await db.get(auth_models.ApiKey, key_id)
    if not k or k.user_id != user.id:
        raise HTTPException(404, "API Key 不存在")
    await db.delete(k)
    await db.commit()
