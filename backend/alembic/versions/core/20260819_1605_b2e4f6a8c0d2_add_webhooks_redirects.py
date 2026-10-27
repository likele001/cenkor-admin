"""add_webhooks_redirects

M3·P2：system_webhooks（事件订阅）+ system_redirects（URL 重定向）。

Revision ID: b2e4f6a8c0d2
Revises: a9b8c7d6e5f4
Create Date: 2026-08-19 16:05:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b2e4f6a8c0d2"
down_revision: str | Sequence[str] | None = "a9b8c7d6e5f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_webhooks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column(
            "events",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("secret", sa.String(128), nullable=True),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "system_redirects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("from_path", sa.String(500), nullable=False),
        sa.Column("to_path", sa.String(500), nullable=False),
        sa.Column("code", sa.Integer(), nullable=False, server_default=sa.text("301")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("from_path", name="uq_redirect_from_path"),
    )
    op.create_index("ix_system_redirects_from_path", "system_redirects", ["from_path"])


def downgrade() -> None:
    op.drop_index("ix_system_redirects_from_path", table_name="system_redirects")
    op.drop_table("system_redirects")
    op.drop_table("system_webhooks")
