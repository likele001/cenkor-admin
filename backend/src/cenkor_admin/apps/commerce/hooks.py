"""应用中心 · 事件订阅（hooks）。

四个订阅：
1. ``app.submitted``     —— 开发者提交应用（可随包带定价）：写入商品定价
2. ``payment.paid``      —— 支付成功：订单转 paid、开发者分账入账、签发授权
3. ``payment.refunded``  —— 支付中心退款：订单转 refunded、吊销授权、资金冲正
4. ``scheduler.tick``    —— 周期任务：把到期的销售收入从冻结池转入可提现池

设计约束：
- **零硬依赖**：不 import 支付中心的任何业务模块，只订阅它派发的事件。支付中心
  未安装时本模块不加载，应用中心仍可用「手工标记已付」通道。
- **幂等**：支付回调可能重复派发 —— 订单已 paid 直接返回，账本侧另有去重判据。
- **金额核对**：事件金额与订单金额不一致视为异常，拒绝入账并告警（防篡改）。
- **失败隔离**：钩子抛异常只写日志，不影响支付主流程；因此出错要看日志。
"""
from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import select

from cenkor_admin.core.hooks import hook

log = structlog.get_logger()

BIZ_TYPE = "app_order"


def _now() -> datetime:
    return datetime.now(UTC)


async def _load_order(db, order_no: str):
    from cenkor_admin.apps.commerce import models as cm

    return (await db.execute(
        select(cm.AppOrder).where(cm.AppOrder.order_no == order_no)
    )).scalar_one_or_none()


@hook("app.submitted", app_key="commerce", priority=50)
async def save_pricing_on_submit(
    *,
    app_key: str | None = None,
    developer_id: int | None = None,
    submission_id: int | None = None,
    product: str | None = None,
    pricing: dict | None = None,
    **kwargs,
) -> dict | None:
    """开发者提交应用时随包带的价格 → 写入 ``app_pricing``。

    - 由公开侧 ``store_router`` 派发；本应用未安装时该事件无人订阅，提交照常成功。
    - 字段已由 ``pricing_rules`` 规范化过，这里仍走 ``apply_price_fields`` 再过一遍，
      保证与定价接口走同一条写入路径（价格规则只有一处）。
    - **product 优先由派发方带上**：定价行的定位键是 ``(product, app_key)``，漏传就吃列
      默认值 ``cenkor-admin``，实例侧按自身产品轴下单时匹配不到定价行 → 算成 0 元白送。
      本钩子另开会话，带上轴就不依赖"提交行已可见"这一时序前提（派发点若在事务内改动，
      回查会拿不到刚建的提交）；没带时兜底回查提交记录。
    - **归属只在新建定价行时写入**，已存在定价行的归属与扣点一律不动
      —— 防止换个账号重传同一个 app_key 就把别人的商品认领走。
    """
    if not app_key or not isinstance(pricing, dict):
        return None

    from cenkor_admin.apps.commerce import models as cm
    from cenkor_admin.apps.commerce import pricing as pr
    from cenkor_admin.core.db import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        axis = str(product or "").strip()[:32] or await pr.resolve_product(db, app_key)
        row = (await db.execute(
            select(cm.AppPricing).where(
                cm.AppPricing.app_key == app_key,
                cm.AppPricing.product == axis,
            )
        )).scalars().first()
        is_new = row is None
        if is_new:
            row = cm.AppPricing(app_key=app_key, product=axis)
            db.add(row)

        try:
            pr.apply_price_fields(row, pricing, touch_fee=False)
        except pr.PriceRuleError as e:
            log.warning("commerce.submit_pricing_rejected", app_key=app_key, error=str(e))
            return None

        if is_new and developer_id is not None:
            row.developer_id = int(developer_id)
        elif not is_new and row.developer_id != (int(developer_id) if developer_id is not None else None):
            log.warning("commerce.submit_pricing_owner_kept", app_key=app_key,
                        owner=row.developer_id, submitter=developer_id)

        await db.commit()
        log.info("commerce.submit_pricing_saved", app_key=app_key, is_new=is_new,
                 developer_id=row.developer_id, model=row.model,
                 price_cents=row.price_cents, list_price_cents=row.list_price_cents,
                 promo_price_cents=row.promo_price_cents, submission_id=submission_id)
        return {
            "app_key": app_key,
            "model": row.model,
            "price_cents": int(row.price_cents or 0),
            "list_price_cents": int(row.list_price_cents or 0),
            "promo_price_cents": int(row.promo_price_cents or 0),
        }


@hook("payment.paid", app_key="commerce", priority=20)
async def issue_license_on_payment(
    *,
    biz_type: str | None = None,
    biz_id: str | None = None,
    out_trade_no: str | None = None,
    trade_no: str | None = None,
    amount_cents: int | None = None,
    provider: str | None = None,
    **kwargs,
) -> dict | None:
    """支付成功 → 订单转 paid → 开发者分账入账 → 签发授权。"""
    if biz_type != BIZ_TYPE or not biz_id:
        return None

    from cenkor_admin.apps.commerce import ledger
    from cenkor_admin.apps.commerce.commerce_router import _issue_license
    from cenkor_admin.core.db import AsyncSessionLocal

    order_no = str(biz_id)
    async with AsyncSessionLocal() as db:
        order = await _load_order(db, order_no)
        if order is None:
            log.warning("commerce.hook.order_missing", order_no=order_no)
            return None

        if order.status == "paid":
            return {"order_no": order_no, "skipped": "already_paid"}

        if order.status not in ("pending", "expired"):
            log.warning("commerce.hook.bad_status", order_no=order_no, status=order.status)
            return None

        if amount_cents is not None and int(amount_cents) != int(order.amount_cents):
            log.error("commerce.hook.amount_mismatch", order_no=order_no,
                      expected=order.amount_cents, got=int(amount_cents))
            return None

        order.status = "paid"
        order.paid_at = _now()
        order.channel = provider or "online"
        order.trade_no = trade_no or out_trade_no
        await db.flush()

        # 分账：开发者净收入入账（T+N 内先落冻结池）。平台自营订单无开发者流水。
        await ledger.credit_sale(db, order)
        income = int(order.developer_income_cents or 0)
        fee = int(order.platform_fee_cents or 0)
        app_key = order.app_key
        await db.commit()

        lic_key = None
        try:
            lic = await _issue_license(db, order)
            lic_key = lic.license_key
        except Exception as e:
            log.error("commerce.hook.license_failed", order_no=order_no, error=str(e))

        log.info("commerce.hook.paid", order_no=order_no, app=app_key, license=lic_key,
                 amount_cents=amount_cents, platform_fee_cents=fee,
                 developer_income_cents=income, pay_order=out_trade_no)
        return {"order_no": order_no, "license_key": lic_key,
                "platform_fee_cents": fee, "developer_income_cents": income}


@hook("payment.refunded", app_key="commerce", priority=20)
async def refund_on_payment(
    *,
    biz_type: str | None = None,
    biz_id: str | None = None,
    out_trade_no: str | None = None,
    amount_cents: int | None = None,
    **kwargs,
) -> dict | None:
    """支付中心退款 → 订单转 refunded、吊销授权、开发者资金冲正。"""
    if biz_type != BIZ_TYPE or not biz_id:
        return None

    from cenkor_admin.apps.commerce import ledger
    from cenkor_admin.apps.commerce import models as cm
    from cenkor_admin.apps.commerce.commerce_router import _resign
    from cenkor_admin.core.db import AsyncSessionLocal

    order_no = str(biz_id)
    async with AsyncSessionLocal() as db:
        order = await _load_order(db, order_no)
        if order is None:
            log.warning("commerce.hook.refund_order_missing", order_no=order_no)
            return None

        already = order.status == "refunded"
        if not already:
            order.status = "refunded"
            order.refunded_at = _now()
            order.remark = ((order.remark or "") + " | 支付中心退款").strip(" |")

            lics = (await db.execute(
                select(cm.AppLicense).where(cm.AppLicense.order_id == order.id)
            )).scalars().all()
            for lic in lics:
                if lic.status != "revoked":
                    lic.status = "revoked"
                    lic.revoked_at = _now()
                    lic.revoke_reason = "支付中心退款"
                    await _resign(db, lic)

        # 资金冲正（ledger 侧按 订单号+类型 去重，重复回调安全）
        await ledger.debit_refund(db, order)
        await db.commit()

        log.info("commerce.hook.refunded", order_no=order_no, amount_cents=amount_cents,
                 pay_order=out_trade_no, already=already)
        return {"order_no": order_no, "refunded": True, "already": already}


@hook("scheduler.tick", app_key="commerce", priority=50)
async def settle_on_tick(**kwargs) -> dict | None:
    """周期任务：结算解冻（pending → available），每 tick 最多 500 条。"""
    from cenkor_admin.apps.commerce import ledger
    from cenkor_admin.core.db import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            settled = await ledger.settle_due(db)
            await db.commit()
        except Exception as e:
            await db.rollback()
            log.warning("commerce.settle_tick_failed", error=str(e))
            return None

    if settled:
        log.info("commerce.settle_tick", settled=settled)
    return {"settled": settled}


# ============================================================
# 价格视图桥接注册（跨源码边界）
# ============================================================
# 公开侧的商店接口（store_router）不直接 import 本模块，因此由本侧**主动**把实现
# 注册进公开侧的注册点（cenkor_admin.apps.system.pricing_bridge）。
#
# 生命周期：main.py 每次进程启动都会 `from cenkor_admin.apps.commerce import hooks`
# （见 main.py「注册内置钩子处理器」段），与 @hook 处理器同一时机恢复注册 ——
# 重启后商店接口即可正常展示价格，无需额外初始化。
def _register_pricing_bridge() -> None:
    from cenkor_admin.apps.commerce import pricing
    from cenkor_admin.apps.system import pricing_bridge

    pricing_bridge.register_price_map_provider(pricing.public_price_map)


_register_pricing_bridge()
