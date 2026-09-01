"""add_builder_pages

M3·P2 3.2 可视化页面构建器：cms_pages。

Revision ID: e5f7a9b1c3d5
Revises: d4e6f8a0b2c4
Create Date: 2026-08-19 17:00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e5f7a9b1c3d5"
down_revision: str | Sequence[str] | None = "d4e6f8a0b2c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cms_pages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(60), nullable=False, unique=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column(
            "schema",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_cms_pages_status", "cms_pages", ["status"])


def downgrade() -> None:
    op.drop_index("ix_cms_pages_status", table_name="cms_pages")
    op.drop_table("cms_pages")
