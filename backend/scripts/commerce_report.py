#!/usr/bin/env python3
"""成交周报（只读）：一条命令看清可插拔市场到底有没有在卖东西。

背景：2026-10-12 做价值判断时，「有没有人掏钱」这件事只能靠翻 nginx 日志和临时
SQL 拼出来，而且我一开始把 500 归到了错误的端点上（真实 500 在
``POST /store/orders/{no}/checkout``，不在 ``POST /store/orders``），也把
``checkout`` 误判成 0 命中。这类口径错误会直接把战略判断带偏，所以把它固化成脚本。

只读保证：连接建立后立刻 ``set_session(readonly=True, autocommit=True)``；
所有 SQL 都是 select/count/group by；不打印任何密钥值，配置项只报「有没有配」。

用法
----
    /www/server/pyporject_evn/cenkor/bin/python scripts/commerce_report.py
    ... commerce_report.py --days 30        # 只看近 N 天
    ... commerce_report.py --json           # 机器可读输出
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta

ENV_FILES = [
    "/www/wwwroot/cenkor-admin/backend/.env",
    "/www/wwwroot/cenkor-admin/.env",
]

# 只报有没有配置，永不打印值
SETTING_KEYS = [
    "commerce.payment_scene_key",
    "commerce.site_base_url",
    "payment.base_url",
]


def mask(url: str) -> str:
    return re.sub(r"://[^@/]*@", "://***@", url)


def find_dsn() -> str:
    """优先取正在服务的 8002 进程环境，其次 .env。

    之所以先读进程：.env 与线上实际可能不是同一套库（本次取证就撞上过——
    早期读到的 ¥399 那批订单不在线程实际连接的 127.0.0.1:5432/cenkor 里）。
    """
    try:
        out = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True).stdout
        for line in out.splitlines():
            if "cenkor_admin" in line and "--port 8002" in line:
                pid = line.split()[0]
                for kv in open(f"/proc/{pid}/environ", "rb").read().split(b"\0"):
                    s = kv.decode("utf-8", "ignore")
                    if s.startswith("DATABASE_URL="):
                        return s.split("=", 1)[1]
    except Exception as e:
        print(f"  （读进程环境失败，回落 .env：{e}）", file=sys.stderr)
    for p in ENV_FILES:
        if os.path.exists(p):
            for line in open(p, encoding="utf-8", errors="ignore"):
                s = line.strip()
                if s.startswith("DATABASE_URL="):
                    return s.split("=", 1)[1].strip().strip('"')
    return os.getenv("DATABASE_URL", "")


def has(cur, table: str) -> bool:
    cur.execute("select to_regclass(%s)", (f"public.{table}",))
    return cur.fetchone()[0] is not None


def cents(v) -> str:
    try:
        return f"¥{int(v) / 100:,.2f}"
    except Exception:
        return str(v)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=0, help="只统计近 N 天（0=全部）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    dsn = find_dsn()
    if not dsn:
        print("找不到 DATABASE_URL", file=sys.stderr)
        return 1
    url = re.sub(r"\+(asyncpg|psycopg2cffi|psycopg2cffi|psycopg2|psycopg)", "", dsn)
    print(f"# 可插拔市场成交周报  {datetime.now():%Y-%m-%d %H:%M}")
    print(f"# 连接: {mask(url)}")
    try:
        import psycopg2
    except ImportError:
        print("需要 psycopg2（用 /www/server/pyporject_evn/cenkor/bin/python 跑）", file=sys.stderr)
        return 1
    try:
        c = psycopg2.connect(url, connect_timeout=5)
    except Exception as e:
        print(f"连不上：{str(e)[:160]}", file=sys.stderr)
        return 1
    c.set_session(readonly=True, autocommit=True)
    cur = c.cursor()

    where = ""
    arg: tuple = ()
    if args.days:
        where = " where created_at >= %s"
        arg = (datetime.now() - timedelta(days=args.days),)
        print(f"# 窗口: 近 {args.days} 天")

    rep: dict = {}

    def rows(sql, params=()):
        cur.execute(sql, params)
        return cur.fetchall()

    if not has(cur, "app_orders"):
        print("! 本库没有 app_orders —— 说明连的不是承载商务数据的那套库（hub 有第二套部署的风险点）")
        return 2

    rep["orders_total"] = rows(f"select count(*), coalesce(sum(amount_cents),0) from app_orders{where}", arg)[0]
    print("\n## 订单 app_orders")
    print(f"  总数 {rep['orders_total'][0]}  合计 {cents(rep['orders_total'][1])}")
    for st, n, amt in rows(f"select status, count(*), coalesce(sum(amount_cents),0) from app_orders{where} group by 1 order by 2 desc", arg):
        print(f"  - {st:<8} {n:>3} 单  {cents(amt)}")
    print(f"  下单账号数 {rows(f'select count(distinct buyer_id) from app_orders{where}', arg)[0][0]}")
    print("  按应用：")
    for ak, n in rows(f"select app_key, count(*) from app_orders{where} group by 1 order by 2 desc limit 10", arg):
        print(f"    {ak:<28} {n}")
    if has(cur, "app_orders"):
        stuck = rows("select order_no, app_key, amount_cents, status, channel, created_at::timestamp(0) from app_orders where status='pending' order by id desc limit 5")
        if stuck:
            print("  挂着的待付单（收银台点过没付成）：")
            for r in stuck:
                print(f"    {r[0]}  {r[1]:<20} {cents(r[2]):>10}  {r[3]}/{r[4] or '-'}  {r[5]}")

    if has(cur, "pay_orders"):
        print("\n## 收银台 pay_orders（真正的支付网关侧）")
        for pv, st, n, amt in rows("select provider, status, count(*), coalesce(sum(amount_cents),0) from pay_orders group by 1,2 order by 3 desc"):
            print(f"  - {pv} / {st:<8} {n:>3} 单  {cents(amt)}")
        print("  判读：failed>0 或 pending 堆积 ⇒ 断点在支付通道，不在买家意愿")

    if has(cur, "app_licenses"):
        print("\n## 授权 app_licenses")
        for st, n, bound in rows("select status, count(*), count(*) filter (where coalesce(instance_fp,'')<>'') from app_licenses group by 1"):
            print(f"  - {st:<8} {n:>3} 条  已绑实例 {bound}")
        print("  判读：绑实例数就是真实装到机器上的授权数，比下载数更硬")

    if has(cur, "app_submissions"):
        print("\n## 供给侧 app_submissions（按产品轴）")
        for pr, n, dis, dl in rows("select product, count(*), count(*) filter (where status in ('approved','installed')), coalesce(sum(download_count),0) from app_submissions group by 1 order by 1"):
            print(f"  - {pr:<16} 提交 {n:>3}  可分发 {dis:>3}  累计下载 {dl}")
        print("  版本对齐检查（源码已升 1.0.1，这里若还是 1.0.0 ⇒ 打包完没发布）：")
        for ak, v, st in rows("select app_key, version, status from app_submissions where product='cenkormes' and app_key in ('mold_management','spc_control','exec_bi_enhance') order by app_key"):
            print(f"    {ak:<20} hub 版本 {v}  {st}")

    print("\n## 配置（只报有没有配，不打印值）")
    if has(cur, "system_settings"):
        got = dict(rows("select key, value::text from system_settings where key = any(%s)", (SETTING_KEYS,)))
        for k in SETTING_KEYS:
            v = got.get(k)
            print(f"  - {k:<28} {'已配' if v else '未配置 ← checkout 的回跳/回调地址只能靠请求头推导'}")
    else:
        print("  ! 没有 system_settings 表")

    print("\n## 表存在性（判断这套库是不是完整部署）")
    for t in ("pay_scenes", "pay_channels", "pay_notify_logs", "app_intros", "cloud_instances", "commerce_settings"):
        print(f"  - {t:<18} {'有' if has(cur, t) else '无'}")

    if args.json:
        print("\n" + json.dumps({k: list(map(str, v)) if isinstance(v, tuple) else v for k, v in rep.items()}, ensure_ascii=False))
    c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
