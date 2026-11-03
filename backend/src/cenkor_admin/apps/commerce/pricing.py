"""应用定价 · 生效价判定与统一序列化。

三个价的语义见 `cenkor_admin.apps.system.pricing_rules`（公开模块，字段规则的唯一真相源）。
本模块负责「认识数据库行」的那一半：

- ``apply_price_fields()`` —— 校验并写入价格列（供所有定价写入点复用，避免规则漂移）
- ``promo_state()`` / ``promo_active()`` —— 促销状态机
- ``unit_price_cents()`` —— **当前生效成交单价**，下单金额必须走它
- ``price_view()`` —— 对外视图，含划线价、促销状态与折扣率

金额一律「分」。座位制按比例套用促销：``seat_price_cents`` 对应「售价」档，
原价与促销价按同一比例换算，因此折扣率对主价与座位价是一致的。
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, select

from cenkor_admin.apps.commerce import models as cm
from cenkor_admin.apps.system import pricing_rules, store_models

PriceRuleError = pricing_rules.PriceRuleError

_PROMO_NONE = "none"
_PROMO_SCHEDULED = "scheduled"
_PROMO_ACTIVE = "active"
_PROMO_EXPIRED = "expired"


async def resolve_product(db: Any, app_key: str, body_product: Any = None) -> str:
    """解析应用的权威 product：以提交记录（``app_submissions``）为准。

    定价行的定位键是 ``(product, app_key)``（见 ``AppPricing.__table_args__``），
    所以**任何定价读写都必须先确定 product**，否则就会落到列默认值 ``cenkor-admin``：
    实例按自身 product 拉定价/下单时匹配不到行 → ``model`` 退成 ``free``、金额算成 0
    → 0 元订单走「即时完成」分支，直接白送一张授权。而商店列表侧只按 app_key 查价格
    （``public_price_map``），于是表现为「看得到价、买不到价」。

    ``approved`` 记录优先（那是实例目录里真正看得见的轴），没有已通过记录时退而取
    最近一条任意状态的提交 —— 开发者在审核通过前定价是常规操作，只认 approved 会把
    这批应用重新推回错轴。
    """
    fallback = str(body_product or "").strip()[:32]
    product = (await db.execute(
        select(store_models.AppSubmission.product)
        .where(store_models.AppSubmission.app_key == app_key)
        .order_by(
            case((store_models.AppSubmission.status == "approved", 0), else_=1),
            store_models.AppSubmission.id.desc(),
        )
        .limit(1)
    )).scalar_one_or_none()
    return product or fallback or "cenkor-admin"


def now_utc() -> datetime:
    return datetime.now(UTC)


def _dt(v: Any) -> datetime | None:
    """DB 取出的时间统一成 aware-UTC（PG timestamptz 正常已是 aware，这里做兜底）。"""
    if v is None:
        return None
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(v, datetime) and v.tzinfo is None:
        return v.replace(tzinfo=UTC)
    return v


def _iso(v: Any) -> str | None:
    d = _dt(v)
    return d.isoformat() if d else None


def _yuan(cents: Any) -> str:
    try:
        return f"{int(cents or 0) / 100:.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _prop(base: int, num: int, den: int) -> int:
    """按比例换算（座位价套用主价的原价/促销比例），至少 1 分。"""
    if base <= 0 or num <= 0 or den <= 0:
        return 0
    return max(1, round(base * num / den))


# ------------------------------------------------------------
# 促销状态机
# ------------------------------------------------------------

def promo_state(p: cm.AppPricing | None, now: datetime | None = None) -> str:
    """返回 none / scheduled / active / expired。

    促销成立的前提：有促销价、且促销价低于售价。时间窗缺省视为「不限制」那一侧。
    """
    if p is None or str(getattr(p, "model", "free")) == "free":
        return _PROMO_NONE
    promo = int(getattr(p, "promo_price_cents", 0) or 0)
    price = int(getattr(p, "price_cents", 0) or 0)
    if promo <= 0 or price <= 0 or promo >= price:
        return _PROMO_NONE

    now = now or now_utc()
    start = _dt(getattr(p, "promo_start_at", None))
    end = _dt(getattr(p, "promo_end_at", None))
    if start and now < start:
        return _PROMO_SCHEDULED
    if end and now >= end:
        return _PROMO_EXPIRED
    return _PROMO_ACTIVE


def promo_active(p: cm.AppPricing | None, now: datetime | None = None) -> bool:
    return promo_state(p, now) == _PROMO_ACTIVE


# ------------------------------------------------------------
# 生效价
# ------------------------------------------------------------

def unit_price_cents(p: cm.AppPricing | None, model: str | None = None) -> int:
    """**当前生效成交单价（分）** —— 下单金额必须用这个，不要直接读 price_cents。

    - 免费 / 无定价行 → 0
    - 座位制 → seat_price_cents（促销期内按同比例换算）
    - 其余 → 促销期内取 promo_price_cents，否则 price_cents
    """
    if p is None:
        return 0
    m = str(model or getattr(p, "model", "free") or "free")
    if m == "free":
        return 0

    price = int(getattr(p, "price_cents", 0) or 0)
    seat = int(getattr(p, "seat_price_cents", 0) or 0)
    promo = int(getattr(p, "promo_price_cents", 0) or 0)

    if m == "seat":
        base = seat or price  # 座位单价缺失时按主价计费，避免下单金额为 0
        if promo_active(p) and price > 0:
            return _prop(base, promo, price)
        return max(base, 0)

    return promo if promo_active(p) else max(price, 0)


def list_unit_price_cents(p: cm.AppPricing | None, model: str | None = None) -> int:
    """展示用「原价」单价：座位制按同比例换算。无原价时返回 0。"""
    if p is None:
        return 0
    m = str(model or getattr(p, "model", "free") or "free")
    price = int(getattr(p, "price_cents", 0) or 0)
    seat = int(getattr(p, "seat_price_cents", 0) or 0)
    lp = int(getattr(p, "list_price_cents", 0) or 0)
    if lp <= 0 or price <= 0:
        return 0
    if m == "seat":
        return _prop(seat or price, lp, price)
    return lp


# ------------------------------------------------------------
# 写入
# ------------------------------------------------------------

def apply_price_fields(row: cm.AppPricing, body: dict, *,
                       touch_fee: bool = False) -> cm.AppPricing:
    """校验并写入价格字段。非法组合抛 ``PriceRuleError``（调用方转 400）。

    ``touch_fee=True`` 时才允许改 ``platform_fee_bp``（仅平台侧）；
    开发者侧传 ``touch_fee=False``，扣点字段被静默忽略。
    """
    f = pricing_rules.normalize_price_fields(body)
    row.model = f["model"]
    row.price_cents = f["price_cents"]
    row.list_price_cents = f["list_price_cents"]
    row.promo_price_cents = f["promo_price_cents"]
    row.promo_start_at = f["promo_start_at"]
    row.promo_end_at = f["promo_end_at"]
    row.promo_label = f["promo_label"]
    row.seat_price_cents = f["seat_price_cents"]
    row.currency = f["currency"]
    row.period_days = f["period_days"]
    row.trial_days = 0  # 试用已下线，恒 0（normalize_price_fields 也不再接受该输入）
    row.min_seats = f["min_seats"]
    row.max_seats = f["max_seats"]
    row.require_approval = f["require_approval"]
    row.enabled = f["enabled"]
    row.intro = f["intro"]

    if touch_fee and "platform_fee_bp" in body:
        raw = body.get("platform_fee_bp")
        if raw in (None, ""):
            row.platform_fee_bp = None
        else:
            try:
                row.platform_fee_bp = max(0, min(10000, int(raw)))
            except (TypeError, ValueError):
                raise PriceRuleError("扣点必须是 0 ~ 10000 的整数（万分比）") from None
    return row


# ------------------------------------------------------------
# 序列化
# ------------------------------------------------------------

def discount_percent(list_cents: int, unit_cents: int) -> float | None:
    """折扣百分比（相对原价）：50.0 表示「5 折」。无划线或没便宜 → None。"""
    if list_cents <= 0 or unit_cents <= 0 or unit_cents >= list_cents:
        return None
    return round(unit_cents / list_cents * 100, 1)


def discount_label(percent: float | None) -> str | None:
    """折扣标签，如「4.9折」。

    向下取一位小数，**不虚报折扣**：49.7% 显示 4.9 折而不是四舍五入成 5 折
    —— 划线价在国内有合规要求，宁可少说不可多说。
    """
    if percent is None:
        return None
    zhe = math.floor(percent / 10 * 10 + 1e-9) / 10  # 向下取到 1 位小数，容一点浮点误差
    if zhe >= 10:
        return None
    text = f"{zhe:.1f}".rstrip("0").rstrip(".")
    return f"{text}折"


def price_view(p: cm.AppPricing | None, app_key: str | None = None,
               now: datetime | None = None) -> dict[str, Any]:
    """定价的对外视图（落库字段 + 展示字段 + 生效价 + 促销状态）。"""
    if p is None:
        return {
            "app_key": app_key, "model": "free", "currency": "CNY",
            "period_days": 365, "trial_days": 0, "min_seats": 1, "max_seats": 0,
            "require_approval": False, "enabled": True, "intro": None,
            "list_price_cents": 0, "price_cents": 0, "promo_price_cents": 0,
            "list_price": "0.00", "price": "0.00", "promo_price": "0.00",
            "seat_price_cents": 0, "seat_price": "0.00",
            "seat_list_price_cents": 0, "seat_list_price": "0.00",
            "unit_price_cents": 0, "unit_price": "0.00",
            "promo_state": "none", "promo_active": False, "promo_label": None,
            "promo_start_at": None, "promo_end_at": None,
            "is_discounted": False, "discount_percent": None, "discount_label": None,
            "updated_at": None,
        }

    model = str(p.model or "free")
    list_cents = int(p.list_price_cents or 0)
    price_cents = int(p.price_cents or 0)
    promo_cents = int(p.promo_price_cents or 0)
    seat_cents = int(p.seat_price_cents or 0)

    unit = unit_price_cents(p, model)
    list_unit = list_unit_price_cents(p, model)
    percent = discount_percent(list_unit, unit)

    state = promo_state(p, now)
    return {
        "app_key": p.app_key, "model": model, "currency": p.currency,
        "period_days": p.period_days, "trial_days": p.trial_days,
        "min_seats": p.min_seats, "max_seats": p.max_seats,
        "require_approval": bool(p.require_approval), "enabled": bool(p.enabled),
        "intro": p.intro,
        # 三个价（分）
        "list_price_cents": list_cents, "price_cents": price_cents,
        "promo_price_cents": promo_cents, "seat_price_cents": seat_cents,
        # 元字符串（主价）
        "list_price": _yuan(list_cents), "price": _yuan(price_cents),
        "promo_price": _yuan(promo_cents), "seat_price": _yuan(seat_cents),
        # 座位制的原价（按比例换算，仅供划线展示）
        "seat_list_price_cents": _prop(seat_cents, list_cents, price_cents),
        "seat_list_price": _yuan(_prop(seat_cents, list_cents, price_cents)),
        # 生效价（下单金额口径）
        "unit_price_cents": unit, "unit_price": _yuan(unit),
        # 促销
        "promo_state": state, "promo_active": state == _PROMO_ACTIVE,
        "promo_label": p.promo_label,
        "promo_start_at": _iso(p.promo_start_at), "promo_end_at": _iso(p.promo_end_at),
        # 折扣展示
        "is_discounted": percent is not None,
        "discount_percent": percent, "discount_label": discount_label(percent),
        "updated_at": _iso(p.updated_at),
    }


# ============================================================
# 买家可见视图（供公开商店接口使用）
# ============================================================

# 白名单：商店接口**匿名可访问**，绝不能带出开发者归属、平台扣点、分账金额。
# 字段语义见 price_view()；这里是「对外可公开」的最小集。
PUBLIC_PRICE_FIELDS: tuple[str, ...] = (
    "app_key", "model", "currency", "enabled", "intro",
    "list_price_cents", "price_cents", "promo_price_cents", "seat_price_cents",
    "list_price", "price", "promo_price", "seat_price",
    "seat_list_price_cents", "seat_list_price",
    "unit_price_cents", "unit_price",
    "promo_state", "promo_active", "promo_label",
    "promo_start_at", "promo_end_at",
    "is_discounted", "discount_percent", "discount_label",
    "period_days", "min_seats", "max_seats",
)


def public_price_view(p: cm.AppPricing | None, app_key: str) -> dict[str, Any]:
    """买家可见的价格视图（按 PUBLIC_PRICE_FIELDS 白名单裁剪）。

    Args:
        p: 定价行；None 表示未定价（视为免费）。
        app_key: 应用标识。

    Returns:
        仅含买家可见字段的 dict。
    """
    full = price_view(p, app_key)
    return {k: full.get(k) for k in PUBLIC_PRICE_FIELDS}


async def public_price_map(db: Any, app_keys: Sequence[str]) -> dict[str, dict[str, Any]]:
    """批量取买家可见价格视图（供公开商店列表「一次查询」使用）。

    Args:
        db: 数据库会话。
        app_keys: 应用标识序列。

    Returns:
        {app_key: 价格视图}；**未建定价行的应用不出现在结果里**。
    """
    keys = [str(k) for k in app_keys if k]
    if not keys:
        return {}
    rows = (await db.execute(
        select(cm.AppPricing).where(cm.AppPricing.app_key.in_(keys))
    )).scalars().all()
    return {r.app_key: public_price_view(r, r.app_key) for r in rows}
