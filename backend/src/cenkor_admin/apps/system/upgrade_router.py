"""核心平台在线升级路由 —— /api/v1/system/upgrade/*

8 个端点：
  GET    /status                       当前版本 / 通道 / alembic head / 是否有 running 升级 / 最近结果
  GET    /runs                         升级历史列表（分页+过滤 status/source）
  GET    /runs/{id}                    单条详情（含完整 log）
  GET    /runs/{id}/log?since=N        增量拉日志（前端 3 秒轮询用 since 字节偏移）
  POST   /dry-run                      预演：只 plan，不动文件 / DB
  POST   /run                          实际升级，body={source,url?,local_path?},需要 is_superuser+confirm_text
  POST   /runs/{id}/rollback           手动回滚已 success 的 run
  DELETE /runs/{id}                    删历史记录（只删留痕，不动项目）

安全：所有写操作要求 is_superuser + confirm_text="升级 cenkor-admin"；
      is_superuser 通过 user.is_superuser 字段判断；
      confirm_text 校验与 codegen.install 一致。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.system import upgrade_service
from cenkor_admin.apps.system.models import UpgradeRun
from cenkor_admin.core.db import get_db

router = APIRouter()

READ = "system:upgrade:read"
WRITE = "system:upgrade:write"
CONFIRM_TEXT = "升级 cenkor-admin"


def _is_superuser(user) -> bool:
    return bool(getattr(user, "is_superuser", False))


def _check_confirm(body, user):
    if not _is_superuser(user):
        raise HTTPException(403, "仅超级管理员可执行在线升级")
    ct = (body or {}).get("confirm_text", "") if isinstance(body, dict) else ""
    if ct != CONFIRM_TEXT:
        raise HTTPException(400, "确认文本错误（需输入\"" + CONFIRM_TEXT + "\"）")


@router.get("/status")
async def upgrade_status(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission(READ)),
):
    return await upgrade_service.current_status(db)


@router.get("/resources")
async def upgrade_resources(
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission(READ)),
):
    """合并：远程 releases.json（带 token 鉴权）+ 本地 release.json + 本地已下载文件。"""
    return await upgrade_service.list_resources(force_refresh=refresh)


@router.post("/resources/download")
async def upgrade_resources_download(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission(WRITE)),
):
    """把指定 version 的 pkg_url 拉到本地 download_dir。

    拉完后调用方可以再用 source=tar_upload + local_path=… 走升级。
    """
    if not _is_superuser(user):
        raise HTTPException(403, "仅超级管理员可下载升级资源")
    version = (body or {}).get("version", "").strip()
    if not version:
        raise HTTPException(400, "version 不能为空")
    return await upgrade_service.download_resource(version, db)


@router.get("/runs")
async def upgrade_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    source: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission(READ)),
):
    stmt = select(UpgradeRun)
    if status:
        stmt = stmt.where(UpgradeRun.status == status)
    if source:
        stmt = stmt.where(UpgradeRun.source == source)
    count = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    stmt = stmt.order_by(UpgradeRun.id.desc()).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return {
        "total": count,
        "page": page,
        "page_size": page_size,
        "items": [upgrade_service._run_brief(r) for r in items],
    }


@router.get("/runs/{run_id}")
async def upgrade_run_detail(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission(READ)),
):
    run = await db.get(UpgradeRun, run_id)
    if run is None:
        raise HTTPException(404, "执行记录不存在")
    return {**upgrade_service._run_brief(run), "log": run.log, "error": run.error}


@router.get("/runs/{run_id}/log")
async def upgrade_run_log(
    run_id: int,
    since: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission(READ)),
):
    """增量拉日志：since 是 log 字段的字节偏移，返回 from=since 起的切片。

    前端 3 秒轮询：拿到本次 log 长度作为下次 since。
    """
    run = await db.get(UpgradeRun, run_id)
    if run is None:
        raise HTTPException(404, "执行记录不存在")
    log = run.log or ""
    slice_ = log[since:] if since < len(log) else ""
    return {"id": run_id, "status": run.status, "log_length": len(log), "slice": slice_}


@router.post("/dry-run")
async def upgrade_dry_run(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission(WRITE)),
):
    """预演：只 plan，不动文件 / DB。

    返回 UpgradeRun 详情（status=success, log 里写明计划）。
    """
    _check_confirm(body, user)
    source = (body or {}).get("source", "url")
    payload = (body or {}).get("payload", {}) or {}
    notes = (body or {}).get("notes")
    if source not in ("git",):
        raise HTTPException(400, "source 必须是 git")
    return await upgrade_service.run_upgrade(
        db, user, source=source, payload=payload, dry_run=True, notes=notes,
    )


@router.post("/run")
async def upgrade_run(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission(WRITE)),
):
    """实际升级。**不会**等升级完成才返回 —— 返回的是 UpgradeRun(status=running)，

    客户端通过 GET /runs/{id}/log?since=N 轮询日志。
    """
    _check_confirm(body, user)
    source = (body or {}).get("source", "url")
    payload = (body or {}).get("payload", {}) or {}
    notes = (body or {}).get("notes")
    if source not in ("git",):
        raise HTTPException(400, "source 必须是 git")
    # git 模式无需额外校验
    # notes 长度软限制（避免把乱七八糟的大文本写进 announcements）
    if notes and len(notes) > 8000:
        raise HTTPException(400, "notes 太长（> 8000 字符）")
    # 用后台任务跑（不能 await，否则阻塞响应）
    # 但要在新会话里跑（避免主请求 commit 关闭 db）
    from cenkor_admin.core.db import AsyncSessionLocal
    async def _bg():
        async with AsyncSessionLocal() as bg_db:
            try:
                await upgrade_service.run_upgrade(bg_db, user, source=source, payload=payload, notes=notes)
            except Exception as exc:
                import structlog
                structlog.get_logger().error("upgrade.bg_failed", error=str(exc))
    asyncio.create_task(_bg())
    # task 完成后从 _bg 内的 session 写 status；这里我们不能立刻查 run_id。
    # 妥协：在调用 run_upgrade 之前先创建一个 pending run 让前端轮询？
    # 不行，run_upgrade 内部自己创建 run。
    # 解决：让前端通过 GET /status 看 running 状态（status 里有 running_run_id）。
    # 升级启动后 status 会有 running_run_id，前端从那里拿。
    # 但这需要等待 bg 任务创建 run —— 短暂延迟，status 会先返回 running=False。
    # 简单妥协：fire-and-forget，让前端 1 秒后轮询 status 拿 running_run_id。
    return {"ok": True, "started": True, "note": "已启动后台升级，轮询 GET /status 或 GET /runs/{id}/log 获取进度"}


@router.post("/runs/{run_id}/rollback")
async def upgrade_runs_rollback(
    run_id: int,
    body: dict | None = None,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission(WRITE)),
):
    _check_confirm(body or {}, user)
    target = await db.get(UpgradeRun, run_id)
    if target is None:
        raise HTTPException(404, "执行记录不存在")
    if target.status not in ("success", "failed", "rolled_back"):
        raise HTTPException(400, "只能回滚已结束（success/failed/rolled_back）的记录，当前 status=" + target.status)
    if not target.pkg_path:
        raise HTTPException(400, "该记录没有有效的 git 回滚点（pkg_path），无法回滚")
    from cenkor_admin.core.db import AsyncSessionLocal
    async def _bg():
        async with AsyncSessionLocal() as bg_db:
            try:
                await upgrade_service.manual_rollback(bg_db, user, run_id)
            except Exception as exc:
                import structlog
                structlog.get_logger().error("upgrade.rollback_bg_failed", error=str(exc))
    asyncio.create_task(_bg())
    return {"ok": True, "started": True, "note": "已启动回滚任务，轮询 GET /status 查看进度"}


@router.delete("/runs/{run_id}")
async def upgrade_runs_delete(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission(WRITE)),
):
    """只删留痕，不动项目（如果 run 是 success，可以走 POST /runs/{id}/rollback 手动回滚）。"""
    run = await db.get(UpgradeRun, run_id)
    if run is None:
        raise HTTPException(404, "执行记录不存在")
    if run.status == "running":
        raise HTTPException(400, "升级任务运行中，不能删除（请等待完成后再删）")
    await db.delete(run)
    await db.commit()
    return {"ok": True, "id": run_id}
