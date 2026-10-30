"""迁移自愈的三场景回归验证。

场景 A（版本号落后，DDL 全在）：生产库的真实形态 → 必须 stamp，不重跑 DDL
场景 B（空库全新环境）        ：→ 必须 upgrade，把 82 张表建出来
场景 C（混合状态）            ：部分缺、部分在 → 必须 upgrade，缺的补上、有的跳过

每个场景都跑完再核对：alembic_version 到 head、关键表在、幂等层无报错。
"""
from __future__ import annotations

import os
import sys
import time

import sqlalchemy as sa

sys.path.insert(0, "/www/wwwroot/cenkor-admin/backend/src")

from cenkor_admin.core.config import get_settings
from cenkor_admin.core.migration_runner import run_migrations_with_drift_guard

MAIN_URL = get_settings().DATABASE_URL_SYNC
TEST_URL = MAIN_URL.rsplit("/", 1)[0] + "/cenkor_drift_test"

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAILS.append(name)


def reset_test_db() -> None:
    import subprocess

    # 先踢掉残留连接，否则 DROP DATABASE 报 "database is being accessed by other users"
    subprocess.run(
        [
            "/www/server/pgsql/bin/psql", "-U", "postgres", "-d", "postgres",
            "-c",
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname='cenkor_drift_test' AND pid <> pg_backend_pid();",
        ],
        check=False,
        capture_output=True,
    )
    subprocess.run(
        [
            "/www/server/pgsql/bin/psql", "-U", "postgres", "-d", "postgres",
            "-c", "DROP DATABASE IF EXISTS cenkor_drift_test;",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "/www/server/pgsql/bin/psql", "-U", "postgres", "-d", "postgres",
            "-c", "CREATE DATABASE cenkor_drift_test OWNER cenkor;",
        ],
        check=True,
        capture_output=True,
    )


def sql(test_url: str, stmt: str) -> list:
    eng = sa.create_engine(test_url, pool_pre_ping=True)
    with eng.connect() as conn:
        result = conn.execute(sa.text(stmt))
        rows = result.fetchall() if result.returns_rows else []
        conn.commit()
    return rows


def version_of(url: str) -> str:
    eng = sa.create_engine(url, pool_pre_ping=True)
    with eng.connect() as conn:
        v = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalars().first()
    return v or "<none>"


def run(url: str) -> str:
    os.environ["CENKOR_DATABASE_URL"] = url
    return run_migrations_with_drift_guard()


def scenario_a() -> None:
    print("\n=== 场景 A：版本号落后，DDL 全在（生产库真实形态）===")
    # 在测试库上模拟：建完表后把版本号退回去
    run(TEST_URL)
    sql(TEST_URL, "UPDATE alembic_version SET version_num='20261029_1500_ai_video_jobs'")
    before = version_of(TEST_URL)
    result = run(TEST_URL)
    after = version_of(TEST_URL)
    check("判定为 stamped（不重跑 DDL）", result == "stamped", result)
    check("版本号推进到 head", after == "20261027_0100_app_schema", f"{before} -> {after}")


def scenario_b() -> None:
    print("\n=== 场景 B：空库全新环境 ===")
    reset_test_db()
    result = run(TEST_URL)
    tables = sql(TEST_URL, "SELECT count(*) FROM pg_tables WHERE schemaname='public'")[0][0]
    version = version_of(TEST_URL)
    check("走 upgrade（不是 stamp）", result == "upgraded", result)
    check("版本号到 head", version == "20261027_0100_app_schema", version)
    check("表已建出来（>=80 张）", tables >= 80, f"{tables} 张")
    # 幂等：再跑一次应该 skip，不该报错
    result2 = run(TEST_URL)
    check("重复执行不报错（skip）", result2 in ("skipped", "stamped"), result2)


def scenario_c() -> None:
    print("\n=== 场景 C：混合状态（部分缺、部分在）===")
    sql(TEST_URL, "DROP TABLE IF EXISTS app_pricing CASCADE")
    sql(TEST_URL, "UPDATE alembic_version SET version_num='20261029_1500_ai_video_jobs'")
    result = run(TEST_URL)
    pricing = sql(TEST_URL, "SELECT to_regclass('public.app_pricing')")[0][0]
    orders = sql(TEST_URL, "SELECT to_regclass('public.app_orders')")[0][0]
    version = version_of(TEST_URL)
    check("走 upgrade（不是 stamp）", result == "upgraded", result)
    check("缺的表被补回", pricing == "app_pricing", str(pricing))
    check("已存在的表未受影响", orders == "app_orders", str(orders))
    check("版本号到 head", version == "20261027_0100_app_schema", version)


def scenario_d() -> None:
    print("\n=== 场景 D：生产库（cenkor）幂等复跑 ===")
    before = version_of(MAIN_URL)
    result = run(MAIN_URL)
    after = version_of(MAIN_URL)
    check("生产库不报错", result in ("skipped", "stamped", "upgraded"), result)
    check("版本号保持在 head", after == "20261027_0100_app_schema", f"{before} -> {after}")


def main() -> int:
    t0 = time.time()
    scenario_a()
    scenario_b()
    scenario_c()
    scenario_d()
    print(f"\n耗时 {time.time() - t0:.1f}s")
    if FAILS:
        print(f"\n❌ 失败 {len(FAILS)} 项: {FAILS}")
        return 1
    print("\n✅ 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
