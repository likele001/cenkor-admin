"""platform_apps 表"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260107_0004_platform_apps"
down_revision = "20260107_0003_media_news_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_apps",
        sa.Column("key", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), server_default="installed"),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uninstalled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("platform_apps")
