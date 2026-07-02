"""审计日志查询 API"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.api.deps import get_current_user, require_permission
from cenkor_admin.apps.system.app_registry import (
    install_app,
    list_apps_with_status,
    uninstall_app,
    update_permissions_grants,
)
from cenkor_admin.apps.system.models import InstalledApp
from cenkor_admin.apps.system.settings_router import router as settings_router
from cenkor_admin.apps.system.tasks_router import router as tasks_router

from cenkor_admin.core.audit import AuditLog
from cenkor_admin.core.db import get_db

AuthUser = auth_models.User

router = APIRouter()

# 子路由：定时任务
router.include_router(tasks_router, prefix="/tasks", tags=["tasks"])
router.include_router(settings_router, prefix="/settings", tags=["settings"])


# 公开路由（无需鉴权）— 供前端插件加载器使用
public_router = APIRouter()


@public_router.get("/apps/plugins", response_model=dict[str, Any])
async def list_app_plugins(
    db: AsyncSession = Depends(get_db),
):
    """获取有前端资源的已安装 App 列表（供前端插件加载器使用，无需鉴权）。"""
    result = await db.execute(
        select(InstalledApp).where(
            InstalledApp.status == "installed",
            InstalledApp.has_frontend == True,  # noqa: E712
        )
    )
    items = result.scalars().all()
    return {
        "items": [
            {
                "key": a.key,
                "name": a.name,
                "version": a.version,
                "script_url": f"/.app-assets/{a.key}/plugin.js",
            }
            for a in items
        ]
    }


@router.get("/apps", response_model=dict[str, Any])
async def list_apps(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:read")),
):
    """应用中心：已扫描 App 及安装状态"""
    items = await list_apps_with_status(db)
    return {"items": items}


@router.post("/apps/{app_key}/install")
async def install_app_endpoint(
    app_key: str,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    try:
        row = await install_app(db, app_key)
        return {"ok": True, "key": row.key, "version": row.version, "status": row.status}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/apps/{app_key}/uninstall")
async def uninstall_app_endpoint(
    app_key: str,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    try:
        await uninstall_app(db, app_key)
        return {"ok": True, "key": app_key, "status": "uninstalled"}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.put("/apps/{app_key}/permissions-grants")
async def update_app_permissions_grants(
    app_key: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """更新 App 的权限委派配置

    Body: { "role_code": ["permission_code", ...], ... }
    """
    try:
        row = await update_permissions_grants(db, app_key, body)
        return {"ok": True, "key": row.key, "permissions_grants": row.permissions_grants or {}}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/apps/{app_key}/registered-data")
async def get_app_registered_data(
    app_key: str,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:read")),
):
    """查看 App 已注册到 DB 的内容/字段/分类数据"""
    from cenkor_admin.apps.cms import models as cms_models
    from cenkor_admin.apps.system.app_registry import scan_app_manifests
    from sqlalchemy import func as sqlfunc

    manifests = scan_app_manifests()
    manifest = manifests.get(app_key)
    if not manifest:
        raise HTTPException(404, f"App '{app_key}' 未找到")

    ct_keys = [ct["key"] for ct in manifest.content_types]
    if not ct_keys:
        return {"content_types": [], "field_definitions": [], "categories": [], "tags": []}

    cts = (await db.execute(
        select(cms_models.ContentType).where(cms_models.ContentType.key.in_(ct_keys))
    )).scalars().all()
    ct_ids = [ct.id for ct in cts]

    fds = (await db.execute(
        select(cms_models.FieldDefinition)
        .where(cms_models.FieldDefinition.content_type_id.in_(ct_ids))
        .options(selectinload(cms_models.FieldDefinition.field_options))
        .order_by(cms_models.FieldDefinition.sort)
    )).scalars().all() if ct_ids else []

    cats = (await db.execute(
        select(cms_models.Category).where(cms_models.Category.content_type_id.in_(ct_ids))
    )).scalars().all() if ct_ids else []

    tags = (await db.execute(
        select(cms_models.Tag).where(cms_models.Tag.content_type_id.in_(ct_ids))
    )).scalars().all() if ct_ids else []

    return {
        "content_types": [
            {"id": ct.id, "key": ct.key, "name": ct.name, "icon": ct.icon}
            for ct in cts
        ],
        "field_definitions": [
            {
                "id": fd.id, "field_key": fd.field_key, "label": fd.label,
                "field_type": fd.field_type, "required": fd.required,
                "options": [{"value": o.value, "label": o.label, "color": o.color} for o in fd.field_options],
            }
            for fd in fds
        ],
        "categories": [
            {"id": c.id, "slug": c.slug, "name": c.name, "parent_id": c.parent_id}
            for c in cats
        ],
        "tags": [
            {"id": t.id, "slug": t.slug, "name": t.name, "color": t.color}
            for t in tags
        ],
    }


@router.get("/audit/stats", response_model=dict[str, Any])
async def audit_stats(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("system:audit:read")),
):
    """审计统计（最近 7 天）"""
    from datetime import datetime, timedelta, timezone
    since = datetime.now(timezone.utc) - timedelta(days=7)

    # 总数
    total = (await db.execute(
        select(func.count()).select_from(AuditLog).where(AuditLog.created_at >= since)
    )).scalar() or 0

    # 按方法
    method_rows = (await db.execute(
        select(AuditLog.method, func.count())
        .where(AuditLog.created_at >= since)
        .group_by(AuditLog.method)
    )).all()
    by_method = {m: c for m, c in method_rows}

    # 按状态码
    status_rows = (await db.execute(
        select(AuditLog.status_code, func.count())
        .where(AuditLog.created_at >= since)
        .group_by(AuditLog.status_code)
    )).all()
    by_status = {s: c for s, c in status_rows}

    # 错误数
    errors = (await db.execute(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.created_at >= since, AuditLog.status_code >= 400)
    )).scalar() or 0

    return {
        "total": total,
        "errors": errors,
        "by_method": by_method,
        "by_status": by_status,
    }


@router.get("/audit", response_model=dict[str, Any])
async def list_audit_logs(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("system:audit:read")),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user_id: int | None = None,
    method: str | None = None,
    status_code: int | None = None,
    path_contains: str | None = None,
):
    """审计日志列表（筛选 + 分页）"""
    stmt = select(AuditLog)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if method:
        stmt = stmt.where(AuditLog.method == method.upper())
    if status_code is not None:
        stmt = stmt.where(AuditLog.status_code == status_code)
    if path_contains:
        stmt = stmt.where(AuditLog.path.contains(path_contains))

    count = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    stmt = stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()

    return {
        "items": [
            {
                "id": x.id,
                "request_id": x.request_id,
                "user_id": x.user_id,
                "method": x.method,
                "path": x.path,
                "status_code": x.status_code,
                "duration_ms": x.duration_ms,
                "ip": x.ip,
                "error": x.error,
                "created_at": x.created_at.isoformat() if x.created_at else None,
            }
            for x in items
        ],
        "total": count,
        "page": page,
        "page_size": page_size,
    }


@router.get("/audit/{audit_id}", response_model=dict[str, Any])
async def get_audit_log(
    audit_id: int,
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(get_current_user),
):
    """单条审计详情（用于 diff 查看）。"""
    obj = await db.get(AuditLog, audit_id)
    if not obj:
        raise HTTPException(404, "审计记录不存在")
    return {
        "id": obj.id,
        "request_id": obj.request_id,
        "user_id": obj.user_id,
        "method": obj.method,
        "path": obj.path,
        "status_code": obj.status_code,
        "duration_ms": obj.duration_ms,
        "ip": obj.ip,
        "user_agent": obj.user_agent,
        "diff": obj.diff,
        "error": obj.error,
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
    }
