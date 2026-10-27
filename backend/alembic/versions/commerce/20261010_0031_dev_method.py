"""app_submissions 新增 dev_method（应用开发方式 / 交付安装目标）

门户/商店/审核/manifest 此前用 ``product != "cenkor-admin"`` 隐式区分「平台内置应用」与
「产品扩展」，无法表达「独立应用（私有化整包，仅门户售卖、不做热挂载）」这一形态，
也不能在 product 变更时保持语义稳定。新增显式字段 dev_method 三值：
- platform    平台内置应用（包内含 manifest.py + __init__.py，装进 cenkor-admin 自身）
- extension   产品扩展插件（包内含 manifest.json，交付到对应 MES 实例热挂载）
- standalone  独立应用（私有化整包，仅门户展示/售卖，不由平台或实例热挂载）

存量回填：product=='cenkor-admin' 的行置 platform（即旧「平台应用」分支），其余置
extension（即旧「扩展」分支）。加列 NOT NULL + server_default='extension'，纯增量、
可安全回滚。挂在链 head 20261009_0030_app_intro 上。

Revision ID: 20261010_0031_dev_method
Revises: 20261009_0030_app_intro
Create Date: 2026-10-10
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261010_0031_dev_method"
down_revision = "20261009_0030_app_intro"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_submissions",
        sa.Column("dev_method", sa.String(length=16), nullable=False, server_default="extension"),
    )
    op.create_index("ix_app_submissions_dev_method", "app_submissions", ["dev_method"])
    # 存量按旧隐式规则回填：cenkor-admin 平台自营 → platform；其余 → extension
    op.execute(
        "UPDATE app_submissions SET dev_method = 'platform' WHERE product = 'cenkor-admin'"
    )


def downgrade() -> None:
    op.drop_index("ix_app_submissions_dev_method", table_name="app_submissions")
    op.drop_column("app_submissions", "dev_method")
