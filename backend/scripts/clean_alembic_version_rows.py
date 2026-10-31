"""清理 alembic_version 里被祖先关系吞掉的多余行。

背景：新增公开迁移时会出现「2 个 head」的中间态，`upgrade heads` 会在
alembic_version 里记 2 行；随后顺延挂载点让其中一个变成另一个的祖先，
alembic 只是「显示上」合并（current 只打 head），表里那行脏数据还在，
check_alembic_drift.py 用 scalar_one() 就直接炸。

做法：只删「是其他行祖先」的那些行，且必须确认它确实出现在
目标 head 的祖先链里 —— 不做无脑 DELETE。
"""

from __future__ import annotations

import os
import pathlib
import re
import sys

from sqlalchemy import create_engine, text

from cenkor_admin.core.config import get_settings

BE = pathlib.Path("/www/wwwroot/cenkor-admin/backend")


def load_graph() -> dict[str, list[str]]:
    """从迁移文件里解析 revision -> down_revision，忽略闭源/公开之分（要全量视图）。"""
    graph: dict[str, list[str]] = {}
    for path in (BE / "alembic/versions").rglob("*.py"):
        src = path.read_text(encoding="utf-8", errors="ignore")
        # 两种写法都要认：新文件的 `revision: str = "x"` 和老文件的 `revision = "x"`
        m = re.search(r"^revision(?:\s*:[^=\n]+)?\s*=\s*[\"']([^\"']+)[\"']", src, re.M)
        if not m:
            continue
        rev = m.group(1)
        d = re.search(r"^down_revision(?:\s*:[^=\n]+)?\s*=\s*(.+)$", src, re.M)
        downs: list[str] = []
        if d:
            downs = re.findall(r"[\"']([^\"']+)[\"']", d.group(1))
        graph[rev] = downs
    return graph


def ancestors(graph: dict[str, list[str]], rev: str) -> set[str]:
    seen: set[str] = set()
    stack = list(graph.get(rev, []))
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(graph.get(cur, []))
    return seen


def main() -> int:
    graph = load_graph()
    eng = create_engine(get_settings().DATABASE_URL_SYNC)
    with eng.begin() as c:
        rows = [r[0] for r in c.execute(text("select version_num from alembic_version"))]
        print("清理前:", len(rows), "行 ->", rows)
        if len(rows) <= 1:
            print("已经是单行，无需处理")
            return 0

        # 找出被别的行「包住」的那些
        stale = []
        for r in rows:
            assert r in graph, f"版本表里的 {r} 在当前工作区找不到对应迁移文件"
            others = [x for x in rows if x != r]
            if any(r in ancestors(graph, o) for o in others):
                stale.append(r)

        if not stale:
            sys.exit("❌ 没有祖先关系，多个 head 是真实的，请用 alembic merge 而不是删行")

        print("判定为冗余祖先行:", stale)
        for r in stale:
            c.execute(text("delete from alembic_version where version_num = :v"), {"v": r})
        after = [x[0] for x in c.execute(text("select version_num from alembic_version"))]
        print("清理后:", len(after), "行 ->", after)
    return 0


if __name__ == "__main__":
    sys.exit(main())
