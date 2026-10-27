"""add website_url to products

Revision ID: 20260108_0001_website_url
Revises: 20260107_0004_platform_apps
Create Date: 2026-06-08 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260108_0001_website_url"
down_revision: str | Sequence[str] | None = "20260107_0004_platform_apps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("cms_products", sa.Column("website_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("cms_products", "website_url")
