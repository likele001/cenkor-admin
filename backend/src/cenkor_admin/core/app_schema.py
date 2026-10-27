"""App 自带 schema 的执行器（方案 D · 2026-10-27）

为什么需要这个模块
==================
在此之前，所有应用的表都由 alembic 主链创建 —— 81 个迁移串成一条链，`upgrade head`
会从核心表一路建到 ERP 74 张、MES 36 张、CRM 17 张。结果是「可插拔」只在代码层成立：
客户只买基础版，库里照样躺着 127 张用不上的表，`uninstall_app()` 也删不掉它们。

本模块把业务应用的表从 alembic 剥离，改由应用目录下的 `schema.sql` 在启动时创建。

三条约定（改之前先读）
====================
1. **schema.sql 必须完全幂等**：`CREATE TABLE IF NOT EXISTS` / `CREATE OR REPLACE VIEW` /
   `CREATE INDEX IF NOT EXISTS`。重复执行必须零副作用 —— 校验和变化时会重跑。
2. **执行记录写 `app_schema_versions`**（app_key 为主键），存 version + checksum。
   checksum 只取 schema.sql 内容，没改就整段跳过，不会每次启动都跑 DDL。
3. **装哪些应用由 `CENKOR_APPS` 控制**：
   - 未设置       → 全部内置应用（保持现状，现有部署不受影响）
   - `crm,erp`    → 只这两个
   - 空字符串 `""` → 一个都不装（基础版只有核心表）

失败策略
========
单个应用失败不阻断启动：记 ERROR、写进返回值，其余应用照常执行，服务继续起。
理由：一个应用的表建不出来，不该让整个平台起不来；但要能在日志里一眼看到。
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

SCHEMA_FILENAME = "schema.sql"
ENV_APPS = "CENKOR_APPS"


@dataclass
class SchemaResult:
    key: str
    status: str          # applied / skipped / no_schema / disabled / failed
    detail: str = ""


def _sync_dsn() -> str:
    from cenkor_admin.core.config import get_settings

    override = os.environ.get("CENKOR_DATABASE_URL")
    url = override or get_settings().DATABASE_URL_SYNC
    return url.replace("postgresql+psycopg2://", "postgresql://")


def enabled_apps() -> set[str] | None:
    """返回允许建表的应用集合；None 表示「全部」（环境变量未设置）。"""
    raw = os.environ.get(ENV_APPS)
    if raw is None:
        return None
    return {x.strip() for x in raw.split(",") if x.strip()}


def read_schema(app_dir: Path, filename: str = SCHEMA_FILENAME):
    """读 schema.sql，返回 (全文, checksum)；文件不存在返回 None。"""
    path = app_dir / filename
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _applied(conn) -> dict[str, tuple[str, str]]:
    """读取已执行记录；表还不存在时返回空（迁移未跑过的情况）。"""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT app_key, version, checksum FROM app_schema_versions")
            return {k: (v, c) for k, v, c in cur.fetchall()}
    except Exception:
        conn.rollback()
        return {}


VIEW_RE = re.compile(r"CREATE\s+OR\s+REPLACE\s+VIEW\s+(public\.[\w]+)", re.I)


def _missing_views(conn, sql: str) -> list[str]:
    """schema.sql 里声明了、但库里还不存在的视图。

    为什么需要：ERP 的 20 个 erp_* 视图透传到 mes_* 真表，而应用按名字排序执行时
    ERP 排在 MES 前面 —— 第一轮视图必然因依赖表缺失被跳过。有了这个检查，
    第二轮（所有应用的表都建完之后）就能把视图补回来。
    """
    names = VIEW_RE.findall(sql)
    if not names:
        return []
    missing = []
    with conn.cursor() as cur:
        for n in dict.fromkeys(names):
            cur.execute("SELECT to_regclass(%s)", (n,))
            if cur.fetchone()[0] is None:
                missing.append(n)
    conn.rollback()
    return missing


def apply_one(conn, key: str, version: str, sql: str, checksum: str) -> None:
    """执行一个应用的 schema.sql 并记录。

    psycopg2 的 execute 走 simple query protocol，整个文件作为一个隐式事务：
    要么全成功，要么全回滚 —— 不会留下建了一半的表。

    注意：schema.sql 里不要写 CREATE INDEX CONCURRENTLY（不能在事务里跑）。
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute(
            """
            INSERT INTO app_schema_versions (app_key, version, checksum, applied_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (app_key) DO UPDATE
               SET version    = EXCLUDED.version,
                   checksum   = EXCLUDED.checksum,
                   applied_at = now()
            """,
            (key, version, checksum),
        )
    conn.commit()


def sync_builtin_apps(apps_dir: Path, manifests: dict) -> list[SchemaResult]:
    """对声明了 schema_managed 的内置应用执行 schema.sql。

    manifests: key -> AppManifest（由 scan_app_manifests() 产出）
    """
    allow = enabled_apps()

    results: list[SchemaResult] = []
    targets: list[tuple[str, str, str, str]] = []

    for key, mf in sorted(manifests.items()):
        if not getattr(mf, "schema_managed", False):
            continue
        if allow is not None and key not in allow:
            results.append(SchemaResult(key, "disabled", "CENKOR_APPS 未包含"))
            continue
        got = read_schema(apps_dir / key, getattr(mf, "schema_file", SCHEMA_FILENAME))
        if got is None:
            results.append(SchemaResult(key, "no_schema", "缺少 schema.sql"))
            log.warning("app.schema.missing", key=key)
            continue
        targets.append((key, mf.version, got[0], got[1]))

    if not targets:
        return results

    import psycopg2  # 局部导入：只有真要跑 DDL 时才需要

    conn = psycopg2.connect(_sync_dsn())
    try:
        done = _applied(conn)

        def _run(key, version, sql, checksum, note="") -> bool:
            try:
                apply_one(conn, key, version, sql, checksum)
                results.append(SchemaResult(key, "applied", f"v{version}{note}"))
                log.info("app.schema.applied", key=key, version=version, note=note)
                return True
            except Exception as exc:
                conn.rollback()
                msg = str(exc).strip().splitlines()[0][:200]
                results.append(SchemaResult(key, "failed", msg))
                log.error("app.schema.failed", key=key, error=msg)
                return False

        # 第一轮：建表。视图因依赖其他应用的表，可能大量跳过，交给第二轮。
        for key, version, sql, checksum in targets:
            if done.get(key) == (version, checksum) and not _missing_views(conn, sql):
                results.append(SchemaResult(key, "skipped", f"v{version} 未变化"))
                continue
            _run(key, version, sql, checksum)

        # 第二轮：所有应用的表都建完了，把第一轮跳过的视图补回来。
        # 典型场景：ERP 排在 MES 之前，erp_* 视图依赖 mes_* 表。
        for key, version, sql, checksum in targets:
            miss = _missing_views(conn, sql)
            if miss:
                log.info("app.schema.views_retry", key=key, missing=len(miss))
                _run(key, version, sql, checksum, note=f"，补 {len(miss)} 视图")
    finally:
        conn.close()

    return results


def summarize(results: list[SchemaResult]) -> str:
    """一行摘要，便于写进启动日志。"""
    if not results:
        return "无 schema 托管应用"
    parts = [f"{r.key}={r.status}" for r in results]
    return " ".join(parts)
