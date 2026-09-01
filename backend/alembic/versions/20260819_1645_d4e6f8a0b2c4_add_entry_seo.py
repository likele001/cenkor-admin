"""add_entry_seo

M4·P3 4.1 OG：cms_entries 增加 seo JSONB 元数据列。

Revision ID: d4e6f8a0b2c4
Revises: c3d5e7f9a1b2
Create Date: 2026-08-19 16:45:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d4e6f8a0b2c4"
down_revision: str | Sequence[str] | None = "c3d5e7f9a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cms_entries",
        sa.Column(
            "seo",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("cms_entries", "seo")
