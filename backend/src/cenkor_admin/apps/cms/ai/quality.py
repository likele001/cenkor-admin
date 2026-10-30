"""AI 产出抽样质检与模型 A/B。

## 为什么需要

上线 AI 之后最常见的一句追问我猜是：「它写得还行吗？」

没有人能回答。因为：
- **没有样本**：谁也不会主动去翻草稿箱，看第 137 号草稿写得好不好
- **没有量尺**：就算看了，「感觉一般」这种结论换个人说就不一样，也无法比较
- **没有时间轴**：模型换了、提示词改了，好坏变化埋在几百条草稿里，看不出来

于是「AI 写得好不好」永远停留在感觉层面，模型选型也只能拍脑袋。
这个模块把三件事变成数据：**随机抽样 → 结构化打分 → 按周/按模型出曲线**。

## 两条独立的产品线

1. **抽样质检**（被动）：从历史 AI 产出里随机抽，人打分。回答「最近的产出怎么样」
2. **模型 A/B**（主动）：同一主题，两个模型各写一版，盲评后揭晓。回答「该用哪个模型」

两者都落到同一张 `cms_ai_reviews`，但 `source` 分开，**不混算均分** ——
抽样反映真实分布（难易混杂），A/B 只反映同题对比，混在一起算均值会互相污染。

## 抽样为什么不按时间取最近的

按时间取最近 N 条，抽到的永远是最新那批模型/提示词的产物，
看不到「三个月前那版提示词是不是更好」。所以用 `ORDER BY random()`。

`random()` 会全表扫，条目上万时会慢。当前规模（百级）无所谓；
真到几万条再换 `TABLESAMPLE SYSTEM`，这个注释就是给那时候的接手人看的。

## A/B 的两条铁律

1. **左右随机**：人能看见「左边/右边」，看不见模型名。固定 A 在左，评分者会
   不知不觉形成位置偏好，对比结果就废了。
2. **参数完全一致**（temperature / max_tokens / system prompt）：最常见的
   A/B 翻车方式就是两个模型跑了不同参数，然后得出「模型 B 更啰嗦」的结论。
"""

from __future__ import annotations

import random
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.ai import prompt_registry as prompts
from cenkor_admin.apps.cms.ai.copilot import _draft_to_text, _record
from cenkor_admin.apps.cms.ai.models import CmsAiAbRun, CmsAiReview
from cenkor_admin.apps.cms.models import Entry
from cenkor_admin.core.llm import get_llm_for

# ------------------------------------------------------------------ 常量

# 评分维度：overall 必填，其余可选。加维度只需要动这里 + 前端
DIMENSIONS = (
    ("overall", "整体"),
    ("accuracy", "准确性"),
    ("readability", "可读性"),
    ("brand", "品牌一致性"),
)

VERDICTS = ("pass", "needs_fix", "reject")

# 抽样窗口默认 90 天：更早的产出多半已经改过或下线，评它没意义
_DEFAULT_WINDOW_DAYS = 90

_AB_SYSTEM = """你是一位资深行业内容编辑。请围绕给定主题，写一篇可直接发布的文章正文。

硬性要求：
1. 直接给成品正文，用 HTML 小标题（<h2>/<h3>）与段落组织
2. 不要写"好的""以下是""希望对你有所帮助"这类客套与元叙述
3. 不要输出标题以外的解释性文字，也不要说明你的写作思路
4. 篇幅 800~1200 字，观点具体、可执行，避免空泛形容词堆砌
"""


_THINK_RE = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.S)
_THINK_OPEN_RE = re.compile(r"<think(?:ing)?>", re.I)


def _strip_think(raw: str) -> tuple[str, bool]:
    """剥掉模型把自己的思考写进正文的 ``<think>`` 块。

    推理模型的 ``reasoning_content`` 与 ``content`` 偶尔会混在一起（实测
    MiniMax-M2.x 会把 ``<think>We need answer...`` 直接写进 content）。
    盲评时看到这堆英文思考过程，评分人根本没法比较「正文好不好」。

    返回 ``(清洗后正文, 是否只剩思考内容)``。第二种情况意味着预算被思考吃光、
    正文没来得及生成 —— 这必须当成失败，而不是「模型写得很短」。
    """
    clean = _THINK_RE.sub("", raw or "").strip()
    leftover = bool(_THINK_OPEN_RE.search(clean))
    if leftover:
        # 未闭合说明输出在思考中途被截断，后面的内容不可用
        clean = ""
    return clean, leftover


def _now() -> datetime:
    return datetime.now(UTC)


def _plain(title: str, content: Any) -> str:
    """条目 → 纯文本（复用起草查重的抽取逻辑，保证「字数」口径一致）。

    excerpt 用**不含标题**的版本：卡片上方已经单独显示了标题，摘要里再重复
    一遍既浪费两行高度，也让人以为是两个东西。
    """
    text = _draft_to_text("", content or {})
    if text.strip():
        return text
    return _draft_to_text(title or "", content or {})


def _excerpt(raw: str, limit: int = 320) -> str:
    text = re.sub(r"\s+", " ", raw or "").strip()
    return text[:limit] + ("…" if len(text) > limit else "")


# ------------------------------------------------------------------ 抽样


async def sample_entries(
    db: AsyncSession,
    *,
    size: int = 5,
    days: int = _DEFAULT_WINDOW_DAYS,
    content_type_id: int | None = None,
    include_reviewed: bool = False,
    site_id: int | None = None,
) -> dict[str, Any]:
    """随机抽 N 条 AI 产出，附上质检需要的全部上下文。

    `include_reviewed=False` 时排除已被评过的条目 —— 否则每次抽样都抽到
    同样那几条，质检就成了重复劳动。
    """
    size = max(1, min(int(size or 5), 20))
    since = _now() - timedelta(days=max(1, min(int(days or 90), 3650)))

    conds = [
        "e.deleted_at IS NULL",
        "e.ai_origin IS NOT NULL",
        "e.created_at >= :since",
    ]
    params: dict[str, Any] = {"since": since, "limit": size}
    if site_id:
        conds.append("e.site_id = :site_id")
        params["site_id"] = site_id
    if content_type_id:
        conds.append("e.content_type_id = :ct")
        params["ct"] = content_type_id
    if not include_reviewed:
        # 只排除「同一批模型产出」的重复评分：条目被改过之后仍值得再评
        conds.append(
            "NOT EXISTS (SELECT 1 FROM cms_ai_reviews r WHERE r.entry_id = e.id)"
        )

    sql = text(
        f"""
        SELECT e.id, e.title, e.slug, e.status, e.content, e.seo,
               e.ai_origin, e.ai_generation_id, e.created_at, e.updated_at,
               g.model AS gen_model, g.provider AS gen_provider, g.kind AS gen_kind
        FROM cms_entries e
        LEFT JOIN cms_ai_generations g ON g.id = e.ai_generation_id
        WHERE {' AND '.join(conds)}
        ORDER BY random()
        LIMIT :limit
        """
    )
    rows = (await db.execute(sql, params)).mappings().all()

    items = []
    for r in rows:
        body = _plain(r["title"], r["content"])
        seo = r["seo"] or {}
        items.append(
            {
                "entry_id": r["id"],
                "title": r["title"],
                "slug": r["slug"],
                "status": r["status"],
                "ai_origin": r["ai_origin"],
                "generation_id": r["ai_generation_id"],
                "model": r["gen_model"] or "",
                "provider": r["gen_provider"] or "",
                "kind": r["gen_kind"] or "entry_draft",
                "chars": len(body),
                "excerpt": _excerpt(body),
                "has_seo": bool(seo.get("title") and seo.get("description")),
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
            }
        )

    logger.info("cms.ai_sample size={} got={}", size, len(items))
    return {
        "items": items,
        "requested": size,
        "returned": len(items),
        "window_days": days,
        "dimensions": [{"key": k, "label": v} for k, v in DIMENSIONS],
        "verdicts": list(VERDICTS),
    }


# ------------------------------------------------------------------ 打分


def _clamp_score(value: Any) -> float | None:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num <= 0:
        return None
    return max(1.0, min(5.0, num))


async def submit_review(
    db: AsyncSession,
    *,
    entry_id: int,
    scores: dict[str, Any],
    verdict: str = "pass",
    note: str = "",
    reviewer_id: int | None = None,
    site_id: int | None = None,
) -> dict[str, Any]:
    """落一条人评。

    `overall` 缺省时用其余维度的均值兜底 —— 逼着每人都先打总分只会得到
    一堆随手填的 4 分，反而是先评维度、再由维度推总分更可信。
    """
    if verdict not in VERDICTS:
        raise ValueError(f"verdict 非法：{verdict}")

    clean: dict[str, float] = {}
    for key, _label in DIMENSIONS:
        val = _clamp_score((scores or {}).get(key))
        if val is not None:
            clean[key] = round(val, 2)

    if "overall" in clean:
        overall = clean["overall"]
    elif clean:
        overall = round(sum(clean.values()) / len(clean), 2)
        clean["overall"] = overall
    else:
        raise ValueError("至少要给一个维度的分数（1~5）")

    entry = await db.get(Entry, entry_id)
    if entry is None:
        raise ValueError(f"条目不存在：{entry_id}")

    # 模型快照：优先取生成溯源；条目没有溯源时留空而不是瞎猜
    provider = ""
    model = ""
    gen_kind = "entry_draft"
    if entry.ai_generation_id:
        row = (
            await db.execute(
                text(
                    "SELECT provider, model, kind FROM cms_ai_generations WHERE id = :g"
                ),
                {"g": entry.ai_generation_id},
            )
        ).mappings().first()
        if row:
            provider = row["provider"] or ""
            model = row["model"] or ""
            gen_kind = row["kind"] or "entry_draft"

    review = CmsAiReview(
        site_id=site_id or entry.site_id or 1,
        entry_id=entry.id,
        generation_id=entry.ai_generation_id,
        source="sample",
        kind=gen_kind,
        provider=provider,
        model=model,
        overall=overall,
        scores=clean,
        verdict=verdict,
        note=(note or "").strip()[:2000],
        reviewer_id=reviewer_id,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)

    return {
        "id": review.id,
        "entry_id": review.entry_id,
        "model": review.model,
        "overall": review.overall,
        "scores": review.scores,
        "verdict": review.verdict,
        "note": review.note,
        "created_at": review.created_at.isoformat() if review.created_at else None,
    }


# ------------------------------------------------------------------ 统计


async def stats(
    db: AsyncSession, *, weeks: int = 12, site_id: int | None = None
) -> dict[str, Any]:
    """质量曲线 + 模型对比 + 覆盖率 + A/B 胜率。

    曲线按 ISO 周聚合：按天太稀疏（一天评不到两条），按月太钝（改一版提示词
    要等一个月才知道有没有变好）。
    """
    weeks = max(1, min(int(weeks or 12), 52))
    since = _now() - timedelta(weeks=weeks)
    # 每个子查询的站点过滤必须按各自别名写死。
    # 踩过的坑：写成 scope.replace("site_id", "r.site_id") 会把
    # ":site_id" 一起替换成 ":r.site_id"，于是凭空多出一个名为 r 的绑定参数，
    # 报 "A value is required for bind parameter 'r'"。
    scope_bare = " AND site_id = :site_id" if site_id else ""
    scope_r = " AND r.site_id = :site_id" if site_id else ""
    scope_a = " AND a.site_id = :site_id" if site_id else ""
    scope_e = " AND e.site_id = :site_id" if site_id else ""
    params: dict[str, Any] = {"since": since}
    site_params: dict[str, Any] = {}
    if site_id:
        params["site_id"] = site_id
        site_params["site_id"] = site_id

    curve = [
        {
            "week": r["wk"].date().isoformat(),
            "avg": round(float(r["avg"] or 0), 2),
            "count": int(r["cnt"]),
            "low": int(r["low_cnt"] or 0),
        }
        for r in (
            await db.execute(
                text(
                    f"""
                    SELECT date_trunc('week', created_at) AS wk,
                           avg(overall) AS avg,
                           count(*) AS cnt,
                           count(*) FILTER (WHERE overall < 3) AS low_cnt
                    FROM cms_ai_reviews
                    WHERE created_at >= :since AND source = 'sample'{scope_bare}
                    GROUP BY 1 ORDER BY 1
                    """
                ),
                params,
            )
        ).mappings()
    ]

    by_model = [
        {
            "model": r["model"] or "（未记录）",
            "provider": r["provider"] or "",
            "count": int(r["cnt"]),
            "overall": round(float(r["avg"] or 0), 2),
            "accuracy": round(float(r["acc"] or 0), 2) if r["acc"] is not None else None,
            "readability": round(float(r["rd"] or 0), 2) if r["rd"] is not None else None,
            "pass_rate": round(float(r["pass_cnt"] or 0) / int(r["cnt"]) * 100, 1),
        }
        for r in (
            await db.execute(
                text(
                    f"""
                    SELECT model, provider,
                           count(*) AS cnt,
                           avg(overall) AS avg,
                           avg((scores->>'accuracy')::float) AS acc,
                           avg((scores->>'readability')::float) AS rd,
                           count(*) FILTER (WHERE verdict = 'pass') AS pass_cnt
                    FROM cms_ai_reviews
                    WHERE source = 'sample'{scope_bare}
                    GROUP BY model, provider
                    ORDER BY cnt DESC
                    """
                ),
                site_params,
            )
        ).mappings()
    ]

    verdicts = {
        r["verdict"]: int(r["cnt"])
        for r in (
            await db.execute(
                text(
                    f"""
                    SELECT verdict, count(*) AS cnt FROM cms_ai_reviews
                    WHERE source = 'sample'{scope_bare} GROUP BY 1
                    """
                ),
                site_params,
            )
        ).mappings()
    }

    # 覆盖率：AI 产出里有多少被看过。这个数字比均分更重要 ——
    # 评了 3 篇的均分 4.8 说明不了任何问题
    cov = (
        await db.execute(
            text(
                f"""
                SELECT
                  (SELECT count(*) FROM cms_entries e
                    WHERE e.deleted_at IS NULL AND e.ai_origin IS NOT NULL{scope_e}) AS total,
                  (SELECT count(DISTINCT r.entry_id) FROM cms_ai_reviews r
                    JOIN cms_entries e ON e.id = r.entry_id
                    WHERE r.source = 'sample'{scope_r}) AS reviewed
                """
            ),
            site_params,
        )
    ).mappings().first()

    ab = [
        {
            "model": r["model"],
            "wins": int(r["wins"] or 0),
            "losses": int(r["losses"] or 0),
            "ties": int(r["ties"] or 0),
        }
        for r in (
            await db.execute(
                text(
                    f"""
                    SELECT m.model,
                           count(*) FILTER (WHERE a.winner = m.side) AS wins,
                           count(*) FILTER (WHERE a.winner IS NOT NULL
                                              AND a.winner <> m.side
                                              AND a.winner <> 'tie') AS losses,
                           count(*) FILTER (WHERE a.winner = 'tie') AS ties
                    FROM cms_ai_ab_runs a
                    CROSS JOIN LATERAL (
                        VALUES ('left', a.left_model), ('right', a.right_model)
                    ) AS m(side, model)
                    WHERE a.winner IS NOT NULL{scope_a}
                    GROUP BY m.model ORDER BY wins DESC
                    """
                ),
                site_params,
            )
        ).mappings()
    ]

    return {
        "curve": curve,
        "by_model": by_model,
        "verdicts": verdicts,
        "coverage": {
            "total": int(cov["total"] or 0) if cov else 0,
            "reviewed": int(cov["reviewed"] or 0) if cov else 0,
            "percent": round(
                (int(cov["reviewed"] or 0) / int(cov["total"] or 1) * 100) if cov else 0.0, 1
            ),
        },
        "ab": ab,
        "weeks": weeks,
    }


# ------------------------------------------------------------------ A/B


async def run_ab(
    db: AsyncSession,
    *,
    topic: str,
    model_a: str,
    model_b: str,
    max_tokens: int = 3000,
    created_by: int | None = None,
    site_id: int | None = None,
) -> dict[str, Any]:
    """同一主题、同一参数，两个模型各写一版，随机左右落位。

    只暴露 left/right，**不返回模型名** —— 模型名随评分一起揭晓，
    否则「盲评」两个字就是摆设。
    """
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("topic 不能为空")
    if len(topic) > 500:
        raise ValueError("topic 过长（上限 500 字）")
    if not model_a or not model_b:
        raise ValueError("model_a / model_b 都必须指定")
    if model_a == model_b:
        raise ValueError("两个模型相同，没有对比意义")

    client = get_llm_for("chat")
    provider = ""
    try:
        from cenkor_admin.apps.cms.ai.registry import get_endpoint

        ep = get_endpoint("chat")
        provider = (ep.provider_slug if ep else "") or ""
    except Exception:
        provider = ""

    # 提示词走版本化：改一句措辞不该发版重启
    system = await prompts.get(db, "ab_run", _AB_SYSTEM)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"主题：{topic}"},
    ]

    async def _one(model: str) -> tuple[str, int, str]:
        import time as _t

        started = _t.monotonic()
        try:
            # temperature 与 max_tokens 两侧必须一致，否则比的不是模型而是参数
            res = await client.chat(
                messages, model=model, temperature=0.4, max_tokens=max_tokens
            )
            await _record(
                db,
                kind="ab_run",
                target=f"ab:{model}",
                result=res,
                params={"temperature": 0.4, "max_tokens": max_tokens},
                created_by=created_by,
                prompt=_AB_SYSTEM,
            )
            clean, truncated_in_think = _strip_think(res.text or "")
            if truncated_in_think:
                return (
                    clean,
                    res.latency_ms,
                    "输出被模型的思考过程占满（max_tokens 偏小），正文未生成",
                )
            return clean, res.latency_ms, ""
        except Exception as exc:
            await _record(
                db,
                kind="ab_run",
                target=f"ab:{model}",
                result=None,
                params={"temperature": 0.4, "max_tokens": max_tokens},
                status="error",
                error=str(exc),
                created_by=created_by,
                prompt=_AB_SYSTEM,
            )
            return "", int((_t.monotonic() - started) * 1000), str(exc)[:500]

    res_a = await _one(model_a)
    res_b = await _one(model_b)

    # 随机左右：这是盲评成立的唯一原因
    flip = random.random() < 0.5
    left_model, right_model = (model_b, model_a) if flip else (model_a, model_b)
    left = res_b if flip else res_a
    right = res_a if flip else res_b

    run = CmsAiAbRun(
        site_id=site_id or 1,
        topic=topic,
        provider=provider,
        left_model=left_model,
        right_model=right_model,
        left_text=left[0],
        right_text=right[0],
        left_ms=left[1],
        right_ms=right[1],
        left_error=left[2] or None,
        right_error=right[2] or None,
        created_by=created_by,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    return {
        "id": run.id,
        "topic": run.topic,
        "left": {
            "text": run.left_text,
            "chars": len(run.left_text),
            "ms": run.left_ms,
            "error": run.left_error,
        },
        "right": {
            "text": run.right_text,
            "chars": len(run.right_text),
            "ms": run.right_ms,
            "error": run.right_error,
        },
        # 两侧都能生成才允许评；单侧失败时这条 A/B 本身无效
        "reviewable": not run.left_error and not run.right_error,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


async def review_ab(
    db: AsyncSession,
    *,
    run_id: int,
    winner: str,
    note: str = "",
    reviewer_id: int | None = None,
) -> dict[str, Any]:
    """提交盲评结论，并把两侧模型名揭晓。"""
    if winner not in ("left", "right", "tie"):
        raise ValueError(f"winner 非法：{winner}")

    run = await db.get(CmsAiAbRun, run_id)
    if run is None:
        raise ValueError(f"A/B 记录不存在：{run_id}")
    if run.winner:
        raise ValueError("这条 A/B 已经评过了")
    # 一侧没生成出来就没什么可比的。放行等于鼓励「拿一条和空字符串比」，
    # 还顺手把胜率算进模型对比里 —— 结论会彻底失真
    if run.left_error or run.right_error:
        raise ValueError("该 A/B 有一侧生成失败，无法评价（请重跑）")

    run.winner = winner
    run.note = (note or "").strip()[:2000]
    run.reviewed_at = _now()
    await db.commit()
    await db.refresh(run)

    won_model = {"left": run.left_model, "right": run.right_model}.get(winner, "")
    return {
        "id": run.id,
        "winner": winner,
        "reveal": {
            "left": run.left_model,
            "right": run.right_model,
            "won": won_model or "平局",
        },
        "note": run.note,
    }


async def list_ab_runs(
    db: AsyncSession, *, limit: int = 20, site_id: int | None = None
) -> dict[str, Any]:
    """历史 A/B 列表（已揭晓的显示模型名，未评的保持盲态）。"""
    limit = max(1, min(int(limit or 20), 100))
    params: dict[str, Any] = {"limit": limit}
    where = ""
    if site_id:
        where = " WHERE site_id = :site_id"
        params["site_id"] = site_id

    rows = (
        await db.execute(
            text(
                f"SELECT * FROM cms_ai_ab_runs{where} ORDER BY id DESC LIMIT :limit"
            ),
            params,
        )
    ).mappings().all()

    items = []
    for r in rows:
        evaluated = bool(r["winner"])
        items.append(
            {
                "id": r["id"],
                "topic": r["topic"],
                "winner": r["winner"],
                "reviewed": evaluated,
                "note": r["note"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "left": {
                    "model": r["left_model"] if evaluated else "模型 ①",
                    "chars": len(r["left_text"] or ""),
                    "ms": r["left_ms"],
                    "error": r["left_error"],
                },
                "right": {
                    "model": r["right_model"] if evaluated else "模型 ②",
                    "chars": len(r["right_text"] or ""),
                    "ms": r["right_ms"],
                    "error": r["right_error"],
                },
            }
        )
    return {"items": items, "total": len(items)}


async def get_ab_run(db: AsyncSession, run_id: int) -> dict[str, Any]:
    """取单条 A/B（未评时不含模型名）。"""
    run = await db.get(CmsAiAbRun, run_id)
    if run is None:
        raise ValueError(f"A/B 记录不存在：{run_id}")
    evaluated = bool(run.winner)
    return {
        "id": run.id,
        "topic": run.topic,
        "winner": run.winner,
        "reviewable": not run.winner and not run.left_error and not run.right_error,
        "left": {
            "model": run.left_model if evaluated else None,
            "text": run.left_text,
            "chars": len(run.left_text),
            "ms": run.left_ms,
            "error": run.left_error,
        },
        "right": {
            "model": run.right_model if evaluated else None,
            "text": run.right_text,
            "chars": len(run.right_text),
            "ms": run.right_ms,
            "error": run.right_error,
        },
    }


# ------------------------------------------------------------------ 候选模型


_MODEL_CACHE: dict[str, Any] = {"at": 0.0, "models": []}
_MODEL_TTL = 300.0


async def list_models(db: AsyncSession, *, force: bool = False) -> dict[str, Any]:
    """列出当前对话服务商可用的模型名，供 A/B 下拉选择。

    为什么不让运营手打模型名：打错一个字符，A/B 就跑成「一个模型 vs 一个
    404」，还得翻日志才知道。服务商不支持 /models 时退回当前绑定模型，
    至少保证下拉里有东西可选。
    """
    import time as _t

    from cenkor_admin.apps.cms.ai.registry import get_endpoint

    ep = get_endpoint("chat")
    if ep is None:
        return {"models": [], "source": "none", "current": ""}

    now = _t.monotonic()
    if not force and _MODEL_CACHE["models"] and now - float(_MODEL_CACHE["at"]) < _MODEL_TTL:
        return {"models": _MODEL_CACHE["models"], "source": "cache", "current": ep.model}

    import httpx

    models: list[str] = []
    source = "fallback"
    try:
        async with httpx.AsyncClient(
            timeout=8.0,
            headers={"Authorization": f"Bearer {ep.api_key}"},
        ) as client:
            resp = await client.get(f"{ep.base_url.rstrip('/')}/models")
            if resp.status_code == 200:
                data = resp.json().get("data") or []
                models = [str(x.get("id")) for x in data if x.get("id")]
                source = "provider"
    except Exception as exc:
        logger.info("cms.ai.list_models_failed err={}", str(exc)[:120])

    if not models:
        models = [ep.model]
    # 当前模型放最前：多数 A/B 是「新模型 vs 现在用的那个」
    if ep.model in models:
        models.remove(ep.model)
    models.insert(0, ep.model)

    _MODEL_CACHE["at"] = now
    _MODEL_CACHE["models"] = models
    return {"models": models, "source": source, "current": ep.model}
