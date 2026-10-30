"""内容效果汇总与表现分析。

口径上最容易搞错的两处，这里固定下来：

1. **停留时长按「会话」取最大值，不对事件求平均**。心跳事件带的是累计时长
   （15s / 30s / 45s ...），直接对事件行求平均，一篇被看完的文章平均值反而
   比只看 10 秒的低 —— 因为看久了心跳事件多，把均值拉下来了。必须先按
   (访客, 会话, 内容) 归并出「这次访问总共停留多久」，再跨会话求平均。

2. **跳出判定要同时看时长和滚动**。只看时长会把「快速扫一眼就走的浅阅读」
   和「刚打开就关掉」混为一谈；只看滚动会把「短文章一次读完」误判成跳出。

汇总采用「整天重算 + 覆盖写」，不搞增量累加。一天的数据量很小，重算一次
不到一秒，换来的是幂等 —— 重复跑不会翻倍，补历史不用写额外脚本。
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms import analytics_models as am
from cenkor_admin.apps.cms.tracking import BIZ_TZ, biz_today

log = structlog.get_logger()

# 跳出阈值：停留 < 10 秒 且 滚动 < 25%
BOUNCE_MS = 10_000
BOUNCE_SCROLL = 25

# 表现分的「满分停留」：3 分钟。再长不再加分 —— 否则一篇万字长文
# 会永远压过真正有用的短文，而后者才是客户想复制的。
FULL_MARK_MS = 180_000

_AGG_SQL = text(
    """
    WITH sess AS (
        SELECT
            site_id,
            entry_id,
            stat_date,
            visitor_id,
            session_id,
            MAX(duration_ms)                                        AS dur,
            MAX(scroll_pct)                                         AS scr,
            COUNT(*) FILTER (WHERE event_type = 'pv')               AS pv_n,
            COUNT(*) FILTER (WHERE event_type = 'conversion')       AS conv_n
        FROM cms_track_events
        WHERE stat_date = :day
          AND entry_id IS NOT NULL
        GROUP BY site_id, entry_id, stat_date, visitor_id, session_id
    )
    INSERT INTO cms_entry_stats_daily
        (site_id, entry_id, stat_date, pv, uv, avg_duration_ms,
         avg_scroll_pct, bounce_count, conversion_count, source, synced_at)
    SELECT
        site_id,
        entry_id,
        stat_date,
        COALESCE(SUM(pv_n), 0)::int                             AS pv,
        COUNT(DISTINCT visitor_id)::int                          AS uv,
        COALESCE(ROUND(AVG(dur)), 0)::int                        AS avg_duration_ms,
        COALESCE(ROUND(AVG(scr)), 0)::smallint                   AS avg_scroll_pct,
        COUNT(*) FILTER (WHERE dur < :bounce_ms AND scr < :bounce_scroll)::int
                                                                 AS bounce_count,
        COALESCE(SUM(conv_n), 0)::int                            AS conversion_count,
        'self'                                                   AS source,
        NOW()
    FROM sess
    GROUP BY site_id, entry_id, stat_date
    ON CONFLICT (entry_id, stat_date, source) DO UPDATE SET
        site_id          = EXCLUDED.site_id,
        pv               = EXCLUDED.pv,
        uv               = EXCLUDED.uv,
        avg_duration_ms  = EXCLUDED.avg_duration_ms,
        avg_scroll_pct   = EXCLUDED.avg_scroll_pct,
        bounce_count     = EXCLUDED.bounce_count,
        conversion_count = EXCLUDED.conversion_count,
        synced_at        = NOW()
    """
)

_SYNC_VIEWS_SQL = text(
    """
    UPDATE cms_entries e
       SET view_count = s.total
      FROM (
            SELECT entry_id, SUM(pv)::int AS total
              FROM cms_entry_stats_daily
             WHERE source = 'self'
             GROUP BY entry_id
           ) s
     WHERE e.id = s.entry_id
       AND e.view_count IS DISTINCT FROM s.total
    """
)


async def aggregate_day(db: AsyncSession, day: date) -> int:
    """重算某一天的汇总，返回影响的条目数。幂等。"""
    res = await db.execute(
        _AGG_SQL,
        {"day": day, "bounce_ms": BOUNCE_MS, "bounce_scroll": BOUNCE_SCROLL},
    )
    await db.commit()
    return int(getattr(res, "rowcount", 0) or 0)


async def aggregate_range(db: AsyncSession, days: int = 7) -> dict[str, int]:
    """重算最近 N 天（含今天）。用于首次上线补历史或修口径后重算。"""
    today = biz_today()
    total = 0
    touched = 0
    for i in range(max(1, days)):
        day = today - timedelta(days=i)
        n = await aggregate_day(db, day)
        if n:
            touched += 1
        total += n
    return {"days": days, "rows": total, "days_with_data": touched}


async def sync_view_count(db: AsyncSession) -> int:
    """把汇总的 PV 总数回写到 ``cms_entries.view_count``。

    ``view_count`` 是老字段，前端列表和排序都在用。保留它并与汇总保持一致，
    比直接删掉字段再改一堆查询安全。注意现在是「按汇总回写」，不再是
    「每次 GET 加一」—— 后者会把刷新和爬虫都算成阅读。
    """
    res = await db.execute(_SYNC_VIEWS_SQL)
    await db.commit()
    return int(getattr(res, "rowcount", 0) or 0)


async def refresh(db: AsyncSession, days: int = 2) -> dict[str, Any]:
    """聚合 + 回写，日常增量用这个。默认只碰最近两天（昨天可能补数据）。"""
    agg = await aggregate_range(db, days=days)
    synced = await sync_view_count(db)
    out = {**agg, "view_count_synced": synced}
    if agg["rows"]:
        log.info("cms.stats.refreshed", **out)
    return out


# ---------------------------------------------------------------------------
# 表现分析（给看板与「效果回填」用）
# ---------------------------------------------------------------------------


def quality_score(
    pv: int, avg_duration_ms: int, avg_scroll_pct: int, conversion: int
) -> tuple[float, str]:
    """把四个指标压成一个 0~100 的表现分，并给出**人能看懂的理由**。

    为什么不用单一指标排名：
    - 只看 PV，标题党永远第一，但它带来的线索可能是零；
    - 只看停留时长，万字长文永远占优，而客户真正想复制的是「短而有用」；
    - 只看转化，样本少的时候噪音比信号大。

    权重按「制造业内容运营的实际目标」定：读得完（滚动）最重要，其次是
    停留，转化作为加分项而不是决定项 —— 一篇技术文带来 0 条线索但被读完
    八成，它的主题仍然值得再做。
    """
    completion = max(0.0, min(100.0, float(avg_scroll_pct))) / 100.0
    dwell = min(1.0, float(avg_duration_ms) / FULL_MARK_MS)
    conv_rate = (conversion / pv) if pv > 0 else 0.0
    conv_part = min(1.0, conv_rate * 100.0)  # 每 100 次阅读 1 条线索即满分

    score = completion * 50.0 + dwell * 30.0 + conv_part * 20.0

    bits = [f"读完 {avg_scroll_pct}%"]
    secs = int(avg_duration_ms / 1000)
    bits.append(f"停留 {secs // 60} 分 {secs % 60} 秒" if secs >= 60 else f"停留 {secs} 秒")
    if pv:
        bits.append(f"每千次阅读带来 {conversion / pv * 1000:.1f} 条线索")
    return round(score, 1), "，".join(bits)


async def entry_performance(
    db: AsyncSession, *, days: int = 30, limit: int = 50, min_pv: int = 1
) -> list[dict[str, Any]]:
    """按表现分排序的内容列表。带可解释的理由，供看板与选题回填共用。"""
    today = biz_today()
    start = today - timedelta(days=max(1, days) - 1)
    rows = (
        await db.execute(
            text(
                """
                SELECT e.id, e.title, e.slug, e.published_at, e.ai_origin,
                       SUM(s.pv)::int                        AS pv,
                       SUM(s.uv)::int                        AS uv,
                       ROUND(AVG(s.avg_duration_ms))::int    AS dur,
                       ROUND(AVG(s.avg_scroll_pct))::int     AS scr,
                       SUM(s.bounce_count)::int              AS bounce,
                       SUM(s.conversion_count)::int          AS conv
                  FROM cms_entry_stats_daily s
                  JOIN cms_entries e ON e.id = s.entry_id
                 WHERE s.stat_date BETWEEN :start AND :end
                   AND s.source = 'self'
                   AND e.deleted_at IS NULL
                 GROUP BY e.id, e.title, e.slug, e.published_at, e.ai_origin
                HAVING SUM(s.pv) >= :min_pv
                 ORDER BY SUM(s.pv) DESC
                 LIMIT :limit
                """
            ),
            {"start": start, "end": today, "min_pv": min_pv, "limit": limit},
        )
    ).all()

    out: list[dict[str, Any]] = []
    for r in rows:
        # 列序：0 id / 1 title / 2 slug / 3 published_at / 4 ai_origin
        #       5 pv / 6 uv / 7 dur / 8 scr / 9 bounce / 10 conv
        pv = int(r[5] or 0)
        uv = int(r[6] or 0)
        dur = int(r[7] or 0)
        scr = int(r[8] or 0)
        bnc = int(r[9] or 0)
        conv = int(r[10] or 0)
        score, reason = quality_score(pv, dur, scr, conv)
        out.append(
            {
                "entry_id": r[0],
                "title": r[1],
                "slug": r[2],
                "published_at": r[3].isoformat() if r[3] else None,
                "ai_origin": r[4],
                "pv": pv,
                "uv": uv,
                "avg_duration_ms": dur,
                "avg_scroll_pct": scr,
                "bounce_count": bnc,
                "bounce_rate": round(bnc / pv * 100, 1) if pv else 0.0,
                "conversions": conv,
                "score": score,
                "reason": reason,
            }
        )
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


async def overview(db: AsyncSession, *, days: int = 30) -> dict[str, Any]:
    """看板顶部的总览数字。"""
    today = biz_today()
    start = today - timedelta(days=max(1, days) - 1)
    r = (
        await db.execute(
            text(
                """
                SELECT COALESCE(SUM(pv), 0)::int     AS pv,
                       COALESCE(SUM(uv), 0)::int     AS uv,
                       COALESCE(SUM(conversion_count), 0)::int AS conv,
                       COUNT(DISTINCT entry_id)::int AS entries,
                       COALESCE(SUM(bounce_count), 0)::int AS bounce,
                       COALESCE(ROUND(AVG(avg_duration_ms)), 0)::int AS dur,
                       COALESCE(ROUND(AVG(avg_scroll_pct)), 0)::int  AS scr
                  FROM cms_entry_stats_daily
                 WHERE stat_date BETWEEN :start AND :end
                   AND source = 'self'
                """
            ),
            {"start": start, "end": today},
        )
    ).one()

    pv = int(r[0] or 0)
    return {
        "days": days,
        "pv": pv,
        "uv": int(r[1] or 0),
        "conversions": int(r[2] or 0),
        "entries": int(r[3] or 0),
        "bounce_rate": round(int(r[4] or 0) / pv * 100, 1) if pv else 0.0,
        "avg_duration_ms": int(r[5] or 0),
        "avg_scroll_pct": int(r[6] or 0),
        "has_data": pv > 0,
    }


async def daily_trend(db: AsyncSession, *, days: int = 30) -> list[dict[str, Any]]:
    """按自然日的 PV / UV / 转化趋势，缺的日期补 0（不让折线断开）。"""
    today = biz_today()
    start = today - timedelta(days=max(1, days) - 1)
    rows = (
        await db.execute(
            text(
                """
                SELECT stat_date, SUM(pv)::int, SUM(uv)::int, SUM(conversion_count)::int
                  FROM cms_entry_stats_daily
                 WHERE stat_date BETWEEN :start AND :end
                   AND source = 'self'
                 GROUP BY stat_date
                 ORDER BY stat_date
                """
            ),
            {"start": start, "end": today},
        )
    ).all()
    got = {r[0]: (int(r[1] or 0), int(r[2] or 0), int(r[3] or 0)) for r in rows}
    out: list[dict[str, Any]] = []
    for i in range(max(1, days)):
        d = start + timedelta(days=i)
        pv, uv, conv = got.get(d, (0, 0, 0))
        out.append({"date": d.isoformat(), "pv": pv, "uv": uv, "conversions": conv})
    return out


async def channel_breakdown(db: AsyncSession, *, days: int = 30) -> list[dict[str, Any]]:
    """按来源渠道（utm_source）拆分，看哪条渠道真的带来阅读。"""
    today = biz_today()
    start = today - timedelta(days=max(1, days) - 1)
    rows = (
        await db.execute(
            text(
                """
                SELECT COALESCE(NULLIF(utm_source, ''), '(直接访问)') AS src,
                       COUNT(*) FILTER (WHERE event_type = 'pv')::int AS pv,
                       COUNT(DISTINCT visitor_id)::int                AS uv,
                       COUNT(*) FILTER (WHERE event_type = 'conversion')::int AS conv
                  FROM cms_track_events
                 WHERE stat_date BETWEEN :start AND :end
                 GROUP BY 1
                 ORDER BY pv DESC
                 LIMIT 20
                """
            ),
            {"start": start, "end": today},
        )
    ).all()
    return [{"source": r[0], "pv": int(r[1] or 0), "uv": int(r[2] or 0), "conversions": int(r[3] or 0)} for r in rows]


async def low_performers(
    db: AsyncSession, *, days: int = 30, min_pv: int = 20, limit: int = 20
) -> list[dict[str, Any]]:
    """高曝光低完成度的内容 —— 需要改标题或改开头的那一批。

    这是「效果回填质检」的输入：有流量进来但没人读完，说明标题承诺和正文
    内容对不上，或者开头写得太空。
    """
    perfs = await entry_performance(db, days=days, limit=200, min_pv=min_pv)
    weak = [p for p in perfs if p["avg_scroll_pct"] < 40 or p["bounce_rate"] > 70]
    weak.sort(key=lambda x: x["pv"], reverse=True)
    for w in weak:
        problems = []
        if w["avg_scroll_pct"] < 40:
            problems.append(f"只读到 {w['avg_scroll_pct']}%")
        if w["bounce_rate"] > 70:
            problems.append(f"跳出率 {w['bounce_rate']}%")
        w["problem"] = "、".join(problems)
    return weak[:limit]


async def dead_content(
    db: AsyncSession, *, days: int = 7, limit: int = 20
) -> list[dict[str, Any]]:
    """发布超过 N 天但一次访问都没有的内容。

    多半是没分发出去（没发公众号、没提交收录），不是内容本身的问题。
    """
    today = biz_today()
    since = today - timedelta(days=days)
    rows = (
        await db.execute(
            text(
                """
                SELECT e.id, e.title, e.slug, e.published_at, e.ai_origin
                  FROM cms_entries e
                  LEFT JOIN cms_entry_stats_daily s
                         ON s.entry_id = e.id AND s.source = 'self'
                 WHERE e.deleted_at IS NULL
                   AND e.status = 'published'
                   AND e.published_at IS NOT NULL
                   AND e.published_at <= :since
                 GROUP BY e.id, e.title, e.slug, e.published_at, e.ai_origin
                HAVING COALESCE(SUM(s.pv), 0) = 0
                 ORDER BY e.published_at
                 LIMIT :limit
                """
            ),
            {"since": since, "limit": limit},
        )
    ).all()
    return [
        {
            "entry_id": r[0],
            "title": r[1],
            "slug": r[2],
            "published_at": r[3].isoformat() if r[3] else None,
            "ai_origin": r[4],
            "hint": "发布后没有任何访问，检查是否已分发、是否被搜索引擎收录",
        }
        for r in rows
    ]


async def topic_weights(db: AsyncSession, *, days: int = 90, limit: int = 30) -> list[dict[str, Any]]:
    """主题权重 —— 给选题用的「数据说了算」部分。

    按内容所属分类聚合表现分，得出「哪类主题值得继续写」。只按分类聚合
    而不做 NLP 主题聚类：分类是人工定的、可解释、运营看得懂；聚类出来的
    「主题簇 3」没人知道该怎么用。
    """
    today = biz_today()
    start = today - timedelta(days=max(1, days) - 1)
    rows = (
        await db.execute(
            text(
                """
                SELECT c.id, c.name,
                       COUNT(DISTINCT e.id)::int                       AS entries,
                       COALESCE(SUM(s.pv), 0)::int                     AS pv,
                       COALESCE(ROUND(AVG(s.avg_scroll_pct)), 0)::int  AS scr,
                       COALESCE(ROUND(AVG(s.avg_duration_ms)), 0)::int AS dur,
                       COALESCE(SUM(s.conversion_count), 0)::int       AS conv
                  FROM cms_entry_stats_daily s
                  JOIN cms_entries e ON e.id = s.entry_id
                  JOIN cms_categories c ON c.id = e.category_id
                 WHERE s.stat_date BETWEEN :start AND :end
                   AND s.source = 'self'
                   AND e.deleted_at IS NULL
                 GROUP BY c.id, c.name
                HAVING SUM(s.pv) > 0
                 ORDER BY pv DESC
                 LIMIT :limit
                """
            ),
            {"start": start, "end": today, "limit": limit},
        )
    ).all()
    out: list[dict[str, Any]] = []
    for r in rows:
        pv = int(r[3] or 0)
        score, reason = quality_score(pv, int(r[5] or 0), int(r[4] or 0), int(r[6] or 0))
        out.append(
            {
                "category_id": r[0],
                "category": r[1],
                "entries": int(r[2] or 0),
                "pv": pv,
                "avg_scroll_pct": int(r[4] or 0),
                "avg_duration_ms": int(r[5] or 0),
                "conversions": int(r[6] or 0),
                "score": score,
                "reason": reason,
            }
        )
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# 效果回填：给选题喂真实数据
# ---------------------------------------------------------------------------

# 高频但没信息量的中文二字组合
_STOP_BIGRAMS = frozenset(
    {
        "的了", "以及", "如何", "怎么", "什么", "为什", "这类", "那些", "一个",
        "我们", "你们", "他们", "可以", "需要", "应该", "到底", "谁管", "为什",
        "是不", "不是", "有没", "没有", "多少", "哪些", "为何", "怎样",
    }
)


def title_keywords(title: str) -> set[str]:
    """从标题抽关键词，用于把「新选题」和「历史已发内容」对上。

    用中文 2-gram 而不是分词库：这个场景只要「大致相关」就够给出有意义的
    证据，引入 jieba 会让依赖变重、启动变慢，换来的准确率提升在几十条
    数据上根本看不出来。
    """
    text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", title or "")
    out: set[str] = set()
    for chunk in text.split():
        if re.fullmatch(r"[A-Za-z0-9]+", chunk):
            if len(chunk) >= 2:
                out.add(chunk.lower())
        else:
            for i in range(len(chunk) - 1):
                gram = chunk[i : i + 2]
                if gram not in _STOP_BIGRAMS:
                    out.add(gram)
    return out


async def enrich_topic_gaps(db: AsyncSession, result: dict[str, Any], *, days: int = 90) -> dict[str, Any]:
    """给选题缺口附上「历史上这类内容表现如何」。

    **不改 AI 提示词**，只在返回结果上加证据。原因：现在的 gaps 输出是调过的，
    往提示词里塞更多上下文，模型很容易开始编「因为 A 文章读完率 88%，所以建议
    写 B」这种看着有道理、实际对不上的因果。数据放在结构里，由人判断。

    匹配用标题 2-gram 重合 ≥2 个。宽进窄出 —— 宁可多给几条参考，
    也不要漏掉真正相关的那篇。
    """
    gaps = result.get("gaps") or []
    if not isinstance(gaps, list):
        return result

    perfs = await entry_performance(db, days=days, limit=120, min_pv=1)
    if not perfs:
        result["performance_evidence"] = {
            "available": False,
            "note": "还没有效果数据。接入埋点脚本、积累几天访问后这里会出现「同类主题表现」。",
        }
        return result

    n = len(perfs)
    baseline = {
        "entries_with_data": n,
        "avg_scroll_pct": round(sum(p["avg_scroll_pct"] for p in perfs) / n),
        "avg_duration_ms": round(sum(p["avg_duration_ms"] for p in perfs) / n),
        "avg_bounce_rate": round(sum(p["bounce_rate"] for p in perfs) / n, 1),
    }
    baseline["note"] = (
        f"现有 {n} 篇有访问的内容平均被读完 {baseline['avg_scroll_pct']}%、"
        f"停留 {baseline['avg_duration_ms'] // 1000} 秒、跳出率 {baseline['avg_bounce_rate']}%"
    )

    # 表现最好 / 最差各取几篇，给「该多做哪类」和「别再这么写」两个方向
    top = perfs[:3]
    bottom = sorted(perfs, key=lambda x: x["score"])[:3]

    for gap in gaps:
        if not isinstance(gap, dict):
            continue
        kws = title_keywords(str(gap.get("title") or ""))
        matched: list[tuple[int, dict[str, Any]]] = []
        if kws:
            for p in perfs:
                overlap = len(kws & title_keywords(str(p.get("title") or "")))
                if overlap >= 2:
                    matched.append((overlap, p))
            matched.sort(key=lambda x: (-x[0], -x[1]["score"]))
        refs = [p for _, p in matched[:3]]
        gap["performance_evidence"] = {
            "related_entries": [
                {
                    "entry_id": p["entry_id"],
                    "title": p["title"],
                    "pv": p["pv"],
                    "avg_scroll_pct": p["avg_scroll_pct"],
                    "score": p["score"],
                    "reason": p["reason"],
                }
                for p in refs
            ],
            "verdict": (
                "同类主题已有内容表现不错，可以在这个方向上做深"
                if refs and sum(p["score"] for p in refs) / len(refs) >= 50
                else "同类主题已有内容但表现一般，要么换角度要么换主题"
                if refs
                else "没有找到同类主题的历史内容，属于空白方向"
            ),
        }

    result["performance_evidence"] = {
        "available": True,
        "baseline": baseline,
        "top_entries": [
            {"entry_id": p["entry_id"], "title": p["title"], "score": p["score"], "reason": p["reason"]}
            for p in top
        ],
        "weak_entries": [
            {
                "entry_id": p["entry_id"],
                "title": p["title"],
                "score": p["score"],
                "problem": f"读完 {p['avg_scroll_pct']}%、跳出 {p['bounce_rate']}%",
            }
            for p in bottom
        ],
        "how_to_read": (
            "每个选题下面会带「同类主题历史表现」。若同类内容读完率明显低于基线，"
            "说明这个角度已经写疲了，换个切口比再写一篇更划算。"
        ),
    }
    return result


async def import_external_stats(
    db: AsyncSession,
    *,
    rows: list[dict[str, Any]],
    source: str,
) -> dict[str, int]:
    """导入第三方统计（百度统计 / GA / 手工表）。

    这是「预留第三方通道」的落点：外部数据按 (entry, 日期, source) upsert，
    与自建埋点并存而不覆盖。看板可以让运营选「看自己采的」还是「看百度
    统计的」—— 两边数据本来就会不一样（口径、去重、爬虫过滤都不同），
    强行合并只会得到一个谁都不认的数字。
    """
    if source not in ("baidu", "ga", "manual"):
        raise ValueError("source 必须是 baidu / ga / manual")
    ok = 0
    for r in rows:
        eid = r.get("entry_id")
        day = r.get("date") or r.get("stat_date")
        if not eid or not day:
            continue
        await db.execute(
            text(
                """
                INSERT INTO cms_entry_stats_daily
                    (site_id, entry_id, stat_date, pv, uv, avg_duration_ms,
                     avg_scroll_pct, bounce_count, conversion_count, source, synced_at)
                VALUES (1, :eid, :day, :pv, :uv, :dur, :scr, :bnc, :conv, :src, NOW())
                ON CONFLICT (entry_id, stat_date, source) DO UPDATE SET
                    pv = EXCLUDED.pv, uv = EXCLUDED.uv,
                    avg_duration_ms = EXCLUDED.avg_duration_ms,
                    avg_scroll_pct = EXCLUDED.avg_scroll_pct,
                    bounce_count = EXCLUDED.bounce_count,
                    conversion_count = EXCLUDED.conversion_count,
                    synced_at = NOW()
                """
            ),
            {
                "eid": int(eid),
                "day": day,
                "pv": int(r.get("pv") or 0),
                "uv": int(r.get("uv") or 0),
                "dur": int(r.get("avg_duration_ms") or 0),
                "scr": int(r.get("avg_scroll_pct") or 0),
                "bnc": int(r.get("bounce_count") or 0),
                "conv": int(r.get("conversion_count") or 0),
                "src": source,
            },
        )
        ok += 1
    await db.commit()
    return {"imported": ok, "source": source}


# ---------------------------------------------------------------------------
# 定时聚合
# ---------------------------------------------------------------------------

_LAST_REFRESH: dict[str, float] = {}
_REFRESH_INTERVAL = 300.0  # 秒


async def on_scheduler_tick(db: AsyncSession | None = None) -> dict[str, Any]:
    """挂在 scheduler.tick 扩展点上。

    scheduler 每 30 秒 tick 一次，但汇总不需要那么频繁：一来一天的数据量
    很小、二来每次都全表重算没必要。这里做 5 分钟节流，用模块级时间戳
    记录上次执行。单进程部署足够（多进程会各算各的，结果一样，只是浪费）。
    """
    import time

    now = time.monotonic()
    last = _LAST_REFRESH.get("at", 0.0)
    if now - last < _REFRESH_INTERVAL:
        return {"skipped": True}
    _LAST_REFRESH["at"] = now

    from cenkor_admin.core.db import AsyncSessionLocal

    if db is None:
        async with AsyncSessionLocal() as own:
            return await refresh(own, days=1)
    return await refresh(db, days=1)


# 挂到调度器扩展点上：scheduler 每 30 秒 tick，这里内部 5 分钟节流。
# 用 hook 而不是改 scheduler 源码 —— 汇总属于「内容运营」这个应用的关注点，
# 不该塞进核心调度器。核心只负责提供扩展点。
from cenkor_admin.core.hooks import hook  # noqa: E402


@hook("scheduler.tick")
async def _hook_refresh_stats() -> None:
    try:
        await on_scheduler_tick()
    except Exception as exc:  # noqa: BLE001
        # 汇总失败不能影响定时发布 —— 那条链路比统计数据重要得多
        log.warning("cms.stats.tick_failed", error=str(exc))
