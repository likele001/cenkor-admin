#!/usr/bin/env python3
"""历史内链回填：把正文里已经存在的站内 <a> 链登记进 cms_entry_links。

背景：内链管理界面是后加的，此前文章的内链直接写在正文 HTML 里，库里没有记录，
界面打开会显示「还没有内链」。这里把存量捞出来统一管理。

判定口径：
- 只认站内链接：相对路径 `/...`，或 cenkor.cn 域名下的绝对地址
- href 尾段去掉 `.html` 后当 slug 反查条目；slug 冲突时优先 published、其次 id 大的
- 跳过自链、跳过指向已删除条目的链、跳过 /cdn-cgi/ 这类非内容路径
- 写入状态 `inserted`（正文里本来就有这条链，无需再审）
- 幂等：同 (source, target, anchor) 且 status != rejected 已存在则跳过

用法（在 backend 目录下）：
    python scripts/backfill_entry_links.py --dry-run
    python scripts/backfill_entry_links.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import func, select

from cenkor_admin.apps.cms.models import Entry, EntryLink
from cenkor_admin.core.db import AsyncSessionLocal

A_TAG = re.compile(r'<a\b[^>]*?href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.S | re.I)
TAG_STRIP = re.compile(r"<[^>]+>")


def walk_strings(node, out: list[str]) -> None:
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, dict):
        for v in node.values():
            walk_strings(v, out)
    elif isinstance(node, (list, tuple)):
        for v in node:
            walk_strings(v, out)


def page_html(content) -> str:
    """content 是富文本 JSON，把字符串叶子拼起来当 HTML 扫。"""
    if content is None:
        return ""
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except Exception:
            return content
    buf: list[str] = []
    walk_strings(content, buf)
    return "\n".join(buf)


def href_to_slug(href: str) -> str | None:
    h = (href or "").strip()
    if not h or h.startswith("#") or h.lower().startswith(("mailto:", "tel:", "javascript:")):
        return None
    h = h.split("#")[0].split("?")[0]
    if h.startswith("//"):
        return None
    if h.lower().startswith(("http://", "https://")):
        if "cenkor.cn" not in h:
            return None
        h = urlparse(h).path
    if not h.startswith("/"):
        return None
    if "/cdn-cgi/" in h:
        return None
    tail = h.rstrip("/").split("/")[-1]
    tail = re.sub(r"\.html?$", "", tail, flags=re.I)
    return tail or None


async def run(dry_run: bool) -> None:
    async with AsyncSessionLocal() as db:
        entries = (
            await db.execute(
                select(Entry).where(Entry.deleted_at.is_(None)).order_by(Entry.id)
            )
        ).scalars().all()

        # slug -> entry：published 优先，其次 id 大的
        index: dict[str, Entry] = {}
        conflicts: dict[str, list[int]] = {}
        for e in entries:
            if not e.slug:
                continue
            prev = index.get(e.slug)
            if prev is None:
                index[e.slug] = e
            else:
                conflicts.setdefault(e.slug, [prev.id]).append(e.id)
                if (e.status == "published", e.id) > (prev.status == "published", prev.id):
                    index[e.slug] = e

        existing = (
            await db.execute(select(EntryLink).where(EntryLink.status != "rejected"))
        ).scalars().all()
        seen = {(r.source_entry_id, r.target_entry_id, r.anchor_text) for r in existing}

        plan: list[tuple[int, int, int, str]] = []
        plan_debug: list[tuple[int, int, str, str]] = []
        unresolved: list[tuple[int, str]] = []
        skipped_self = skipped_dup = 0

        for src in entries:
            html = page_html(src.content)
            if "<a " not in html.lower():
                continue
            for href, raw_text in A_TAG.findall(html):
                slug = href_to_slug(href)
                if not slug:
                    continue
                tgt = index.get(slug)
                if not tgt:
                    unresolved.append((src.id, href))
                    continue
                if tgt.id == src.id:
                    skipped_self += 1
                    continue
                anchor = re.sub(r"\s+", " ", TAG_STRIP.sub("", raw_text)).strip()[:60]
                if not anchor:
                    anchor = (tgt.slug or "")[:60]
                key = (src.id, tgt.id, anchor)
                if key in seen:
                    skipped_dup += 1
                    continue
                seen.add(key)
                plan.append((tgt.site_id or 1, src.id, tgt.id, anchor))
                plan_debug.append((src.id, tgt.id, anchor, href))

        print(f"扫描条目: {len(entries)}")
        print(f"待写入: {len(plan)}   跳过自链: {skipped_self}   跳过重复: {skipped_dup}")
        print(f"无法解析的 href: {len(unresolved)}")
        if conflicts:
            print(f"slug 冲突: {len(conflicts)} 个")
            for slug, ids in list(conflicts.items())[:8]:
                print(f"  slug={slug} entries={ids}")
        if unresolved:
            print("--- 未解析样例 ---")
            for eid, href in unresolved[:12]:
                print(f"  entry={eid} href={href}")

        print("--- 计划写入 ---")
        for s, t, anchor, href in plan_debug[:40]:
            print(f"  {s} -> {t}  锚文本={anchor!r}  href={href}")

        if dry_run:
            print("\n[dry-run] 未写入数据库。")
            return

        for site_id, s, t, anchor in plan:
            db.add(
                EntryLink(
                    site_id=site_id,
                    source_entry_id=s,
                    target_entry_id=t,
                    anchor_text=anchor,
                    status="inserted",
                )
            )
        await db.commit()

        total = (await db.execute(select(func.count()).select_from(EntryLink))).scalar()
        print(f"\n已写入 {len(plan)} 条，当前 cms_entry_links 总数: {total}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    asyncio.run(run(args.dry_run))
