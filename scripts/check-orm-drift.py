#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ORM ↔ 迁移漂移检查 —— 防止「代码能起、一用就 UndefinedColumn」。

背景
----
本仓库踩过两次同一个坑：

  2026-11-02  AI 层 12 张表（批量生产 / 记忆 / 会话 / AB 测试 / 工作流）只有 ORM
              定义，建表迁移从未提交。干净环境跑完 `alembic upgrade heads`
              后，AI 页面一打开就报「表不存在」。
  2026-11-03  再扫一遍发现还有 6 张表 + 18 个字段是同样的情况（知识库 / 发布
              渠道 / 阅读统计 / 线索表单 / 应用上架元数据）。生产库是靠手工 SQL
              补出来的，仓库里只有 ORM。

根因不是「忘了写迁移」，而是**没有任何门禁能发现这件事**：
`alembic upgrade heads` 只要迁移图自洽就会成功返回，它不知道 ORM 里还有
别的表；单元测试跑的是 mock，不会真的连库。于是缺口一路带到用户环境。

本脚本补的正是这个门禁：把 SQLAlchemy metadata 里的**每个表、每个列**
与目标库的实际结构逐项比对。

两类「不该由迁移建」的对象
--------------------------
1. **声明式 schema 的应用**（方案 D）：`AppManifest.schema_managed=True` 的
   app（erp / crm / mes）其表结构由自带的 `schema.sql` 管理，启动时由
   bootstrap 执行，**alembic 主链刻意不建、也不纳入 diff**。
   这类表缺失不算迁移的责任，归入提示级。
2. **视图**：ERP 与 MES 共享同一批物理表，ERP 侧通过 `<app>/schema.sql`
   里的同名视图透传（如 `erp_boms → mes_boms`）。视图在 PostgreSQL 里和
   表同属 ``pg_class``，但 ``inspect.get_table_names()`` 只返回基表。
   早先版本漏了这点，把 20 个正常视图误报成「缺 20 张表」。
   现改为「表 / 视图 / 物化视图 / 外部表」统一视为存在。

判定
----
  MISSING_TABLE         ORM 有表、库里没有任何同名关系对象 → 一定失败
  MISSING_COLUMN        ORM 有列、库没有                   → --strict 下失败
  MISSING_SCHEMA_MANAGED schema_managed 应用的表缺失        → 仅提示
                        （该应用启动时会由 schema.sql 建）
  EXTRA_COLUMN          库有列、ORM 没有                    → 仅提示

在 CI 里对着「刚跑完迁移的空库」执行，任何一处缺失都说明迁移不完整。

用法
----
  # 默认读环境变量 DATABASE_URL_SYNC（与 alembic 一致）
  python3 scripts/check-orm-drift.py --strict

  # 显式指定库
  python3 scripts/check-orm-drift.py --url "postgresql+psycopg2://u:p@h:5432/db" --strict

  # 供 hook 用：通过时不输出
  python3 scripts/check-orm-drift.py --strict --quiet

注意
----
必须在 ``backend/`` 目录下运行（或把 ``backend/src`` 加进 PYTHONPATH），
因为要 import 应用自己的 ORM 定义。

退出码：0 通过，1 有缺失。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# pgvector 在降级环境下建出来的是 double precision[]，类型与 ORM 的 Vector 不同，
# 但列存在性才决定「会不会 UndefinedColumn」，所以本检查只比列名。
PGVECTOR_NOTE = "vector 列在无扩展环境会降级为 double precision[]，本检查只比对列是否存在"

# `CREATE TABLE IF NOT EXISTS public.xxx (` / `CREATE TABLE public.xxx (`
_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


def load_models() -> None:
    """导入全部 ORM 定义。复用运行时同一个加载器，避免两套路径出现分歧。"""
    from cenkor_admin.core.model_loader import load_all_models

    load_all_models(verbose=False)


def collect_schema_managed_tables() -> tuple[set[str], dict[str, str]]:
    """收集由各应用 ``schema.sql`` 托管的表名。

    返回 ``(表名集合, 表名 → 应用 key 的映射)``。扫描失败不致命：
    开源包里没有 erp/crm/mes 的 manifest，这时返回空集即可。
    """
    tables: set[str] = set()
    owner: dict[str, str] = {}

    try:
        from cenkor_admin.apps.system.app_registry import scan_app_manifests
    except Exception as exc:  # 应用框架都导不进来，说明环境不对，交给上层报错
        print("  [warn] 无法扫描 app manifest：%s" % exc, file=sys.stderr)
        return tables, owner

    try:
        manifests = scan_app_manifests()
    except Exception as exc:
        print("  [warn] app manifest 扫描失败：%s" % exc, file=sys.stderr)
        return tables, owner

    for key, mf in manifests.items():
        if not getattr(mf, "schema_managed", False):
            continue
        # manifest 里只有文件名，真实路径在 app 包目录下
        try:
            import importlib

            mod = importlib.import_module("cenkor_admin.apps.%s.manifest" % key)
            base_dir = Path(mod.__file__).resolve().parent
        except Exception:
            continue
        sql_path = base_dir / (getattr(mf, "schema_file", None) or "schema.sql")
        if not sql_path.is_file():
            # 外部 app（src/apps/<key>）也走同一条规则
            alt = base_dir.parent.parent / "apps" / key / "schema.sql"
            if alt.is_file():
                sql_path = alt
            else:
                continue
        try:
            text = sql_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print("  [warn] 读取 %s 失败：%s" % (sql_path, exc), file=sys.stderr)
            continue
        for name in _CREATE_TABLE_RE.findall(text):
            n = name.lower()
            tables.add(n)
            owner.setdefault(n, key)

    return tables, owner


def main() -> int:
    ap = argparse.ArgumentParser(description="ORM ↔ 迁移漂移检查")
    ap.add_argument("--url", default=None,
                    help="同步数据库 URL；缺省读 DATABASE_URL_SYNC")
    ap.add_argument("--strict", action="store_true",
                    help="缺失列也算失败（推荐在 CI 里开启）")
    ap.add_argument("--quiet", action="store_true", help="通过时不输出")
    ap.add_argument("--max-show", type=int, default=40, help="每类最多显示多少条")
    args = ap.parse_args()

    url = args.url or os.environ.get("DATABASE_URL_SYNC")
    if not url:
        print("✗ 未提供数据库 URL：用 --url 或设置 DATABASE_URL_SYNC", file=sys.stderr)
        return 1

    # 统一成同步驱动，检查本身不需要异步
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg2://" + url[len(prefix):]

    try:
        from sqlalchemy import create_engine, inspect
    except ImportError:
        print("✗ 缺少 SQLAlchemy，请先安装后端依赖", file=sys.stderr)
        return 1

    try:
        load_models()
        from cenkor_admin.core.db import Base
    except ModuleNotFoundError as exc:
        print("✗ 缺少 Python 依赖：%s" % exc, file=sys.stderr)
        print("  请在项目虚拟环境里运行，或先 pip install -r backend/requirements.txt",
              file=sys.stderr)
        return 1
    except Exception as exc:
        print("✗ 加载 ORM 模型失败：%s" % exc, file=sys.stderr)
        print("  多数是 PYTHONPATH 没指到 backend/src（或不在 backend/ 下运行）",
              file=sys.stderr)
        return 1

    # schema_managed 应用的表由其 schema.sql 负责，迁移不需要建
    managed_tables, managed_owner = collect_schema_managed_tables()

    try:
        engine = create_engine(url, future=True)
        insp = inspect(engine)
        # 视图与表同属 pg_class；只查 get_table_names() 会把视图误判为缺失
        db_relations: set[str] = set(insp.get_table_names())
        db_relations.update(insp.get_view_names())
        get_matview = getattr(insp, "get_materialized_view_names", None)
        if callable(get_matview):
            try:
                db_relations.update(get_matview())
            except Exception:
                pass  # 老版本 PG / SQLAlchemy 不支持，忽略
        db_tables = set(insp.get_table_names())
    except Exception as exc:
        print("✗ 连接数据库失败：%s" % exc, file=sys.stderr)
        return 1

    missing_tables: list[str] = []
    missing_managed: list[str] = []
    missing_cols: list[tuple[str, str]] = []
    extra_cols: list[tuple[str, str]] = []
    compared = 0
    views_hit = 0

    for tname, table in sorted(Base.metadata.tables.items()):
        if tname not in db_relations:
            # 由 schema.sql 托管的表，缺失不是迁移的责任
            if tname in managed_tables:
                missing_managed.append(tname)
            else:
                missing_tables.append(tname)
            continue
        if tname not in db_tables:
            # 命中的是视图（ERP 透传 MES 表的场景），列结构可比，计入已比对
            views_hit += 1
        db_cols = {c["name"] for c in insp.get_columns(tname)}
        orm_cols = {c.name for c in table.columns}
        missing_cols.extend((tname, c) for c in sorted(orm_cols - db_cols))
        extra_cols.extend((tname, c) for c in sorted(db_cols - orm_cols))
        compared += 1

    failed = bool(missing_tables) or (args.strict and bool(missing_cols))
    ok = not failed

    if args.quiet and ok:
        return 0

    print("ORM ↔ 迁移漂移检查")
    print("  ORM 表数        : %d" % len(Base.metadata.tables))
    print("  库中基表数      : %d（关系对象合计 %d）" % (len(db_tables), len(db_relations)))
    print("  双方比对        : %d（经视图映射 %d）" % (compared, views_hit))
    print("  schema.sql 托管 : %d 张表（%s）" % (
        len(managed_tables),
        "、".join(sorted({v for v in managed_owner.values()})) or "无",
    ))
    print("  %s" % PGVECTOR_NOTE)
    print()

    if missing_tables:
        print("✗ MISSING_TABLE（ORM 有、库里没有）— %d 张：" % len(missing_tables))
        for t in missing_tables[: args.max_show]:
            print("    %s" % t)
        if len(missing_tables) > args.max_show:
            print("    ... 另 %d 张" % (len(missing_tables) - args.max_show))
        print()
        print("  修法：为这些表补一条幂等建表迁移（CREATE TABLE IF NOT EXISTS），")
        print("        结构从生产库 `pg_dump --schema-only` 导出，不凭 ORM 反推。")
        print()

    if missing_managed:
        print("· MISSING_SCHEMA_MANAGED（由 schema.sql 托管，缺失仅提示）— %d 张" %
              len(missing_managed))
        for t in missing_managed[:10]:
            print("    %-38s (%s)" % (t, managed_owner.get(t, "?")))
        if len(missing_managed) > 10:
            print("    ... 另 %d 张" % (len(missing_managed) - 10))
        print("  这些表在对应应用启动时由 schema.sql 创建；若应用从未启动过，属正常。")
        print()

    if missing_cols:
        mark = "✗" if args.strict else "·"
        print("%s MISSING_COLUMN（ORM 有列、库里没有）— %d 处：" % (mark, len(missing_cols)))
        for t, c in missing_cols[: args.max_show]:
            print("    %-38s . %s" % (t, c))
        if len(missing_cols) > args.max_show:
            print("    ... 另 %d 处" % (len(missing_cols) - args.max_show))
        print()
        if args.strict:
            print("  修法：补 ALTER TABLE ... ADD COLUMN IF NOT EXISTS，写在公开迁移里。")
            print()

    if extra_cols:
        print("· EXTRA_COLUMN（库有列、ORM 无，仅提示）— %d 处" % len(extra_cols))
        for t, c in extra_cols[:10]:
            print("    %-38s . %s" % (t, c))
        if len(extra_cols) > 10:
            print("    ... 另 %d 处" % (len(extra_cols) - 10))
        print()

    if ok:
        print("✓ 无 MISSING_TABLE%s" % ("，也无 MISSING_COLUMN" if args.strict else ""))
        return 0

    print("✗ 漂移检查未通过：迁移没有覆盖 ORM 的全部定义。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
