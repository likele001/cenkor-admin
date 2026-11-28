"""敏感词库（cms_sensitive_words）

Revision ID: 20261127_1300_cms_sensitive
Revises: 20261127_1200_cms_site_plans
Create Date: 2026-11-27 13:00

注：revision 长度必须 ≤32（alembic_version.version_num 是 varchar(32)），
所以这里不带 _words 后缀。
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "20261127_1300_cms_sensitive"
down_revision: str | None = "20261127_1200_cms_site_plans"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "cms_sensitive_words",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), nullable=True),
        sa.Column("scope", sa.String(8), nullable=False, server_default="site"),
        sa.Column("word", sa.String(120), nullable=False),
        sa.Column("level", sa.String(8), nullable=False, server_default="warn"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_sensitive_words_site", "cms_sensitive_words", ["site_id"])
    op.create_index("ix_sensitive_words_level", "cms_sensitive_words", ["level"])


def downgrade() -> None:
    op.drop_index("ix_sensitive_words_level", table_name="cms_sensitive_words")
    op.drop_index("ix_sensitive_words_site", table_name="cms_sensitive_words")
    op.drop_table("cms_sensitive_words")
