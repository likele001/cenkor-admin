"""ERP App Phase 5 — 采购 + 仓库（采购订单/收货/仓库/库存）

Revision ID: 20260831_0004_pu
Revises: 20260831_0003_so
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260831_0004_pu"
down_revision = "20260831_0003_so"
branch_labels = None
depends_on = None


def _table_exists(tbl: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return insp.has_table(tbl)


def upgrade() -> None:
    # ===== 仓库 =====
    if not _table_exists("erp_warehouses"):
        op.create_table(
            "erp_warehouses",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(32), nullable=False),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("location", sa.String(255), nullable=True),
            sa.Column("manager", sa.String(64), nullable=True),
            sa.Column("phone", sa.String(32), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("code", name="uq_erp_warehouses_code"),
            mysql_engine="InnoDB",
        )

    # ===== 采购订单 =====
    if not _table_exists("erp_purchase_orders"):
        op.create_table(
            "erp_purchase_orders",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(32), nullable=False),
            sa.Column("supplier_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
            sa.Column("order_date", sa.Date(), nullable=True),
            sa.Column("expected_date", sa.Date(), nullable=True),
            sa.Column("currency", sa.String(8), nullable=False, server_default="CNY"),
            sa.Column("subtotal", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("tax_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("discount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("total_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("paid_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("payment_status", sa.String(16), nullable=False, server_default="unpaid"),
            sa.Column("owner_user_id", sa.Integer(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["supplier_id"], ["erp_suppliers.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["owner_user_id"], ["auth_users.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("code", name="uq_erp_purchase_orders_code"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_purchase_orders_supplier_id", "erp_purchase_orders", ["supplier_id"])

    # ===== 采购明细 =====
    if not _table_exists("erp_purchase_order_items"):
        op.create_table(
            "erp_purchase_order_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("purchase_order_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("product_code", sa.String(32), nullable=True),
            sa.Column("product_name", sa.String(128), nullable=True),
            sa.Column("spec", sa.String(128), nullable=True),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("received_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("unit", sa.String(16), nullable=True),
            sa.Column("unit_price", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("tax_rate", sa.Numeric(6, 2), nullable=False, server_default="0"),
            sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(["purchase_order_id"], ["erp_purchase_orders.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["product_id"], ["erp_products.id"], ondelete="SET NULL"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_purchase_order_items_purchase_order_id", "erp_purchase_order_items", ["purchase_order_id"])

    # ===== 收货单 =====
    if not _table_exists("erp_purchase_receipts"):
        op.create_table(
            "erp_purchase_receipts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(32), nullable=False),
            sa.Column("purchase_order_id", sa.Integer(), nullable=True),
            sa.Column("supplier_id", sa.Integer(), nullable=True),
            sa.Column("warehouse_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
            sa.Column("receipt_date", sa.Date(), nullable=True),
            sa.Column("carrier", sa.String(64), nullable=True),
            sa.Column("tracking_no", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["purchase_order_id"], ["erp_purchase_orders.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["supplier_id"], ["erp_suppliers.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["warehouse_id"], ["erp_warehouses.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("code", name="uq_erp_purchase_receipts_code"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_purchase_receipts_purchase_order_id", "erp_purchase_receipts", ["purchase_order_id"])
        op.create_index("ix_erp_purchase_receipts_supplier_id", "erp_purchase_receipts", ["supplier_id"])
        op.create_index("ix_erp_purchase_receipts_warehouse_id", "erp_purchase_receipts", ["warehouse_id"])

    # ===== 库存余额 =====
    if not _table_exists("erp_stock_balance"):
        op.create_table(
            "erp_stock_balance",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("warehouse_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("product_code", sa.String(32), nullable=True),
            sa.Column("product_name", sa.String(128), nullable=True),
            sa.Column("unit", sa.String(16), nullable=True),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("available_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("last_movement_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["warehouse_id"], ["erp_warehouses.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["product_id"], ["erp_products.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("warehouse_id", "product_id", name="uq_erp_stock_balance_wh_product"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_stock_balance_warehouse_id", "erp_stock_balance", ["warehouse_id"])
        op.create_index("ix_erp_stock_balance_product_id", "erp_stock_balance", ["product_id"])

    # ===== 出入库流水 =====
    if not _table_exists("erp_stock_movements"):
        op.create_table(
            "erp_stock_movements",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("warehouse_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("product_code", sa.String(32), nullable=True),
            sa.Column("product_name", sa.String(128), nullable=True),
            sa.Column("unit", sa.String(16), nullable=True),
            sa.Column("movement_type", sa.String(16), nullable=False),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("balance_after", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("ref_type", sa.String(32), nullable=True),
            sa.Column("ref_id", sa.Integer(), nullable=True),
            sa.Column("receipt_id", sa.Integer(), nullable=True),
            sa.Column("remark", sa.String(255), nullable=True),
            sa.Column("operator_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["warehouse_id"], ["erp_warehouses.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["product_id"], ["erp_products.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["receipt_id"], ["erp_purchase_receipts.id"], ondelete="SET NULL"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_stock_movements_warehouse_id", "erp_stock_movements", ["warehouse_id"])
        op.create_index("ix_erp_stock_movements_product_id", "erp_stock_movements", ["product_id"])
        op.create_index("ix_erp_stock_movements_receipt_id", "erp_stock_movements", ["receipt_id"])


def downgrade() -> None:
    for tbl in [
        "erp_stock_movements", "erp_stock_balance", "erp_purchase_receipts",
        "erp_purchase_order_items", "erp_purchase_orders", "erp_warehouses",
    ]:
        if _table_exists(tbl):
            op.drop_table(tbl)