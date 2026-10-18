"""codegen_runs：代码生成执行历史

后台「系统 > 代码生成」页此前只在内存里预览，下载源码包 / 安装之后没有任何留痕，
出问题时无法回答「谁、什么时候、用哪份 spec 做了什么、失败原因是什么」。新增旁表
codegen_runs 记录每次「下载源码包 / 安装到本系统」：

- spec 快照（当时提交的原始 spec，JSON，可直接「再次执行」）
- status（ok / failed）+ summary（文件数·大小 / 权限数·菜单数）
- error（失败时的后端原始报错原文）
- duration_ms（耗时）+ operator_id（操作人）
- action（generate / install）+ app_key / app_name

纯新增表，不影响任何既有数据，可安全回滚。挂在链 head 20261007_0029_product_commerce 上
（注意：0031_dev_method 只是该 head 之下的中间节点 —— ERP 应用链被 rebase 挂在 0031 之下，
真正唯一的 head 是 0029_product_commerce）。

Revision ID: 20261015_0032_codegen_runs
Revises: 20261007_0029_product_commerce
Create Date: 2026-10-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from cenkor_admin.core.compat import alembic_json

revision = "20261015_0032_codegen_runs"
down_revision = "20261007_0029_product_commerce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    JSON_TYPE = alembic_json()
    op.create_table(
        "codegen_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("app_key", sa.String(length=50), nullable=False),
        sa.Column("app_name", sa.String(length=120), nullable=True),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ok"),
        sa.Column("spec", JSON_TYPE(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("operator_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_codegen_runs"),
    )
    op.create_index("ix_codegen_runs_app_key", "codegen_runs", ["app_key"])
    op.create_index("ix_codegen_runs_created_at", "codegen_runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_codegen_runs_created_at", table_name="codegen_runs")
    op.drop_index("ix_codegen_runs_app_key", table_name="codegen_runs")
    op.drop_table("codegen_runs")
