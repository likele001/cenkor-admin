"""定时任务管理 API（管理后台）"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.api.deps import require_permission
from cenkor_admin.core.db import get_db

router = APIRouter()


# 简单的内存调度存储（重启失效；生产应换成 DB / Redis）
_SCHEDULE: dict[str, dict] = {}


class TaskSchedule(BaseModel):
    enabled: bool
    cron: str | None = None  # 形如 "0 3 * * *"，None=on_demand


@router.get("", response_model=dict[str, Any])
async def list_tasks(
    _: auth_models.User = Depends(require_permission("task:read")),
):
    """所有已注册的任务（含当前调度）"""
    from cenkor_admin.tasks import TASK_REGISTRY
    items = []
    for t in TASK_REGISTRY:
        sched = _SCHEDULE.get(t["name"], {"enabled": True, "cron": t["default_schedule"]})
        items.append({**t, "schedule": sched})
    return {"items": items, "total": len(items)}


@router.put("/{task_name}/schedule", response_model=dict[str, Any])
async def update_task_schedule(
    task_name: str,
    body: TaskSchedule,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("task:write")),
):
    """更新任务调度（启用/禁用/修改 cron）"""
    from cenkor_admin.tasks import TASK_REGISTRY
    if not any(t["name"] == task_name for t in TASK_REGISTRY):
        raise HTTPException(404, f"任务不存在: {task_name}")
    if body.cron and len(body.cron.split()) not in (5, 6):
        raise HTTPException(400, "cron 表达式必须为 5 或 6 段")
    _SCHEDULE[task_name] = {
        "enabled": body.enabled,
        "cron": body.cron,
        "updated_at": datetime.utcnow().isoformat(),
    }
    return _SCHEDULE[task_name]


@router.post("/{task_name}/run", response_model=dict[str, Any])
async def run_task_now(
    task_name: str,
    _: auth_models.User = Depends(require_permission("task:write")),
):
    """立即触发一次任务（生产走 Celery）"""
    from cenkor_admin.tasks import TASK_REGISTRY
    if not any(t["name"] == task_name for t in TASK_REGISTRY):
        raise HTTPException(404, f"任务不存在: {task_name}")
    try:
        from cenkor_admin.core.celery_app import celery_app
        result = celery_app.send_task(task_name)
        return {"ok": True, "task_id": result.id, "transport": "celery"}
    except Exception as e:
        return {"ok": False, "transport": "noop", "reason": str(e)}
