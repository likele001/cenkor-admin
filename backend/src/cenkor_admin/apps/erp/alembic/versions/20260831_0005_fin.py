"""ERP App Phase 6 — 财务（销售发票/采购发票/收付款/应收/应付）

Revision ID: 20260831_0005_fin
Revises: 20260831_0004_pu
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260831_0005_fin"
down_revision = "20260831_0004_pu"
branch_labels = None
depends_on = None


def _table_exists(tbl: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return insp.has_table(tbl)


def upgrade() -> None:
    # ===== 销售发票 =====
    if not _table_exists("erp_invoices"):
        op.create_table(
            "erp_invoices",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(32), nullable=False),
            sa.Column("sales_order_id", sa.Integer(), nullable=True),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="issued"),
            sa.Column("invoice_date", sa.Date(), nullable=True),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("currency", sa.String(8), nullable=False, server_default="CNY"),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("tax_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("total_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("paid_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["sales_order_id"], ["erp_sales_orders.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["customer_id"], ["erp_customers.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("code", name="uq_erp_invoices_code"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_invoices_sales_order_id", "erp_invoices", ["sales_order_id"])
        op.create_index("ix_erp_invoices_customer_id", "erp_invoices", ["customer_id"])

    # ===== 采购发票 =====
    if not _table_exists("erp_purchase_invoices"):
        op.create_table(
            "erp_purchase_invoices",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(32), nullable=False),
            sa.Column("purchase_order_id", sa.Integer(), nullable=True),
            sa.Column("supplier_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="issued"),
            sa.Column("invoice_date", sa.Date(), nullable=True),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("currency", sa.String(8), nullable=False, server_default="CNY"),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("tax_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("total_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("paid_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["purchase_order_id"], ["erp_purchase_orders.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["supplier_id"], ["erp_suppliers.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("code", name="uq_erp_purchase_invoices_code"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_purchase_invoices_purchase_order_id", "erp_purchase_invoices", ["purchase_order_id"])
        op.create_index("ix_erp_purchase_invoices_supplier_id", "erp_purchase_invoices", ["supplier_id"])

    # ===== 收付款记录 =====
    if not _table_exists("erp_payments"):
        op.create_table(
            "erp_payments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(32), nullable=False),
            sa.Column("direction", sa.String(8), nullable=False),
            sa.Column("method", sa.String(32), nullable=True),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("paid_at", sa.Date(), nullable=True),
            sa.Column("ref_type", sa.String(32), nullable=True),
            sa.Column("ref_id", sa.Integer(), nullable=True),
            sa.Column("customer_id", sa.Integer(), nullable=True),
            sa.Column("supplier_id", sa.Integer(), nullable=True),
            sa.Column("remark", sa.String(255), nullable=True),
            sa.Column("operator_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("code", name="uq_erp_payments_code"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_payments_ref_id", "erp_payments", ["ref_id"])
        op.create_index("ix_erp_payments_customer_id", "erp_payments", ["customer_id"])
        op.create_index("ix_erp_payments_supplier_id", "erp_payments", ["supplier_id"])

    # ===== 应收账款 =====
    if not _table_exists("erp_accounts_receivable"):
        op.create_table(
            "erp_accounts_receivable",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("customer_id", sa.Integer(), nullable=True),
            sa.Column("invoice_id", sa.Integer(), nullable=True),
            sa.Column("source_type", sa.String(32), nullable=True),
            sa.Column("source_id", sa.Integer(), nullable=True),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("paid_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="open"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_accounts_receivable_customer_id", "erp_accounts_receivable", ["customer_id"])
        op.create_index("ix_erp_accounts_receivable_invoice_id", "erp_accounts_receivable", ["invoice_id"])

    # ===== 应付账款 =====
    if not _table_exists("erp_accounts_payable"):
        op.create_table(
            "erp_accounts_payable",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("supplier_id", sa.Integer(), nullable=True),
            sa.Column("invoice_id", sa.Integer(), nullable=True),
            sa.Column("source_type", sa.String(32), nullable=True),
            sa.Column("source_id", sa.Integer(), nullable=True),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("paid_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="open"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_accounts_payable_supplier_id", "erp_accounts_payable", ["supplier_id"])
        op.create_index("ix_erp_accounts_payable_invoice_id", "erp_accounts_payable", ["invoice_id"])


def downgrade() -> None:
    for tbl in [
        "erp_accounts_payable", "erp_accounts_receivable", "erp_payments",
        "erp_purchase_invoices", "erp_invoices",
    ]:
        if _table_exists(tbl):
            op.drop_table(tbl)