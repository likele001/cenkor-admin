"""add_i18n_languages_translations

多语言 i18n（M1·P0）：
- cms_content_types 增加 translatable 开关
- 新增 cms_languages（站点语言）
- 新增 cms_entry_translations（条目翻译）

Revision ID: c4a7d29e6f18
Revises: e0b1bc517b5f
Create Date: 2026-08-19 14:55:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c4a7d29e6f18"
down_revision: str | Sequence[str] | None = "e0b1bc517b5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. 内容类型支持多语言
    op.add_column(
        "cms_content_types",
        sa.Column(
            "translatable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # 2. 站点语言表
    op.create_table(
        "cms_languages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("flag", sa.String(20), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 3. 条目翻译表
    op.create_table(
        "cms_entry_translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "entry_id", sa.Integer(),
            sa.ForeignKey("cms_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("lang", sa.String(20), nullable=False),
        sa.Column(
            "field_values",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("entry_id", "lang", name="uq_entry_translation_lang"),
    )
    op.create_index("ix_cms_entry_translations_entry_id", "cms_entry_translations", ["entry_id"])


def downgrade() -> None:
    op.drop_index("ix_cms_entry_translations_entry_id", table_name="cms_entry_translations")
    op.drop_table("cms_entry_translations")
    op.drop_table("cms_languages")
    op.drop_column("cms_content_types", "translatable")
