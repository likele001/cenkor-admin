"""add register_ip to portal_users

Revision ID: 20260611_1300_portal_register_ip
Revises: 20260610_1220_app_perms
Create Date: 2026-06-11 13:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260611_1300_portal_register_ip"
down_revision: str | Sequence[str] | None = "20260610_1220_app_perms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "portal_users",
        sa.Column("register_ip", sa.String(45), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("portal_users", "register_ip")
