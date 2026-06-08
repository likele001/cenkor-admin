"""Alembic env.py — 同步模式（async 由业务代码处理）"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# 加载应用配置
import sys
sys.path.insert(0, "src")

from cenkor_admin.core.config import get_settings  # noqa: E402
from cenkor_admin.core.db import Base  # noqa: E402
from cenkor_admin.apps.cms import models as cms_models  # noqa: F401, E402  # 注册模型

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 用 .env 的同步 URL 覆盖
config.set_main_option("sqlalchemy.url", get_settings().DATABASE_URL_SYNC)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
