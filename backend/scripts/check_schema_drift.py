#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""schema 漂移体检（只读）—— ORM 声明的结构与线上真实库差多少。

与 `check_hub_schema.py`（核对某几个迁移建的对象在不在）不同，本脚本做的是
**全量双向 diff**：Base.metadata 里的每一张表 / 列 / 索引 / 约束，都拿去和真实库比。

为什么需要它
------------
2026-10 之前 `alembic/env.py` 有 bug：`erp/models.py` 其实是包目录（`models/__init__.py`），
旧循环只认单文件 `models.py`，导致 ERP 74 张表从没进过 metadata；
`crm/integration/models.py`、`system/store_models.py` 同理。
后果是任何人跑一次 `alembic revision --autogenerate`，都会生成 **101 个 drop_table**
—— 执行下去就是删库。

修完加载逻辑后表级误判已清零，但历史积累的列级漂移仍在（NOT NULL 声明、列注释、
索引命名等）。本脚本把这份"欠债"量化出来，避免下次有人看到一堆 alter_column
就以为是新引入的问题；也用于确认「新加的表/列是否真的进到 metadata」。

用法
----
    cd backend
    python3 scripts/check_schema_drift.py           # 汇总（按域）
    python3 scripts/check_schema_drift.py -v        # 逐条列出
    python3 scripts/check_schema_drift.py --json    # 机器可读（CI 存档）

退出码
------
0 = 无表级漂移（表集合一致；仅剩列/索引级差异或完全一致）
1 = 存在表级漂移（有表在库不在 metadata，或反之 —— 先查 models 是不是没加载上）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BACKEND, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
os.chdir(BACKEND)


from cenkor_admin.core.db import Base  # noqa: E402
from cenkor_admin.core.model_loader import load_all_models  # noqa: E402
from cenkor_admin.core.schema_filters import fetch_view_names, make_include_object  # noqa: E402

# 域归属，用于把漂移按业务线拆开看
DOMAIN_RULES = (
    ("平台核心", ("auth_", "portal_", "rbac_", "system_", "audit_logs", "login_logs",
                  "notifications", "api_keys", "password_resets", "platform_apps",
                  "announcements", "links", "tickets", "ticket_comments", "upgrade_", "codegen_")),
    ("CMS", ("cms_",)),
    ("CRM", ("crm_",)),
    ("ERP", ("erp_",)),
    ("MES", ("mes_", "mesx_")),
    ("工作流", ("workflow_",)),
    ("云存储", ("cloud_",)),
    ("商业化", ("app_", "dev_")),
    ("支付", ("pay_",)),
    ("库存", ("inventory_",)),
    ("轻应用", ("my_todo", "quick_notes", "builder_")),
)


def domain_of(table: str) -> str:
    for label, prefixes in DOMAIN_RULES:
        if table.startswith(prefixes):
            return label
    return "未归类"




def classify(item) -> tuple[str, str]:
    """把一层 diff 归到 (类别, 表名)。

    alembic 的 diff 元素既可能是 tuple 也可能是 list，形如
      ('add_table', Table) / ('remove_table', 'name')
      ('modify_nullable', schema, 'announcements', 'category', {...}, True, False)
    这里两种都认，否则会全部落到「其他」。
    """
    seq = item if isinstance(item, (tuple, list)) else [item]
    # alembic 有时把整个元素再包一层 list/tuple，剥到最内层
    while len(seq) == 1 and isinstance(seq[0], (tuple, list)):
        seq = seq[0]
    kind = str(seq[0]) if seq else str(item)
    table = ""
    if len(seq) > 2 and isinstance(seq[2], str) and seq[2]:
        table = seq[2]                       # (kind, schema, tname, col, ...)
    elif len(seq) > 1:
        payload = seq[1]
        owner = getattr(payload, "table", None)   # Index / ForeignKeyConstraint 等
        if owner is not None and getattr(owner, "name", None):
            table = owner.name
        elif isinstance(payload, str):
            table = payload
        elif getattr(payload, "name", None):
            table = payload.name              # Table 对象
    return kind, table


def bucket(kind: str) -> str:
    if kind in ("add_table", "remove_table"):
        return "表级"
    if kind in ("add_column", "remove_column"):
        return "列增删"
    if kind.startswith("modify_"):
        return "列属性"
    if "index" in kind:
        return "索引"
    if "fk" in kind or "constraint" in kind:
        return "约束"
    return "其他"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true", help="逐条列出差异")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    failed = load_all_models(verbose=False)

    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine

    from cenkor_admin.core.config import get_settings

    engine = create_engine(get_settings().DATABASE_URL_SYNC)
    with engine.connect() as conn:
        views = fetch_view_names(conn)
        mc = MigrationContext.configure(
            conn,
            opts={
                "include_object": make_include_object(views, None),
                "compare_type": True,
                "compare_server_default": False,
            },
        )
        diff = compare_metadata(mc, Base.metadata)
    engine.dispose()

    rows = []
    for item in diff:
        kind, table = classify(item)
        rows.append({"kind": kind, "table": table, "bucket": bucket(kind),
                     "domain": domain_of(table) if table else "-"})

    summary = Counter(r["bucket"] for r in rows)
    table_level = [r for r in rows if r["bucket"] == "表级"]

    if args.json:
        print(json.dumps({
            "metadata_tables": len(Base.metadata.tables),
            "views": sorted(views),
            "load_failures": failed,
            "summary": dict(summary),
            "table_level": table_level,
            "all": rows,
        }, ensure_ascii=False, indent=2))
        return 1 if table_level else 0

    print("schema 漂移体检")
    print("  metadata 表数 : %d" % len(Base.metadata.tables))
    print("  视图托管表    : %d（已排除）" % len(views))
    if failed:
        print("  ⚠ 模型加载失败 %d 个 —— 这些 app 的表会被误判为「库里多余」：" % len(failed))
        for f in failed:
            print("      -", f)
    print()

    if not rows:
        print("  ✓ 完全一致，没有任何漂移。")
        return 0

    print("  差异合计 %d 处" % len(rows))
    for b in ("表级", "列增删", "列属性", "索引", "约束", "其他"):
        if summary.get(b):
            flag = "  ← 危险：先确认 models 是否漏加载" if b == "表级" else ""
            print("    %-8s %4d%s" % (b, summary[b], flag))
    print()

    by_domain = defaultdict(Counter)
    for r in rows:
        by_domain[r["domain"]][r["bucket"]] += 1
    print("  按业务域：")
    print("    %-12s %6s %6s %6s %6s %6s" % ("域", "表级", "列增删", "列属性", "索引", "约束"))
    for d in sorted(by_domain, key=lambda x: -sum(by_domain[x].values())):
        c = by_domain[d]
        print("    %-12s %6d %6d %6d %6d %6d" % (
            d, c["表级"], c["列增删"], c["列属性"], c["索引"], c["约束"]))
    print()

    if args.verbose:
        print("  逐条明细：")
        for r in sorted(rows, key=lambda x: (x["bucket"], x["table"], x["kind"])):
            print("    [%-6s] %-32s %s" % (r["bucket"], r["table"] or "-", r["kind"]))
        print()

    if table_level:
        print("  ✗ 存在表级漂移，autogenerate 会生成 drop_table / create_table：")
        for r in table_level:
            print("      %-12s %s" % (r["kind"], r["table"]))
        print("  处理：检查该表所属 app 的 models 是否已被 env.py 加载；")
        print("        确认是历史遗留后，加入 core/schema_filters.py 的 LEGACY_UNMAPPED_TABLES。")
        return 1

    print("  ✓ 表级一致（无漏加载、无误删风险）。")
    print("  剩余列/索引级差异属历史积累，不影响新迁移：")
    print("      用 ALEMBIC_SCOPE_TABLES=<表名> 做定向 autogenerate 即可避开。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
