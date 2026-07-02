"""create app store tables

Revision ID: 20260611_1500_app_store
Revises: 20260611_1400_app_tables
Create Date: 2026-06-11 15:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from cenkor_admin.core.compat import json_column

revision: str = "20260611_1500_app_store"
down_revision: str | Sequence[str] | None = "20260611_1400_app_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_developers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, unique=True, nullable=False, index=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "app_submissions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("developer_id", sa.Integer, sa.ForeignKey("app_developers.id"), nullable=False, index=True),
        sa.Column("app_key", sa.String(50), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("icon", sa.String(10), server_default="📦"),
        sa.Column("category", sa.String(50), server_default="system"),
        sa.Column("manifest_data", json_column(), nullable=True),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("file_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), server_default="pending", index=True),
        sa.Column("review_note", sa.Text, nullable=True),
        sa.Column("reviewed_by", sa.Integer, nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("download_count", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("app_key", "version", name="uq_app_submission_key_version"),
    )


def downgrade() -> None:
    op.drop_table("app_submissions")
    op.drop_table("app_developers")
