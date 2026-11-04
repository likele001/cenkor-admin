"""站内搜索词：记录与聚合。

## 这个模块为什么存在

选题缺口（``ai/topic_gap.py``）擅长回答「库里缺哪些主题」，但它只能看见
**已经写出来的东西**。它不知道读者真正在找什么。

搜索框是唯一能直接观察需求的地方，而且带一个特别有价值的信号：
**零结果的词**。搜了没搜到、然后走了 —— 这是最便宜的选题清单，
比任何关键词工具都准，因为它来自本站读者而不是全网热度。

## 记录的三个克制

1. **不阻塞搜索**：写日志失败只记 warn，绝不让一次统计打挂用户的搜索。
   这类旁路数据丢一条无所谓，搜索慢 200ms 才是真问题。
2. **不存可识别信息**：没有 IP、没有 UA，只留前台已有的匿名 visitor_id。
3. **归一化在写入时做**：``query_norm`` 落库时就算好，读的时候直接 group by。
   否则每次聚合都要在 SQL 里做 lower + 去空白，既没法走索引，
   也会因为大小写差异把同一个词拆成好几条。

## stat_date 用业务时区

与 ``cms_track_events`` 保持一致：按 Asia/Shanghai 切自然日。
用 UTC 切会在北京时间早上 8 点断一天，运营看「今天搜了什么」会以为数据丢了。
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms import analytics_models as am

log = structlog.get_logger(__name__)

BIZ_TZ = ZoneInfo("Asia/Shanghai")
MAX_QUERY_LEN = 200
_WS_RE = re.compile(r"\s+")


def normalize(query: str) -> str:
    """归一化：去首尾空白、压缩内部空白、转小写、截断。

    只做这三件事。不要去掉标点 —— 「Vue 3.4」「vue@3」对读者是不同的东西，
    过度归一化会把不同意图合并成一个，反而丢信息。
    """
    q = (query or "").strip()
    if not q:
        return ""
    q = _WS_RE.sub(" ", q).lower()
    return q[:MAX_QUERY_LEN]


def _today() -> date:
    return datetime.now(BIZ_TZ).date()


async def record(
    db: AsyncSession,
    *,
    query: str,
    result_count: int,
    site_id: int = 1,
    visitor_id: str = "",
    lang: str | None = None,
) -> None:
    """写一条搜索日志。

    旁路数据：任何异常都吞掉并记 warn。调用方不需要 try/except。
    """
    norm = normalize(query)
    if not norm:
        return
    try:
        db.add(
            am.CmsSearchLog(
                site_id=site_id or 1,
                query=(query or "").strip()[:MAX_QUERY_LEN],
                query_norm=norm,
                result_count=max(0, int(result_count or 0)),
                visitor_id=(visitor_id or "")[:64],
                lang=(lang or None) and str(lang)[:10],
                stat_date=_today(),
            )
        )
        await db.commit()
    except Exception as exc:
        log.warning("cms.search_log.write_failed", error=str(exc))
        with_log = getattr(db, "rollback", None)
        if callable(with_log):
            try:
                await db.rollback()
            except Exception:
                pass


async def top_terms(
    db: AsyncSession,
    *,
    days: int = 30,
    site_id: int = 1,
    limit: int = 30,
    only_zero: bool = False,
    order: str = "hits",
) -> list[dict[str, Any]]:
    """按词聚合。

    ``order``：
      - ``hits``  —— 搜索次数（谁问得最多）
      - ``zero``  —— 零结果次数（最该补的内容）
      - ``gap``   —— 零结果占比（搜索量够但完全没覆盖的那几个）
    """
    since = _today() - timedelta(days=max(1, days) - 1)
    hits = func.count().label("hits")
    zero_hits = func.sum(
        case((am.CmsSearchLog.result_count == 0, 1), else_=0)
    ).label("zero_hits")
    # 空 visitor_id 不算一个访客：公开搜索可能不带匿名标识，
    # 直接 count(distinct) 会把「全都没有」算成 1 个人。
    visitors = func.count(
        func.distinct(
            case((am.CmsSearchLog.visitor_id != "", am.CmsSearchLog.visitor_id))
        )
    ).label("visitors")
    sample = func.min(am.CmsSearchLog.query).label("sample")
    last_seen = func.max(am.CmsSearchLog.stat_date).label("last_seen")

    conds = [
        am.CmsSearchLog.stat_date >= since,
        am.CmsSearchLog.site_id == (site_id or 1),
    ]
    if only_zero:
        conds.append(am.CmsSearchLog.result_count == 0)

    stmt = (
        select(am.CmsSearchLog.query_norm, sample, hits, zero_hits, visitors, last_seen)
        .where(*conds)
        .group_by(am.CmsSearchLog.query_norm)
    )
    if order == "zero":
        stmt = stmt.order_by(zero_hits.desc(), hits.desc())
    elif order == "gap":
        # 零结果占比高的优先，但要求至少被搜过 2 次，避免个例上榜
        stmt = stmt.having(hits >= 2).order_by((zero_hits * 1.0 / hits).desc(), hits.desc())
    else:
        stmt = stmt.order_by(hits.desc())
    stmt = stmt.limit(max(1, min(limit, 200)))

    rows = (await db.execute(stmt)).all()
    out: list[dict[str, Any]] = []
    for norm, sample_q, h, z, v, seen in rows:
        h = int(h or 0)
        z = int(z or 0)
        out.append(
            {
                "query": sample_q or norm,
                "query_norm": norm,
                "hits": h,
                "zero_hits": z,
                "visitors": int(v or 0),
                "gap_rate": round(z / h, 3) if h else 0.0,
                "last_seen": seen.isoformat() if seen else None,
            }
        )
    return out


async def summary(db: AsyncSession, *, days: int = 30, site_id: int = 1) -> dict[str, Any]:
    """概览：总量、零结果量、独立词数、独立访客数。"""
    since = _today() - timedelta(days=max(1, days) - 1)
    conds = [
        am.CmsSearchLog.stat_date >= since,
        am.CmsSearchLog.site_id == (site_id or 1),
    ]
    row = (
        await db.execute(
            select(
                func.count().label("total"),
                func.sum(
                    case((am.CmsSearchLog.result_count == 0, 1), else_=0)
                ).label("zero"),
                func.count(func.distinct(am.CmsSearchLog.query_norm)).label("terms"),
                func.count(
                    func.distinct(
                        case(
                            (
                                am.CmsSearchLog.visitor_id != "",
                                am.CmsSearchLog.visitor_id,
                            )
                        )
                    )
                ).label("visitors"),
            ).where(*conds)
        )
    ).one()
    total = int(row[0] or 0)
    zero = int(row[1] or 0)
    return {
        "days": days,
        "total": total,
        "zero_result": zero,
        "zero_rate": round(zero / total, 3) if total else 0.0,
        "distinct_terms": int(row[2] or 0),
        "visitors": int(row[3] or 0),
    }


async def purge_old(db: AsyncSession, keep_days: int = 180) -> int:
    """清掉过期日志。挂在 scheduler.tick 上跑，与埋点同一套路子。"""
    cutoff = _today() - timedelta(days=max(30, keep_days))
    res = await db.execute(
        delete(am.CmsSearchLog).where(am.CmsSearchLog.stat_date < cutoff)
    )
    await db.commit()
    return int(res.rowcount or 0)
