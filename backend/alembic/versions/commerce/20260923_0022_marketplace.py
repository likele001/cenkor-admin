"""marketplace settlement

开发者/平台双边结算：商品归属、订单分账快照、开发者钱包、资金流水、提现申请。

Revision ID: 20260923_0022_marketplace
Revises: 20260922_0021_payment
Create Date: 2026-09-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260923_0022_marketplace"
down_revision = "20260922_0021_payment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ============================================================
    # 1) app_pricing：商品归属 + 单应用扣点覆盖
    # ============================================================
    op.add_column("app_pricing", sa.Column("developer_id", sa.Integer(), nullable=True))
    op.add_column("app_pricing", sa.Column("platform_fee_bp", sa.Integer(), nullable=True))
    op.create_index("ix_app_pricing_developer_id", "app_pricing", ["developer_id"])

    # ============================================================
    # 2) app_orders：分账快照（下单时定死）
    # ============================================================
    op.add_column("app_orders", sa.Column("developer_id", sa.Integer(), nullable=True))
    op.add_column("app_orders", sa.Column(
        "platform_fee_bp", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("app_orders", sa.Column(
        "platform_fee_cents", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("app_orders", sa.Column(
        "developer_income_cents", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("app_orders", sa.Column(
        "settle_status", sa.String(length=20), nullable=False, server_default="none"))
    op.add_column("app_orders", sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_app_orders_developer_id", "app_orders", ["developer_id"])

    # ============================================================
    # 3) dev_wallets：开发者钱包（三池）
    # ============================================================
    op.create_table(
        "dev_wallets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("developer_id", sa.Integer(), nullable=False),
        sa.Column("available_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pending_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("frozen_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_income_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_withdrawn_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_refunded_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dev_wallets_developer_id", "dev_wallets", ["developer_id"], unique=True)

    # ============================================================
    # 4) dev_ledger：资金流水（只增不改）
    # ============================================================
    op.create_table(
        "dev_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("developer_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=24), nullable=False),
        sa.Column("pool", sa.String(length=16), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("pool_after_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("order_no", sa.String(length=40), nullable=True),
        sa.Column("withdrawal_id", sa.Integer(), nullable=True),
        sa.Column("app_key", sa.String(length=50), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dev_ledger_developer_id", "dev_ledger", ["developer_id"])
    op.create_index("ix_dev_ledger_type", "dev_ledger", ["type"])
    op.create_index("ix_dev_ledger_order_no", "dev_ledger", ["order_no"])
    op.create_index("ix_dev_ledger_withdrawal_id", "dev_ledger", ["withdrawal_id"])
    op.create_index("ix_dev_ledger_available_at", "dev_ledger", ["available_at"])
    op.create_index("ix_dev_ledger_created_at", "dev_ledger", ["created_at"])

    # ============================================================
    # 5) dev_withdrawals：提现申请
    # ============================================================
    op.create_table(
        "dev_withdrawals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("developer_id", sa.Integer(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("fee_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actual_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("account_type", sa.String(length=20), nullable=False, server_default="alipay"),
        sa.Column("account_no", sa.String(length=200), nullable=True),
        sa.Column("account_name", sa.String(length=120), nullable=True),
        sa.Column("bank_name", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_remark", sa.Text(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pay_voucher", sa.String(length=300), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dev_withdrawals_developer_id", "dev_withdrawals", ["developer_id"])
    op.create_index("ix_dev_withdrawals_status", "dev_withdrawals", ["status"])


def downgrade() -> None:
    op.drop_index("ix_dev_withdrawals_status", table_name="dev_withdrawals")
    op.drop_index("ix_dev_withdrawals_developer_id", table_name="dev_withdrawals")
    op.drop_table("dev_withdrawals")

    for _idx in ("ix_dev_ledger_created_at", "ix_dev_ledger_available_at",
                 "ix_dev_ledger_withdrawal_id", "ix_dev_ledger_order_no",
                 "ix_dev_ledger_type", "ix_dev_ledger_developer_id"):
        op.drop_index(_idx, table_name="dev_ledger")
    op.drop_table("dev_ledger")

    op.drop_index("ix_dev_wallets_developer_id", table_name="dev_wallets")
    op.drop_table("dev_wallets")

    op.drop_index("ix_app_orders_developer_id", table_name="app_orders")
    for _col in ("settled_at", "settle_status", "developer_income_cents",
                 "platform_fee_cents", "platform_fee_bp", "developer_id"):
        op.drop_column("app_orders", _col)

    op.drop_index("ix_app_pricing_developer_id", table_name="app_pricing")
    op.drop_column("app_pricing", "platform_fee_bp")
    op.drop_column("app_pricing", "developer_id")
