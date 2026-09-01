"""ERP App Phase 4 — 销售订单（报价单/订单/出货）

Revision ID: 20260831_0003_so
Revises: 20260831_0002_sp
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260831_0003_so"
down_revision = "20260831_0002_sp"
branch_labels = None
depends_on = None


def _table_exists(tbl: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return insp.has_table(tbl)


def upgrade() -> None:
    # ===== 报价单 =====
    if not _table_exists("erp_quotations"):
        op.create_table(
            "erp_quotations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(32), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("contact_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
            sa.Column("quote_date", sa.Date(), nullable=True),
            sa.Column("valid_until", sa.Date(), nullable=True),
            sa.Column("currency", sa.String(8), nullable=False, server_default="CNY"),
            sa.Column("subtotal", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("tax_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("discount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("total_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("owner_user_id", sa.Integer(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["customer_id"], ["erp_customers.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["contact_id"], ["erp_customer_contacts.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["owner_user_id"], ["auth_users.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("code", name="uq_erp_quotations_code"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_quotations_customer_id", "erp_quotations", ["customer_id"])

    # ===== 报价单明细 =====
    if not _table_exists("erp_quotation_items"):
        op.create_table(
            "erp_quotation_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("quotation_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("product_code", sa.String(32), nullable=True),
            sa.Column("product_name", sa.String(128), nullable=True),
            sa.Column("spec", sa.String(128), nullable=True),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("unit", sa.String(16), nullable=True),
            sa.Column("unit_price", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("tax_rate", sa.Numeric(6, 2), nullable=False, server_default="0"),
            sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(["quotation_id"], ["erp_quotations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["product_id"], ["erp_products.id"], ondelete="SET NULL"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_quotation_items_quotation_id", "erp_quotation_items", ["quotation_id"])

    # ===== 销售订单 =====
    if not _table_exists("erp_sales_orders"):
        op.create_table(
            "erp_sales_orders",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(32), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("contact_id", sa.Integer(), nullable=True),
            sa.Column("quotation_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
            sa.Column("order_date", sa.Date(), nullable=True),
            sa.Column("delivery_date", sa.Date(), nullable=True),
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
            sa.ForeignKeyConstraint(["customer_id"], ["erp_customers.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["contact_id"], ["erp_customer_contacts.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["quotation_id"], ["erp_quotations.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["owner_user_id"], ["auth_users.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("code", name="uq_erp_sales_orders_code"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_sales_orders_customer_id", "erp_sales_orders", ["customer_id"])

    # ===== 销售订单明细 =====
    if not _table_exists("erp_sales_order_items"):
        op.create_table(
            "erp_sales_order_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("sales_order_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("product_code", sa.String(32), nullable=True),
            sa.Column("product_name", sa.String(128), nullable=True),
            sa.Column("spec", sa.String(128), nullable=True),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("unit", sa.String(16), nullable=True),
            sa.Column("unit_price", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("tax_rate", sa.Numeric(6, 2), nullable=False, server_default="0"),
            sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(["sales_order_id"], ["erp_sales_orders.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["product_id"], ["erp_products.id"], ondelete="SET NULL"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_sales_order_items_sales_order_id", "erp_sales_order_items", ["sales_order_id"])

    # ===== 出货单 =====
    if not _table_exists("erp_shipments"):
        op.create_table(
            "erp_shipments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(32), nullable=False),
            sa.Column("sales_order_id", sa.Integer(), nullable=False),
            sa.Column("warehouse_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
            sa.Column("ship_date", sa.Date(), nullable=True),
            sa.Column("receiver", sa.String(64), nullable=True),
            sa.Column("phone", sa.String(32), nullable=True),
            sa.Column("address", sa.String(255), nullable=True),
            sa.Column("tracking_no", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["sales_order_id"], ["erp_sales_orders.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("code", name="uq_erp_shipments_code"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_shipments_sales_order_id", "erp_shipments", ["sales_order_id"])
        op.create_index("ix_erp_shipments_warehouse_id", "erp_shipments", ["warehouse_id"])

    # ===== 出货明细 =====
    if not _table_exists("erp_shipment_items"):
        op.create_table(
            "erp_shipment_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("shipment_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("product_code", sa.String(32), nullable=True),
            sa.Column("product_name", sa.String(128), nullable=True),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("unit", sa.String(16), nullable=True),
            sa.ForeignKeyConstraint(["shipment_id"], ["erp_shipments.id"], ondelete="CASCADE"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_shipment_items_shipment_id", "erp_shipment_items", ["shipment_id"])


def downgrade() -> None:
    for tbl in [
        "erp_shipment_items", "erp_shipments",
        "erp_sales_order_items", "erp_sales_orders",
        "erp_quotation_items", "erp_quotations",
    ]:
        if _table_exists(tbl):
            op.drop_table(tbl)