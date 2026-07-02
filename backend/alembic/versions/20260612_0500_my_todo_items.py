"""create my_todo_items table for my_todo app

Revision ID: 20260612_0500_my_todo_items
Revises: 20260612_0400_add_has_frontend
Create Date: 2026-06-12 05:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260612_0500_my_todo_items"
down_revision: str | Sequence[str] | None = "20260612_0400_add_has_frontend"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "my_todo_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("done", sa.Boolean, server_default=sa.text("false")),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("creator_id", sa.Integer, nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("my_todo_items")
