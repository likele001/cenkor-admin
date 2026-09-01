"""ERP App Phase 8 — 采购申请+审批流 + 制造深化

新增：采购申请(PR/明细/审批记录) / 工作中心/工艺路线/工艺步骤/生产排程

Revision ID: 20260901_0007_pr_routing_schedule
Revises: 20260901_0006_gl_wh_mfg
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260901_0007_pr_routing_schedule"
down_revision = "20260901_0006_gl_wh_mfg"
branch_labels = None
depends_on = None


def _table_exists(tbl: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return insp.has_table(tbl)


def upgrade() -> None:
    # ========== 采购申请（PR）+ 审批流 ==========
    if not _table_exists("erp_purchase_requests"):
        op.create_table(
            "erp_purchase_requests",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(32), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
            sa.Column("title", sa.String(128), nullable=True),
            sa.Column("requester", sa.String(64), nullable=True),
            sa.Column("department", sa.String(64), nullable=True),
            sa.Column("required_date", sa.Date(), nullable=True),
            sa.Column("urgency", sa.String(8), nullable=False, server_default="normal"),
            sa.Column("expected_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("currency", sa.String(8), nullable=False, server_default="CNY"),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("current_level", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("approver_user_id", sa.Integer(), nullable=True),
            sa.Column("approver_name", sa.String(64), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reject_reason", sa.String(255), nullable=True),
            sa.Column("purchase_order_id", sa.Integer(), nullable=True),
            sa.Column("owner_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["purchase_order_id"], ["erp_purchase_orders.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("code", name="uq_erp_purchase_requests_code"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_purchase_requests_purchase_order_id", "erp_purchase_requests", ["purchase_order_id"])

    if not _table_exists("erp_purchase_request_items"):
        op.create_table(
            "erp_purchase_request_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("request_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("product_code", sa.String(32), nullable=True),
            sa.Column("product_name", sa.String(128), nullable=True),
            sa.Column("spec", sa.String(128), nullable=True),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("converted_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("unit", sa.String(16), nullable=True),
            sa.Column("expected_price", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("need_date", sa.Date(), nullable=True),
            sa.Column("remark", sa.String(255), nullable=True),
            sa.Column("sort", sa.Integer(), default=0),
            sa.ForeignKeyConstraint(["request_id"], ["erp_purchase_requests.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["product_id"], ["erp_products.id"], ondelete="SET NULL"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_purchase_request_items_request_id", "erp_purchase_request_items", ["request_id"])

    if not _table_exists("erp_approval_records"):
        op.create_table(
            "erp_approval_records",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("request_id", sa.Integer(), nullable=True),
            sa.Column("ref_type", sa.String(32), nullable=False, server_default="purchase_request"),
            sa.Column("ref_id", sa.Integer(), nullable=True),
            sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("decision", sa.String(16), nullable=False),
            sa.Column("comment", sa.String(255), nullable=True),
            sa.Column("approver_user_id", sa.Integer(), nullable=True),
            sa.Column("approver_name", sa.String(64), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["request_id"], ["erp_purchase_requests.id"], ondelete="CASCADE"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_approval_records_request_id", "erp_approval_records", ["request_id"])

    # ========== 制造深化（工作中心/工艺路线/排程） ==========
    if not _table_exists("erp_work_centers"):
        op.create_table(
            "erp_work_centers",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(32), nullable=False),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("wc_type", sa.String(32), nullable=False, server_default="machine"),
            sa.Column("location", sa.String(128), nullable=True),
            sa.Column("capacity", sa.Numeric(10, 2), nullable=False, server_default="8"),
            sa.Column("unit", sa.String(16), nullable=True),
            sa.Column("labor_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("remark", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("code", name="uq_erp_work_centers_code"),
            mysql_engine="InnoDB",
        )

    if not _table_exists("erp_routings"):
        op.create_table(
            "erp_routings",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("product_code", sa.String(32), nullable=True),
            sa.Column("product_name", sa.String(128), nullable=True),
            sa.Column("name", sa.String(128), nullable=True),
            sa.Column("version", sa.String(16), nullable=False, server_default="V1"),
            sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("output_qty", sa.Numeric(18, 4), nullable=False, server_default="1"),
            sa.Column("unit", sa.String(16), nullable=True),
            sa.Column("lead_time_hours", sa.Numeric(10, 2), nullable=False, server_default="0"),
            sa.Column("remark", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["product_id"], ["erp_products.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("product_id", "version", name="uq_erp_routings_product_version"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_routings_product_id", "erp_routings", ["product_id"])

    if not _table_exists("erp_routing_steps"):
        op.create_table(
            "erp_routing_steps",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("routing_id", sa.Integer(), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("process_code", sa.String(32), nullable=True),
            sa.Column("process_name", sa.String(64), nullable=False),
            sa.Column("work_center_id", sa.Integer(), nullable=True),
            sa.Column("work_center_name", sa.String(128), nullable=True),
            sa.Column("std_time", sa.Numeric(10, 4), nullable=False, server_default="0"),
            sa.Column("setup_minutes", sa.Numeric(10, 2), nullable=False, server_default="0"),
            sa.Column("time_type", sa.String(8), nullable=False, server_default="per_unit"),
            sa.Column("yield_rate", sa.Numeric(6, 2), nullable=False, server_default="100"),
            sa.Column("is_last", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("sort", sa.Integer(), default=0),
            sa.ForeignKeyConstraint(["routing_id"], ["erp_routings.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["work_center_id"], ["erp_work_centers.id"], ondelete="SET NULL"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_routing_steps_routing_id", "erp_routing_steps", ["routing_id"])
        op.create_index("ix_erp_routing_steps_work_center_id", "erp_routing_steps", ["work_center_id"])

    if not _table_exists("erp_production_schedules"):
        op.create_table(
            "erp_production_schedules",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(32), nullable=False),
            sa.Column("work_order_id", sa.Integer(), nullable=True),
            sa.Column("work_order_code", sa.String(32), nullable=True),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("product_code", sa.String(32), nullable=True),
            sa.Column("product_name", sa.String(128), nullable=True),
            sa.Column("routing_id", sa.Integer(), nullable=True),
            sa.Column("step_id", sa.Integer(), nullable=True),
            sa.Column("step_seq", sa.Integer(), nullable=True),
            sa.Column("process_name", sa.String(64), nullable=True),
            sa.Column("work_center_id", sa.Integer(), nullable=True),
            sa.Column("work_center_name", sa.String(128), nullable=True),
            sa.Column("plan_date", sa.Date(), nullable=True),
            sa.Column("plan_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("done_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("plan_hours", sa.Numeric(10, 2), nullable=False, server_default="0"),
            sa.Column("status", sa.String(16), nullable=False, server_default="planned"),
            sa.Column("remark", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["work_order_id"], ["erp_work_orders.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["work_center_id"], ["erp_work_centers.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("code", name="uq_erp_production_schedules_code"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_production_schedules_work_order_id", "erp_production_schedules", ["work_order_id"])
        op.create_index("ix_erp_production_schedules_work_center_id", "erp_production_schedules", ["work_center_id"])
        op.create_index("ix_erp_production_schedules_product_id", "erp_production_schedules", ["product_id"])


def downgrade() -> None:
    for tbl in (
        "erp_production_schedules", "erp_routing_steps", "erp_routings", "erp_work_centers",
        "erp_approval_records", "erp_purchase_request_items", "erp_purchase_requests",
    ):
        if _table_exists(tbl):
            op.drop_table(tbl)