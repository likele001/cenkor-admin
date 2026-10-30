"""AI 用量与成本核算。

为什么单独一个模块：「单价怎么匹配」这层必须能单独测、单独改。
金额算错比不显示金额更糟 —— 显示 0.03 元而实际花了 3 元，比显示「未配置单价」
对运营的伤害大得多。所以这里的原则是：**匹配不到就明确说匹配不到，绝不兜底猜**。

匹配优先级（`provider` / `model` / `kind` 三维，空串=任意）：
    模型精确(4) > 服务商精确(2) > 能力类型精确(1)
打分越高越优先，同分时 id 小的先配先生效。

成本有两条路径，必须分清：
1. **快照优先** —— 记录里存了 `cost` 就直接用。运营调价不能篡改历史账单。
2. **现算兜底** —— 老记录没快照（功能上线前产生的），按当前单价补算，
   并在返回里标明有多少调用是补算的，让前端能提示「部分金额为估算」。
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta
from datetime import timezone as _tz
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

# 业务时区。趋势图按「自然日」切分，用 UTC 切会在北京时间早上 8 点断一天，
# 运营看到的「今天花了多少」会莫名其妙少一截。
BIZ_TZ = "Asia/Shanghai"

# 价格表进程内缓存：每次记账都要查单价，而单价可能几个月不变。
# 60 秒足够短 —— 运营改价后最迟一分钟生效，比每笔生成都查一次库划算。
_PRICE_TTL = 60.0
_price_cache: tuple[float, list[dict[str, Any]]] | None = None


def _dec(value: Any) -> Decimal:
    """统一转 Decimal。浮点先转 str，避免 0.1 变成 0.10000000000000001。"""
    if value is None:
        return Decimal(0)
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(0)


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
    rule: dict[str, Any],
    tokens_in: int,
    tokens_out: int,
    calls: int = 0,
    tokens_cache: int = 0,
) -> Decimal:
    """折算金额。

    - `unit="token"`：输入/缓存/输出三段分别计价
    - `unit="image"` / `unit="video"`：按张/按条计价，用调用次数乘单价

    缓存为什么要单独算：**各家的 prompt_tokens 都包含缓存命中数**，
    若整段按输入价乘，缓存省下的钱就白省了 —— 明明只花了 1/10 的价钱，
    报表上却按全价显示，运营会以为缓存没生效。反过来，没配缓存单价时
    按输入价计（`cache_per_m IS NULL`），宁可高估也不假装便宜。
    """
    if (rule.get("unit") or "token") in ("image", "video"):
        return (Decimal(int(calls or 0)) * _dec(rule["input_per_m"])).quantize(_COST_QUANT)

    tin = Decimal(max(0, int(tokens_in or 0)))
    # 缓存数不能超过输入总数（上游偶尔给不一致的数），超了按输入截断
    tcache = Decimal(min(max(0, int(tokens_cache or 0)), int(tin)))
    uncached = tin - tcache
    tout = Decimal(max(0, int(tokens_out or 0)))

    cache_price = rule.get("cache_per_m")
    cache_rate = _dec(rule["input_per_m"]) if cache_price is None else _dec(cache_price)

    cost = uncached / _MILLION * _dec(rule["input_per_m"])
    cost += tcache / _MILLION * cache_rate
    cost += tout / _MILLION * _dec(rule["output_per_m"])
    return cost.quantize(_COST_QUANT)


def compute_cache_saved(rule: dict[str, Any], tokens_cache: int) -> Decimal:
    """缓存究竟省了多少钱 = 命中部分按输入价算 − 按缓存价算。

    这不是「成本」，是「不接缓存会多花多少」，用于告诉运营缓存值不值得开。
    没配缓存单价时返回 0（因为本来就没打折，谈不上省）。
    """
    if (rule.get("unit") or "token") in ("image", "video"):
        return Decimal(0)
    cache_price = rule.get("cache_per_m")
    if cache_price is None:
        return Decimal(0)
    diff = _dec(rule["input_per_m"]) - _dec(cache_price)
    saved = Decimal(max(0, int(tokens_cache or 0))) / _MILLION * diff
    return saved.quantize(_COST_QUANT)


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
            "cache_per_m": r.cache_per_m,
            "currency": r.currency or "CNY",
            "note": r.note or "",
        }
        for r in rows
    ]


def invalidate_cache() -> None:
    """单价改动后调用，让下一笔账立刻用新价（而不是等 60 秒 TTL）。"""
    global _price_cache
    _price_cache = None


async def cached_rules(db: AsyncSession) -> list[dict[str, Any]]:
    global _price_cache
    now = time.monotonic()
    if _price_cache is not None and now - _price_cache[0] < _PRICE_TTL:
        return _price_cache[1]
    rules = await load_rules(db)
    _price_cache = (now, rules)
    return rules


async def snapshot_cost(
    db: AsyncSession,
    *,
    kind: str,
    provider: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    tokens_cache: int = 0,
    calls: int = 1,
) -> tuple[Decimal | None, str]:
    """算一笔账并返回 `(金额, 币种)`。匹配不到单价时金额为 None。

    记账时立刻算，是为了让历史账单不随调价漂移。返回 None 与返回 0 严格
    区别：None = 没配单价（不知道），0 = 配了单价且确实免费。
    """
    rules = await cached_rules(db)
    rule = resolve_rule(rules, provider=provider or "", model=model or "", kind=kind or "")
    if rule is None:
        return None, "CNY"
    return (
        compute_cost(
            rule,
            tokens_in,
            tokens_out,
            calls=calls,
            tokens_cache=tokens_cache,
        ),
        rule["currency"],
    )


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


def _f(value: Decimal | float | int | None) -> float:
    return float(_dec(value).quantize(_COST_QUANT))


def _day_col():
    """按业务时区切自然日。"""
    return func.date_trunc("day", func.timezone(BIZ_TZ, CmsAiGeneration.created_at))


async def _fetch(
    db: AsyncSession, *, days: int, offset_days: int = 0, with_day: bool = False
) -> list[Any]:
    """按 (day?) + (kind, provider, model) 聚合一个时间窗口的用量。

    分组必须细到 `(kind, provider, model)`：不同模型单价不同，
    先按 kind 聚合再算钱等于拿一个单价套所有模型，算出来的数没意义。

    成本用 FILTER 拆成两路取出：快照部分直接求和，无快照部分留给上层现算。
    这样「部分金额为估算」能精确到调用条数，而不是含糊地说「仅供参考」。
    """
    offset = max(0, int(offset_days))
    lower = func.now() - func.make_interval(0, 0, 0, offset + days)
    upper = func.now() - func.make_interval(0, 0, 0, offset)

    snap_cost = func.coalesce(
        func.sum(CmsAiGeneration.cost).filter(CmsAiGeneration.cost.is_not(None)), 0
    )
    snap_calls = func.count(CmsAiGeneration.id).filter(CmsAiGeneration.cost.is_not(None))

    cols: list[Any] = []
    group_cols: list[Any] = []
    if with_day:
        day = _day_col()
        cols.append(day.label("day"))
        group_cols.append(day)
    cols.extend(
        [
            CmsAiGeneration.kind,
            CmsAiGeneration.provider,
            CmsAiGeneration.model,
            func.count(CmsAiGeneration.id),
            func.coalesce(func.sum(CmsAiGeneration.tokens_in), 0),
            func.coalesce(func.sum(CmsAiGeneration.tokens_out), 0),
            func.coalesce(func.sum(CmsAiGeneration.tokens_cache), 0),
            func.coalesce(func.avg(CmsAiGeneration.latency_ms), 0),
            snap_cost,
            snap_calls,
        ]
    )
    group_cols.extend(
        [CmsAiGeneration.kind, CmsAiGeneration.provider, CmsAiGeneration.model]
    )

    stmt = (
        select(*cols)
        .where(
            CmsAiGeneration.created_at >= lower,
            CmsAiGeneration.created_at < upper,
            CmsAiGeneration.status == "ok",
        )
        .group_by(*group_cols)
        .order_by(func.count(CmsAiGeneration.id).desc())
    )
    return list((await db.execute(stmt)).all())


def _split(row: Any, has_day: bool) -> dict[str, Any]:
    """把 _fetch 的一行拆成字典（不含金额，金额由上层按规则算）。"""
    i = 0
    day = row[i] if has_day else None
    if has_day:
        i += 1
    return {
        "day": day,
        "kind": row[i] or "",
        "provider": row[i + 1] or "",
        "model": row[i + 2] or "",
        "calls": int(row[i + 3] or 0),
        "tokens_in": int(row[i + 4] or 0),
        "tokens_out": int(row[i + 5] or 0),
        "tokens_cache": int(row[i + 6] or 0),
        "avg_latency": float(row[i + 7] or 0),
        "snap_cost": _dec(row[i + 8]),
        "snap_calls": int(row[i + 9] or 0),
    }


def _price_row(r: dict[str, Any], rules: list[dict[str, Any]]) -> dict[str, Any]:
    """给一行用量配上金额：快照优先，剩下的按当前单价现算。"""
    rule = resolve_rule(rules, provider=r["provider"], model=r["model"], kind=r["kind"])
    live_calls = max(0, r["calls"] - r["snap_calls"])

    cost = r["snap_cost"]
    live_cost = Decimal(0)
    saved = Decimal(0)
    if rule is not None:
        # 无快照部分的 token 无法精确拆分，按「无快照调用数 / 总调用数」比例摊。
        # 同一 (kind, provider, model) 分组内单次 token 量差异通常不大，够用。
        ratio = (Decimal(live_calls) / Decimal(r["calls"])) if r["calls"] else Decimal(0)
        live_cost = compute_cost(
            rule,
            int(r["tokens_in"] * ratio),
            int(r["tokens_out"] * ratio),
            calls=live_calls,
            tokens_cache=int(r["tokens_cache"] * ratio),
        )
        saved = compute_cache_saved(rule, r["tokens_cache"])

    return {
        **r,
        "rule": rule,
        "cost": (cost + live_cost).quantize(_COST_QUANT) if rule else None,
        "priced": rule is not None,
        "live_calls": live_calls,
        "cache_saved": saved,
        "currency": (rule or {}).get("currency", "CNY"),
    }


async def usage_summary(db: AsyncSession, *, days: int = 30) -> dict[str, Any]:
    """按能力类型汇总用量、缓存命中和金额。"""
    rows = [_split(raw, False) for raw in await _fetch(db, days=days)]
    rules = await cached_rules(db)
    currencies = {r["currency"] for r in rules}

    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "calls": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "tokens_cache": 0,
            "latency_sum": 0.0,
            "cost": Decimal(0),
            "cache_saved": Decimal(0),
            "priced_calls": 0,
            "unpriced_calls": 0,
            "live_calls": 0,
            "models": [],
        }
    )

    for r in rows:
        priced = _price_row(r, rules)
        b = buckets[r["kind"] or "unknown"]
        b["calls"] += r["calls"]
        b["tokens_in"] += r["tokens_in"]
        b["tokens_out"] += r["tokens_out"]
        b["tokens_cache"] += r["tokens_cache"]
        b["latency_sum"] += r["avg_latency"] * r["calls"]
        b["live_calls"] += priced["live_calls"]
        b["cache_saved"] += priced["cache_saved"]

        if priced["priced"]:
            b["cost"] += priced["cost"] or Decimal(0)
            b["priced_calls"] += r["calls"]
        else:
            b["unpriced_calls"] += r["calls"]

        b["models"].append(
            {
                "provider": r["provider"],
                "model": r["model"],
                "calls": r["calls"],
                "tokens_in": r["tokens_in"],
                "tokens_out": r["tokens_out"],
                "tokens_cache": r["tokens_cache"],
                "cost": _f(priced["cost"]) if priced["priced"] else None,
                "priced": priced["priced"],
            }
        )

    items: list[dict[str, Any]] = []
    for kind, b in buckets.items():
        calls = b["calls"] or 1
        tin = b["tokens_in"]
        items.append(
            {
                "kind": kind,
                "calls": b["calls"],
                "tokens_in": tin,
                "tokens_out": b["tokens_out"],
                "tokens_cache": b["tokens_cache"],
                # 命中率分母是 tokens_in（缓存是它的子集），不是总额
                "cache_hit_rate": round(b["tokens_cache"] / tin, 4) if tin else 0.0,
                "avg_tokens_in": int(tin / calls),
                "avg_tokens_out": int(b["tokens_out"] / calls),
                "avg_latency_ms": int(b["latency_sum"] / calls),
                "cost": _f(b["cost"]),
                "cache_saved": _f(b["cache_saved"]),
                "priced_calls": b["priced_calls"],
                "unpriced_calls": b["unpriced_calls"],
                "live_calls": b["live_calls"],
                "priced": b["unpriced_calls"] == 0,
                "models": sorted(b["models"], key=lambda m: -m["calls"]),
            }
        )
    items.sort(key=lambda x: -(x["tokens_in"] + x["tokens_out"]))

    total_cost = sum((b["cost"] for b in buckets.values()), Decimal(0))
    priced_calls = sum(b["priced_calls"] for b in buckets.values())
    unpriced_calls = sum(b["unpriced_calls"] for b in buckets.values())
    total_in = sum(i["tokens_in"] for i in items)
    total_cache = sum(i["tokens_cache"] for i in items)
    live_calls = sum(b["live_calls"] for b in buckets.values())
    total_calls = sum(i["calls"] for i in items)

    return {
        "items": items,
        "total_calls": total_calls,
        "total_tokens": sum(i["tokens_in"] + i["tokens_out"] for i in items),
        "total_tokens_in": total_in,
        "total_tokens_out": sum(i["tokens_out"] for i in items),
        "total_tokens_cache": total_cache,
        "cache_hit_rate": round(total_cache / total_in, 4) if total_in else 0.0,
        "total_cache_saved": _f(
            sum((b["cache_saved"] for b in buckets.values()), Decimal(0))
        ),
        "total_cost": _f(total_cost),
        # 只要有调用没匹配到单价，金额就是「部分金额」，前端必须说明这点
        "priced": unpriced_calls == 0 and priced_calls > 0,
        "priced_calls": priced_calls,
        "unpriced_calls": unpriced_calls,
        # 有多少调用没走成本快照、是按当前单价补算的
        "estimated_calls": live_calls,
        "estimated": live_calls > 0 and total_calls > 0,
        "unpriced_kinds": [i["kind"] for i in items if i["unpriced_calls"] > 0],
        # 币种不一致时不做换算，直接标 mixed 让前端别显示单一符号
        "currency": currencies.pop() if len(currencies) == 1 else ("mixed" if currencies else "CNY"),
        "price_count": len(rules),
    }


def _empty_day(key: str) -> dict[str, Any]:
    return {
        "date": key,
        "calls": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "tokens_cache": 0,
        "cost": Decimal(0),
        "unpriced_calls": 0,
    }


async def usage_trend(db: AsyncSession, *, days: int = 30) -> list[dict[str, Any]]:
    """按自然日的时间序列，用来画趋势。

    没有数据的日子**补零**：折线图缺天会直接连成直线，看起来像「那天用了很多」，
    比空着更误导。
    """
    rows = [_split(raw, True) for raw in await _fetch(db, days=days, with_day=True)]
    rules = await cached_rules(db)

    by_day: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r["day"] is None:
            continue
        key = r["day"].strftime("%Y-%m-%d")
        d = by_day.setdefault(key, _empty_day(key))
        priced = _price_row(r, rules)
        d["calls"] += r["calls"]
        d["tokens_in"] += r["tokens_in"]
        d["tokens_out"] += r["tokens_out"]
        d["tokens_cache"] += r["tokens_cache"]
        if priced["priced"]:
            d["cost"] += priced["cost"] or Decimal(0)
        else:
            d["unpriced_calls"] += r["calls"]

    today = datetime.now(_tz(timedelta(hours=8))).date()
    out: list[dict[str, Any]] = []
    for i in range(days - 1, -1, -1):
        key = (today - timedelta(days=i)).isoformat()
        d = by_day.get(key) or _empty_day(key)
        tin = d["tokens_in"]
        item = {k: v for k, v in d.items() if k != "cost"}
        item["cost"] = _f(d["cost"])
        item["cache_hit_rate"] = round(d["tokens_cache"] / tin, 4) if tin else 0.0
        out.append(item)
    return out


async def usage_prev_total(db: AsyncSession, *, days: int = 30) -> dict[str, Any]:
    """上一个等长窗口的总量，用于环比。"""
    rows = [_split(raw, False) for raw in await _fetch(db, days=days, offset_days=days)]
    rules = await cached_rules(db)

    calls = tin = tout = tcache = 0
    cost = Decimal(0)
    unpriced = 0
    for r in rows:
        priced = _price_row(r, rules)
        calls += r["calls"]
        tin += r["tokens_in"]
        tout += r["tokens_out"]
        tcache += r["tokens_cache"]
        if priced["priced"]:
            cost += priced["cost"] or Decimal(0)
        else:
            unpriced += r["calls"]

    return {
        "days": days,
        "calls": calls,
        "tokens_in": tin,
        "tokens_out": tout,
        "tokens_cache": tcache,
        "cost": _f(cost),
        "cache_hit_rate": round(tcache / tin, 4) if tin else 0.0,
        "unpriced_calls": unpriced,
    }


async def recalc_costs(db: AsyncSession, *, days: int | None = None) -> dict[str, Any]:
    """用当前单价重算历史记录的 `cost` 快照。

    只在「单价一开始填错了、想按正确单价重出账单」时用。日常不调 ——
    调价不该动历史，那正是快照存在的意义。
    """
    stmt = select(CmsAiGeneration).where(CmsAiGeneration.status == "ok")
    if days:
        stmt = stmt.where(
            CmsAiGeneration.created_at
            >= func.now() - func.make_interval(0, 0, 0, int(days))
        )
    rows = (await db.execute(stmt)).scalars().all()

    invalidate_cache()
    rules = await load_rules(db)

    updated = 0
    unpriced = 0
    for row in rows:
        rule = resolve_rule(
            rules, provider=row.provider or "", model=row.model or "", kind=row.kind or ""
        )
        if rule is None:
            row.cost = None
            row.currency = "CNY"
            unpriced += 1
            continue
        row.cost = compute_cost(
            rule,
            row.tokens_in or 0,
            row.tokens_out or 0,
            calls=1,
            tokens_cache=row.tokens_cache or 0,
        )
        row.currency = rule["currency"]
        updated += 1

    await db.commit()
    return {"scanned": len(rows), "updated": updated, "unpriced": unpriced, "days": days}
