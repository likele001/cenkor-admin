"""add_entry_versions

内容版本控制（M1·P0）：新增 cms_entry_versions 快照表。

Revision ID: e0b1bc517b5f
Revises: 20260807_1347
Create Date: 2026-08-19 14:41:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e0b1bc517b5f"
down_revision: str | Sequence[str] | None = "20260807_1347"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 版本快照表（data 存整条 Entry 的可变字段）
    op.create_table(
        "cms_entry_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "entry_id", sa.Integer(),
            sa.ForeignKey("cms_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "data",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("entry_id", "version", name="uq_entry_version"),
    )
    op.create_index("ix_cms_entry_versions_entry_id", "cms_entry_versions", ["entry_id"])


def downgrade() -> None:
    op.drop_index("ix_cms_entry_versions_entry_id", table_name="cms_entry_versions")
    op.drop_table("cms_entry_versions")
