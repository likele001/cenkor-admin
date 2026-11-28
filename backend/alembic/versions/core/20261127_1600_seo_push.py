"""收录推送队列（cms_seo_push_queue）

Revision ID: 20261127_1600_seo_push
Revises: 20261127_1500_monitor
Create Date: 2026-11-27 16:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "20261127_1600_seo_push"
down_revision: str | None = "20261127_1300_cms_sensitive"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "cms_seo_push_queue",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("engine", sa.String(16), nullable=False, server_default="indexnow"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_cms_seo_push_queue_site_id", "cms_seo_push_queue", ["site_id"])
    op.create_index("ix_seo_push_site_status", "cms_seo_push_queue", ["site_id", "status"])
    op.create_index("ix_seo_push_status", "cms_seo_push_queue", ["status"])


def downgrade() -> None:
    op.drop_index("ix_seo_push_status", table_name="cms_seo_push_queue")
    op.drop_index("ix_seo_push_site_status", table_name="cms_seo_push_queue")
    op.drop_index("ix_cms_seo_push_queue_site_id", table_name="cms_seo_push_queue")
    op.drop_table("cms_seo_push_queue")
