"""add_entry_previews

M4·P3 4.4 staging：cms_entry_previews（暂存预览 token）。

Revision ID: f6a8b0c2d4e6
Revises: e5f7a9b1c3d5
Create Date: 2026-08-19 17:40:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "f6a8b0c2d4e6"
down_revision: str | Sequence[str] | None = "e5f7a9b1c3d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cms_entry_previews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "entry_id", sa.Integer(),
            sa.ForeignKey("cms_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_cms_entry_previews_entry_id", "cms_entry_previews", ["entry_id"])
    op.create_index("ix_cms_entry_previews_token", "cms_entry_previews", ["token"])


def downgrade() -> None:
    op.drop_index("ix_cms_entry_previews_token", table_name="cms_entry_previews")
    op.drop_index("ix_cms_entry_previews_entry_id", table_name="cms_entry_previews")
    op.drop_table("cms_entry_previews")
