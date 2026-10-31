#!/usr/bin/env python3
"""公开页静态缓存的运维工具（模板系统 P2）。

背景
----
公开详情页由后端渲染后落盘，nginx `try_files` 命中就不再回源。
正常失效靠写入口的显式 purge（条目保存 / 模板保存 / 站点改名…），
但总有漏网场景（直接改库、导入历史数据、脚本批量操作），所以留这个工具兜底。

用法
----
    cd backend
    python3 scripts/build_static_cache.py --stats           # 看现状（默认）
    python3 scripts/build_static_cache.py --purge           # 清空全部站点
    python3 scripts/build_static_cache.py --purge-site www.cenkor.cn
    python3 scripts/build_static_cache.py --purge-entry my-slug --site-id 1
    python3 scripts/build_static_cache.py --warm https://www.cenkor.cn

`--warm` 会按 sitemap 把每个 URL 真打一遍，让后端边渲染边落盘。
它只对「Host 等于站点规范域名」的请求有效 —— 拿 IP 或 localhost 预热写不进文件
（详见 static_cache.record_public_page 的注释），所以这里必须传完整 https:// 域名。

清空是安全的：nginx 全部 miss → 回落动态渲染 → 后端顺手重新落盘。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BACKEND, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
os.chdir(BACKEND)

from cenkor_admin.apps.cms import static_cache

_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return f"{n:.1f} GB"


def show_stats(host: str | None) -> None:
    info = static_cache.stats(host)
    print(f"开关（{static_cache.ENABLE_ENV}）：{'已启用' if info['enabled'] else '未启用'}")
    print(f"根目录：{info['root']}")
    print(f"已挂载：{'是' if info['mounted'] else '否（还没有任何文件）'}")
    print(f"文件数：{info['files']}    占用：{_human(info['bytes'])}")
    if not info["enabled"]:
        print("\n提示：未启用时后端不会写盘，nginx 的 try_files 永远 miss（等于没开）。")


def purge_all() -> None:
    n = static_cache.purge_all()
    print(f"已清空全部站点静态文件：{n} 个")


def purge_site(host: str) -> None:
    n = static_cache.purge_site(host)
    print(f"已清空 {host} 的静态文件：{n} 个")


def purge_entry(slug: str, site_id: int) -> None:
    """按 slug 清一个条目的详情页（需要从库里取站点规范域名）。"""
    from sqlalchemy import select

    from cenkor_admin.apps.cms import models
    from cenkor_admin.core.db import AsyncSessionLocal

    async def run() -> int:
        async with AsyncSessionLocal() as session:
            row = (
                await session.execute(select(models.Site).where(models.Site.id == site_id))
            ).scalars().first()
            domain = (getattr(row, "domain", None) or "").strip().lower()
            if not domain:
                print(f"站点 {site_id} 没有配置域名，无法定位静态目录", file=sys.stderr)
                return 0
            n = static_cache.purge_entry(domain, slug)
            print(f"已清理 {domain} 下 slug={slug} 的静态页：{n} 个")
            return n

    asyncio.run(run())


def warm(base_url: str) -> None:
    """按 sitemap 逐个 GET，让后端把每一页渲染并落盘。"""
    import httpx

    base_url = base_url.rstrip("/")
    sitemap_url = f"{base_url}/sitemap.xml"
    print(f"读取 {sitemap_url} …")
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        resp = client.get(sitemap_url)
        resp.raise_for_status()
        urls = _LOC_RE.findall(resp.text)

    # 只预热 CMS 渲染的页面；官网静态首页等不归后端管
    targets = [u for u in urls if re.search(r"/(article|product|news|case)/[^/]+\.html$", u)]
    print(f"sitemap 共 {len(urls)} 条，其中详情页 {len(targets)} 条，开始预热…")

    ok = fail = 0
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for i, url in enumerate(targets, 1):
            try:
                r = client.get(url)
                if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
                    ok += 1
                else:
                    fail += 1
                    print(f"  [{i}/{len(targets)}] {r.status_code} {url}")
            except Exception as exc:
                fail += 1
                print(f"  [{i}/{len(targets)}] 失败 {url}: {exc}")
    print(f"完成：成功 {ok}，失败 {fail}")
    show_stats(base_url.split("://")[-1].split("/")[0])


def main() -> int:
    p = argparse.ArgumentParser(description="公开页静态缓存运维工具")
    p.add_argument("--stats", action="store_true", help="显示现状（默认）")
    p.add_argument("--purge", action="store_true", help="清空全部站点")
    p.add_argument("--purge-site", metavar="HOST", help="清空指定域名")
    p.add_argument("--purge-entry", metavar="SLUG", help="按 slug 清单个条目的详情页")
    p.add_argument("--site-id", type=int, default=1, help="配合 --purge-entry 使用的站点 id")
    p.add_argument("--warm", metavar="BASE_URL", help="按 sitemap 预热，如 https://www.cenkor.cn")
    args = p.parse_args()

    if args.purge:
        purge_all()
    elif args.purge_site:
        purge_site(args.purge_site)
    elif args.purge_entry:
        purge_entry(args.purge_entry, args.site_id)
    elif args.warm:
        warm(args.warm)
    else:
        show_stats(None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
