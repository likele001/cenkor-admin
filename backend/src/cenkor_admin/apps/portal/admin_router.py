"""Portal App · 前台用户后台管理 API（管理员操作 portal_users）"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import get_current_user, require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.portal import models, schemas
from cenkor_admin.apps.portal.auth import hash_password
from cenkor_admin.core.db import get_db
from cenkor_admin.core.repository import paginate

router = APIRouter()


@router.get("/users", response_model=dict[str, Any])
async def list_portal_users(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("portal:users:read")),
    search: str | None = Query(None, description="按 username / email / phone / nickname 模糊搜索"),
    status_filter: str | None = Query(None, alias="status"),
    include_deleted: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """前台用户列表"""
    conds = []
    if search:
        like = f"%{search}%"
        conds.append(
            (models.PortalUser.username.ilike(like))
            | (models.PortalUser.email.ilike(like))
            | (models.PortalUser.phone.ilike(like))
            | (models.PortalUser.nickname.ilike(like))
        )
    if status_filter:
        conds.append(models.PortalUser.status == status_filter)
    if not include_deleted:
        conds.append(models.PortalUser.deleted_at.is_(None))

    stmt = (
        select(models.PortalUser)
        .where(*conds)
        .order_by(models.PortalUser.id.desc())
    )
    data = await paginate(db, stmt, page=page, page_size=page_size)

    return {
        "items": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "phone": u.phone,
                "nickname": u.nickname,
                "avatar": u.avatar,
                "status": u.status,
                "register_ip": u.register_ip,
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                "last_login_ip": u.last_login_ip,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "updated_at": u.updated_at.isoformat() if u.updated_at else None,
            }
            for u in data["items"]
        ],
        "total": data["total"],
        "page": data["page"],
        "page_size": data["page_size"],
    }


@router.get("/users/{user_id}", response_model=dict[str, Any])
async def get_portal_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("portal:users:read")),
):
    """前台用户详情"""
    user = await db.get(models.PortalUser, user_id)
    if not user or user.deleted_at:
        raise HTTPException(404, "Portal user not found")

    # OAuth 绑定列表
    oauths = (await db.execute(
        select(models.PortalUserOAuth)
        .where(models.PortalUserOAuth.user_id == user_id)
    )).scalars().all()

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "phone": user.phone,
        "nickname": user.nickname,
        "avatar": user.avatar,
        "status": user.status,
        "register_ip": user.register_ip,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "last_login_ip": user.last_login_ip,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "oauth_bindings": [
            {"id": o.id, "provider": o.provider, "open_id": o.open_id, "union_id": o.union_id}
            for o in oauths
        ],
    }


@router.post("/users", status_code=201)
async def create_portal_user(
    body: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("portal:users:write")),
):
    """管理员创建前台用户"""
    username = (body.get("username") or "").strip()
    email = body.get("email")
    password = body.get("password") or ""
    if not username or not password or len(password) < 8:
        raise HTTPException(400, "username / password 必填且密码 ≥ 8 字符")

    existing = (await db.execute(
        select(models.PortalUser).where(
            models.PortalUser.username == username,
            models.PortalUser.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "用户名已存在")

    ip = request.client.host if request.client else None
    user = models.PortalUser(
        username=username,
        email=email,
        phone=body.get("phone"),
        nickname=body.get("nickname") or username,
        password_hash=hash_password(password),
        status=body.get("status", "active"),
        register_ip=ip,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"id": user.id, "username": user.username}


@router.patch("/users/{user_id}", response_model=dict[str, Any])
async def update_portal_user(
    user_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("portal:users:write")),
):
    """更新前台用户资料/状态"""
    user = await db.get(models.PortalUser, user_id)
    if not user or user.deleted_at:
        raise HTTPException(404, "Portal user not found")

    for k in ("nickname", "email", "phone", "avatar", "status"):
        if k in body:
            setattr(user, k, body[k])
    await db.commit()
    await db.refresh(user)
    return {"id": user.id}


@router.post("/users/{user_id}/reset-password", status_code=200)
async def admin_reset_portal_password(
    user_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("portal:users:write")),
):
    """管理员重置前台用户密码"""
    new_pwd = body.get("new_password") or ""
    if len(new_pwd) < 8:
        raise HTTPException(400, "新密码至少 8 字符")
    user = await db.get(models.PortalUser, user_id)
    if not user or user.deleted_at:
        raise HTTPException(404, "Portal user not found")
    user.password_hash = hash_password(new_pwd)
    user.token_version = (user.token_version or 0) + 1  # 强制旧 token 失效
    await db.commit()
    return {"ok": True}


@router.delete("/users/{user_id}", status_code=204)
async def delete_portal_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("portal:users:write")),
):
    """软删前台用户"""
    user = await db.get(models.PortalUser, user_id)
    if not user or user.deleted_at:
        raise HTTPException(404, "Portal user not found")
    user.deleted_at = datetime.now(timezone.utc)
    user.token_version = (user.token_version or 0) + 1
    await db.commit()


@router.post("/users/{user_id}/restore", status_code=200)
async def restore_portal_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("portal:users:write")),
):
    """恢复软删的前台用户"""
    await db.execute(
        update(models.PortalUser)
        .where(models.PortalUser.id == user_id)
        .values(deleted_at=None)
    )
    await db.commit()
    return {"id": user_id, "restored": True}


# ============================================================
# OAuth 绑定管理
# ============================================================

@router.delete("/users/{user_id}/oauth/{oauth_id}", status_code=204)
async def admin_unbind_oauth(
    user_id: int,
    oauth_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("portal:users:write")),
):
    """管理员解绑 OAuth（强制）"""
    oauth = await db.get(models.PortalUserOAuth, oauth_id)
    if not oauth or oauth.user_id != user_id:
        raise HTTPException(404, "OAuth binding not found")
    await db.delete(oauth)
    await db.commit()


@router.get("/users/{user_id}/login-history", response_model=dict[str, Any])
async def get_portal_user_login_history(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("portal:users:read")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """前台用户登录历史"""
    from datetime import timedelta
    since = datetime.now(timezone.utc) - timedelta(days=90)
    stmt = (
        select(models.PortalLoginLog)
        .where(
            models.PortalLoginLog.user_id == user_id,
            models.PortalLoginLog.created_at >= since,
        )
        .order_by(models.PortalLoginLog.created_at.desc(), models.PortalLoginLog.id.desc())
    )
    data = await paginate(db, stmt, page=page, page_size=page_size)
    return {
        "items": [
            {
                "id": l.id, "ip": l.ip, "user_agent": l.user_agent,
                "success": l.success, "reason": l.reason, "provider": l.provider,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in data["items"]
        ],
        "total": data["total"],
        "page": data["page"],
        "page_size": data["page_size"],
    }


@router.get("/stats", response_model=dict[str, Any])
async def portal_user_stats(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("portal:users:read")),
):
    """前台用户统计"""
    from sqlalchemy import func as sqlfunc

    total = (await db.execute(
        select(sqlfunc.count()).select_from(models.PortalUser).where(
            models.PortalUser.deleted_at.is_(None)
        )
    )).scalar() or 0

    active = (await db.execute(
        select(sqlfunc.count()).select_from(models.PortalUser).where(
            models.PortalUser.status == "active", models.PortalUser.deleted_at.is_(None)
        )
    )).scalar() or 0

    disabled = (await db.execute(
        select(sqlfunc.count()).select_from(models.PortalUser).where(
            models.PortalUser.status != "active", models.PortalUser.deleted_at.is_(None)
        )
    )).scalar() or 0

    # OAuth 绑定数
    oauth_count = (await db.execute(
        select(sqlfunc.count()).select_from(models.PortalUserOAuth)
    )).scalar() or 0

    # 最近 7 天新增
    seven_days_ago = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    from datetime import timedelta
    seven_days_ago -= timedelta(days=7)
    new_last_7d = (await db.execute(
        select(sqlfunc.count()).select_from(models.PortalUser).where(
            models.PortalUser.created_at >= seven_days_ago,
            models.PortalUser.deleted_at.is_(None),
        )
    )).scalar() or 0

    return {
        "total": total,
        "active": active,
        "disabled": disabled,
        "oauth_bindings": oauth_count,
        "new_last_7d": new_last_7d,
    }