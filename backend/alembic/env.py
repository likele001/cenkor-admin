"""Alembic env.py — 同步模式（async 由业务代码处理）"""
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# 加载应用配置
import sys
sys.path.insert(0, "src")

from cenkor_admin.core.config import get_settings  # noqa: E402
from cenkor_admin.core.db import Base  # noqa: E402
# 导入所有 app 的 models，确保 autogenerate 能感知全部表，避免误生成 drop 全表的迁移
import importlib, os
import cenkor_admin.apps as _apps_pkg  # noqa: F401
_APPS_DIR = os.path.dirname(_apps_pkg.__file__)
for _name in sorted(os.listdir(_APPS_DIR)):
    if _name.startswith("_"):
        continue
    _modfile = os.path.join(_APPS_DIR, _name, "models.py")
    if os.path.isfile(_modfile):
        try:
            importlib.import_module(f"cenkor_admin.apps.{_name}.models")  # noqa: F401
        except Exception:
            pass

# 外置应用目录（独立/商业应用，默认不进公开仓库）同样纳入 metadata，
# 否则 `alembic revision --autogenerate` 会把它们的表误判为待删除。
_EXTERNAL_APPS_DIR = os.path.join(os.path.dirname(os.path.dirname(_APPS_DIR)), "apps")
if os.path.isdir(_EXTERNAL_APPS_DIR):
    for _name in sorted(os.listdir(_EXTERNAL_APPS_DIR)):
        if _name.startswith("_"):
            continue
        _modfile = os.path.join(_EXTERNAL_APPS_DIR, _name, "models.py")
        if os.path.isfile(_modfile):
            try:
                importlib.import_module(f"cenkor_admin.apps.{_name}.models")  # noqa: F401
            except Exception:
                pass

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
