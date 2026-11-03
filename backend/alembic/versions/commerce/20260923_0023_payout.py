"""developer payout account

Revision ID: 20260923_0023_payout
Revises: 20260923_0022_marketplace
Create Date: 2026-09-23
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260923_0023_payout"
down_revision = "20260923_0022_marketplace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dev_payout_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("developer_id", sa.Integer(), nullable=False),
        sa.Column("account_type", sa.String(length=20), nullable=False, server_default="alipay"),
        sa.Column("account_no", sa.String(length=200), nullable=True),
        sa.Column("account_name", sa.String(length=120), nullable=True),
        sa.Column("bank_name", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dev_payout_accounts_developer_id", "dev_payout_accounts",
                    ["developer_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_dev_payout_accounts_developer_id", table_name="dev_payout_accounts")
    op.drop_table("dev_payout_accounts")
