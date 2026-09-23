"""应用定价字段规则（原价 / 售价 / 限时促销价）。

**本模块属公开源码**，是定价字段规则的唯一真相源：
- 应用商店提交接口（`store_router.submit_app`）用它校验开发者提交的价格；
- 闭源 commerce 应用的定价写入（`apps/commerce/pricing.py`）也 import 它。

只做「规则」，不碰数据库、不认识任何表：给定一份 dict，返回规范化后的 dict；
非法组合抛 ``PriceRuleError``，其 message 可直接回给前端。

**收费模式只支持「免费 / 一次性买断 / 按席位」三种**（2026-09-23 收敛）：
- 「试用」与「按期订阅」已下线。在源码交付模式下，两者的有效性都只能依赖客户实例上的
  本地时间校验，客户改一行 ``licensing.py`` 即可无限延长 —— 收不到第二笔钱，
  却要给每个客户送一次绕过机会。与其留着做样子，不如不做。
- 「按席位」保留为独立模式：席位制按 ``period_days`` 周期授权，其余模式买断后**永久有效**。
- ``trial_days`` / ``period_days`` 字段保留仅为兼容既有数据库列，不再接受前端输入。

三个价的语义（金额单位一律「分」）：
- ``list_price_cents``  原价（划线价）—— **仅用于展示，不参与任何结算**
- ``price_cents``       售价 —— 常规成交价
- ``promo_price_cents`` 促销价 —— 限时，促销期内取代售价成交，到期自动回落到售价

成交一律取「生效价」= 促销期内 ? 促销价 : 售价，由 commerce 侧负责计算。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

# 与 apps/commerce/models.py 的 PRICING_MODELS 同源（那边 import 本模块）
PRICING_MODELS: tuple[str, ...] = ("free", "one_time", "seat")

PROMO_LABEL_MAX = 60
CURRENCIES = ("CNY",)

# 单应用定价上限 100 万元 —— 防手滑把「99 元」填成「99 万分」
MAX_PRICE_CENTS = 100_000_000
MAX_PERIOD_DAYS = 3650

# 前端 <input type="datetime-local"> 不带时区，按东八区解释（服务器与用户均在国内）
LOCAL_TZ = timezone(timedelta(hours=8))


class PriceRuleError(ValueError):
    """定价字段不合法。message 可直接展示给用户。"""


def _as_int(v: Any, field: str, *, minimum: int = 0,
            maximum: int = MAX_PRICE_CENTS) -> int:
    if v in (None, ""):
        return 0
    if isinstance(v, bool):  # bool 是 int 的子类，显式挡掉 True/False
        raise PriceRuleError(f"{field}必须是整数")
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise PriceRuleError(f"{field}必须是整数") from None
    if n < minimum:
        raise PriceRuleError(f"{field}不能小于 {minimum}")
    if n > maximum:
        raise PriceRuleError(f"{field}超出允许范围（上限 {maximum}）")
    return n


def _as_dt(v: Any, field: str) -> datetime | None:
    """解析时间。支持 ISO 8601 字符串、datetime；naive 按东八区处理，一律转 UTC 存储。"""
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        dt = v
    elif isinstance(v, str):
        s = v.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            raise PriceRuleError(
                f"{field}格式不对，请用 ISO 8601（如 2026-10-01T00:00）"
            ) from None
    else:
        raise PriceRuleError(f"{field}格式不对")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(timezone.utc)


def normalize_price_fields(body: dict) -> dict:
    """校验并规范化定价字段。返回可直接落库的 dict（时间已转 UTC）。"""
    if not isinstance(body, dict):
        raise PriceRuleError("定价数据必须是对象")

    model = str(body.get("model") or "free").strip() or "free"
    if model not in PRICING_MODELS:
        raise PriceRuleError(f"收费模式必须是 {' / '.join(PRICING_MODELS)} 之一")

    price = _as_int(body.get("price_cents"), "售价")
    list_price = _as_int(body.get("list_price_cents"), "原价")
    promo_price = _as_int(body.get("promo_price_cents"), "促销价")
    seat_price = _as_int(body.get("seat_price_cents"), "座位单价")

    label = str(body.get("promo_label") or "").strip() or None
    if label and len(label) > PROMO_LABEL_MAX:
        raise PriceRuleError(f"促销活动名最长 {PROMO_LABEL_MAX} 个字")

    start = _as_dt(body.get("promo_start_at"), "促销开始时间")
    end = _as_dt(body.get("promo_end_at"), "促销结束时间")

    if model == "free":
        # 免费应用不允许残留任何价格与促销，避免「标价 0 元却挂着促销」
        price = list_price = promo_price = seat_price = 0
        label, start, end = None, None, None
    else:
        if price <= 0:
            raise PriceRuleError("售价必须大于 0（免费应用请把收费模式选为「免费」）")
        if seat_price <= 0:
            # 座位制没填座位单价时按主价计费，避免下单金额为 0
            seat_price = price
        if promo_price:
            if promo_price >= price:
                raise PriceRuleError("促销价必须低于售价（否则不是促销）")
            if start and end and end <= start:
                raise PriceRuleError("促销结束时间必须晚于开始时间")
        else:
            # 没填促销价时清掉活动名与时间，避免残留脏数据
            label, start, end = None, None, None
        if list_price and list_price < price:
            raise PriceRuleError("原价不能低于售价（原价是划线价）")

    currency = str(body.get("currency") or "CNY").upper()
    if currency not in CURRENCIES:
        raise PriceRuleError(f"币种只支持 {' / '.join(CURRENCIES)}")

    # 授权周期只对「按席位」有意义；其余模式是买断、永久有效，不写周期
    if model == "seat":
        period_days = _as_int(body.get("period_days"), "授权周期（天）", minimum=1,
                              maximum=MAX_PERIOD_DAYS) or 365
    else:
        period_days = 365
    # 试用已下线：恒 0。不再读取前端输入，避免「填了试用却发现没用」的错觉
    trial_days = 0
    min_seats = _as_int(body.get("min_seats"), "最小坐席数", minimum=1,
                        maximum=100000) or 1
    max_seats = _as_int(body.get("max_seats"), "最大坐席数", maximum=100000)
    if max_seats and max_seats < min_seats:
        raise PriceRuleError("最大坐席数不能小于最小坐席数")

    intro = body.get("intro")
    if intro is not None:
        intro = str(intro).strip()[:500] or None

    return {
        "model": model,
        "price_cents": price,
        "list_price_cents": list_price,
        "promo_price_cents": promo_price,
        "promo_start_at": start,
        "promo_end_at": end,
        "promo_label": label,
        "seat_price_cents": seat_price,
        "currency": currency,
        "period_days": period_days,
        "trial_days": trial_days,
        "min_seats": min_seats,
        "max_seats": max_seats,
        "require_approval": bool(body.get("require_approval", False)),
        "enabled": bool(body.get("enabled", True)),
        "intro": intro,
    }
