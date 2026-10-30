#!/usr/bin/env python3
"""批量设置 / 更新 app_pricing（默认 dry-run）。

为什么要有这个脚本
------------------
hub 的定价写入原本只有后台「市场 → 定价」页面（要管理员登录态）和开发者提交时
随包带价两条入口，命令行没有可复用工具。给一批已发布但没定价的扩展补价时，
直接手写 SQL 很容易落错产品轴（`product` 默认值 `cenkor-admin`）——定价行挂在错轴，
实例按 `cenkormes` 拉价匹配不到，`model` 退成 free、下单金额算 0，等于白送授权。

本脚本复用 `pricing.apply_price_fields()`（与后台页面、开发者提交同一个校验器），
默认只打印计划；`--apply` 才写库。幂等：同价重复执行只打印 unchanged。

用法
----
    PY=/www/server/pyporject_evn/cenkor/bin/python
    $PY scripts/set_app_pricing.py --keys crm_suite erp_finance --product cenkormes
    $PY scripts/set_app_pricing.py --keys crm_suite erp_finance --product cenkormes --apply

价格覆盖（元）：
    $PY scripts/set_app_pricing.py --keys crm_suite --price crm_suite=999,499
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

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

from cenkor_admin.apps.commerce import models as cm
from cenkor_admin.apps.commerce import pricing
from sqlalchemy import select

from cenkor_admin.apps.system import store_models
from cenkor_admin.core.db import AsyncSessionLocal

# 与既有在售应用同一套档位（元）：
#   99/299 标准分析 / 单点功能；199/499 平台级能力；499/999 大型模块；
#   999/1999 旗舰套件；9.9/99 轻量工具。
DEFAULT_PRICES: dict[str, tuple[int, int]] = {
    # key: (售价元, 原价元)
    "crm_suite": (999, 1999),
    "erp_finance": (999, 1999),
    "digital_twin": (499, 999),
    "pricing_ai": (199, 499),
    "approval_center": (199, 499),
    "abac": (199, 499),
    "wechat_mp_push": (199, 499),
    "finance_reconciliation": (99, 299),
    "stock_safety": (99, 299),
    "equipment_inspection": (99, 299),
    "stock_check": (99, 299),
    "hourly_salary": (99, 299),
    "purchase_plus": (99, 299),
    "temp_report": (99, 199),
    "hook_monitor": (9.9, 99),
}


def mask(url: str) -> str:
    return re.sub(r"://[^@/]*@", "://***@", url)


def yuan(v: int) -> str:
    return f"{v / 100:.2f}"


async def main_async(args) -> int:
    from cenkor_admin.core.config import get_settings
    print(f"连接：{mask(get_settings().DATABASE_URL)}")

    overrides: dict[str, tuple[int, int]] = {}
    for raw in args.price or []:
        try:
            key, pair = raw.split("=", 1)
            price, list_price = (int(x.strip()) for x in pair.split(",", 1))
        except Exception:
            print(f"--price 格式错误：{raw!r}（应为 key=售价元,原价元）")
            return 2
        overrides[key.strip()] = (price, list_price)

    plan = {k: overrides.get(k, DEFAULT_PRICES[k]) for k in args.keys}
    missing = [k for k in args.keys if k not in DEFAULT_PRICES and k not in overrides]
    if missing:
        print(f"没有默认价，请用 --price 指定：{', '.join(missing)}")
        return 2

    async with AsyncSessionLocal() as db:
        for key, (price_yuan, list_yuan) in plan.items():
            sub = (await db.execute(
                select(store_models.AppSubmission)
                .where(store_models.AppSubmission.product == args.product)
                .where(store_models.AppSubmission.app_key == key)
                .where(store_models.AppSubmission.status == "approved")
                .order_by(store_models.AppSubmission.id.desc()).limit(1)
            )).scalars().first()
            if not sub:
                print(f"SKIP {key}: {args.product} 轴上没有 approved 记录（先发布再定价）")
                continue

            row = (await db.execute(
                select(cm.AppPricing).where(
                    cm.AppPricing.product == args.product,
                    cm.AppPricing.app_key == key,
                )
            )).scalars().first()

            body = {
                "model": "one_time",
                "price_cents": round(price_yuan * 100),
                "list_price_cents": round(list_yuan * 100),
                "seat_price_cents": round(price_yuan * 100),
                "promo_price_cents": 0,
                "currency": "CNY",
                "enabled": True,
                "require_approval": False,
                "intro": None,
            }
            old = (f"{yuan(row.price_cents)}/{yuan(row.list_price_cents)} {row.model}"
                   if row else "无定价行")
            if not args.apply:
                print(f"PLANNED {key:24} {old} → {yuan(body['price_cents'])}"
                      f"/{yuan(body['list_price_cents'])} one_time"
                      f"（product={args.product}, developer_id={sub.developer_id}）")
                continue

            if row is None:
                row = cm.AppPricing(
                    product=args.product, app_key=key, developer_id=sub.developer_id)
                db.add(row)
            pricing.apply_price_fields(row, body)
            print(f"DONE    {key:24} {old} → {yuan(row.price_cents)}"
                  f"/{yuan(row.list_price_cents)} one_time")
        if args.apply:
            await db.commit()
        else:
            print("\n（以上只是计划，加 --apply 才写库）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="批量设置 app_pricing（默认 dry-run）")
    ap.add_argument("--keys", nargs="+", required=True, metavar="APP_KEY")
    ap.add_argument("--product", default="cenkormes")
    ap.add_argument("--price", action="append", metavar="KEY=售价元,原价元",
                    help="覆盖默认价，可重复")
    ap.add_argument("--apply", action="store_true", help="真正写库")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
