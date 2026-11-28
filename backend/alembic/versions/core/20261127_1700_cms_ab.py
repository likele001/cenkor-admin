"""页面级 A/B 实验表

Revision ID: 20261127_1700_cms_ab
Revises: 20261127_1600_seo_push
Create Date: 2026-11-27 17:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261127_1700_cms_ab"
down_revision: str | None = "20261127_1600_seo_push"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "cms_ab_tests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column(
            "entry_id",
            sa.Integer(),
            sa.ForeignKey("cms_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False, server_default=""),
        sa.Column(
            "variant_b", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("views_a", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("views_b", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_cms_ab_tests_site_id", "cms_ab_tests", ["site_id"])
    op.create_index("ix_cms_ab_tests_entry_id", "cms_ab_tests", ["entry_id"])
    op.create_index("ix_ab_entry_status", "cms_ab_tests", ["entry_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_ab_entry_status", table_name="cms_ab_tests")
    op.drop_index("ix_cms_ab_tests_entry_id", table_name="cms_ab_tests")
    op.drop_index("ix_cms_ab_tests_site_id", table_name="cms_ab_tests")
    op.drop_table("cms_ab_tests")
