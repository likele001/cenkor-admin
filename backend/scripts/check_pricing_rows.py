# Copyright (C) 2026 CenkorAdmin Project
# SPDX-License-Identifier: AGPL-3.0
"""只读哨兵：找出「已上架可售、却没有定价行」的应用。

背景：定价行的定位键是 (product, app_key)。缺行**不等于免费** —— 下单端点缺行即拒单
（commerce_router.create_order），门户也不再给缺行的应用挂购买按钮。

所以缺行分两种，只有后一种是要管的：
1. `dev_method=platform` 的内置模块（通知、公告、CMS、工单……）随平台一同交付，
   装好就有、本来不走下单 —— 没有定价行是**正确状态**，只列出来供确认。
2. 开发者提交的扩展包（`extension` / `standalone`）出现在目录里却没有定价行 ——
   等于上架了一件买不到的商品，门户显示「暂未开售」，需要去「市场 → 定价」建行。

纯 HTTP 只读，不连数据库、不写任何数据。

用法：
    python3 scripts/check_pricing_rows.py                      # 查全部四个轴
    python3 scripts/check_pricing_rows.py --base http://127.0.0.1:8002
    python3 scripts/check_pricing_rows.py --product cenkormes

退出码：0 = 无第 2 类缺行；1 = 有第 2 类缺行（逐条打印 product/app_key）；2 = 请求失败。
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

# 与底座 store_router.ALLOWED_PRODUCTS 保持一致；那边加了新产品时这里要补
PRODUCTS = ("cenkor-admin", "cenkormes", "lightmes", "cenkor-process")


def fetch_apps(base: str, product: str) -> list[dict]:
    url = f"{base}/api/v1/store/apps?product={urllib.parse.quote(product)}&page_size=100"
    with urllib.request.urlopen(url, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    items = payload.get("items")
    if items is None:
        raise ValueError(f"{url} 返回里没有 items 字段")
    total = payload.get("total")
    if isinstance(total, int) and total > len(items):
        raise ValueError(f"{product} 轴共 {total} 条，只取回 {len(items)} 条，请调大 page_size")
    return items


def main() -> int:
    ap = argparse.ArgumentParser(description="找出在架但无定价行的应用（只读）")
    ap.add_argument("--base", default="http://127.0.0.1:8002", help="hub 根地址")
    ap.add_argument("--product", action="append", choices=PRODUCTS, help="只查指定轴，可重复")
    args = ap.parse_args()

    base = args.base.rstrip("/")
    unorderable: list[tuple[str, str, str]] = []   # 上架了却买不到 —— 真正要管的
    builtin: list[tuple[str, str, str]] = []       # 内置自带，无定价行是正确状态
    for product in args.product or PRODUCTS:
        try:
            items = fetch_apps(base, product)
        except (urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
            print(f"!! 取 {product} 轴失败：{exc}", file=sys.stderr)
            return 2
        no_price = [i for i in items if not i.get("price")]
        print(f"{product:16} 在架 {len(items):3} 条，无定价行 {len(no_price)} 条")
        for i in no_price:
            row = (product, i.get("app_key", "?"), i.get("version", "?"))
            (builtin if i.get("dev_method") == "platform" else unorderable).append(row)

    if builtin:
        print("\n>>> 内置模块（随平台交付、不走下单，无需定价行）：")
        for product, app_key, version in builtin:
            print(f"    {product} / {app_key} (v{version})")
    if not unorderable:
        print("\n>>> 没有「已上架却买不到」的应用")
        return 0
    print("\n>>> 以下非内置应用已上架却没有定价行，门户不会给购买入口；要卖请在「市场 → 定价」建行：", file=sys.stderr)
    for product, app_key, version in unorderable:
        print(f"    {product} / {app_key} (v{version})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
