"""AI 层 schema 引导（幂等）

在应用启动时执行 ai/schema.sql 建表，并把结果记进 app_schema_versions。

设计要点：
1. **不阻塞启动**：任何异常只告警，CMS 传统功能照常可用
2. **checksum 短路**：schema.sql 没改就整段跳过，不为一条 DDL 每次启动付代价
3. **只用同步连接**：lifespan 阶段已有同步引擎的用法先例（app_schema.sync_builtin_apps）
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from loguru import logger
from sqlalchemy import create_engine, text

from cenkor_admin.core.config import get_settings

APP_KEY = "cms_ai"
VERSION = "1.1.0"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# 需要落库的核心表：用于校验 schema.sql 是否真的执行成功
_REQUIRED_TABLES = ("cms_embeddings", "cms_ai_generations")


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()[:32]


def ensure_cms_ai_schema() -> bool:
    """建 AI 层四张表。已建且 checksum 未变时直接返回 True（零 DDL）。"""
    if not SCHEMA_PATH.exists():
        logger.warning("cms_ai.schema_missing", path=str(SCHEMA_PATH))
        return False

    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    checksum = _checksum(sql)
    settings = get_settings()

    try:
        engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
    except Exception as exc:
        logger.warning("cms_ai.schema_engine_failed", error=str(exc))
        return False

    try:
        with engine.begin() as conn:
            # 1) 检查版本记录，未变则短路
            applied: str | None = None
            try:
                row = conn.execute(
                    text("SELECT checksum FROM app_schema_versions WHERE app_key = :k"),
                    {"k": APP_KEY},
                ).first()
                applied = row[0] if row else None
            except Exception:
                applied = None

            if applied == checksum:
                # 版本一致，但仍要确认表真在（防止有人手工删表）
                missing = [
                    t
                    for t in _REQUIRED_TABLES
                    if conn.execute(text("SELECT to_regclass(:t)"), {"t": t}).scalar() is None
                ]
                if not missing:
                    logger.debug("cms_ai.schema_skip", reason="checksum_unchanged")
                    return True
                logger.warning("cms_ai.schema_table_missing", tables=",".join(missing))

            # 2) 执行建表（psycopg2 支持多语句）
            try:
                conn.exec_driver_sql(sql)
            except Exception as exc:
                logger.error("cms_ai.schema_apply_failed", error=str(exc))
                return False

            # 3) 记版本
            try:
                conn.execute(
                    text(
                        "INSERT INTO app_schema_versions (app_key, version, checksum) "
                        "VALUES (:k, :v, :c) "
                        "ON CONFLICT (app_key) DO UPDATE "
                        "SET version = EXCLUDED.version, "
                        "    checksum = EXCLUDED.checksum, "
                        "    applied_at = now()"
                    ),
                    {"k": APP_KEY, "v": VERSION, "c": checksum},
                )
            except Exception as exc:
                logger.warning("cms_ai.schema_version_record_failed", error=str(exc))

            # 4) 校验
            missing = [
                t
                for t in _REQUIRED_TABLES
                if conn.execute(text("SELECT to_regclass(:t)"), {"t": t}).scalar() is None
            ]
            if missing:
                logger.error("cms_ai.schema_verify_failed", tables=",".join(missing))
                return False

        logger.info("cms_ai.schema_ready", version=VERSION, tables=len(_REQUIRED_TABLES))
        return True
    except Exception as exc:
        logger.warning("cms_ai.schema_unexpected", error=str(exc))
        return False
    finally:
        engine.dispose()
