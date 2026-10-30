"""AI 批量生产执行器。

## 为什么不用 Celery

本机跑着的 Celery worker 属于其它项目（`main.py` 有注释说明），为本项目单开
一个 worker 要动 supervisord 和队列路由，配置错了会静默不执行。而批量任务的
形态特殊：**长但不密集** —— 每篇 10-30 秒几乎全在等 LLM 的 HTTP 响应，CPU 和
内存占用接近于零。这种负载用进程内 asyncio 完全够，还能少一个要监控的进程。

代价是进程重启会带走正在跑的任务。应对：状态全落 DB，启动时把僵死的
`running` 回退成 `pending`，用户点「继续」即可续跑，已完成的篇目不重复生成。

## 并发控制

三层：
1. 站点级 —— `uq_batch_jobs_one_running` 部分唯一索引，一个站点同时只能有一个
   running 批次（两批一起跑会抢 LLM 配额，进度条也互相干扰）
2. 批次级 —— `job.concurrency`（1-4），同一个批次内跑几篇
3. 全局级 —— `_GLOBAL_SEM`，所有批次合计的 LLM 并发上限

## 抢单

`UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED) RETURNING` 一条语句
完成「选中 + 占住」。单进程下其实不需要，但这样写将来加 worker 也不用改。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.ai import copilot
from cenkor_admin.apps.cms.ai.models import CmsAiBatchItem, CmsAiBatchJob
from cenkor_admin.core.db import AsyncSessionLocal
from cenkor_admin.core.site_scope import reset_current_site, set_current_site

# 全局 LLM 并发上限。设在 2：再多也只是排队等限流，反而让单篇延迟变得不可预测。
_GLOBAL_SEM = asyncio.Semaphore(2)

# job_id -> 正在跑的 task。只在本进程有效，进程重启即清空。
_tasks: dict[int, asyncio.Task[None]] = {}

# 单篇最大尝试次数：超过就判死，避免一次系统性故障把整批刷成无限重试
MAX_ATTEMPTS = 3


# ---------------------------------------------------------------------------
# 原子抢单
# ---------------------------------------------------------------------------
_CLAIM_SQL = text(
    """
    UPDATE cms_ai_batch_items
       SET status = 'running',
           started_at = now(),
           attempts = attempts + 1,
           error = NULL
     WHERE id = (
        SELECT id FROM cms_ai_batch_items
         WHERE job_id = :job_id
           AND status = 'pending'
         ORDER BY seq
         LIMIT 1
         FOR UPDATE SKIP LOCKED
     )
 RETURNING id, seq, brief, attempts
"""
)


async def _claim(db: AsyncSession, job_id: int) -> dict[str, Any] | None:
    """抢一条 pending。**不按 attempts 过滤** —— 次数控制在 _fail_item 里。

    若在这里过滤 `attempts < MAX`，一个 attempts 已达上限却仍是 pending 的行
    就永远抢不到，批次也永远结算不成 done（pending 永远 > 0），整批卡死。
    """
    row = (await db.execute(_CLAIM_SQL, {"job_id": job_id})).first()
    # 先把 Row 转成纯 dict 再 commit：commit 会让结果集与 session 解绑，
    # 之后再访问 row[0] 会触发 MissingGreenlet（async 下尤其难查）。
    data = (
        {"id": row[0], "seq": row[1], "brief": row[2], "attempts": row[3]}
        if row is not None
        else None
    )
    await db.commit()
    return data


# ---------------------------------------------------------------------------
# 单个 job 的主循环
# ---------------------------------------------------------------------------
async def _run_job(job_id: int) -> None:
    """跑完一个批次。中途可能因为暂停/取消提前退出。"""
    # 后台任务没有请求上下文，contextvar 是空的 —— 不显式设置的话
    # with_loader_criteria 不生效，写入也不会自动盖 site_id
    async with AsyncSessionLocal() as boot:
        job = await boot.get(CmsAiBatchJob, job_id)
        if job is None:
            logger.warning("cms.ai.batch.job_missing job={}", job_id)
            return
        site_id = job.site_id

    token = set_current_site(site_id)
    try:
        while True:
            # 暂停/取消的检查点放在每次取新条目之前：
            # 正在跑的那篇让它跑完，中断 LLM 调用等于白扔已花的 token
            async with AsyncSessionLocal() as db:
                job = await db.get(CmsAiBatchJob, job_id)
                if job is None or job.status != "running":
                    logger.info("cms.ai.batch.stopped job={} status={}", job_id, job.status if job else "-")
                    return
                concurrency = max(1, min(int(job.concurrency or 1), 4))

            claimed = await _claim_concurrent(job_id, concurrency)
            if claimed == 0:
                await _finalize(job_id)
                return

    except asyncio.CancelledError:
        # 进程退出或被显式取消：把手上 running 的条目回退，下次能接着跑
        await _release_running_items(job_id)
        raise
    except Exception as exc:
        logger.error("cms.ai.batch.crashed job={} err={}", job_id, exc)
        await _mark_job_failed(job_id, str(exc))
    finally:
        reset_current_site(token)
        _tasks.pop(job_id, None)


async def _claim_concurrent(job_id: int, concurrency: int) -> int:
    """并发跑一批 pending 条目，返回本轮实际处理的数量（0 表示没活了）。"""
    processed = 0

    async def one() -> bool:
        nonlocal processed
        async with AsyncSessionLocal() as db:
            item = await _claim(db, job_id)
        if item is None:
            return False
        # 开工前再确认一次批次还活着，避免暂停后还在继续消耗
        async with AsyncSessionLocal() as db:
            job = await db.get(CmsAiBatchJob, job_id)
            if job is None or job.status != "running":
                await _release_item(item["id"])
                return False
        await _process_item(job_id, item)
        processed += 1
        return True

    # 最多并发 concurrency 个，但受全局信号量约束
    async def guarded() -> bool:
        async with _GLOBAL_SEM:
            return await one()

    results = await asyncio.gather(*[guarded() for _ in range(concurrency)])
    return processed if any(results) else 0


async def _process_item(job_id: int, item: dict[str, Any]) -> None:
    """起草一篇并落库。任何异常都记在 item 上，不往外抛。"""
    item_id = item["id"]
    try:
        async with AsyncSessionLocal() as db:
            job = await db.get(CmsAiBatchJob, job_id)
            if job is None:
                raise RuntimeError("批次不存在")

            draft = await copilot.draft_entry(
                db,
                job.content_type_id,
                item["brief"],
                created_by=job.created_by,
                lang=job.lang,
            )

            # 起草后落库前查重：命中高相似直接跳过，避免重复产出线上内容
            try:
                dups = await copilot.detect_duplicates(
                    db,
                    draft["title"],
                    draft.get("content") or {},
                    content_type_id=job.content_type_id,
                    threshold=0.8,
                    limit=3,
                )
            except Exception as exc:
                logger.warning("cms.ai.batch.dedup_failed item={} err={}", item_id, str(exc))
                dups = []
            hit = next((d for d in dups if d.get("is_duplicate")), None)
            if hit is not None:
                await db.execute(
                    update(CmsAiBatchItem)
                    .where(CmsAiBatchItem.id == item_id)
                    .values(
                        status="skipped",
                        error=f"查重命中：与《{hit['title']}》高度相似（相似度 {hit['score']}）",
                        finished_at=datetime.now(UTC),
                    )
                )
                await db.commit()
                logger.info(
                    "cms.ai.batch.item_dedup_skip job={} item={} hit={}",
                    job_id, item_id, hit["entry_id"],
                )
                return

            entry = await copilot.create_entry_from_draft(db, draft, created_by=job.created_by)

            meta = draft.get("_meta") or {}
            await db.execute(
                update(CmsAiBatchItem)
                .where(CmsAiBatchItem.id == item_id)
                .values(
                    status="done",
                    entry_id=entry.id,
                    title=(entry.title or "")[:200],
                    tokens_in=int(meta.get("tokens_in") or 0),
                    tokens_out=int(meta.get("tokens_out") or 0),
                    error=None,
                    finished_at=datetime.now(UTC),
                )
            )
            await db.execute(
                update(CmsAiBatchJob)
                .where(CmsAiBatchJob.id == job_id)
                .values(succeeded=CmsAiBatchJob.succeeded + 1)
            )
            await db.commit()
        logger.info("cms.ai.batch.item_done job={} item={}", job_id, item_id)

    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"[:2000]
        logger.warning("cms.ai.batch.item_failed job={} item={} err={}", job_id, item_id, msg)
        await _fail_item(item_id, msg)


async def _fail_item(item_id: int, error: str) -> None:
    """标记单篇失败。attempts 未到上限就回退成 pending 让它再试一轮。

    次数判断放在这里而不是抢单 SQL 里，是为了保证 attempts 用尽的行一定能
    变成 failed —— 否则它会以 pending 状态赖着，批次永远结算不完。
    """
    async with AsyncSessionLocal() as db:
        row = await db.get(CmsAiBatchItem, item_id)
        if row is None:
            return
        will_retry = row.attempts < MAX_ATTEMPTS
        row.status = "pending" if will_retry else "failed"
        row.error = error
        row.finished_at = None if will_retry else datetime.now(UTC)
        if not will_retry:
            await db.execute(
                update(CmsAiBatchJob)
                .where(CmsAiBatchJob.id == row.job_id)
                .values(failed=CmsAiBatchJob.failed + 1)
            )
        await db.commit()


async def _release_item(item_id: int) -> None:
    """把一条已抢占但还没真正开工的条目放回 pending（不计失败）。"""
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(CmsAiBatchItem)
            .where(CmsAiBatchItem.id == item_id, CmsAiBatchItem.status == "running")
            .values(status="pending", started_at=None)
        )
        await db.commit()


async def _release_running_items(job_id: int) -> None:
    """把僵死的 running 条目回退成 pending（进程中断时用）。"""
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(CmsAiBatchItem)
            .where(CmsAiBatchItem.job_id == job_id, CmsAiBatchItem.status == "running")
            .values(status="pending", started_at=None)
        )
        await db.commit()


async def _finalize(job_id: int) -> None:
    """没有 pending 了，结算批次状态。"""
    async with AsyncSessionLocal() as db:
        job = await db.get(CmsAiBatchJob, job_id)
        if job is None:
            return
        counts = dict(
            (
                await db.execute(
                    select(CmsAiBatchItem.status, func.count())
                    .where(CmsAiBatchItem.job_id == job_id)
                    .group_by(CmsAiBatchItem.status)
                )
            ).all()
        )
        pending = int(counts.get("pending", 0))
        running = int(counts.get("running", 0))
        done = int(counts.get("done", 0))
        failed = int(counts.get("failed", 0))
        skipped = int(counts.get("skipped", 0))

        job.succeeded = done
        job.failed = failed
        job.skipped = skipped
        if pending == 0 and running == 0:
            job.status = "done"
            job.finished_at = datetime.now(UTC)
        await db.commit()
        logger.info(
            "cms.ai.batch.finalized job={} done={} failed={} pending={} status={}",
            job_id, done, failed, pending, job.status,
        )


async def _mark_job_failed(job_id: int, error: str) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(CmsAiBatchJob)
            .where(CmsAiBatchJob.id == job_id)
            .values(status="pending", last_error=error[:2000])
        )
        await db.commit()


# ---------------------------------------------------------------------------
# 公共 API（给 router 调）
# ---------------------------------------------------------------------------
def is_active(job_id: int) -> bool:
    task = _tasks.get(job_id)
    return task is not None and not task.done()


def start(job_id: int) -> None:
    """开跑（幂等：已在跑就直接返回）。"""
    if is_active(job_id):
        return
    task = asyncio.create_task(_run_job(job_id), name=f"cms-batch-{job_id}")
    _tasks[job_id] = task


def stop(job_id: int) -> None:
    """取消内存里的 task（DB 状态由调用方先改）。"""
    task = _tasks.pop(job_id, None)
    if task is not None and not task.done():
        task.cancel()


async def resume_on_boot() -> int:
    """进程启动时收拾残局。

    上一轮进程被杀时，可能有 job 停在 running、item 停在 running。
    这里统一回退成 pending 并返回需要续跑的 job_id 列表 —— 交给调用方决定
    要不要自动开跑（默认不自动，避免重启瞬间就冲 LLM 配额）。
    """
    async with AsyncSessionLocal() as db:
        stuck_items = await db.execute(
            update(CmsAiBatchItem)
            .where(CmsAiBatchItem.status == "running")
            .values(status="pending", started_at=None)
            .returning(CmsAiBatchItem.job_id)
        )
        job_ids = {r[0] for r in stuck_items.all()}
        await db.execute(
            update(CmsAiBatchJob)
            .where(CmsAiBatchJob.status == "running")
            .values(status="pending")
        )
        await db.commit()
    if job_ids:
        logger.warning("cms.ai.batch.recovered jobs={}", sorted(job_ids))
    return len(job_ids)
