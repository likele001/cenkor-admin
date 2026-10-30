"""Alembic env.py — 同步模式（async 由业务代码处理）

关于「为什么 metadata 必须尽量全」：
`alembic revision --autogenerate` 是拿 Base.metadata 和真实库做双向对比。
少加载一个 app 的 models，autogenerate 就会把那个 app 的所有表判成「库里多出来的」
并生成 drop_table —— 2026-10 就踩过：erp 的 models 是包目录（models/__init__.py）
而不是单文件 models.py，旧版循环只认 models.py 文件，ERP 74 张表全没进 metadata，
一次 autogenerate 会生成 101 个 drop_table。加载逻辑现在收在 core/model_loader.py，
与体检脚本共用，失败会打 stderr 而不是静默 pass。

关于「视图托管表」：
ERP 侧有 20 个 `erp_xxx` 在库里是**视图**，透传到 MES 的 `mes_xxx` 真表
（追溯记录要连通采购/制造/出货多段经历，共用一张真表 + 视图兼容最省）。
ORM 仍按 `erp_xxx` 映射，但库里同名对象是视图，autogenerate 会误判成
「表缺失 → create_table」。过滤规则见 core/schema_filters.py。
"""
import os

# 加载应用配置
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

sys.path.insert(0, "src")

from cenkor_admin.core.config import get_settings
from cenkor_admin.core.db import Base
from cenkor_admin.core.model_loader import load_all_models

# 把内置 + 外置 app 的 ORM 模型全部并入 Base.metadata。
# 三种目录形态、routers/ 排除、显式登记清单都在 core/model_loader.py 里，
# 体检脚本 scripts/check_schema_drift.py 共用同一份 —— 两边各写一遍迟早会对不上。
# 失败必须打到 stderr：漏加载一个 app，autogenerate 就会把那个 app 的表全判成待删。
load_all_models(verbose=True)


config = context.config
if config.config_file_name is not None:
    # disable_existing_loggers=False：本进程在 uvicorn --log-config 之后才跑迁移，
    # 默认(True)会按 alembic.ini 重排 logging、把 uvicorn.error 等已有 logger 连同
    # 它们的 RotatingFileHandler 一起禁用 —— backend/logs/hub.log 就再也写不进东西，
    # 500 的 traceback 又只剩 stdout。别把这个参数“顺手清理”掉。
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# 用 .env 的同步 URL 覆盖
# CENKOR_DATABASE_URL 可临时覆盖目标库（运维 / 演练 / 测试用），
# 不改 .env 就能对指定库跑迁移。格式：postgresql+psycopg2://user:pw@host:5432/db
config.set_main_option(
    "sqlalchemy.url",
    os.environ.get("CENKOR_DATABASE_URL") or get_settings().DATABASE_URL_SYNC,
)

target_metadata = Base.metadata

# 过滤规则放在 core 里，和 scripts/check_schema_drift.py 共用同一套 ——
# 两边各写一份的话，体检结论和 autogenerate 结论迟早会对不上。
from cenkor_admin.core.schema_filters import (
    fetch_view_names,
    make_include_object,
    scope_from_env,
)
# DDL 幂等层：库结构与 alembic_version 不同步时（历史上手工补过 DDL，
# 加上挂载点被 rebase_closed_chain 反复顺延），重跑迁移会撞
# DuplicateColumn/DuplicateTable。装上这层后「已存在就跳过」，
# 版本号漂移到哪都不炸。详见 core/migration_idempotent.py。
from cenkor_admin.core.migration_idempotent import install_idempotent_ops


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
        # 当前 schema 里的视图名，用于排除「ORM 映射到视图」的托管表
        view_names = fetch_view_names(connection)
        # 必须有这一行，否则整条迁移链静默失效。
        # SQLAlchemy 2.0 执行任何 SQL 都会隐式开启事务；alembic 的
        # begin_transaction() 检测到 in_transaction() 为 True 时退化成
        # nullcontext()、**不做 commit** —— 所有迁移的 DDL 和 alembic_version
        # 更新会在连接关闭时被整体 rollback，而命令照样打印 "Running upgrade"。
        # 2026-10-27 踩过：加了上面那行 SELECT 之后，alembic upgrade 全部不生效，
        # alembic_version 卡在 0029，0030~0035 的列只能靠手工 SQL 补。
        connection.rollback()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=make_include_object(view_names, scope_from_env()),
        )
        # 幂等层：必须在 configure 之后、run_migrations 之前装
        install_idempotent_ops(connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
