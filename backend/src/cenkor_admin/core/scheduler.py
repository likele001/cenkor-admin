"""定时发布调度器（M2·P1 2.5）。

- ``scheduler_tick()``：扫描 cms_entries，把到达 scheduled_at 的条目发布（published_at=now），
  把到达 expire_at 的已发布条目下线（archived）。
- ``scheduler_loop()``：后台循环，每 30s tick 一次；由 main.py lifespan 启动/取消。
- 幂等：重复执行安全；单进程场景够用（uvicorn 单 worker）。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, update

from cenkor_admin.apps.cms import models
from cenkor_admin.core.db import AsyncSessionLocal

log = structlog.get_logger()

DEFAULT_INTERVAL = 30  # 秒


async def scheduler_tick() -> dict[str, int]:
    """执行一次调度扫描，返回本次发布/下线数量。"""
    now = datetime.now(timezone.utc)
    published: int = 0
    expired: int = 0
    async with AsyncSessionLocal() as db:
        # 1) 到期发布：非 published + scheduled_at <= now
        due_ids = (await db.execute(
            select(models.Entry.id).where(
                models.Entry.deleted_at.is_(None),
                models.Entry.status != "published",
                models.Entry.scheduled_at.is_not(None),
                models.Entry.scheduled_at <= now,
            )
        )).scalars().all()
        if due_ids:
            await db.execute(
                update(models.Entry)
                .where(models.Entry.id.in_(due_ids))
                .values(status="published", published_at=now)
            )
            published = len(due_ids)

        # 2) 到期下线：published + expire_at <= now
        exp_ids = (await db.execute(
            select(models.Entry.id).where(
                models.Entry.deleted_at.is_(None),
                models.Entry.status == "published",
                models.Entry.expire_at.is_not(None),
                models.Entry.expire_at <= now,
            )
        )).scalars().all()
        if exp_ids:
            await db.execute(
                update(models.Entry)
                .where(models.Entry.id.in_(exp_ids))
                .values(status="archived")
            )
            expired = len(exp_ids)

        if published or expired:
            await db.commit()

    if published or expired:
        log.info("scheduler.tick", published=published, expired=expired)
    return {"published": published, "expired": expired}


async def scheduler_loop(interval: int = DEFAULT_INTERVAL) -> None:
    """后台调度循环（永远运行，直到被取消）。"""
    while True:
        try:
            await scheduler_tick()
        except Exception as e:  # noqa: BLE001 - 调度器必须自愈
            log.warning("scheduler.tick_failed", error=str(e))
        await asyncio.sleep(interval)
