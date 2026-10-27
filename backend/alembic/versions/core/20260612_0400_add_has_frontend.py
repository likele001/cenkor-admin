"""add has_frontend column to platform_apps

Revision ID: 20260612_0400_add_has_frontend
Revises: 20260611_1500_app_store
Create Date: 2026-06-12 04:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260612_0400_add_has_frontend"
down_revision: str | Sequence[str] | None = "20260611_1500_app_store"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "platform_apps",
        sa.Column("has_frontend", sa.Boolean, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("platform_apps", "has_frontend")
