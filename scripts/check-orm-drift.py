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

判定
----
  MISSING_TABLE   ORM 有表、库没有   → 一定失败（业务一访问就炸）
  MISSING_COLUMN  ORM 有列、库没有   → --strict 下失败（写入时炸）
  EXTRA_COLUMN    库有列、ORM 没有   → 仅提示（多为闭源扩展或历史遗留）

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
import sys

# pgvector 在降级环境下建出来的是 double precision[]，类型与 ORM 的 Vector 不同，
# 但列存在性才决定「会不会 UndefinedColumn」，所以本检查只比列名。
PGVECTOR_NOTE = "vector 列在无扩展环境会降级为 double precision[]，本检查只比对列是否存在"


def load_models() -> None:
    """导入全部 ORM 定义。复用运行时同一个加载器，避免两套路径出现分歧。"""
    from cenkor_admin.core.model_loader import load_all_models  

    load_all_models(verbose=False)


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

    try:
        engine = create_engine(url, future=True)
        insp = inspect(engine)
        db_tables = set(insp.get_table_names())
    except Exception as exc:
        print("✗ 连接数据库失败：%s" % exc, file=sys.stderr)
        return 1

    missing_tables: list[str] = []
    missing_cols: list[tuple[str, str]] = []
    extra_cols: list[tuple[str, str]] = []
    compared = 0

    for tname, table in sorted(Base.metadata.tables.items()):
        if tname not in db_tables:
            missing_tables.append(tname)
            continue
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
    print("  库中实际表数    : %d" % len(db_tables))
    print("  双方比对        : %d" % compared)
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
