"""add_comments_forms

M4·P3：cms_comments（评论）+ cms_forms / cms_form_submissions（表单问卷）。

Revision ID: c3d5e7f9a1b2
Revises: b2e4f6a8c0d2
Create Date: 2026-08-19 16:30:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c3d5e7f9a1b2"
down_revision: str | Sequence[str] | None = "b2e4f6a8c0d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 评论
    op.create_table(
        "cms_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_type_key", sa.String(60), nullable=False),
        sa.Column("object_id", sa.Integer(), nullable=False),
        sa.Column(
            "parent_id", sa.Integer(),
            sa.ForeignKey("cms_comments.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("author_name", sa.String(80), nullable=False),
        sa.Column("author_email", sa.String(120), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_cms_comments_ct_object", "cms_comments", ["content_type_key", "object_id"])

    # 表单
    op.create_table(
        "cms_forms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(60), nullable=False, unique=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "fields",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("success_message", sa.String(200), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "cms_form_submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "form_id", sa.Integer(),
            sa.ForeignKey("cms_forms.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "data",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_cms_form_submissions_form_id", "cms_form_submissions", ["form_id"])


def downgrade() -> None:
    op.drop_index("ix_cms_form_submissions_form_id", table_name="cms_form_submissions")
    op.drop_table("cms_form_submissions")
    op.drop_table("cms_forms")
    op.drop_index("ix_cms_comments_ct_object", table_name="cms_comments")
    op.drop_table("cms_comments")
