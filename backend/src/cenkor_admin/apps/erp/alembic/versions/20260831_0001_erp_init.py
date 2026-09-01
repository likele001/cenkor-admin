"""create erp app base tables — Phase 1 脚手架

Revision ID: 20260831_0001
Revises: <由应用中心在安装时串接>
Create Date: 2026-08-31
"""
from alembic import op
import sqlalchemy as sa

revision = "20260831_0001_erp_init"
down_revision = None  # 由应用中心根据已装 app 串接
branch_labels = ("erp_app",)
depends_on = None


def upgrade() -> None:
    # ===== 客户主数据 =====
    op.create_table(
        "erp_customers",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(32), nullable=False, comment="客户编号 C001"),
        sa.Column("name", sa.String(128), nullable=False, comment="客户全称"),
        sa.Column("short_name", sa.String(64), nullable=True, comment="简称"),
        sa.Column("customer_type", sa.String(16), nullable=False, server_default="company", comment="company/individual"),
        sa.Column("tax_id", sa.String(32), nullable=True, comment="税号"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="CNY"),
        sa.Column("payment_terms", sa.String(32), nullable=True, comment="月结30天/现金"),
        sa.Column("credit_limit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("industry", sa.String(64), nullable=True),
        sa.Column("scale", sa.String(16), nullable=True, comment="small/medium/large"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active", comment="active/inactive/blocked"),
        sa.Column("owner_user_id", sa.Integer, sa.ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("code", name="uq_erp_customers_code"),
    )
    op.create_index("ix_erp_customers_name", "erp_customers", ["name"])
    op.create_index("ix_erp_customers_owner", "erp_customers", ["owner_user_id"])

    op.create_table(
        "erp_customer_contacts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("erp_customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("position", sa.String(64), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("email", sa.String(128), nullable=True),
        sa.Column("wechat", sa.String(64), nullable=True),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("birthday", sa.Date, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_erp_customer_contacts_customer", "erp_customer_contacts", ["customer_id"])

    op.create_table(
        "erp_customer_addresses",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("erp_customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("address_type", sa.String(16), server_default="shipping", comment="shipping/billing"),
        sa.Column("recipient", sa.String(64), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("province", sa.String(32), nullable=True),
        sa.Column("city", sa.String(32), nullable=True),
        sa.Column("district", sa.String(32), nullable=True),
        sa.Column("detail", sa.String(255), nullable=True),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "erp_follow_ups",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("erp_customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", sa.Integer, sa.ForeignKey("erp_customer_contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("follow_type", sa.String(16), nullable=False, comment="call/visit/email/meeting"),
        sa.Column("follow_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("next_action", sa.String(255), nullable=True),
        sa.Column("next_follow_date", sa.Date, nullable=True),
        sa.Column("owner_user_id", sa.Integer, sa.ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_erp_follow_ups_customer", "erp_follow_ups", ["customer_id"])

    op.create_table(
        "erp_attachments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("business_type", sa.String(32), nullable=False, comment="customer/supplier/product/sales_order/..."),
        sa.Column("business_id", sa.Integer, nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_url", sa.String(500), nullable=True),
        sa.Column("file_size", sa.Integer, nullable=True),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("uploader_id", sa.Integer, sa.ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_erp_attachments_business", "erp_attachments", ["business_type", "business_id"])


def downgrade() -> None:
    op.drop_table("erp_attachments")
    op.drop_table("erp_follow_ups")
    op.drop_table("erp_customer_addresses")
    op.drop_table("erp_customer_contacts")
    op.drop_table("erp_customers")