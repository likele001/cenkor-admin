"""media + news + audit_logs schema

Revision ID: 20260107_0003_media_news_audit
Revises: 20260107_0002_auth_rbac
Create Date: 2026-01-07 00:02:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260107_0003_media_news_audit"
down_revision: str | Sequence[str] | None = "20260107_0002_auth_rbac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # CMS: news 已有，这里加 media
    op.create_table(
        "cms_media",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("bucket", sa.String(80), nullable=False, index=True),
        sa.Column("key", sa.String(500), nullable=False, index=True),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("mime", sa.String(120), nullable=False, index=True),
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("alt", sa.String(200), nullable=False, server_default=""),
        sa.Column("uploader_id", sa.Integer, nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # System: audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("request_id", sa.String(36), nullable=False, index=True),
        sa.Column("user_id", sa.Integer, nullable=True, index=True),
        sa.Column("tenant_id", sa.Integer, nullable=False, server_default="1", index=True),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.String(500), nullable=False, index=True),
        sa.Column("status_code", sa.Integer, nullable=False, index=True),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("diff", postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("cms_media")
