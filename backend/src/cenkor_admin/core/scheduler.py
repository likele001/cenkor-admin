"""定时发布调度器（M2·P1 2.5）。

- ``scheduler_tick()``：扫描 cms_entries，把到达 scheduled_at 的条目发布（published_at=now），
  把到达 expire_at 的已发布条目下线（archived）。
- ``scheduler_loop()``：后台循环，每 30s tick 一次；由 main.py lifespan 启动/取消。
- 幂等：重复执行安全；单进程场景够用（uvicorn 单 worker）。
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog
from sqlalchemy import select, update

from cenkor_admin.apps.cms import models
from cenkor_admin.core.db import AsyncSessionLocal

log = structlog.get_logger()

DEFAULT_INTERVAL = 30  # 秒


async def _purge_static_pages(db, rows: list) -> None:
    """清掉这批条目的静态详情页。

    缓存失效属于旁路：失败只记日志，绝不能让一次写盘失败把整个调度循环打停。
    按 (site_id, slug) 去重 —— 同一批里可能有多条同站内容，也可能同 slug 跨类型。
    """
    targets = {(r.site_id, r.slug) for r in rows if r.site_id and r.slug}
    if not targets:
        return
    try:
        from cenkor_admin.apps.cms import static_cache

        if not static_cache.cache_enabled():
            return
        for site_id, slug in targets:
            await static_cache.purge_entry_by_site(db, site_id, slug)
    except Exception as exc:
        log.warning("scheduler.purge_failed", error=str(exc))


async def scheduler_tick() -> dict[str, int]:
    """执行一次调度扫描，返回本次发布/下线数量。"""
    now = datetime.now(UTC)
    published: int = 0
    expired: int = 0
    async with AsyncSessionLocal() as db:
        # 1) 到期发布：approved + scheduled_at <= now（待审内容不会自动发布）
        due_rows = (await db.execute(
            select(models.Entry.id, models.Entry.slug, models.Entry.site_id).where(
                models.Entry.deleted_at.is_(None),
                # 只有审核通过（approved）的才允许到点自动发布。
                # 原来写的是「status != published」，意味着 pending_review 的内容
                # 只要设了排期就会绕过审核直接上线 —— 那审核就等于不存在。
                models.Entry.status == "approved",
                models.Entry.scheduled_at.is_not(None),
                models.Entry.scheduled_at <= now,
            )
        )).all()
        due_ids = [r.id for r in due_rows]
        if due_ids:
            await db.execute(
                update(models.Entry)
                .where(models.Entry.id.in_(due_ids))
                .values(status="published", published_at=now)
            )
            published = len(due_ids)

        # 2) 到期下线：published + expire_at <= now
        exp_rows = (await db.execute(
            select(models.Entry.id, models.Entry.slug, models.Entry.site_id).where(
                models.Entry.deleted_at.is_(None),
                models.Entry.status == "published",
                models.Entry.expire_at.is_not(None),
                models.Entry.expire_at <= now,
            )
        )).all()
        exp_ids = [r.id for r in exp_rows]
        if exp_ids:
            await db.execute(
                update(models.Entry)
                .where(models.Entry.id.in_(exp_ids))
                .values(status="archived")
            )
            expired = len(exp_ids)

        if published or expired:
            await db.commit()

        # 定时发布/下线必须撤掉已落盘的静态详情页，和内容引擎的写入口同一口径。
        # 漏这一步的后果不对称：
        #   · 下线漏了：文件还在，nginx try_files 直接命中 → 数据库说 archived、
        #     线上照样 200 且返回全文，是最难发现的一类事故；
        #   · 发布漏了：之前下线过的条目会留着旧版文件，到点"发布"了但线上仍是旧内容。
        # 一定在 commit 之后清 —— 先删文件后提交，一旦回滚就留下「文件没了库没变」的空洞。
        if due_rows or exp_rows:
            await _purge_static_pages(db, [*due_rows, *exp_rows])

        # [P2C] 定时发布同样要发 entry.published：下游 Agent 不该区分「人点的」还是「到点发的」
        if published and due_ids:
            try:
                from cenkor_admin.core.hooks import dispatch as _dispatch

                for _eid in due_ids:
                    _e = await db.get(models.Entry, _eid)
                    if _e is not None:
                        await _dispatch("entry.published", entry=_e, db=db, user=None)
            except Exception as _de:
                log.warning("scheduler.publish_dispatch_failed", error=str(_de))

    # 通用扩展点：任何应用都可订阅 scheduler.tick 挂自己的周期任务
    # （结算解冻、超时关单等）。扩展点失败不能拖垮核心调度。
    try:
        from cenkor_admin.core.hooks import dispatch

        await dispatch("scheduler.tick")
    except Exception as e:
        log.warning("scheduler.hook_failed", error=str(e))

    if published or expired:
        log.info("scheduler.tick", published=published, expired=expired)
    return {"published": published, "expired": expired}


async def scheduler_loop(interval: int = DEFAULT_INTERVAL) -> None:
    """后台调度循环（永远运行，直到被取消）。"""
    while True:
        try:
            await scheduler_tick()
        except Exception as e:
            log.warning("scheduler.tick_failed", error=str(e))
        await asyncio.sleep(interval)
