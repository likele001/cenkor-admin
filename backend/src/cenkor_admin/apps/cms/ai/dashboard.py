"""AI 驾驶舱：把 AI 在站内到底干了多少活，用真实数字摆出来。

## 为什么需要这个页面

多站点、批量生产、提示词版本化都做完之后，AI 能力其实不少，但都散在各个
二级菜单里 —— 用户打开后台看到的仍是「内容管理 + 一堆 CRUD」。这个端点是
驾驶舱的数据源：不新增任何 AI 能力，只把已有事实聚合成一眼能读的数字。

## 数据口径（都与条目列表对齐，避免「驾驶舱说 23、列表说 26」）

- 产出：`cms_entries.ai_origin IS NOT NULL AND deleted_at IS NULL`
- 占比分母：同站点、同时间窗内的全部未删除条目
- 用量：`cms_ai_generations`，只算 `status='ok'`（失败调用同样烧钱，但算进
  成功产出里会让人误以为 AI 很能干，所以单列在最近记录里可见）
- 全部按站点切分；脚本产生的记录归默认站

## 性能

8 个聚合查询，全走索引，单站数据量下 <20ms。前端一次请求拿全，不做多个
接口拼接 —— 驾驶舱是打开的默认页，多一次往返就多一次白屏。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms.ai import registry as ai_registry
from cenkor_admin.apps.cms.ai.models import CmsAiBatchJob, CmsAiGeneration, CmsEmbedding
from cenkor_admin.apps.cms.models import Entry, Site
from cenkor_admin.core.db import get_db
from cenkor_admin.core.site_scope import current_site_id, site_scope_bypass

router = APIRouter(tags=["cms-ai"])

_TREND_DAYS = 7
_RECENT_LIMIT = 12

# 能力矩阵的「是否真能用」判据。wired=False 的（rerank/asr/tts）即使配了也
# 没有调用链，界面上标「仅配置」，不许它冒充能力。
_LABELS = {
    "chat": ("对话补全", "起草 / 翻译 / SEO / 建模"),
    "embedding": ("向量化", "语义检索与相似内容"),
    "vision": ("视觉理解", "看图说话、截图转结构化"),
    "image": ("图片生成", "封面图、配图"),
    "rerank": ("重排序", "检索结果精排"),
    "asr": ("语音识别", "音视频转文字"),
    "tts": ("语音合成", "文案转语音"),
}


async def _site_info(db: AsyncSession, sid: int) -> dict[str, Any]:
    row = (
        await db.execute(select(Site.id, Site.name, Site.key).where(Site.id == sid))
    ).first()
    if row is None:
        return {"id": sid, "name": "未知站点", "key": ""}
    return {"id": row[0], "name": row[1], "key": row[2]}


async def _capabilities(db: AsyncSession) -> list[dict[str, Any]]:
    reg = await ai_registry.load(db)
    out: list[dict[str, Any]] = []
    for spec in ai_registry.CAPABILITIES:
        ep = reg.endpoint(spec.key)
        label, hint = _LABELS.get(spec.key, (spec.label, spec.hint))
        out.append(
            {
                "key": spec.key,
                "label": label,
                "hint": hint,
                "wired": spec.wired,
                "ready": ep is not None and spec.wired,
                # 配了但没接调用链，和「没配」要区分开，否则用户以为功能能用了
                "configured_only": ep is not None and not spec.wired,
                "model": ep.model if ep else "",
                "provider": ep.provider_name if ep else "",
                "source": ep.source if ep else "",
                # 嵌入维度：降维到 1024 才建得了 HNSW，界面上要看得见
                "dims": (ep.params or {}).get("dimensions") if ep else None,
            }
        )
    return out


async def _output_stats(db: AsyncSession, sid: int) -> dict[str, Any]:
    """产出：今日 / 本周 / 本月 / 累计 + 按来源 + 近 7 天趋势。"""
    ai_row = (
        await db.execute(
            text(
                """
                SELECT
                  count(*) FILTER (WHERE created_at >= current_date)                     AS today,
                  count(*) FILTER (WHERE created_at >= current_date - interval '6 days') AS week,
                  count(*) FILTER (WHERE created_at >= date_trunc('month', now()))       AS month,
                  count(*)                                                              AS total
                  FROM cms_entries
                 WHERE site_id = :sid AND ai_origin IS NOT NULL AND deleted_at IS NULL
                """
            ),
            {"sid": sid},
        )
    ).first()

    by_origin = (
        await db.execute(
            text(
                """
                SELECT ai_origin, count(*)
                  FROM cms_entries
                 WHERE site_id = :sid AND ai_origin IS NOT NULL AND deleted_at IS NULL
                 GROUP BY ai_origin ORDER BY 2 DESC
                """
            ),
            {"sid": sid},
        )
    ).all()

    trend_rows = (
        await db.execute(
            text(
                """
                SELECT CAST(date_trunc('day', created_at) AS date) AS d, count(*)
                  FROM cms_entries
                 WHERE site_id = :sid
                   AND ai_origin IS NOT NULL
                   AND deleted_at IS NULL
                   AND created_at >= current_date - interval '6 days'
                 GROUP BY 1 ORDER BY 1
                """
            ),
            {"sid": sid},
        )
    ).all()

    # 补齐空缺日期 —— 前端画柱状图需要连续 7 天，缺一天图就断
    got = {r[0]: int(r[1]) for r in trend_rows}
    today = datetime.now(timezone.utc).date()
    trend = [
        {
            "date": (today - timedelta(days=_TREND_DAYS - 1 - i)).isoformat(),
            "count": got.get(today - timedelta(days=_TREND_DAYS - 1 - i), 0),
        }
        for i in range(_TREND_DAYS)
    ]

    return {
        "today": int(ai_row[0] or 0),
        "week": int(ai_row[1] or 0),
        "month": int(ai_row[2] or 0),
        "total": int(ai_row[3] or 0),
        "by_origin": [{"origin": r[0], "count": int(r[1])} for r in by_origin],
        "trend": trend,
    }


async def _coverage(db: AsyncSession, sid: int, ai_month: int) -> dict[str, Any]:
    """AI 产出占全部内容的比重 —— 「AI 到底占了多少活」最直观的一个数。"""
    month_start = func.date_trunc("month", func.now())
    row = (
        await db.execute(
            select(
                func.count(Entry.id).filter(Entry.deleted_at.is_(None)),
                func.count(Entry.id).filter(
                    Entry.deleted_at.is_(None),
                    Entry.ai_origin.is_not(None),
                ),
                func.count(Entry.id).filter(
                    Entry.deleted_at.is_(None),
                    Entry.created_at >= month_start,
                ),
            ).where(Entry.site_id == sid)
        )
    ).first()

    all_total = int(row[0] or 0)
    ai_total = int(row[1] or 0)
    month_all = int(row[2] or 0)

    def ratio(a: int, b: int) -> float:
        return round(a / b, 4) if b else 0.0

    return {
        "ai_entries": ai_total,
        "all_entries": all_total,
        "ai_ratio": ratio(ai_total, all_total),
        "month_ai": ai_month,
        "month_all": month_all,
        "month_ratio": ratio(ai_month, month_all),
    }


async def _usage_stats(db: AsyncSession, sid: int) -> dict[str, Any]:
    """用量：今日 / 本月 token 与调用数、平均耗时、按 kind 明细。"""
    row = (
        await db.execute(
            text(
                """
                SELECT
                  count(*) FILTER (WHERE created_at >= current_date)               AS today_calls,
                  coalesce(sum(tokens_in + tokens_out) FILTER (
                      WHERE created_at >= current_date), 0)                        AS today_tokens,
                  count(*) FILTER (WHERE created_at >= date_trunc('month', now()))  AS month_calls,
                  coalesce(sum(tokens_in + tokens_out) FILTER (
                      WHERE created_at >= date_trunc('month', now())), 0)           AS month_tokens,
                  coalesce(avg(latency_ms) FILTER (
                      WHERE created_at >= date_trunc('month', now())), 0)           AS avg_latency
                  FROM cms_ai_generations
                 WHERE site_id = :sid AND status = 'ok'
                """
            ),
            {"sid": sid},
        )
    ).first()

    by_kind = (
        await db.execute(
            text(
                """
                SELECT kind, count(*) AS calls,
                       coalesce(sum(tokens_in), 0), coalesce(sum(tokens_out), 0),
                       coalesce(avg(latency_ms), 0)
                  FROM cms_ai_generations
                 WHERE site_id = :sid AND status = 'ok'
                   AND created_at >= date_trunc('month', now())
                 GROUP BY kind ORDER BY calls DESC
                """
            ),
            {"sid": sid},
        )
    ).all()

    return {
        "today_calls": int(row[0] or 0),
        "today_tokens": int(row[1] or 0),
        "month_calls": int(row[2] or 0),
        "month_tokens": int(row[3] or 0),
        "avg_latency_ms": int(row[4] or 0),
        "by_kind": [
            {
                "kind": r[0],
                "calls": int(r[1]),
                "tokens_in": int(r[2]),
                "tokens_out": int(r[3]),
                "avg_latency_ms": int(r[4] or 0),
            }
            for r in by_kind
        ],
    }


async def _recent(db: AsyncSession, sid: int) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(
                CmsAiGeneration.id,
                CmsAiGeneration.kind,
                CmsAiGeneration.target,
                CmsAiGeneration.model,
                CmsAiGeneration.tokens_in,
                CmsAiGeneration.tokens_out,
                CmsAiGeneration.latency_ms,
                CmsAiGeneration.status,
                CmsAiGeneration.error,
                CmsAiGeneration.created_at,
            )
            .where(CmsAiGeneration.site_id == sid)
            .order_by(CmsAiGeneration.id.desc())
            .limit(_RECENT_LIMIT)
        )
    ).all()

    gen_ids = [r[0] for r in rows]
    # 反查这些生成记录最终变成了哪篇文章，「最近产出」才能点进去
    entry_map: dict[int, int] = {}
    if gen_ids:
        linked = (
            await db.execute(
                select(Entry.ai_generation_id, Entry.id).where(
                    Entry.ai_generation_id.in_(gen_ids),
                    Entry.deleted_at.is_(None),
                )
            )
        ).all()
        entry_map = {r[0]: r[1] for r in linked}

    return [
        {
            "id": r[0],
            "kind": r[1],
            "target": r[2],
            "model": r[3],
            "tokens_in": r[4],
            "tokens_out": r[5],
            "latency_ms": r[6],
            "status": r[7],
            "error": (r[8] or "")[:200] or None,
            "created_at": r[9].isoformat() if r[9] else None,
            "entry_id": entry_map.get(r[0]),
        }
        for r in rows
    ]


async def _batches(db: AsyncSession, sid: int) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(
                CmsAiBatchJob.id,
                CmsAiBatchJob.name,
                CmsAiBatchJob.status,
                CmsAiBatchJob.total,
                CmsAiBatchJob.succeeded,
                CmsAiBatchJob.failed,
                CmsAiBatchJob.skipped,
            )
            .where(CmsAiBatchJob.site_id == sid)
            .order_by(CmsAiBatchJob.id.desc())
            .limit(5)
        )
    ).all()
    return [
        {
            "id": r[0],
            "name": r[1],
            "status": r[2],
            "total": r[3],
            "succeeded": r[4],
            "failed": r[5],
            "skipped": r[6],
        }
        for r in rows
    ]


async def _prompt_stats(db: AsyncSession) -> dict[str, Any]:
    """提示词改动数：版本 > 1 的 key 数量，提醒「模型行为被改过」。

    v1 即出厂默认（迁移 006 时按代码常量灌的），所以「改过」等价于存在 v2+。
    注意表里是 prompt_key，不是 key —— 这名字和业务里的 key 撞，容易写错。
    """
    row = (
        await db.execute(
            text(
                """
                SELECT count(DISTINCT prompt_key) FROM cms_ai_prompts
                 WHERE version > 1
                """
            )
        )
    ).first()
    total = (
        await db.execute(
            text("SELECT count(DISTINCT prompt_key) FROM cms_ai_prompts")
        )
    ).first()
    return {"keys": int(total[0] or 0), "modified": int(row[0] or 0)}


async def _vector_stats(db: AsyncSession, sid: int) -> dict[str, Any]:
    """向量覆盖率与**实际维度** —— 语义检索能不能用的前置条件。

    cms_embeddings 没有 site_id（迁移 001 只覆盖了内容归属表），所以靠
    entry_id 关联到 Entry 拿站点。关联后不带 deleted_at 过滤会虚高：
    回收站里的条目向量还在，检索时却被过滤掉。

    dim 从库里读真实向量维度，而不是信配置里的 dimensions。两者可能不一致
    （改配置没重建向量就是这样），而建 HNSW 索引的实际上限只认库里那个 ——
    界面必须显示能被验证为真的数字。
    """
    total = (
        await db.execute(
            select(func.count(Entry.id)).where(
                Entry.site_id == sid, Entry.deleted_at.is_(None)
            )
        )
    ).scalar_one()
    ready = (
        await db.execute(
            select(func.count(CmsEmbedding.id))
            .join(Entry, Entry.id == CmsEmbedding.entry_id)
            .where(Entry.site_id == sid, Entry.deleted_at.is_(None))
        )
    ).scalar_one()
    dim_row = (
        await db.execute(
            select(CmsEmbedding.dim, func.count(CmsEmbedding.id))
            .join(Entry, Entry.id == CmsEmbedding.entry_id)
            .where(Entry.site_id == sid)
            .group_by(CmsEmbedding.dim)
            .order_by(func.count(CmsEmbedding.id).desc())
            .limit(1)
        )
    ).first()
    total, ready = int(total or 0), int(ready or 0)
    return {
        "entries": total,
        "embedded": ready,
        "ratio": round(ready / total, 4) if total else 0.0,
        # 库内真实维度；没有向量时为空
        "dim": int(dim_row[0]) if dim_row else None,
    }


@router.get("/dashboard", summary="AI 驾驶舱总览")
async def ai_dashboard(
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    sid = current_site_id() or 1

    # 站点信息查询会被中间件自动过滤，这里要绕过 —— 它本身就是按 id 查
    with site_scope_bypass():
        site = await _site_info(db, sid)

    capabilities = await _capabilities(db)
    output = await _output_stats(db, sid)
    usage = await _usage_stats(db, sid)
    coverage = await _coverage(db, sid, output["month"])

    return {
        "site": site,
        "capabilities": capabilities,
        "health": {
            "chat_ready": any(c["ready"] for c in capabilities if c["key"] == "chat"),
            "embedding_ready": any(c["ready"] for c in capabilities if c["key"] == "embedding"),
            "ready_count": sum(1 for c in capabilities if c["ready"]),
            "total_count": len(capabilities),
        },
        "output": output,
        "coverage": coverage,
        "usage": usage,
        "vectors": await _vector_stats(db, sid),
        "recent": await _recent(db, sid),
        "batches": await _batches(db, sid),
        "prompts": await _prompt_stats(db),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
