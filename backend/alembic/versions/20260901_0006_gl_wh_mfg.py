"""ERP App Phase 7 — 财务闭环 + 仓储深度 + 制造基础

新增：总账(科目/期间/凭证/分录) / 库位/批次/序列号/盘点 / BOM/工单/报工/质检

Revision ID: 20260901_0006_gl_wh_mfg
Revises: 20260831_0005_fin
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260901_0006_gl_wh_mfg"
down_revision = "20260831_0005_fin"
branch_labels = None
depends_on = None


def _table_exists(tbl: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return insp.has_table(tbl)


def upgrade() -> None:
    # ========== 总账（GL）==========
    if not _table_exists("erp_accounts"):
        op.create_table(
            "erp_accounts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(20), nullable=False),
            sa.Column("name", sa.String(64), nullable=False),
            sa.Column("category", sa.String(16), nullable=False),
            sa.Column("direction", sa.String(8), nullable=False, server_default="debit"),
            sa.Column("parent_id", sa.Integer(), nullable=True),
            sa.Column("is_leaf", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("initial_balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("code", name="uq_erp_accounts_code"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_accounts_parent_id", "erp_accounts", ["parent_id"])

    if not _table_exists("erp_accounting_periods"):
        op.create_table(
            "erp_accounting_periods",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("period", sa.String(7), nullable=False),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="open"),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("period", name="uq_erp_accounting_periods_period"),
            mysql_engine="InnoDB",
        )

    if not _table_exists("erp_vouchers"):
        op.create_table(
            "erp_vouchers",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(32), nullable=False),
            sa.Column("period", sa.String(7), nullable=False),
            sa.Column("voucher_date", sa.Date(), nullable=False),
            sa.Column("word", sa.String(16), nullable=True),
            sa.Column("source_type", sa.String(32), nullable=True),
            sa.Column("source_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
            sa.Column("total_debit", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("total_credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("remark", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("code", name="uq_erp_vouchers_code"),
            mysql_engine="InnoDB",
        )

    if not _table_exists("erp_voucher_entries"):
        op.create_table(
            "erp_voucher_entries",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("voucher_id", sa.Integer(), nullable=False),
            sa.Column("account_id", sa.Integer(), nullable=True),
            sa.Column("account_code", sa.String(20), nullable=True),
            sa.Column("account_name", sa.String(64), nullable=True),
            sa.Column("summary", sa.String(255), nullable=True),
            sa.Column("debit", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(["voucher_id"], ["erp_vouchers.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["account_id"], ["erp_accounts.id"], ondelete="SET NULL"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_voucher_entries_voucher_id", "erp_voucher_entries", ["voucher_id"])
        op.create_index("ix_erp_voucher_entries_account_id", "erp_voucher_entries", ["account_id"])

    # ========== 仓储深度 ==========
    if not _table_exists("erp_stock_locations"):
        op.create_table(
            "erp_stock_locations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("warehouse_id", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(32), nullable=False),
            sa.Column("name", sa.String(128), nullable=True),
            sa.Column("area", sa.String(64), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("remarks", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["warehouse_id"], ["erp_warehouses.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("warehouse_id", "code", name="uq_erp_stock_locations_wh_code"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_stock_locations_warehouse_id", "erp_stock_locations", ["warehouse_id"])

    if not _table_exists("erp_batches"):
        op.create_table(
            "erp_batches",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("batch_no", sa.String(64), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("product_code", sa.String(32), nullable=True),
            sa.Column("product_name", sa.String(128), nullable=True),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("production_date", sa.Date(), nullable=True),
            sa.Column("expiry_date", sa.Date(), nullable=True),
            sa.Column("supplier_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["product_id"], ["erp_products.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("batch_no", name="uq_erp_batches_batch_no"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_batches_product_id", "erp_batches", ["product_id"])

    if not _table_exists("erp_serials"):
        op.create_table(
            "erp_serials",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("serial_no", sa.String(64), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("product_code", sa.String(32), nullable=True),
            sa.Column("product_name", sa.String(128), nullable=True),
            sa.Column("batch_id", sa.Integer(), nullable=True),
            sa.Column("warehouse_id", sa.Integer(), nullable=True),
            sa.Column("location_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="in_stock"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["product_id"], ["erp_products.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["warehouse_id"], ["erp_warehouses.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("serial_no", name="uq_erp_serials_serial_no"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_serials_product_id", "erp_serials", ["product_id"])
        op.create_index("ix_erp_serials_warehouse_id", "erp_serials", ["warehouse_id"])

    if not _table_exists("erp_stocktakes"):
        op.create_table(
            "erp_stocktakes",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(32), nullable=False),
            sa.Column("warehouse_id", sa.Integer(), nullable=True),
            sa.Column("location_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
            sa.Column("take_date", sa.Date(), nullable=True),
            sa.Column("remark", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["warehouse_id"], ["erp_warehouses.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("code", name="uq_erp_stocktakes_code"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_stocktakes_warehouse_id", "erp_stocktakes", ["warehouse_id"])

    if not _table_exists("erp_stocktake_items"):
        op.create_table(
            "erp_stocktake_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("stocktake_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("product_code", sa.String(32), nullable=True),
            sa.Column("product_name", sa.String(128), nullable=True),
            sa.Column("unit", sa.String(16), nullable=True),
            sa.Column("book_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("actual_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("diff_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("remark", sa.String(255), nullable=True),
            sa.ForeignKeyConstraint(["stocktake_id"], ["erp_stocktakes.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["product_id"], ["erp_products.id"], ondelete="SET NULL"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_stocktake_items_stocktake_id", "erp_stocktake_items", ["stocktake_id"])

    # ========== 制造基础 ==========
    if not _table_exists("erp_boms"):
        op.create_table(
            "erp_boms",
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
            sa.Column("remark", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["product_id"], ["erp_products.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("product_id", "version", name="uq_erp_boms_product_version"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_boms_product_id", "erp_boms", ["product_id"])

    if not _table_exists("erp_bom_items"):
        op.create_table(
            "erp_bom_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("bom_id", sa.Integer(), nullable=False),
            sa.Column("component_id", sa.Integer(), nullable=True),
            sa.Column("component_code", sa.String(32), nullable=True),
            sa.Column("component_name", sa.String(128), nullable=True),
            sa.Column("spec", sa.String(128), nullable=True),
            sa.Column("unit", sa.String(16), nullable=True),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("loss_rate", sa.Numeric(6, 2), nullable=False, server_default="0"),
            sa.Column("is_substitute", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("substitute_for", sa.String(32), nullable=True),
            sa.Column("sort", sa.Integer(), default=0),
            sa.ForeignKeyConstraint(["bom_id"], ["erp_boms.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["component_id"], ["erp_products.id"], ondelete="SET NULL"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_bom_items_bom_id", "erp_bom_items", ["bom_id"])

    if not _table_exists("erp_work_orders"):
        op.create_table(
            "erp_work_orders",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(32), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("product_code", sa.String(32), nullable=True),
            sa.Column("product_name", sa.String(128), nullable=True),
            sa.Column("bom_id", sa.Integer(), nullable=True),
            sa.Column("sales_order_id", sa.Integer(), nullable=True),
            sa.Column("warehouse_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("produced_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("unit", sa.String(16), nullable=True),
            sa.Column("remark", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["product_id"], ["erp_products.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["warehouse_id"], ["erp_warehouses.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("code", name="uq_erp_work_orders_code"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_work_orders_product_id", "erp_work_orders", ["product_id"])
        op.create_index("ix_erp_work_orders_warehouse_id", "erp_work_orders", ["warehouse_id"])

    if not _table_exists("erp_work_order_items"):
        op.create_table(
            "erp_work_order_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("work_order_id", sa.Integer(), nullable=False),
            sa.Column("component_id", sa.Integer(), nullable=True),
            sa.Column("component_code", sa.String(32), nullable=True),
            sa.Column("component_name", sa.String(128), nullable=True),
            sa.Column("unit", sa.String(16), nullable=True),
            sa.Column("need_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("issued_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(["work_order_id"], ["erp_work_orders.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["component_id"], ["erp_products.id"], ondelete="SET NULL"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_work_order_items_work_order_id", "erp_work_order_items", ["work_order_id"])

    if not _table_exists("erp_op_reports"):
        op.create_table(
            "erp_op_reports",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("work_order_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("product_code", sa.String(32), nullable=True),
            sa.Column("product_name", sa.String(128), nullable=True),
            sa.Column("process_name", sa.String(64), nullable=True),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("qualified_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("reject_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("work_hours", sa.Numeric(10, 2), nullable=False, server_default="0"),
            sa.Column("operator", sa.String(64), nullable=True),
            sa.Column("report_date", sa.Date(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="reported"),
            sa.Column("remark", sa.String(255), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["work_order_id"], ["erp_work_orders.id"], ondelete="CASCADE"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_op_reports_work_order_id", "erp_op_reports", ["work_order_id"])

    if not _table_exists("erp_quality_checks"):
        op.create_table(
            "erp_quality_checks",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(32), nullable=False),
            sa.Column("check_type", sa.String(8), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("product_code", sa.String(32), nullable=True),
            sa.Column("product_name", sa.String(128), nullable=True),
            sa.Column("ref_type", sa.String(32), nullable=True),
            sa.Column("ref_id", sa.Integer(), nullable=True),
            sa.Column("check_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("qualified_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("reject_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("result", sa.String(16), nullable=False, server_default="pending"),
            sa.Column("inspector", sa.String(64), nullable=True),
            sa.Column("check_date", sa.Date(), nullable=True),
            sa.Column("remark", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["product_id"], ["erp_products.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("code", name="uq_erp_quality_checks_code"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_quality_checks_product_id", "erp_quality_checks", ["product_id"])


def downgrade() -> None:
    for tbl in ("erp_quality_checks", "erp_op_reports", "erp_work_order_items",
                "erp_work_orders", "erp_bom_items", "erp_boms",
                "erp_stocktake_items", "erp_stocktakes", "erp_serials", "erp_batches",
                "erp_stock_locations", "erp_voucher_entries", "erp_vouchers",
                "erp_accounting_periods", "erp_accounts"):
        if _table_exists(tbl):
            op.drop_table(tbl)