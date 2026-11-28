"""收录推送：IndexNow（必应/Yandex）与百度普通收录。

配置从 cms_site_config 读（全站 KV）：
- `seo.indexnow_key`
- `seo.baidu_token`
取不到就标 failed 并写明原因 —— 静默失败比报错更难查。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms import models
from cenkor_admin.apps.cms.seo_push_models import SeoPushJob
from cenkor_admin.core.hooks import hook

MAX_ATTEMPTS = 3
INDEXNOW_URL = "https://api.indexnow.org/indexnow"
BAIDU_URL = "http://data.6.zz.baidu.com/urls"
_bg: set[asyncio.Task] = set()


async def _conf(db: AsyncSession, key: str) -> str:
    row = (
        await db.execute(select(models.SiteConfig).where(models.SiteConfig.key == key))
    ).scalars().first()
    if row is None or row.value is None:
        return ""
    val = row.value
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, dict):
        for k in ("value", "token", "key"):
            if isinstance(val.get(k), str):
                return val[k].strip()
        for v in val.values():
            if isinstance(v, str):
                return v.strip()
    return ""


async def _domain(db: AsyncSession, site_id: int) -> str:
    site = (await db.execute(select(models.Site).where(models.Site.id == site_id))).scalars().first()
    return (site.domain or "").strip() if site else ""


async def enqueue(db: AsyncSession, site_id: int, urls: list[str], engine: str = "indexnow") -> int:
    clean = [u.strip() for u in urls if u and u.strip().startswith("http")]
    if not clean:
        return 0
    # 同 URL 已有 pending 的不重复入队，避免一次改版把同一条推十遍
    exist = set(
        (
            await db.execute(
                select(SeoPushJob.url).where(
                    SeoPushJob.site_id == site_id,
                    SeoPushJob.status == "pending",
                    SeoPushJob.url.in_(clean),
                )
            )
        ).scalars().all()
    )
    added = 0
    for u in clean:
        if u in exist:
            continue
        db.add(SeoPushJob(site_id=site_id, url=u[:500], engine=engine))
        added += 1
    await db.commit()
    return added


async def _push_indexnow(urls: list[str], domain: str, key: str) -> tuple[bool, str]:
    if not key:
        return False, "未配置 seo.indexnow_key"
    if not domain:
        return False, "站点未绑定域名，IndexNow 需要 host"
    payload = {
        "host": domain,
        "key": key,
        "keyLocation": f"https://{domain}/{key}.txt",
        "urlList": urls,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(INDEXNOW_URL, json=payload)
    ok = resp.status_code < 400
    return ok, "" if ok else f"HTTP {resp.status_code}: {resp.text[:200]}"


async def _push_baidu(urls: list[str], domain: str, token: str) -> tuple[bool, str]:
    if not token:
        return False, "未配置 seo.baidu_token"
    if not domain:
        return False, "站点未绑定域名，百度推送需要 site"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            BAIDU_URL, params={"site": domain, "token": token}, content="\n".join(urls).encode()
        )
    if resp.status_code >= 400:
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    if data.get("error"):
        return False, str(data.get("message") or data["error"])[:200]
    return True, ""


async def process_pending(db: AsyncSession, limit: int = 20) -> dict[str, int]:
    rows = (
        await db.execute(
            select(SeoPushJob)
            .where(SeoPushJob.status == "pending", SeoPushJob.attempts < MAX_ATTEMPTS)
            .order_by(SeoPushJob.id)
            .limit(limit)
        )
    ).scalars().all()
    if not rows:
        return {"ran": 0, "success": 0, "failed": 0}

    # 按 (站点, 引擎) 归组，一个接口一次推多 URL，省配额
    groups: dict[tuple[int, str], list[SeoPushJob]] = {}
    for job in rows:
        groups.setdefault((job.site_id, job.engine), []).append(job)

    stats = {"ran": 0, "success": 0, "failed": 0}
    for (site_id, engine), jobs in groups.items():
        urls = [j.url for j in jobs]
        domain = await _domain(db, site_id)
        try:
            if engine == "baidu":
                ok, err = await _push_baidu(urls, domain, await _conf(db, "seo.baidu_token"))
            else:
                ok, err = await _push_indexnow(urls, domain, await _conf(db, "seo.indexnow_key"))
        except Exception as exc:
            ok, err = False, str(exc)[:200]

        now = datetime.now(UTC)
        for job in jobs:
            job.attempts += 1
            stats["ran"] += 1
            if ok:
                job.status = "success"
                job.sent_at = now
                job.last_error = None
                stats["success"] += 1
            else:
                job.last_error = err
                # 配置缺失不是瞬时故障，重试三次也不会自己好 —— 直接失败，让人去补配置
                non_retry = err.startswith("未配置") or err.startswith("站点未绑定域名")
                job.status = "failed" if (job.attempts >= MAX_ATTEMPTS or non_retry) else "pending"
                stats["failed"] += 1
    await db.commit()
    return stats


async def _drain() -> None:
    from cenkor_admin.core.db import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await process_pending(db, limit=20)


@hook("scheduler.tick")
async def _hook_seo_push() -> None:
    """后台跑，别让第三方接口拖住定时发布。"""
    try:
        task = asyncio.create_task(_drain())
        _bg.add(task)
        task.add_done_callback(_bg.discard)
    except Exception:
        pass


async def stats(db: AsyncSession, site_id: int) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(SeoPushJob.status, SeoPushJob.engine).where(SeoPushJob.site_id == site_id)
        )
    ).all()
    by_status: dict[str, int] = {}
    for st, _engine in rows:
        by_status[st] = by_status.get(st, 0) + 1
    recent_failed = (
        await db.execute(
            select(SeoPushJob)
            .where(SeoPushJob.site_id == site_id, SeoPushJob.status == "failed")
            .order_by(SeoPushJob.id.desc())
            .limit(10)
        )
    ).scalars().all()
    return {
        "by_status": by_status,
        "recent_failed": [
            {"id": r.id, "url": r.url, "engine": r.engine, "attempts": r.attempts, "error": r.last_error}
            for r in recent_failed
        ],
    }
