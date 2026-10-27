"""create announcements, tickets, links tables

Revision ID: 20260611_1400_app_tables
Revises: 20260611_1300_portal_register_ip
Create Date: 2026-06-11 14:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from cenkor_admin.core.compat import json_column

revision: str = "20260611_1400_app_tables"
down_revision: str | Sequence[str] | None = "20260611_1300_portal_register_ip"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Announcements
    op.create_table(
        "announcements",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(200), nullable=False, index=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("summary", sa.String(500), nullable=True),
        sa.Column("category", sa.String(50), server_default="general"),
        sa.Column("priority", sa.String(20), server_default="normal"),
        sa.Column("is_pinned", sa.Boolean, server_default="false"),
        sa.Column("is_published", sa.Boolean, server_default="false"),
        sa.Column("publish_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expire_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("author_id", sa.Integer, nullable=True, index=True),
        sa.Column("view_count", sa.Integer, server_default="0"),
        sa.Column("extra", json_column(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Tickets
    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(200), nullable=False, index=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), server_default="open", index=True),
        sa.Column("priority", sa.String(20), server_default="normal"),
        sa.Column("category", sa.String(50), server_default="general"),
        sa.Column("creator_id", sa.Integer, nullable=False, index=True),
        sa.Column("assignee_id", sa.Integer, nullable=True, index=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra", json_column(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "ticket_comments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ticket_id", sa.Integer, nullable=False, index=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Links
    op.create_table(
        "links",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("url", sa.String(2000), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("category", sa.String(50), server_default="general"),
        sa.Column("favicon", sa.String(500), nullable=True),
        sa.Column("is_favorite", sa.Boolean, server_default="false"),
        sa.Column("click_count", sa.Integer, server_default="0"),
        sa.Column("creator_id", sa.Integer, nullable=False, index=True),
        sa.Column("extra", json_column(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("links")
    op.drop_table("ticket_comments")
    op.drop_table("tickets")
    op.drop_table("announcements")
