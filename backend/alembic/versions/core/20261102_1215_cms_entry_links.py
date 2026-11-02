"""内链关系表 cms_entry_links

文章互链（source → target）+ 锚文本 + 审核状态机
（pending 待审核 / approved 已通过 / inserted 已插入正文 / rejected 已拒绝）。
与 cms_content_tags（主题标签）互补：标签管「文章↔主题词」，内链管「文章↔文章」。

唯一约束是部分索引（排除 rejected）：拒绝后允许对同一条重新建议。

Revision ID: 20261102_1215_cms_entry_links   （28 字符，alembic 上限 32）
Revises: 20261102_1210_cms_cat_url_tpl
Create Date: 2026-11-02 12:15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261102_1215_cms_entry_links"
down_revision: str | Sequence[str] | None = "20261102_1210_cms_cat_url_tpl"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cms_entry_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_entry_id", sa.Integer(), nullable=False),
        sa.Column("target_entry_id", sa.Integer(), nullable=False),
        sa.Column("anchor_text", sa.String(length=120), nullable=False),
        sa.Column("insert_after", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(["site_id"], ["cms_sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_entry_id"], ["cms_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_entry_id"], ["cms_entries.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_cms_entry_links_site_src", "cms_entry_links", ["site_id", "source_entry_id"],
    )
    op.create_index(
        "ix_cms_entry_links_site_tgt", "cms_entry_links", ["site_id", "target_entry_id"],
    )
    op.create_index("ix_cms_entry_links_status", "cms_entry_links", ["status"])
    # 部分唯一索引：排除 rejected，拒绝后可重新建议同一条
    op.create_index(
        "uq_entry_link_src_tgt_anchor",
        "cms_entry_links",
        ["source_entry_id", "target_entry_id", "anchor_text"],
        unique=True,
        postgresql_where=sa.text("status <> 'rejected'"),
    )


def downgrade() -> None:
    op.drop_index("uq_entry_link_src_tgt_anchor", table_name="cms_entry_links")
    op.drop_index("ix_cms_entry_links_status", table_name="cms_entry_links")
    op.drop_index("ix_cms_entry_links_site_tgt", table_name="cms_entry_links")
    op.drop_index("ix_cms_entry_links_site_src", table_name="cms_entry_links")
    op.drop_table("cms_entry_links")
