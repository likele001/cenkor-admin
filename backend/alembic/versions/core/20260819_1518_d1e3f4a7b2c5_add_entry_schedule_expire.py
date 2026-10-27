"""add_entry_schedule_expire

定时发布（M2·P1 2.5）：cms_entries 新增 scheduled_at / expire_at。

Revision ID: d1e3f4a7b2c5
Revises: c4a7d29e6f18
Create Date: 2026-08-19 15:18:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "d1e3f4a7b2c5"
down_revision: str | Sequence[str] | None = "c4a7d29e6f18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cms_entries",
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "cms_entries",
        sa.Column("expire_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_cms_entries_scheduled", "cms_entries",
        ["status", "scheduled_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_cms_entries_scheduled", table_name="cms_entries")
    op.drop_column("cms_entries", "expire_at")
    op.drop_column("cms_entries", "scheduled_at")
