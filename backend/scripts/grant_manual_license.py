#!/usr/bin/env python3
"""manual 通道发卡：记一笔已付订单 + 签发授权（线下/赠送/补偿）。

为什么要有这个脚本
------------------
hub 本来就有正规接口 `POST /api/v1/store/licenses`（`issue_license_manual`），但它要
管理员登录态，命令行里拿不到 token。而**只建授权不建订单**会留下坏账：凭空多出一张卡，
订单表、分账流水、开发者中心的销量全都对不上，月底对账时说不清。
所以这里保持和线上一致的两步：

1. 按 `app_pricing` 的**生效价**建一条 `channel=manual, status=paid` 的订单（含分账快照）；
2. 调 hub 自己的 `_issue_license()` 发卡 —— 授权 token 由授权中心私钥签
   （`license_authority.get_or_create_keypair`，密钥在库里），跟扫码支付发出的卡
   是同一条代码路径，不是手搓的假卡。

安全设计
--------
- **默认 dry-run**，加 `--apply` 才写库。
- **幂等**：同一 (buyer, product, app_key) 已有未吊销授权就跳过，不重复发卡。
- **不接受自定价格**：金额一律现算 `pricing.unit_price_cents()`，防止手滑把 0.99 记成 99。
- 买家默认从 `cloud_instances` 里按产品轴自动定位（实例归属哪个门户账号，
  授权就该发给谁），可用 `--buyer-id` 覆盖。

用法
----
    PY=/www/server/pyporject_evn/cenkor/bin/python
    $PY scripts/grant_manual_license.py --keys ai_insight --product cenkormes          # 干跑
    $PY scripts/grant_manual_license.py --keys a b c --product cenkormes --apply       # 真发
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# 先定数据库再 import 应用模块：settings 是进程级单例，晚改环境变量没用。
ENV_FILES = [Path("/www/wwwroot/cenkor-admin/backend/.env"), Path("/www/wwwroot/cenkor-admin/.env")]
if not os.getenv("DATABASE_URL"):
    for f in ENV_FILES:
        if f.is_file():
            for line in f.read_text(encoding="utf8", errors="ignore").splitlines():
                if line.strip().startswith("DATABASE_URL="):
                    os.environ["DATABASE_URL"] = line.strip().split("=", 1)[1]
                    break
        if os.getenv("DATABASE_URL"):
            break

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from cenkor_admin.apps.commerce import (
    ledger,
    pricing,
)
from cenkor_admin.apps.commerce import models as cm
from cenkor_admin.apps.commerce.commerce_router import _issue_license
from sqlalchemy import select

from cenkor_admin.apps.system import store_models
from cenkor_admin.core.db import AsyncSessionLocal


def mask(url: str) -> str:
    return re.sub(r"://[^@/]*@", "://***@", url)


def _now() -> datetime:
    return datetime.now(UTC)


async def resolve_buyer(db, product: str, hint: int | None) -> tuple[int, str | None, str]:
    """定位买家：显式 --buyer-id 优先，否则取该产品轴上最近活跃实例的归属门户账号。"""
    from cenkor_admin.apps.portal import models as pm
    if hint:
        buyer = (await db.execute(
            select(pm.PortalUser).where(pm.PortalUser.id == int(hint))
        )).scalars().first()
        if not buyer:
            return 0, None, ""
        return int(buyer.id), getattr(buyer, "email", None), f"显式指定 --buyer-id={hint}"
    inst = (await db.execute(
        select(cm.CloudInstance)
        .where(cm.CloudInstance.product == product)
        .where(cm.CloudInstance.revoked_at.is_(None))
        .order_by(cm.CloudInstance.last_seen_at.desc().nullslast())
        .limit(1)
    )).scalars().first()
    if not inst:
        return 0, None, ""
    buyer = (await db.execute(
        select(pm.PortalUser).where(pm.PortalUser.id == inst.portal_user_id)
    )).scalars().first()
    email = getattr(buyer, "email", None) if buyer else None
    return int(inst.portal_user_id), email, (
        f"实例 {inst.instance_uid}（{inst.instance_url}）的归属账号")


async def existing_licensing(db, product: str, buyer_id: int, app_key: str):
    """该买家在该产品轴上是否已持有这个应用的未吊销授权。"""
    return (await db.execute(
        select(cm.AppLicense).where(
            cm.AppLicense.product == product,
            cm.AppLicense.app_key == app_key,
            cm.AppLicense.buyer_id == buyer_id,
            cm.AppLicense.status != "revoked",
        ).order_by(cm.AppLicense.id.desc()).limit(1)
    )).scalars().first()


async def grant_one(db, product: str, buyer_id: int, buyer_email: str | None,
                    app_key: str, remark: str, apply: bool) -> str:
    sub = (await db.execute(
        select(store_models.AppSubmission)
        .where(store_models.AppSubmission.product == product)
        .where(store_models.AppSubmission.app_key == app_key)
        .where(store_models.AppSubmission.status == "approved")
        .order_by(store_models.AppSubmission.id.desc()).limit(1)
    )).scalars().first()
    if not sub:
        return f"SKIP {app_key}: {product} 轴上没有 approved 记录（先发布再发卡）"

    price_row = (await db.execute(
        select(cm.AppPricing).where(
            cm.AppPricing.product == product, cm.AppPricing.app_key == app_key)
    )).scalars().first()
    if not price_row or not price_row.enabled:
        return f"SKIP {app_key}: 没有可用定价行（app_pricing 缺失或已停用）"

    model = price_row.model
    unit = pricing.unit_price_cents(price_row, model)
    list_unit = pricing.list_unit_price_cents(price_row, model)
    amount = unit

    old = await existing_licensing(db, product, buyer_id, app_key)
    if old:
        return (f"OK   {app_key}: 买家 {buyer_id} 已持有授权 {old.license_key}"
                f"（状态 {old.status}），跳过不重复发卡")

    dev_id = price_row.developer_id
    fee_bp = await ledger.resolve_fee_bp(db, price_row, dev_id)
    fee_cents, income_cents = ledger.split_amount(amount, fee_bp)

    head = (f"     {app_key} 「{sub.name}」 买家={buyer_id} 轴={product} 模式={model} "
            f"金额={amount}分（生效价，划线 {list_unit} 分）扣点={fee_bp}bp")
    if not apply:
        return f"PLANNED {head}"

    order = cm.AppOrder(
        order_no=cm.generate_order_no(), product=product, app_key=app_key,
        app_name=sub.name, buyer_id=buyer_id, buyer_type="portal",
        buyer_email=buyer_email, buyer_name=buyer_email,
        model=model, seats=1, unit_price_cents=unit, list_unit_price_cents=list_unit,
        promo_label=None, amount_cents=amount, currency=price_row.currency,
        developer_id=dev_id, platform_fee_bp=fee_bp, platform_fee_cents=fee_cents,
        developer_income_cents=income_cents,
        status="paid", channel="manual", paid_at=_now(),
        expires_at=_now() + timedelta(hours=72), remark=remark,
    )
    db.add(order)
    await db.commit()
    lic = await _issue_license(db, order)   # hub 自己的发卡路径（含私钥签 token）
    return (f"DONE {app_key}: 订单 {order.order_no}（{amount}分 manual/paid）→ "
            f"授权 {lic.license_key} 状态={lic.status} 令牌={'已签' if lic.token else '未签!'}")


async def main_async(args) -> int:
    from cenkor_admin.core.config import get_settings
    print(f"连接：{mask(get_settings().DATABASE_URL)}")
    results: list[str] = []
    async with AsyncSessionLocal() as db:
        buyer_id, email, how = await resolve_buyer(db, args.product, args.buyer_id)
        if not buyer_id:
            print(f"定位不到买家：{args.product} 轴下没有未吊销的实例，请显式传 --buyer-id")
            return 2
        print(f"买家：id={buyer_id} email={email}（{how}）")
        remark = args.remark or (
            f"scripts/grant_manual_license.py 于 {_now():%Y-%m-%d %H:%M} 线下发卡")
        print(f"备注：{remark}\n")
        for key in args.keys:
            results.append(await grant_one(db, args.product, buyer_id, email,
                                           key, remark, args.apply))
        print("\n".join(results))
        done = sum(1 for r in results if r.startswith("DONE"))
        planned = sum(1 for r in results if r.startswith("PLANNED"))
        skipped = sum(1 for r in results if r.startswith("OK") or r.startswith("SKIP"))
        print(f"\n汇总：发卡 {done}，待发卡 {planned}，跳过 {skipped}"
              + ("" if args.apply else "\n（以上只是计划，加 --apply 才写库）"))
        if args.apply and done:
            print("\n下一步：实例侧市场页点「刷新授权」（或等门控线程自动 sync）→ "
                  "已购列表出现该应用 → 安装。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="manual 通道记已付订单并签发授权（默认 dry-run）")
    ap.add_argument("--keys", nargs="+", required=True, metavar="APP_KEY")
    ap.add_argument("--product", default="cenkormes")
    ap.add_argument("--buyer-id", type=int, default=None,
                    help="门户账号 id；不填则按产品轴上的实例自动定位归属账号")
    ap.add_argument("--remark", default=None)
    ap.add_argument("--apply", action="store_true", help="真正写库发卡")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
