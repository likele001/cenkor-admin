"""ERP App Phase 3 — 供应商 + 商品

Revision ID: 20260831_0002_sp
Revises: 20260831_0001_erp_init
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260831_0002_sp"
down_revision = "20260831_0001_erp_init"
branch_labels = None
depends_on = None


def _table_exists(tbl: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return insp.has_table(tbl)


def upgrade() -> None:
    # ===== 供应商主数据 =====
    if not _table_exists("erp_suppliers"):
        op.create_table(
            "erp_suppliers",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(32), nullable=False, comment="供应商编号"),
            sa.Column("name", sa.String(128), nullable=False, comment="供应商名称"),
            sa.Column("short_name", sa.String(64), nullable=True),
            sa.Column("contact_person", sa.String(64), nullable=True),
            sa.Column("phone", sa.String(32), nullable=True),
            sa.Column("email", sa.String(128), nullable=True),
            sa.Column("tax_id", sa.String(32), nullable=True),
            sa.Column("category", sa.String(64), nullable=True, comment="供应品类"),
            sa.Column("payment_terms", sa.String(32), nullable=True),
            sa.Column("currency", sa.String(8), nullable=False, server_default="CNY"),
            sa.Column("credit_limit", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("owner_user_id", sa.Integer(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["owner_user_id"], ["auth_users.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("code", name="uq_erp_suppliers_code"),
            comment="供应商主数据",
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_suppliers_owner_user_id", "erp_suppliers", ["owner_user_id"])

    # ===== 供应商联系人 =====
    if not _table_exists("erp_supplier_contacts"):
        op.create_table(
            "erp_supplier_contacts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("supplier_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(64), nullable=False),
            sa.Column("position", sa.String(64), nullable=True),
            sa.Column("phone", sa.String(32), nullable=True),
            sa.Column("email", sa.String(128), nullable=True),
            sa.Column("wechat", sa.String(64), nullable=True),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["supplier_id"], ["erp_suppliers.id"], ondelete="CASCADE"),
            comment="供应商联系人",
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_supplier_contacts_supplier_id", "erp_supplier_contacts", ["supplier_id"])

    # ===== 商品分类 =====
    if not _table_exists("erp_product_categories"):
        op.create_table(
            "erp_product_categories",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(64), nullable=False),
            sa.Column("code", sa.String(32), nullable=True),
            sa.Column("parent_id", sa.Integer(), nullable=True),
            sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["parent_id"], ["erp_product_categories.id"], ondelete="SET NULL"),
            comment="商品分类",
            mysql_engine="InnoDB",
        )

    # ===== 商品主数据 =====
    if not _table_exists("erp_products"):
        op.create_table(
            "erp_products",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(32), nullable=False, comment="商品编码"),
            sa.Column("name", sa.String(128), nullable=False, comment="商品名称"),
            sa.Column("model", sa.String(128), nullable=True, comment="规格型号"),
            sa.Column("category_id", sa.Integer(), nullable=True),
            sa.Column("unit", sa.String(16), nullable=False, server_default="件"),
            sa.Column("barcode", sa.String(32), nullable=True),
            sa.Column("sale_price", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("purchase_price", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("cost_price", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("min_stock", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("tax_rate", sa.Numeric(6, 2), nullable=False, server_default="0"),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["category_id"], ["erp_product_categories.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("code", name="uq_erp_products_code"),
            comment="商品主数据",
            mysql_engine="InnoDB",
        )
        op.create_index("ix_erp_products_category_id", "erp_products", ["category_id"])


def downgrade() -> None:
    if _table_exists("erp_products"):
        op.drop_index("ix_erp_products_category_id", table_name="erp_products")
        op.drop_table("erp_products")
    if _table_exists("erp_product_categories"):
        op.drop_table("erp_product_categories")
    if _table_exists("erp_supplier_contacts"):
        op.drop_index("ix_erp_supplier_contacts_supplier_id", table_name="erp_supplier_contacts")
        op.drop_table("erp_supplier_contacts")
    if _table_exists("erp_suppliers"):
        op.drop_index("ix_erp_suppliers_owner_user_id", table_name="erp_suppliers")
        op.drop_table("erp_suppliers")