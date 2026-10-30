"""核对线上库实况与「待跑迁移链」的期望是否一致。

用途
----
2026-10-30：alembic 启动报 DuplicateColumn。根因是 app_submissions 的 DDL 早被
手工脚本补过，但 alembic_version 落后于实际库结构 —— 每次启动都重跑 0035。

本脚本在 stamp 之前/之后都能跑，用来回答一个问题：
**「stamp 到 head 是不是安全的？」**
安全 = 待跑链里每一个迁移期望的对象（表/列/索引/唯一约束）在库里都已存在。
只要有一条缺失，就不该 stamp，而应该先补齐 DDL。

用法：
    /www/server/pyporject_evn/cenkor/bin/python3 scripts/check_alembic_drift.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR / "src"))

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

from cenkor_admin.core.config import get_settings


def collect_expected(chain) -> dict:
    """把迁移链里所有 DDL 期望解析成 {'tables': [...], 'columns': {(t,c)}, 'indexes': [...], 'uniques': [...]}"""
    exp = {"tables": [], "columns": set(), "indexes": [], "uniques": []}
    for rev in chain:
        src = Path(rev.path).read_text(encoding="utf-8")
        up = src.split("def upgrade()", 1)[-1].split("def downgrade()", 1)[0]
        # 去掉 docstring，避免注释里的表名被误判
        import re

        up = re.sub(r'"""[\s\S]*?"""', "", up)
        for m in re.finditer(r'op\.create_table\(\s*["\']([^"\']+)', up):
            exp["tables"].append(m.group(1))
        for m in re.finditer(r'op\.add_column\(\s*["\']([^"\']+)["\']\s*,\s*sa\.Column\(\s*["\']([^"\']+)', up):
            exp["columns"].add((m.group(1), m.group(2)))
        for m in re.finditer(r'op\.create_index\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)', up):
            exp["indexes"].append((m.group(1), m.group(2)))
        for m in re.finditer(r'op\.create_unique_constraint\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)', up):
            exp["uniques"].append((m.group(1), m.group(2)))
    return exp


def main() -> int:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", get_settings().DATABASE_URL_SYNC)
    sd = ScriptDirectory.from_config(cfg)

    engine = sa.create_engine(get_settings().DATABASE_URL_SYNC, pool_pre_ping=True)
    with engine.connect() as conn:
        insp = sa.inspect(conn)
        cur = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()

        children: dict[str, list] = {}
        for rev in sd.walk_revisions():
            children.setdefault(rev.down_revision, []).append(rev)

        # 沿 children 从 current 走到 head
        chain, node, seen = [], cur, set()
        while True:
            kids = children.get(node, [])
            if not kids:
                break
            if len(kids) > 1:
                print(f"!! 分叉 @ {node}: {[k.revision for k in kids]}")
                return 2
            node = kids[0].revision
            if node in seen:
                print(f"!! 成环 @ {node}")
                return 2
            seen.add(node)
            chain.append(kids[0])

        print(f"当前版本 : {cur}")
        print(f"head     : {sd.get_heads()}")
        print(f"待跑迁移 : {len(chain)} 个")
        for rev in chain:
            print(f"    {rev.revision}  {Path(rev.path).name}")

        exp = collect_expected(chain)
        real_tables = set(insp.get_table_names())
        missing_tables = sorted({t for t in exp["tables"] if t not in real_tables})
        missing_cols: list[tuple[str, str]] = []
        for tbl, col in sorted(exp["columns"]):
            if tbl not in real_tables:
                continue
            cols = {c["name"] for c in insp.get_columns(tbl)}
            if col not in cols:
                missing_cols.append((tbl, col))
        {i["name"] for i in insp.get_indexes("app_pricing")}
        all_idx = set()
        for tbl in real_tables:
            try:
                all_idx |= {i["name"] for i in insp.get_indexes(tbl)}
            except Exception:
                pass
        missing_idx = sorted({(n, t) for n, t in exp["indexes"] if n not in all_idx})
        real_uniques = set()
        for tbl in real_tables:
            try:
                for u in insp.get_unique_constraints(tbl):
                    real_uniques.add((u["name"], tbl))
            except Exception:
                pass
        missing_uniques = sorted({(n, t) for n, t in exp["uniques"] if (n, t) not in real_uniques})

        print()
        print("=== 期望 vs 实况 ===")
        print(f"建表 {len(set(exp['tables'])):3d} 个 → 缺 {len(missing_tables)}  {missing_tables}")
        print(f"加列 {len(exp['columns']):3d} 个 → 缺 {len(missing_cols)}  {missing_cols}")
        print(f"索引 {len(exp['indexes']):3d} 个 → 缺 {len(missing_idx)}  {missing_idx}")
        print(f"唯一 {len(exp['uniques']):3d} 个 → 缺 {len(missing_uniques)}  {missing_uniques}")

        total_missing = len(missing_tables) + len(missing_cols) + len(missing_idx) + len(missing_uniques)
        if total_missing == 0:
            print()
            print("✅ 库结构已完全达到 head 期望 —— stamp 是安全的（不丢任何 DDL）")
            return 0
        print()
        print(f"⚠️ 还有 {total_missing} 项缺失，stamp 会跳过它们 —— 先补齐再 stamp")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
