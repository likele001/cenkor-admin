"""add token_version to portal_users

Revision ID: 20260610_1211_portaltv
Revises: 20260610_0001_content_engine
Create Date: 2026-06-10 12:11:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260610_1211_portaltv"
down_revision: str | Sequence[str] | None = "20260610_0001_content_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("portal_users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("portal_users", "token_version")
