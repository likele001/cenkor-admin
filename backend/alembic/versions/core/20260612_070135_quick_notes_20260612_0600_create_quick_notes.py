"""create quick_notes_notes

Revision ID: 20260612_0600
Revises:
Create Date: 2026-06-12 06:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "20260612_0600"
down_revision = "20260612_0500_my_todo_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quick_notes_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("color", sa.String(length=20), server_default="default", nullable=False),
        sa.Column("creator_id", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_quick_notes_notes_creator_id", "quick_notes_notes", ["creator_id"])


def downgrade() -> None:
    op.drop_index("ix_quick_notes_notes_creator_id", table_name="quick_notes_notes")
    op.drop_table("quick_notes_notes")
