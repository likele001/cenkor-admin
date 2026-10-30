"""选题 Gap 分析：已有内容 vs 应该有的内容。

## 为什么要做这个

内容团队真正的问题不是「写不出来」，是**不知道该写什么**。
拍脑袋选题的结果是：三篇讲同一个卖点、缺掉客户最常问的那个对比问题。

这个模块做的事：把库里已有的内容摊开，让模型判断「覆盖了哪些主题簇、
缺哪些」，并且按**买家决策阶段**分层输出缺口 —— 因为一个 B2B 内容库的
典型毛病是认知层文章一大堆，决策层（选型对比、报价逻辑、落地案例）几乎没有。

## 防模型编造（核心）

模型很擅长说「你已经有《XX》一文，但缺少对比」——**而《XX》根本不存在**。

所以 `related_existing` 字段做白名单校验：
模型只能引用输入里真实给出的标题，任何对不上的直接置空。
"缺什么"是判断（可以放给模型），"有什么"是事实（必须来自数据库）。

## 输入裁剪

只给标题 + 摘要前 120 字，不给正文 —— 正文会瞬间吃满上下文，
而且判断「这个主题有没有」标题和摘要足够了。条数上限 80，超了按更新时间取样。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.ai import prompt_registry as prompts
from cenkor_admin.apps.cms.ai.copilot import _as_object, _record
from cenkor_admin.apps.cms.models import ContentType, Entry
from cenkor_admin.core.llm import LLMError, LLMNotConfiguredError, get_llm

_KIND_GAP = "topic_gap"

# 单次分析最多喂多少条内容（标题级，成本可控）
_MAX_INPUT = 80
# 每条摘要截断长度：判断「这个主题有没有」靠标题+一句摘要就够，
# 给多了只会拉长推理模型的思考过程（实测 reasoning 能吃满 6000 token）
_DESC_MAX = 100

INTENTS = ("awareness", "consideration", "decision", "retention")
INTENT_LABELS = {
    "awareness": "认知（是什么/为什么重要）",
    "consideration": "比较（选型/方案对比/怎么挑）",
    "decision": "决策（报价/交期/落地/风险）",
    "retention": "留存（使用/维护/常见问题）",
}

_GAP_SYSTEM = """你是 B2B 内容策略顾问。任务是找出内容库的**覆盖缺口**。

## 输入

一份现有内容清单（标题 + 摘要），以及内容类型分布。

## 你要做的

1. 归纳现有内容覆盖了哪些**主题簇**（不是逐篇复述，是聚类）。
   **直接给结论，不要逐篇分析** —— 思考过程越长越容易把输出预算吃光。
2. 按买家决策阶段找出**缺口**：
   - awareness 认知：这是什么、为什么需要、行业趋势
   - consideration 比较：选型标准、方案/参数对比、替代品差异
   - decision 决策：报价逻辑、交期、认证资质、失败案例、落地流程
   - retention 留存：安装、使用、维护、常见故障
   B2B 库最常见的病就是 awareness 一堆、decision 几乎没有。优先补后面三层。
3. 每个缺口给一个**可直接开工的标题**（具体、有信息量，不要「XX 指南」这种空壳）。

## 铁律

1. `related_existing` **只能填输入清单里逐字出现过的标题**。清单里没有的，
   一律填空数组。不许编造、不许改写、不许合成。
2. 缺口必须是**真的没被覆盖**的。如果清单里已有明显对应的文章，不要把它列成缺口。
3. 不要提「多写原创内容」「提升内容质量」这类废话。每条缺口都要能落到一个标题上。
4. 优先级按「对成交的影响 × 当前缺失程度」判断，不是按「好写程度」。

## 输出

严格 JSON：
{
  "coverage_summary": "两三句话概括现有覆盖的强项与偏科",
  "gaps": [
    {
      "topic": "主题名（短，8 字内）",
      "intent": "awareness|consideration|decision|retention",
      "why_gap": "为什么这是缺口，一句话，要具体",
      "suggested_title": "可直接用的文章标题",
      "keywords": ["搜索词 3~5 个"],
      "priority": "high|medium|low",
      "related_existing": ["清单里的真实标题"]
    }
  ]
}
"""


def _norm_title(t: str) -> str:
    """标题归一化用于白名单比对：去空白与标点，保留中英文数字。"""
    return "".join(ch for ch in (t or "") if ch.isalnum())


async def analyze(
    session: AsyncSession,
    *,
    content_type_key: str | None = None,
    limit: int = 10,
    created_by: int | None = None,
) -> dict[str, Any]:
    """分析选题缺口。只读，不改内容。"""
    limit = max(1, min(int(limit or 10), 20))

    ct_filter = None
    if content_type_key:
        ct = (
            await session.execute(select(ContentType).where(ContentType.key == content_type_key))
        ).scalar_one_or_none()
        if ct is None:
            raise ValueError(f"内容类型不存在: {content_type_key}")
        ct_filter = ct.id

    # 只取必要列：正文级数据既贵又没用
    stmt = (
        select(Entry.id, Entry.title, Entry.seo, Entry.content_type_id, Entry.published_at)
        .where(Entry.deleted_at.is_(None), Entry.status == "published")
        .order_by(Entry.published_at.desc().nullslast())
        .limit(_MAX_INPUT)
    )
    if ct_filter:
        stmt = stmt.where(Entry.content_type_id == ct_filter)
    rows = (await session.execute(stmt)).all()

    if not rows:
        return {
            "coverage_summary": "库里还没有已发布内容，先把基础内容补齐再谈缺口。",
            "gaps": [],
            "total_entries": 0,
            "content_types": [],
            "generated_at": datetime.now().isoformat(),
            "warning": "没有已发布内容，无法做覆盖分析",
        }

    # 内容类型分布
    cnt_stmt = (
        select(Entry.content_type_id, func.count())
        .where(Entry.deleted_at.is_(None), Entry.status == "published")
        .group_by(Entry.content_type_id)
    )
    cnt_rows = (await session.execute(cnt_stmt)).all()
    ct_ids = [r[0] for r in cnt_rows]
    ct_names: dict[int, str] = {}
    if ct_ids:
        ct_names = {
            r[0]: r[1]
            for r in (
                await session.execute(
                    select(ContentType.id, ContentType.name).where(ContentType.id.in_(ct_ids))
                )
            ).all()
        }
    ct_dist = [
        {"key": ct_names.get(cid, str(cid)), "count": n} for cid, n in cnt_rows if cid in ct_names
    ]

    listing: list[str] = []
    real_titles: set[str] = set()
    for idx, r in enumerate(rows, start=1):
        desc = ""
        if isinstance(r.seo, dict):
            desc = str(r.seo.get("description") or "").strip()[:_DESC_MAX]
        ct_name = ct_names.get(r.content_type_id, "")
        line = f"{idx}. {r.title}"
        if ct_name:
            line += f"（{ct_name}）"
        if desc:
            line += f" — {desc}"
        listing.append(line)
        real_titles.add(_norm_title(r.title))

    ct_desc = ", ".join(f"{c['key']}={c['count']}" for c in ct_dist)
    user_msg = (
        f"内容类型分布：{ct_desc}\n"
        f"已发布内容共 {sum(c['count'] for c in ct_dist)} 篇，下面列出 {len(rows)} 篇：\n\n"
        + "\n".join(listing)
        + f"\n\n请输出最多 {limit} 个缺口。"
    )

    messages = [
        {"role": "system", "content": await prompts.get(session, "topic_gap", _GAP_SYSTEM)},
        {"role": "user", "content": user_msg},
    ]

    try:
        llm = get_llm()
        # 推理模型的 reasoning 与正文共享预算：实测 6000 会被 reasoning 吃满并截断
        # （reasoning 单次可达 24000+ 字符）。这是低频操作，给足 16000。
        raw, result = await llm.chat_json(messages, temperature=0.4, max_tokens=16000)
    except LLMNotConfiguredError as exc:
        raise LLMError("AI 模型未配置，无法做选题分析") from exc
    except LLMError as exc:
        await _record(
            session,
            kind=_KIND_GAP,
            target="site",
            result=None,
            status="failed",
            error=str(exc),
            created_by=created_by,
            prompt=user_msg,
        )
        raise

    obj = _as_object(raw, "选题缺口")
    gaps: list[dict[str, Any]] = []
    dropped_refs = 0

    for g in obj.get("gaps") or []:
        if not isinstance(g, dict):
            continue
        title = str(g.get("suggested_title") or "").strip()
        topic = str(g.get("topic") or "").strip()
        if not title and not topic:
            continue

        # 白名单校验：模型说的"已有内容"必须真的存在
        refs_in = [str(x).strip() for x in (g.get("related_existing") or []) if str(x).strip()]
        refs_ok = [t for t in refs_in if _norm_title(t) in real_titles]
        dropped_refs += len(refs_in) - len(refs_ok)

        intent = str(g.get("intent") or "").strip().lower()
        if intent not in INTENTS:
            intent = "awareness"
        priority = str(g.get("priority") or "").strip().lower()
        if priority not in ("high", "medium", "low"):
            priority = "medium"

        gaps.append(
            {
                "topic": topic[:40],
                "intent": intent,
                "intent_label": INTENT_LABELS[intent],
                "why_gap": str(g.get("why_gap") or "").strip()[:300],
                "suggested_title": title[:120],
                "keywords": [str(k).strip()[:30] for k in (g.get("keywords") or []) if str(k).strip()][:6],
                "priority": priority,
                "related_existing": refs_ok[:5],
            }
        )

    # 优先级排序：high 在前，同优先级保持模型给的相对顺序
    order = {"high": 0, "medium": 1, "low": 2}
    gaps.sort(key=lambda x: order[x["priority"]])
    gaps = gaps[:limit]

    if dropped_refs:
        logger.info(f"[topic_gap] dropped {dropped_refs} fabricated related_existing refs")

    await _record(
        session,
        kind=_KIND_GAP,
        target="site",
        result=result,
        params={"entries": len(rows), "gaps": len(gaps), "dropped_refs": dropped_refs},
        created_by=created_by,
        prompt=user_msg,
    )

    logger.info(f"[topic_gap] entries={len(rows)} gaps={len(gaps)} dropped={dropped_refs}")

    return {
        "coverage_summary": str(obj.get("coverage_summary") or "").strip()[:600],
        "gaps": gaps,
        "total_entries": sum(c["count"] for c in ct_dist),
        "sampled_entries": len(rows),
        "content_types": ct_dist,
        "intent_distribution": _intent_dist(gaps),
        # 模型编造的 related_existing 条数。长期不为 0 说明提示词该收紧，
        # 或者模型开始"想象"已有内容 —— 这是个免费的提示词质量探针。
        "refs_dropped": dropped_refs,
        "generated_at": datetime.now().isoformat(),
        "warning": None,
    }


def _intent_dist(gaps: list[dict[str, Any]]) -> dict[str, int]:
    dist = dict.fromkeys(INTENTS, 0)
    for g in gaps:
        dist[g["intent"]] += 1
    return dist
