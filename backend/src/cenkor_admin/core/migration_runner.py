"""启动时的迁移自愈：先查漂移，再决定 stamp 还是 upgrade。

见 core/migration_drift.py 的背景说明。本模块只做编排。

决策表
------
    待跑迁移期望的对象全在库里  → stamp 到 head（跳过重跑 DDL）
    有缺失                        → 正常 alembic upgrade（让 alembic 补齐）
    待跑集合为空                  → 什么都不做（已经是 head）

安全边界
--------
只有「100% 都在」才 stamp —— 不会跳过任何真正需要执行的 DDL。
"""
from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
import structlog
from alembic.config import Config

from cenkor_admin.core.migration_drift import check_drift

log = structlog.get_logger()


def _alembic_cfg() -> Config:
    backend_root = Path(__file__).resolve().parent.parent.parent.parent
    cfg = Config(str(backend_root / "alembic.ini"))
    # URL 解析必须与 alembic/env.py 完全一致 —— 漂移检测连的库和
    # upgrade/stamp 操作的库必须是同一个，否则「检测说没问题、实际在另一个库
    # 补 DDL」这种错位会发生。
    # env.py 的规则是 CENKOR_DATABASE_URL 优先，否则用 settings。
    import os

    from cenkor_admin.core.config import get_settings

    cfg.set_main_option(
        "sqlalchemy.url",
        os.environ.get("CENKOR_DATABASE_URL") or get_settings().DATABASE_URL_SYNC,
    )
    return cfg


def run_migrations_with_drift_guard() -> str:
    """执行启动迁移，返回结果标记：stamped / upgraded / skipped。

    任何异常都向上抛 —— 由调用方（main.py）决定怎么记日志。
    不在这里吞异常：迁移失败必须显式告警。
    """
    from alembic import command

    cfg = _alembic_cfg()
    db_url = cfg.get_main_option("sqlalchemy.url")

    engine = sa.create_engine(db_url, pool_pre_ping=True)
    with engine.connect() as conn:
        report = check_drift(cfg, conn)
        conn.commit()

    log.info(
        "migration.drift_checked",
        current=report.current,
        heads=report.heads,
        pending=len(report.pending),
        expected_objects=report.expected.total(),
        missing=report.missing_total,
    )

    if not report.pending:
        log.info("migration.skip", reason="已是 head")
        return "skipped"

    if report.ok:
        # 库结构已完全达到 head 期望 —— 只是版本号落后，重跑 DDL 只会撞
        # DuplicateColumn/DuplicateTable。stamp 是安全且唯一正确的动作。
        log.warning(
            "migration.drift_detected",
            detail=report.summary(),
            pending=len(report.pending),
        )
        command.stamp(cfg, "heads")
        log.info("migration.stamped", target=report.heads)
        return "stamped"

    log.warning(
        "migration.drift_detected",
        detail=report.summary(),
        missing_tables=report.missing_tables[:20],
        missing_columns=report.missing_columns[:20],
        missing_indexes=report.missing_indexes[:20],
        missing_uniques=report.missing_uniques[:20],
    )
    command.upgrade(cfg, "heads")
    log.info("migration.upgraded", target=report.heads)
    return "upgraded"
