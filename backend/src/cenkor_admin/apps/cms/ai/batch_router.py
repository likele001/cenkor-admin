"""AI 批量生产 · HTTP 接口

端点：
    POST   /ai/batch                    建批次（粘贴选题，一行一条）
    GET    /ai/batch                    批次列表
    GET    /ai/batch/{job_id}           详情 + 逐篇状态
    POST   /ai/batch/{job_id}/start     开始 / 继续
    POST   /ai/batch/{job_id}/pause     暂停
    POST   /ai/batch/{job_id}/cancel    取消
    POST   /ai/batch/{job_id}/retry-failed  只重试失败的
    DELETE /ai/batch/{job_id}           删除（连带条目，不删已生成的草稿）

权限：读 cms:ai:read，写 cms:ai:manage —— 批量生成会一次消耗大量 token，
和「改提示词」同档，只给能对成本负责的人。

站点：所有查询走会话级自动过滤（这两个表已纳入 scoped_models）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms.ai import batch_runner
from cenkor_admin.apps.cms.ai.models import CmsAiBatchItem, CmsAiBatchJob
from cenkor_admin.apps.cms.models import ContentType
from cenkor_admin.core.db import get_db
from cenkor_admin.core.site_scope import require_site_id

router = APIRouter(tags=["cms-ai-batch"])

# 一个批次最多多少篇。20 篇 × 20s ≈ 7 分钟，200 篇要一个多小时，
# 中间任何一次限流都会拖死整批 —— 上限放在这里挡，让用户拆批次。
MAX_TOPICS = 200
MAX_BRIEF_LEN = 6000


# ---------------------------------------------------------------------------
# 出入参
# ---------------------------------------------------------------------------
class CreateJobIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    content_type_id: int
    topics: list[str] = Field(min_length=1, description="选题/素材，一行一条")
    lang: str = Field(default="zh-CN", max_length=20)
    concurrency: int = Field(default=1, ge=1, le=4)


class JobOut(BaseModel):
    id: int
    site_id: int
    name: str
    content_type_id: int
    content_type_key: str
    status: str
    lang: str
    total: int
    succeeded: int
    failed: int
    skipped: int
    concurrency: int
    last_error: str | None = None
    created_by: int | None = None
    created_at: Any = None
    started_at: Any = None
    finished_at: Any = None


class ItemOut(BaseModel):
    id: int
    seq: int
    brief: str
    status: str
    entry_id: int | None = None
    title: str | None = None
    error: str | None = None
    attempts: int
    tokens_in: int
    tokens_out: int
    started_at: Any = None
    finished_at: Any = None


class JobDetailOut(JobOut):
    items: list[ItemOut]
    # 前端轮询用：还有没有在跑的（false 时可以停掉定时器）
    live: bool = False


def _job_out(j: CmsAiBatchJob) -> JobOut:
    return JobOut(
        id=j.id,
        site_id=j.site_id,
        name=j.name,
        content_type_id=j.content_type_id,
        content_type_key=j.content_type_key,
        status=j.status,
        lang=j.lang,
        total=j.total,
        succeeded=j.succeeded,
        failed=j.failed,
        skipped=j.skipped,
        concurrency=j.concurrency,
        last_error=j.last_error,
        created_by=j.created_by,
        created_at=j.created_at,
        started_at=j.started_at,
        finished_at=j.finished_at,
    )


def _item_out(i: CmsAiBatchItem) -> ItemOut:
    return ItemOut(
        id=i.id,
        seq=i.seq,
        brief=i.brief,
        status=i.status,
        entry_id=i.entry_id,
        title=i.title,
        error=i.error,
        attempts=i.attempts,
        tokens_in=i.tokens_in,
        tokens_out=i.tokens_out,
        started_at=i.started_at,
        finished_at=i.finished_at,
    )


async def _get_or_404(db: AsyncSession, job_id: int) -> CmsAiBatchJob:
    job = await db.get(CmsAiBatchJob, job_id)
    if job is None:
        raise HTTPException(404, "批次不存在")
    return job


async def _require_ai(db: AsyncSession) -> None:
    """复用 router 里的 AI 就绪判定。

    延迟 import：ai/router.py 会 include 本模块，模块级 import 会成环。
    """
    from cenkor_admin.apps.cms.ai.router import _require_ai as impl

    await impl(db)


# ---------------------------------------------------------------------------
# 建批次
# ---------------------------------------------------------------------------
@router.post("/batch", response_model=JobDetailOut, status_code=201)
async def create_job(
    body: CreateJobIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> JobDetailOut:
    await _require_ai(db)
    site_id = require_site_id()

    ct = await db.get(ContentType, body.content_type_id)
    if ct is None:
        raise HTTPException(404, "内容类型不存在（或不属于当前站点）")

    # 清洗选题：去空行、去重（保持原序）、逐条截断
    seen: set[str] = set()
    topics: list[str] = []
    for raw in body.topics:
        t = (raw or "").strip()
        if not t:
            continue
        key = t[:200]
        if key in seen:
            continue
        seen.add(key)
        topics.append(t[:MAX_BRIEF_LEN])
    if not topics:
        raise HTTPException(422, "选题列表为空")
    if len(topics) > MAX_TOPICS:
        raise HTTPException(422, f"一个批次最多 {MAX_TOPICS} 篇，请拆成多批")

    name = (body.name or "").strip() or f"{ct.name} · {datetime.now(UTC):%m-%d %H:%M}"
    job = CmsAiBatchJob(
        site_id=site_id,
        name=name[:120],
        content_type_id=ct.id,
        content_type_key=ct.key,
        status="pending",
        lang=body.lang,
        total=len(topics),
        concurrency=body.concurrency,
        created_by=getattr(user, "id", None),
    )
    db.add(job)
    await db.flush()

    db.add_all(
        [
            CmsAiBatchItem(job_id=job.id, site_id=site_id, seq=n, brief=t, status="pending")
            for n, t in enumerate(topics, start=1)
        ]
    )
    await db.commit()
    await db.refresh(job)

    items = (
        (
            await db.execute(
                select(CmsAiBatchItem)
                .where(CmsAiBatchItem.job_id == job.id)
                .order_by(CmsAiBatchItem.seq)
            )
        )
        .scalars()
        .all()
    )
    return JobDetailOut(**_job_out(job).model_dump(), items=[_item_out(i) for i in items])


# ---------------------------------------------------------------------------
# 列表 / 详情
# ---------------------------------------------------------------------------
@router.get("/batch", response_model=list[JobOut])
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    _user: auth_models.User = Depends(get_current_user),
) -> list[JobOut]:
    rows = (
        (
            await db.execute(
                select(CmsAiBatchJob)
                .order_by(CmsAiBatchJob.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [_job_out(j) for j in rows]


@router.get("/batch/{job_id}", response_model=JobDetailOut)
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> JobDetailOut:
    job = await _get_or_404(db, job_id)
    items = (
        (
            await db.execute(
                select(CmsAiBatchItem)
                .where(CmsAiBatchItem.job_id == job_id)
                .order_by(CmsAiBatchItem.seq)
            )
        )
        .scalars()
        .all()
    )
    return JobDetailOut(
        **_job_out(job).model_dump(),
        items=[_item_out(i) for i in items],
        live=batch_runner.is_active(job_id) or job.status == "running",
    )


# ---------------------------------------------------------------------------
# 状态流转
# ---------------------------------------------------------------------------
@router.post("/batch/{job_id}/start", response_model=JobOut)
async def start_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> JobOut:
    await _require_ai(db)
    job = await _get_or_404(db, job_id)
    if job.status == "running" and batch_runner.is_active(job_id):
        return _job_out(job)
    if job.status == "done":
        raise HTTPException(409, "批次已完成，如需再跑请新建批次")
    if job.status == "cancelled":
        raise HTTPException(409, "批次已取消，未跑的条目不会恢复；如需再跑请新建批次")

    # 先查有没有别的 running，给出可读提示。这一步和下面的唯一索引重复，
    # 但正常路径只有它能给出「是哪个批次在跑」；索引只是并发竞态的兜底。
    site_id = job.site_id
    clash = (
        await db.execute(
            select(CmsAiBatchJob.id, CmsAiBatchJob.name).where(
                CmsAiBatchJob.site_id == site_id,
                CmsAiBatchJob.status == "running",
                CmsAiBatchJob.id != job_id,
            )
        )
    ).first()
    if clash is not None:
        raise HTTPException(
            409, f"本站点已有正在跑的批次（#{clash[0]} {clash[1]}），请先等它结束或暂停"
        )

    now = datetime.now(UTC)
    job.status = "running"
    job.last_error = None
    job.started_at = job.started_at or now
    job.finished_at = None
    try:
        await db.commit()
    except IntegrityError:
        # uq_batch_jobs_one_running 兜住并发竞态（两个请求同时过了上面那道检查）。
        # 关键：rollback 之后**不能再在这个 session 上查库** —— 连接已被 invalidate，
        # asyncpg 重新 checkout 要 ping，会在同步上下文里 await 而抛 MissingGreenlet。
        await db.rollback()
        raise HTTPException(409, "本站点已有正在跑的批次，请稍后重试") from None

    await db.refresh(job)
    batch_runner.start(job_id)
    return _job_out(job)


@router.post("/batch/{job_id}/pause", response_model=JobOut)
async def pause_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> JobOut:
    job = await _get_or_404(db, job_id)
    if job.status != "running":
        raise HTTPException(409, f"只有进行中的批次能暂停（当前 {job.status}）")
    # 只改状态不 cancel task：正在跑的那篇让它把 LLM 调用走完，
    # 中途掐断等于白扔已经花掉的 token。循环会在下一个检查点自己退出。
    job.status = "paused"
    await db.commit()
    await db.refresh(job)
    return _job_out(job)


@router.post("/batch/{job_id}/cancel", response_model=JobOut)
async def cancel_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> JobOut:
    job = await _get_or_404(db, job_id)
    if job.status in ("done", "cancelled"):
        raise HTTPException(409, f"批次已结束（{job.status}）")
    job.status = "cancelled"
    job.finished_at = datetime.now(UTC)
    # 未开工的条目标成 skipped，否则会显示成「一直 pending」
    await db.execute(
        update(CmsAiBatchItem)
        .where(CmsAiBatchItem.job_id == job_id, CmsAiBatchItem.status == "pending")
        .values(status="skipped", finished_at=datetime.now(UTC))
    )
    await db.commit()
    await db.refresh(job)
    return _job_out(job)


@router.post("/batch/{job_id}/retry-failed", response_model=JobOut)
async def retry_failed(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> JobOut:
    await _require_ai(db)
    job = await _get_or_404(db, job_id)
    if job.status == "running":
        raise HTTPException(409, "批次正在跑，先暂停再重试失败项")

    # attempts 清零，否则重试一次就立刻又到上限
    res = await db.execute(
        update(CmsAiBatchItem)
        .where(CmsAiBatchItem.job_id == job_id, CmsAiBatchItem.status == "failed")
        .values(
            status="pending",
            attempts=0,
            error=None,
            started_at=None,
            finished_at=None,
        )
    )
    retried = res.rowcount or 0
    if retried == 0:
        raise HTTPException(409, "没有失败项可重试")

    job.failed = max(0, job.failed - retried)
    job.status = "pending"
    job.finished_at = None
    await db.commit()
    await db.refresh(job)
    return _job_out(job)


@router.delete("/batch/{job_id}")
async def delete_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    job = await _get_or_404(db, job_id)
    if job.status == "running":
        raise HTTPException(409, "批次正在跑，先暂停或取消再删除")
    # 条目随批次级联删除（ON DELETE CASCADE）；已生成的草稿条目保留 ——
    # 删批次不该顺手删掉用户的文章
    await db.delete(job)
    await db.commit()
    return {"ok": True, "deleted": job_id}


# ---------------------------------------------------------------------------
# 统计：给概览卡用
# ---------------------------------------------------------------------------
@router.get("/batch-stats")
async def batch_stats(
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    row = (
        await db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(CmsAiBatchJob.total), 0),
                func.coalesce(func.sum(CmsAiBatchJob.succeeded), 0),
                func.coalesce(func.sum(CmsAiBatchJob.failed), 0),
            )
        )
    ).first()
    running = (
        await db.execute(select(func.count()).where(CmsAiBatchJob.status == "running"))
    ).scalar() or 0
    return {
        "jobs": int(row[0] or 0),
        "topics": int(row[1] or 0),
        "succeeded": int(row[2] or 0),
        "failed": int(row[3] or 0),
        "running": int(running),
    }
