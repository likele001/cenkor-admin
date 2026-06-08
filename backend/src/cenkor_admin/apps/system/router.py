"""审计日志查询 API"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.system.app_registry import install_app, list_apps_with_status, uninstall_app
from cenkor_admin.core.audit import AuditLog
from cenkor_admin.core.db import get_db

router = APIRouter()


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
