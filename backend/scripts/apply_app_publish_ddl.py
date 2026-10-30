"""补齐 0035_app_publish 的列（幂等，默认预演）

为什么需要单独跑
----------------
0035_app_publish 是公开链迁移，但 2026-10-20 合入时闭源链的挂载点
gen_inventory 还挂在 0034 上，于是公开链与闭源链各留一个 head：
`alembic upgrade head` 抛 MultipleHeads，hub 启动时的自动迁移静默失败，
0035 从未执行 —— 门户 /api/v1/store/apps 因此报 UndefinedColumnError。

挂载点现已顺延为 gen_inventory → 0035，图恢复单 head；代价是线上库
（alembic_version=0029）在拓扑上被视作「0035 已应用」，upgrade 不会再补 DDL。
本脚本按 0035 的定义幂等补齐：加列 → 建索引 → 回填 published_at。
规则、顺序与事故复盘见 docs/migrations.md §6。

用法（在 backend/ 目录下）::

    PY=/www/server/pyporject_evn/cenkor/bin/python
    $PY scripts/apply_app_publish_ddl.py            # 预演，只读
    $PY scripts/apply_app_publish_ddl.py --apply    # 执行（同一事务）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR / "src"))

from sqlalchemy import create_engine, inspect, text

from cenkor_admin.core.config import get_settings

TABLE = "app_submissions"
COLUMNS: list[tuple[str, str]] = [
    ("schema_version", "INTEGER"),
    ("min_core_version", "VARCHAR(20)"),
    ("changelog", "TEXT"),
    ("published_at", "TIMESTAMP WITH TIME ZONE"),
    ("yanked_at", "TIMESTAMP WITH TIME ZONE"),
]
INDEX = "ix_app_submissions_published_at"
BACKFILL = text(
    "UPDATE app_submissions SET published_at = COALESCE(reviewed_at, created_at) "
    "WHERE status IN ('approved', 'installed') AND published_at IS NULL"
)


def main() -> int:
    ap = argparse.ArgumentParser(description="补齐 0035_app_publish 的列（幂等）")
    ap.add_argument("--apply", action="store_true", help="真正写库；缺省只预演")
    args = ap.parse_args()

    engine = create_engine(get_settings().DATABASE_URL_SYNC, pool_pre_ping=True)
    insp = inspect(engine)

    existing = {c["name"] for c in insp.get_columns(TABLE)}
    missing = [(name, ddl) for name, ddl in COLUMNS if name not in existing]
    has_index = INDEX in {i["name"] for i in insp.get_indexes(TABLE)}

    print(f"表 {TABLE}：现有列 {len(existing)} 个")
    print("  待加列 : " + (", ".join(n for n, _ in missing) if missing else "（无，已齐）"))
    print(f"  索引   : {INDEX} " + ("已存在" if has_index else "缺失"))
    if not missing and has_index:
        print("无需变更。")
        return 0

    if not args.apply:
        print("\n（预演，未写库；确认无误后加 --apply 执行）")
        return 0

    with engine.begin() as conn:
        for name, ddl in missing:
            conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS {name} {ddl}"))
        conn.execute(text(f"CREATE INDEX IF NOT EXISTS {INDEX} ON {TABLE} (published_at)"))
        result = conn.execute(BACKFILL)
        print(f"\n已补 {len(missing)} 列、索引就绪；published_at 回填 {result.rowcount} 行。")

    insp = inspect(engine)
    after = {c["name"] for c in insp.get_columns(TABLE)}
    still = [n for n, _ in COLUMNS if n not in after]
    if still:
        print(f"✗ 仍缺列：{', '.join(still)}")
        return 1
    print("✓ 校验通过：5 列与索引均已就位。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
