"""AI 用量与成本核算。

为什么单独一个模块：「单价怎么匹配」这层必须能单独测、单独改。
金额算错比不显示金额更糟 —— 显示 0.03 元而实际花了 3 元，比显示「未配置单价」
对运营的伤害大得多。所以这里的原则是：**匹配不到就明确说匹配不到，绝不兜底猜**。

匹配优先级（`provider` / `model` / `kind` 三维，空串=任意）：
    模型精确(4) > 服务商精确(2) > 能力类型精确(1)
打分越高越优先，同分时 id 小的先配先生效。
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.ai.models import CmsAiGeneration, CmsAiPrice

_MILLION = Decimal(1_000_000)
# 单价算到 0.000001 元（千分之一厘），够细，也不会显示成科学计数法
_COST_QUANT = Decimal("0.000001")

# kind 匹配的是**业务功能**（entry_draft / seo / embedding ...），不是
# chat/embedding 这类调用类型 —— 单价由模型决定，同一个模型做起草和做 SEO
# 单价一样。所以 kind 一般留空，只有某个功能单独议价时才填。
MAX_KIND_LEN = 32

# 计价单位。生图/生视频都没有 token（tokens_in=0），按 token 折算恒为 0 元，
# 而这两类恰恰是最贵的调用 —— 漏掉它，「预估成本」会系统性偏低。
# image=按张，video=按条；两者共用「次数 × 单价」的算法。
UNITS = ("token", "image", "video")


def _score(rule: dict[str, Any], *, provider: str, model: str, kind: str) -> int:
    """规则对某次调用的匹配度。返回 -1 表示不匹配。

    为什么不写成「逐条 if 判断」：多维度通配的组合一共 8 种，
    硬编码优先级容易漏掉某个组合（比如「只按 kind」这种）。
    打分法天然覆盖全部组合，加维度也只需加一行权重。
    """
    score = 0
    if rule["model"]:
        if rule["model"] != model:
            return -1
        score += 4
    if rule["provider"]:
        if rule["provider"] != provider:
            return -1
        score += 2
    if rule["kind"]:
        if rule["kind"] != kind:
            return -1
        score += 1
    return score


def resolve_rule(
    rules: list[dict[str, Any]], *, provider: str, model: str, kind: str
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_score = -1
    for rule in rules:
        score = _score(rule, provider=provider or "", model=model or "", kind=kind or "")
        if score < 0:
            continue
        if score > best_score:
            best, best_score = rule, score
    return best


def compute_cost(
    rule: dict[str, Any], tokens_in: int, tokens_out: int, calls: int = 0
) -> Decimal:
    """折算金额。

    - `unit="token"`：按每百万 token 计价
    - `unit="image"` / `unit="video"`：按张/按条计价，用调用次数乘单价
    """
    if (rule.get("unit") or "token") in ("image", "video"):
        return (Decimal(int(calls or 0)) * Decimal(str(rule["input_per_m"]))).quantize(_COST_QUANT)

    tin = Decimal(int(tokens_in or 0))
    tout = Decimal(int(tokens_out or 0))
    cost = tin / _MILLION * Decimal(str(rule["input_per_m"]))
    cost += tout / _MILLION * Decimal(str(rule["output_per_m"]))
    return cost.quantize(_COST_QUANT)


async def load_rules(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        (
            await db.execute(
                select(CmsAiPrice)
                .where(CmsAiPrice.enabled.is_(True))
                .order_by(CmsAiPrice.id)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": r.id,
            "provider": r.provider or "",
            "model": r.model or "",
            "kind": r.kind or "",
            "unit": r.unit or "token",
            "input_per_m": r.input_per_m,
            "output_per_m": r.output_per_m,
            "currency": r.currency or "CNY",
            "note": r.note or "",
        }
        for r in rows
    ]


async def distinct_kinds(db: AsyncSession) -> list[str]:
    """库里实际出现过的业务功能类型，供前端下拉选择。"""
    rows = (
        await db.execute(
            select(CmsAiGeneration.kind)
            .where(CmsAiGeneration.status == "ok")
            .group_by(CmsAiGeneration.kind)
            .order_by(func.count(CmsAiGeneration.id).desc())
        )
    ).all()
    return [r[0] for r in rows if r[0]]


def _f(value: Decimal) -> float:
    return float(value.quantize(_COST_QUANT))


async def usage_summary(db: AsyncSession, *, days: int = 30) -> dict[str, Any]:
    """按能力类型汇总用量，并尽量折算成金额。

    分组必须细到 `(kind, provider, model)`：不同模型单价不同，
    先按 kind 聚合再算钱等于拿一个单价套所有模型，算出来的数没意义。
    """
    rows = (
        await db.execute(
            select(
                CmsAiGeneration.kind,
                CmsAiGeneration.provider,
                CmsAiGeneration.model,
                func.count(CmsAiGeneration.id),
                func.coalesce(func.sum(CmsAiGeneration.tokens_in), 0),
                func.coalesce(func.sum(CmsAiGeneration.tokens_out), 0),
                func.coalesce(func.avg(CmsAiGeneration.latency_ms), 0),
            )
            .where(
                CmsAiGeneration.created_at >= func.now() - func.make_interval(0, 0, 0, days),
                CmsAiGeneration.status == "ok",
            )
            .group_by(
                CmsAiGeneration.kind,
                CmsAiGeneration.provider,
                CmsAiGeneration.model,
            )
        )
    ).all()

    rules = await load_rules(db)
    currencies = {r["currency"] for r in rules}

    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "calls": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "latency_sum": 0.0,
            "cost": Decimal(0),
            "priced_calls": 0,
            "unpriced_calls": 0,
            "models": [],
        }
    )

    for kind, provider, model, calls, tin, tout, avg_lat in rows:
        calls = int(calls or 0)
        tin = int(tin or 0)
        tout = int(tout or 0)
        provider = provider or ""
        model = model or ""
        b = buckets[kind or "unknown"]
        b["calls"] += calls
        b["tokens_in"] += tin
        b["tokens_out"] += tout
        b["latency_sum"] += float(avg_lat or 0) * calls

        rule = resolve_rule(rules, provider=provider, model=model, kind=kind or "")
        if rule is None:
            b["unpriced_calls"] += calls
            cost = None
        else:
            cost = compute_cost(rule, tin, tout, calls=calls)
            b["cost"] += cost
            b["priced_calls"] += calls

        b["models"].append(
            {
                "provider": provider,
                "model": model,
                "calls": calls,
                "tokens_in": tin,
                "tokens_out": tout,
                "cost": _f(cost) if cost is not None else None,
            }
        )

    items: list[dict[str, Any]] = []
    for kind, b in buckets.items():
        calls = b["calls"] or 1
        items.append(
            {
                "kind": kind,
                "calls": b["calls"],
                "tokens_in": b["tokens_in"],
                "tokens_out": b["tokens_out"],
                "avg_latency_ms": int(b["latency_sum"] / calls),
                "cost": _f(b["cost"]),
                "priced_calls": b["priced_calls"],
                "unpriced_calls": b["unpriced_calls"],
                "priced": b["unpriced_calls"] == 0,
                "models": sorted(b["models"], key=lambda m: -m["calls"]),
            }
        )
    items.sort(key=lambda x: -(x["tokens_in"] + x["tokens_out"]))

    total_cost = sum((b["cost"] for b in buckets.values()), Decimal(0))
    priced_calls = sum(b["priced_calls"] for b in buckets.values())
    unpriced_calls = sum(b["unpriced_calls"] for b in buckets.values())

    return {
        "items": items,
        "total_calls": sum(i["calls"] for i in items),
        "total_tokens": sum(i["tokens_in"] + i["tokens_out"] for i in items),
        "total_tokens_in": sum(i["tokens_in"] for i in items),
        "total_tokens_out": sum(i["tokens_out"] for i in items),
        "total_cost": _f(total_cost),
        # 只要有调用没匹配到单价，金额就是「部分金额」，前端必须说明这点
        "priced": unpriced_calls == 0 and priced_calls > 0,
        "priced_calls": priced_calls,
        "unpriced_calls": unpriced_calls,
        "unpriced_kinds": [i["kind"] for i in items if i["unpriced_calls"] > 0],
        # 币种不一致时不做换算，直接标 mixed 让前端别显示单一符号
        "currency": currencies.pop() if len(currencies) == 1 else ("mixed" if currencies else "CNY"),
        "price_count": len(rules),
    }
