"""hub 库 schema 只读体检：迁移版本 vs 实际列/表

用法（在 backend/ 目录下）：

    /www/server/pyporject_evn/cenkor/bin/python scripts/check_hub_schema.py

只执行 SELECT / information_schema 查询，不写库、不跑迁移。
用途：确认 alembic 记录的版本与真实 schema 一致，尤其是 0030–0035 这批
「被重挂过的链」——alembic 认为已应用的修订不会再补建对象，必须单独核对。
规则与背景见 docs/migrations.md。
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR / "src"))

from sqlalchemy import create_engine, inspect, text

from cenkor_admin.core.config import get_settings

# 修订 → 它应当创建的对象。列/索引按 (表, 名) 存放。
CHECKS = [
    ("20261009_0030_app_intro", {"tables": ["app_intros"]}),
    (
        "20261010_0031_dev_method",
        {
            "columns": [("app_submissions", "dev_method")],
            "indexes": [("app_submissions", "ix_app_submissions_dev_method")],
        },
    ),
    (
        "20261014_124126_gen_inventory",
        {"tables": ["inventory_warehouse", "inventory_location"]},
    ),
    ("20261015_0032_codegen_runs", {"tables": ["codegen_runs"]}),
    ("20261015_0033_upgrade_runs", {"tables": ["upgrade_runs"]}),
    ("20261018_0034_upgrade_notes", {"columns": [("upgrade_runs", "notes")]}),
    (
        "20261020_0035_app_publish",
        {
            "columns": [
                ("app_submissions", "schema_version"),
                ("app_submissions", "min_core_version"),
                ("app_submissions", "changelog"),
                ("app_submissions", "published_at"),
                ("app_submissions", "yanked_at"),
            ],
            "indexes": [("app_submissions", "ix_app_submissions_published_at")],
        },
    ),
]


def main() -> int:
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
    insp = inspect(engine)
    table_names = set(insp.get_table_names())

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    print(f"alembic_version: {rows or '(空)'}")
    if len(rows) == 2:
        print("  （两条为正常：公开/基础链 head + 商业应用(闭源)链 head）")

    missing_total = 0
    for revision, spec in CHECKS:
        missing: list[str] = []
        for table in spec.get("tables", []):
            if table not in table_names:
                missing.append(f"table:{table}")
        for table, column in spec.get("columns", []):
            if table not in table_names:
                missing.append(f"table:{table}(列 {column} 无从谈起)")
            elif column not in {c["name"] for c in insp.get_columns(table)}:
                missing.append(f"column:{table}.{column}")
        for table, index in spec.get("indexes", []):
            if table not in table_names:
                continue
            if index not in {i["name"] for i in insp.get_indexes(table)}:
                missing.append(f"index:{table}.{index}")
        missing_total += len(missing)
        flag = "OK      " if not missing else "MISSING "
        print(f"{flag}{revision}" + (f"  ← {', '.join(missing)}" if missing else ""))

    if missing_total:
        print(f"\n共 {missing_total} 项缺失。alembic 认为这些修订已应用，upgrade 不会补建；")
        print("0035 的列/索引可跑 scripts/apply_app_publish_ddl.py（先预演再 --apply），")
        print("其余缺失项按对应迁移定义手工补 DDL。")
        return 1
    print("\n全部对象就位。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
