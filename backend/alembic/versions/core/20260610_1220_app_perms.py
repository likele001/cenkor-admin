"""add permissions_grants to platform_apps

Revision ID: 20260610_1220_app_perms
Revises: 20260610_1215_pwdrst
Create Date: 2026-06-10 12:20:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260610_1220_app_perms"
down_revision: str | Sequence[str] | None = "20260610_1215_pwdrst"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "platform_apps",
        sa.Column("permissions_grants",
                  sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
                  nullable=True, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("platform_apps", "permissions_grants")
