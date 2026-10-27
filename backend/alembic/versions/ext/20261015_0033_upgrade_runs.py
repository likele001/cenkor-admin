"""upgrade_runs：核心平台在线升级日志（后台「系统 > 在线升级」页）

在线升级每次在「下载核心包 / 安装 / 失败回滚 / 手动回滚」时各写一条，成功与失败都写：
- status 标识结果（pending/running/success/failed/rolled_back）
- spec / pkg_path 记录当时用的升级包来源与位置
- log 落 stream 输出的全文（truncate 200KB）
- backup_path 指向 /www/backup/cenkor-admin/snapshot_<时间>/（升级前快照）
- error 失败时的后端原始报错 + 关键路径
- duration_ms / operator_id 耗时 + 操作人

纯新增表，不影响任何既有数据。挂在 head 0032_codegen_runs 之下 ——
历史 head 分叉已确认：0026_app_enabled(平台) 与 0027_workflow(业务应用链) 在 0029_product_commerce 汇合，
之后 0028/0030/0031 一并汇入 0029 → 0032。branch_labels=("crm_app",) 仅是 0001_crm_0001 的标签、
不构成图分叉。所以 0033 挂唯一 head 0032 即可。

Revision ID: 20261015_0033_upgrade_runs
Revises: 20261015_0032_codegen_runs
Create Date: 2026-10-15
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from cenkor_admin.core.compat import alembic_json

revision = "20261015_0033_upgrade_runs"
down_revision = "20261015_0032_codegen_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    alembic_json()
    op.create_table(
        "upgrade_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="core"),
        sa.Column("source", sa.String(length=16), nullable=False),  # url | tar_upload | git
        sa.Column("channel", sa.String(length=16), nullable=False, server_default="stable"),
        sa.Column("from_version", sa.String(length=64), nullable=True),
        sa.Column("to_version", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("backup_path", sa.Text(), nullable=True),
        sa.Column("pkg_path", sa.Text(), nullable=True),
        sa.Column("log", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("operator_id", sa.Integer(), nullable=True),
        sa.Column("rollback_from_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_upgrade_runs"),
        sa.ForeignKeyConstraint(
            ["operator_id"], ["auth_users.id"],
            name="fk_upgrade_runs_operator_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_upgrade_runs_status", "upgrade_runs", ["status"])
    op.create_index("ix_upgrade_runs_created_at", "upgrade_runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_upgrade_runs_created_at", table_name="upgrade_runs")
    op.drop_index("ix_upgrade_runs_status", table_name="upgrade_runs")
    op.drop_table("upgrade_runs")
