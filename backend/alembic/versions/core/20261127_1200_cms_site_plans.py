"""建站方案编排（cms_site_plans / cms_site_plan_items）

## 背景

需求清单要的是「一句话需求 → 栏目+选题 → 确认 → 自动产出」这条链，
原来只有零件（内容引擎、AI 批量），没有编排层，也没有「方案」这个中间态。
两张表就为这个中间态服务：方案先落库、人确认、再执行，避免模型输出直接
变成生产数据。

## 执行

`alembic upgrade heads`（down_revision 指向当前 head，链路保持单头）

Revision ID: 20261127_1200_cms_site_plans
Revises: 20261104_1100_cms_search_logs
Create Date: 2026-11-27 12:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261127_1200_cms_site_plans"
down_revision: str | None = "20261104_1100_cms_search_logs"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "cms_site_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "site_id",
            sa.Integer(),
            sa.ForeignKey("cms_sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("brief", postgresql.JSONB(), nullable=True),
        sa.Column("plan_json", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column(
            "content_type_id",
            sa.Integer(),
            sa.ForeignKey("cms_content_types.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("lang", sa.String(20), nullable=False, server_default="zh-CN"),
        sa.Column("batch_job_id", sa.Integer(), nullable=True),
        sa.Column("summary", sa.String(200), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("confirmed_by", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_cms_site_plans_site_id", "cms_site_plans", ["site_id"])
    op.create_index("ix_cms_site_plans_status", "cms_site_plans", ["status"])
    op.create_index("ix_site_plans_site_status", "cms_site_plans", ["site_id", "status"])

    op.create_table(
        "cms_site_plan_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "plan_id",
            sa.Integer(),
            sa.ForeignKey("cms_site_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kind", sa.String(16), nullable=False, server_default="category"),
        sa.Column("parent_key", sa.String(64), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_cms_site_plan_items_site_id", "cms_site_plan_items", ["site_id"])
    op.create_index("ix_site_plan_items_plan_seq", "cms_site_plan_items", ["plan_id", "seq"])
    op.create_index("ix_site_plan_items_plan_kind", "cms_site_plan_items", ["plan_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_site_plan_items_plan_kind", table_name="cms_site_plan_items")
    op.drop_index("ix_site_plan_items_plan_seq", table_name="cms_site_plan_items")
    op.drop_index("ix_cms_site_plan_items_site_id", table_name="cms_site_plan_items")
    op.drop_table("cms_site_plan_items")
    op.drop_index("ix_site_plans_site_status", table_name="cms_site_plans")
    op.drop_index("ix_cms_site_plans_status", table_name="cms_site_plans")
    op.drop_index("ix_cms_site_plans_site_id", table_name="cms_site_plans")
    op.drop_table("cms_site_plans")
