"""drop password_resets FK to allow both auth and portal users

Revision ID: 20260610_1215_pwdrst
Revises: 20260610_1211_portaltv
Create Date: 2026-06-10 12:15:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260610_1215_pwdrst"
down_revision: str | Sequence[str] | None = "20260610_1211_portaltv"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop FK constraint without dropping the column
    op.drop_constraint("password_resets_user_id_fkey", "password_resets", type_="foreignkey")


def downgrade() -> None:
    op.create_foreign_key(
        "password_resets_user_id_fkey", "password_resets", "auth_users",
        ["user_id"], ["id"], ondelete="CASCADE",
    )
