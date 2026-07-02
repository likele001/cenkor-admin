"""API 依赖：鉴权 / 权限校验"""
from __future__ import annotations

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.portal.auth import is_portal_token
from cenkor_admin.apps.rbac.models import Role, UserRole, RolePermission, Permission, RoleMenu, Menu
from cenkor_admin.core.db import get_db
from cenkor_admin.core.security import decode_token

log = structlog.get_logger()
security = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> auth_models.User:
    """从 Bearer token 解析当前后台用户（含完整角色/权限/菜单关联）。

    拒绝 portal token（前台用户无法访问后台路由）。
    """
    if not creds or not creds.credentials:
        raise HTTPException(status_code=401, detail="未提供认证信息")

    # 先尝试 admin SECRET 解码；失败则尝试 portal SECRET 并返回 403
    try:
        payload = decode_token(creds.credentials)
    except JWTError:
        try:
            from cenkor_admin.apps.portal.auth import decode_portal_token, PORTAL_JWT_ISSUER
            portal_payload = decode_portal_token(creds.credentials)
            if portal_payload.get("iss") == PORTAL_JWT_ISSUER:
                raise HTTPException(403, "前台用户无法访问后台管理接口")
        except HTTPException:
            raise
        except Exception:
            pass
        raise HTTPException(401, "Token 无效")

    if payload.get("type") != "access":
        raise HTTPException(401, "不是 access token")

    # 拒绝 portal token（如果 SECRET 相同也能区分）
    if is_portal_token(payload):
        raise HTTPException(403, "前台用户无法访问后台管理接口")

    user_id = int(payload["sub"])

    stmt = (
        select(auth_models.User)
        .options(
            joinedload(auth_models.User.roles)
            .joinedload(UserRole.role)
            .joinedload(Role.permissions)
            .joinedload(RolePermission.permission),
            joinedload(auth_models.User.roles)
            .joinedload(UserRole.role)
            .joinedload(Role.menus)
            .joinedload(RoleMenu.menu),
        )
        .where(auth_models.User.id == user_id, auth_models.User.deleted_at.is_(None))
    )
    user = (await db.execute(stmt)).unique().scalar_one_or_none()
    if not user:
        raise HTTPException(401, "用户不存在")
    if user.status != "active":
        raise HTTPException(403, f"账号已{user.status}")
    return user


def collect_user_permissions(user: auth_models.User) -> set[str]:
    """从已加载的用户角色关联中收集权限码。"""
    perms: set[str] = set()
    for user_role in user.roles:  # type: ignore[attr-defined]
        role = user_role.role
        for rp in role.permissions:  # type: ignore[attr-defined]
            perms.add(rp.permission.code)
    return perms


def permission_matches(have: str, need: str) -> bool:
    """精确匹配或通配符：cms:* 匹配 cms:product:read。"""
    if have == need:
        return True
    if have.endswith(":*") and need.startswith(have[:-1]):
        return True
    return False


def user_has_permission(user: auth_models.User, code: str) -> bool:
    if user.is_superuser:
        return True
    perms = collect_user_permissions(user)
    return any(permission_matches(p, code) for p in perms)


def require_permission(code: str):
    """权限装饰器工厂：检查用户是否拥有指定权限码

    支持通配符：cms:* 匹配 cms:product:read 等。superuser 始终通过。
    """
    async def checker(user: auth_models.User = Depends(get_current_user)) -> auth_models.User:
        if not user_has_permission(user, code):
            raise HTTPException(status_code=403, detail=f"无权限：{code}")
        return user
    return checker
