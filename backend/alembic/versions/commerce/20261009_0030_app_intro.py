"""app_intros：应用富介绍（详情页长图文）旁表

门户详情页的「卖点 / 功能亮点 / 标签 / 截图 / 富文本长介绍」此前只能来自 manifest
或 showcase_meta 静态兜底，开发者后台无处可编辑。新增独立旁表 app_intros，按
(product, app_key) 唯一，独立于 app_submissions —— 即便应用尚未提交/审核也能预置介绍，
提交入库后门户详情按 DB 介绍 > manifest > SHOWCASE 优先级自动带出。

挂在公开/商业合并后的链 head 20261007_0029_product_commerce 上。纯新增表，可安全回滚。

Revision ID: 20261009_0030_app_intro
Revises: 20261007_0029_product_commerce
Create Date: 2026-10-09
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from cenkor_admin.core.compat import alembic_json

revision = "20261009_0030_app_intro"
down_revision = "20261007_0028_product_axis"
branch_labels = None
depends_on = None



def upgrade() -> None:
    JSON_TYPE = alembic_json()
    op.create_table(
        "app_intros",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product", sa.String(length=32), nullable=False, server_default="cenkor-admin"),
        sa.Column("app_key", sa.String(length=50), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("highlights", JSON_TYPE(), nullable=True),
        sa.Column("tags", JSON_TYPE(), nullable=True),
        sa.Column("screenshots", JSON_TYPE(), nullable=True),
        sa.Column("long_description", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_app_intros"),
        sa.UniqueConstraint("product", "app_key", name="uq_app_intro_product_key"),
    )
    op.create_index("ix_app_intros_product", "app_intros", ["product"])
    op.create_index("ix_app_intros_app_key", "app_intros", ["app_key"])


def downgrade() -> None:
    op.drop_index("ix_app_intros_app_key", table_name="app_intros")
    op.drop_index("ix_app_intros_product", table_name="app_intros")
    op.drop_table("app_intros")
