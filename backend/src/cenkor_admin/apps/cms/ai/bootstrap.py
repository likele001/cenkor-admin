"""AI 层 schema 校验（建表已移交 alembic）

⚠️ 2026-10-31 起，AI 五张表由 alembic 创建：
   backend/alembic/versions/core/20261031_1310_cms_ai_tables.py

本模块原先负责在启动时执行 `ai/schema.sql` 建表（方案 D）。那条路和 alembic 打架：
- 本模块在**应用启动后**跑，alembic 在**启动前**跑；
- 而 003_embed_dims / 004_vector_pgvector 两条历史 SQL 要对这几张表做 ALTER，
  等于「后来者去改还没建的表」，新装环境必然失败 ——
  所以这两条 SQL 从来没被任何脚本自动执行过，只在生产手工跑过一次。

现在本模块只剩校验职责：
1. **不阻塞启动**：任何异常只告警，CMS 传统功能照常可用；
2. 启动后确认表真的在，缺表时给出明确 error，而不是等接口 500；
3. 只用同步连接（与 alembic 一致，不受事件循环影响）。
"""

from __future__ import annotations

from loguru import logger
from sqlalchemy import create_engine, text

from cenkor_admin.core.config import get_settings

APP_KEY = "cms_ai"

# 需要落库的表：用于校验 alembic 迁移是否真的执行成功
_REQUIRED_TABLES = (
    "cms_embeddings",
    "cms_ai_generations",
    "cms_ai_providers",
    "cms_ai_capabilities",
    "cms_ai_prompts",
)


def ensure_cms_ai_schema() -> bool:
    """校验 AI 层五张表存在。只读查询，零 DDL。"""
    settings = get_settings()

    try:
        engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
    except Exception as exc:
        logger.warning(f"cms_ai.schema_engine_failed: {exc}")
        return False

    try:
        with engine.begin() as conn:
            missing = [
                t
                for t in _REQUIRED_TABLES
                if conn.execute(text("SELECT to_regclass(:t)"), {"t": t}).scalar() is None
            ]
            if missing:
                logger.error(
                    f"cms_ai.schema_verify_failed: 缺少 {','.join(missing)}"
                    "｜请执行 alembic upgrade heads（core/20261031_1310_cms_ai_tables.py）"
                )
                return False

        logger.info(f"cms_ai.schema_ready tables={len(_REQUIRED_TABLES)}")
        return True
    except Exception as exc:
        logger.error(f"cms_ai.schema_verify_error: {exc}")
        return False
    finally:
        engine.dispose()
