"""upgrade_runs 加 notes 列 —— 升级时填写的「更新日志」

前端在升级表单加 notes textarea；升级成功后既写入本字段（自包含历史），
也软依赖 announcements App 发布一条置顶公告（30 天后 expire_at 自动 unpin）。

Revision ID: 20261018_0034_upgrade_notes
Revises: 20261015_0033_upgrade_runs
Create Date: 2026-10-18
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261018_0034_upgrade_notes"
down_revision = "20261015_0033_upgrade_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "upgrade_runs",
        sa.Column("notes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("upgrade_runs", "notes")
