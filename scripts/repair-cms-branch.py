#!/usr/bin/env python3
"""修复「版本戳在 CMS 分支之后、但 CMS 分支 DDL 从未执行」的脏库。

## 症状

    psycopg2.errors.UndefinedTable: relation "cms_sites" does not exist
    INFO  [alembic.runtime.migration] Running upgrade 20261104_1100_cms_search_logs
                                            -> 20261127_1200_cms_site_plans

## 成因（不是迁移写错）

2026-11 给 `merge_commerce` **追加**了 `cms_orphan` 作为第二个父节点，把
CMS 分支（`cms_multisite` 起的一段）挂进了合流点。迁移图上从此
`cms_multisite` 是 `cms_search_logs` 的祖先，全新库按顺序跑必然有 `cms_sites`。

但当时已经越过 `merge_commerce` 的老库只被改了版本戳，没有补跑那段分支，
于是版本号说「在 cms_sites 之后」、库里却没有 `cms_sites`。这种库再往后升级，
第一条依赖 `cms_sites` 的迁移就炸。

## 修法

CMS 分支在链上的形状是一段**连续区间**，合流点 `merge_commerce` 以
`down_revision = (cms_orphan, app_publish)` 双父收口。`app_schema` 正是接在
`merge_commerce` 之后的第一条，且它是个**空实现**（方案 D 留下的占位）。

因此：

    1. 记录当前版本 current；
    2. 把版本戳回退到分支的起点之前 —— `20261014_124200_schema_versions`
       （删掉 alembic_version 再写入一行，等价于 stamp）；
    3. `alembic upgrade <cms_orphan>`：重放区间内已被标记「执行过」的那批
       迁移。靠 `core/migration_idempotent.py` 的全局幂等层，已存在的
       table/column/index 全部跳过，只补真正缺的（正是 CMS 分支那一段）；
    4. 把版本戳恢复到 current。

第 2-4 步无法共享同一个事务：`command.stamp/upgrade` 各自提交自己的事务。
所以改用「失败即恢复」——第 3 步抛异常时立刻把版本戳写回 current，
保证任何失败路径下版本戳都不停在中间态。

区间内的 `app_schema` 是空实现、`cms_search_logs` 建表已被幂等层保护，
所以重放对已有对象零副作用（已用 `_replay_audit.py` 逐个核过 39 条迁移）。

## 用法

    python3 scripts/repair-cms-branch.py --dry-run          # 只看诊断，不动库
    python3 scripts/repair-cms-branch.py --db cenkor_old    # 指定库名
    python3 scripts/repair-cms-branch.py --yes              # 修 DATABASE_URL 指向的库

必须先看清输出里的「数据库」一行再决定是否加 `--yes`：本脚本会改写
alembic_version，连着生产库跑就不是演练了。

纯开发库、数据可弃时，直接 `dropdb && createdb && alembic upgrade heads` 更快。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND / "src"))

# 分支起点之前：这一段是 CMS 分支与公共链的分叉点，重放它之后到 cms_orphan
# 之间的迁移，就能把整段 CMS 分支补齐。
FORK_POINT = "20261014_124200_schema_versions"
# CMS 分支的终点（合流迁移 cms_orphan 的父节点之一即此链尾）
BRANCH_END = "20261103_1100_cms_orphan"

# 判断「已修好」的关键对象。缺任意一个就说明分支没跑全。
REQUIRED = (
    "cms_sites",
    "cms_templates",
    "cms_embeddings",
    "cms_entry_links",
    "cms_site_config",
)


def _mask(url: str) -> str:
    """隐去连接串里的密码，避免日志泄漏。"""
    if "@" not in url:
        return url
    head, tail = url.rsplit("@", 1)
    if ":" in head.split("//")[-1]:
        user = head.split("//")[-1].split(":")[0]
        head = head[: head.rindex("//") + 2] + user + ":***"
    return head + "@" + tail


def _diag(conn) -> dict:
    from sqlalchemy import text

    dbname = conn.execute(text("select current_database()")).scalar()
    vers = conn.execute(text("select version_num from alembic_version")).scalars().all()
    present = {
        t: bool(conn.execute(text(f"select to_regclass('public.{t}')")).scalar())
        for t in REQUIRED
    }
    return {"db": dbname, "versions": list(vers), "present": present}


def _print_diag(d: dict) -> None:
    print(f"  数据库      : {d['db']}")
    print(f"  alembic_ver : {', '.join(d['versions']) or '(空)'}")
    for t, ok in d["present"].items():
        print(f"  {t:<20}: {'存在' if ok else '缺失 ←'}")


def main() -> int:
    ap = argparse.ArgumentParser(description="修复 CMS 分支未执行的脏库")
    ap.add_argument("--db", help="目标库名（默认取 DATABASE_URL）")
    ap.add_argument("--dry-run", action="store_true", help="只诊断不修改")
    ap.add_argument("--force", action="store_true", help="分支表都在时也照样重放")
    ap.add_argument("--yes", action="store_true", help="确认真要改写目标库的版本戳")
    args = ap.parse_args()

    os.chdir(BACKEND)
    os.environ.setdefault("PYTHONPATH", "src")

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    cfg = Config(str(BACKEND / "alembic.ini"))

    # 连接串优先级必须与 alembic/env.py 完全一致：
    #   CENKOR_DATABASE_URL  >  settings.DATABASE_URL_SYNC  >  alembic.ini
    # 顺序搞反的后果很严重 —— 本脚本会 DELETE/INSERT alembic_version，
    # 拿错连接串就等于把生产库的版本戳回退。
    url = os.environ.get("CENKOR_DATABASE_URL") or ""
    if not url:
        try:
            from cenkor_admin.core.config import get_settings

            url = get_settings().DATABASE_URL_SYNC or ""
        except Exception:
            pass
    url = url or cfg.get_main_option("sqlalchemy.url") or ""

    if args.db:
        # 只替换库名，保留 user / host / port / query。
        # 用 sqlalchemy 的 URL 解析而不是字符串切分：.env 里可能是
        # postgresql+psycopg2://user:pw@127.0.0.1:5432/cenkor 这种常规形态，
        # 也可能是 postgresql+psycopg2://postgres@/x?host=/tmp 这种 socket 形态，
        # 手写切分会把库名切错。
        from sqlalchemy.engine import make_url

        parsed = make_url(url).set(database=args.db)
        url = parsed.render_as_string(hide_password=False)

    # 让 alembic 子命令也连同一个库（env.py 优先读这个变量）
    os.environ["CENKOR_DATABASE_URL"] = url

    print(f"目标连接: {_mask(url)}\n")

    engine = create_engine(url, future=True)
    with engine.connect() as conn:
        before = _diag(conn)
    _print_diag(before)

    missing = [t for t, ok in before["present"].items() if not ok]
    if not missing:
        print("\n✓ CMS 分支对象齐全，无需修复")
        return 0
    if not args.force:
        print(f"\n诊断：缺 {', '.join(missing)}")
        print("      版本戳已越过 CMS 分支，但分支 DDL 从未执行 —— 属历史 stamp 遗留")

    plan = (f"回退版本戳到 {FORK_POINT} → 重放到 {BRANCH_END} → 恢复到 "
            f"{', '.join(before['versions']) or '(空)'}")
    print(f"\n修复步骤：{plan}")

    if args.dry_run:
        print("\n[dry-run] 未做任何修改")
        return 0

    if not before["versions"]:
        print("\n✗ alembic_version 为空，无法判断目标版本；请手工确认后用 "
              "alembic upgrade heads", file=sys.stderr)
        return 1

    # 确认要动的就是刚才诊断的那个库 —— 版本戳会被改写，连错库代价很大
    if not args.yes:
        print(f"\n将要修改数据库 “{before['db']}” 的 alembic_version。")
        print("确认无误请重新执行并加 --yes")
        return 0

    def _restore_versions() -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM alembic_version"))
            for v in before["versions"]:
                conn.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                    {"v": v},
                )

    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM alembic_version"))
            conn.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                {"v": FORK_POINT},
            )
        print(f"\n[1/3] 版本戳已回退到 {FORK_POINT}")

        command.upgrade(cfg, BRANCH_END)
        print(f"[2/3] 已重放到 {BRANCH_END}，CMS 分支补齐")

        _restore_versions()
        print(f"[3/3] 版本戳已恢复为 {', '.join(before['versions'])}")
    except Exception as exc:  # noqa: BLE001
        print(f"\n✗ 修复失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        # 关键：失败时必须把版本戳写回原值，不能停在中间态
        try:
            _restore_versions()
            print(f"  版本戳已回滚为 {', '.join(before['versions'])}", file=sys.stderr)
        except Exception as exc2:  # noqa: BLE001
            print(f"  ✗ 版本戳回滚也失败了：{exc2}", file=sys.stderr)
            print(f"  请手工执行：DELETE FROM alembic_version; "
                  f"INSERT INTO alembic_version VALUES "
                  f"({', '.join(repr(v) for v in before['versions'])});", file=sys.stderr)
        with engine.connect() as conn:
            print("\n当前状态：")
            _print_diag(_diag(conn))
        return 2

    with engine.connect() as conn:
        after = _diag(conn)
    print("\n修复后：")
    _print_diag(after)
    still = [t for t, ok in after["present"].items() if not ok]
    if still:
        print(f"\n⚠ 仍缺：{', '.join(still)}", file=sys.stderr)
        return 3

    print("\n✓ 修复完成，现在可以正常执行：alembic upgrade heads")
    return 0


if __name__ == "__main__":
    sys.exit(main())