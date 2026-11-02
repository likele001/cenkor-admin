"""栏目级文章 URL 规则 + 栏目级模板

cms_categories 新增两列（均可空，空 = 继承站点默认）：
- article_pattern  该栏目下「文章内容页」的地址规则，变量集同 article
  （{type} {catdir} {cat} {slug} {id} {year} {month} {day}）。
  注意与 url_pattern 的分工：url_pattern 只管栏目页自己的地址，
  article_pattern 只管该栏目下条目的详情页地址 —— 两层规则正交。
- template         该栏目页面用的主题内模板文件名（如 list.html），
  空 = 用 KIND_TEMPLATE 按 kind 走默认。文件不存在时渲染层自动回退。

Revision ID: 20261102_1210_cms_cat_url_tpl   （27 字符，alembic 上限 32）
Revises: 20261031_1600_cms_permalink
Create Date: 2026-11-02 12:10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261102_1210_cms_cat_url_tpl"
down_revision: str | Sequence[str] | None = "20261031_1600_cms_permalink"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cms_categories",
        sa.Column("article_pattern", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "cms_categories",
        sa.Column("template", sa.String(length=120), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cms_categories", "template")
    op.drop_column("cms_categories", "article_pattern")
