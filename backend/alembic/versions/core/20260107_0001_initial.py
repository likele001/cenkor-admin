"""initial schema (cms app)

Revision ID: 20260107_0001_initial
Revises:
Create Date: 2026-01-07 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260107_0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # CMS: products
    op.create_table(
        "cms_products",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.String(120), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False, index=True),
        sa.Column("chinese_name", sa.String(120), nullable=True),
        sa.Column("tagline", sa.String(200), nullable=False),
        sa.Column("line", sa.String(50), nullable=False, index=True),
        sa.Column("stack", sa.String(200), nullable=False),
        sa.Column("desc", sa.Text, nullable=False),
        sa.Column("features", postgresql.JSONB, nullable=True, default=list),
        sa.Column("is_flagship", sa.Boolean, nullable=False, default=False),
        sa.Column("is_open_source", sa.Boolean, nullable=False, default=False),
        sa.Column("github_url", sa.String(500), nullable=True),
        sa.Column("demo_url", sa.String(500), nullable=True),
        sa.Column("license", sa.String(50), nullable=True),
        sa.Column("sort", sa.Integer, nullable=False, default=0),
        sa.Column("status", sa.String(20), nullable=False, default="published"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_cms_products_line_status", "cms_products", ["line", "status"])

    # CMS: cases
    op.create_table(
        "cms_cases",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("industry", sa.String(80), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("desc", sa.Text, nullable=False),
        sa.Column("tag", sa.String(80), nullable=False),
        sa.Column("href", sa.String(500), nullable=True),
        sa.Column("sort", sa.Integer, nullable=False, default=0),
        sa.Column("status", sa.String(20), nullable=False, default="published"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # CMS: news
    op.create_table(
        "cms_news",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.String(200), unique=True, nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False, index=True),
        sa.Column("excerpt", sa.String(500), nullable=False),
        sa.Column("content_md", sa.Text, nullable=False),
        sa.Column("cover_image", sa.String(500), nullable=True),
        sa.Column("author_id", sa.Integer, nullable=True, index=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("view_count", sa.Integer, nullable=False, default=0),
        sa.Column("status", sa.String(20), nullable=False, default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # CMS: site_config
    op.create_table(
        "cms_site_config",
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column("value", postgresql.JSONB, nullable=False),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column("updated_by", sa.Integer, nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("cms_site_config")
    op.drop_table("cms_news")
    op.drop_table("cms_cases")
    op.drop_table("cms_products")
