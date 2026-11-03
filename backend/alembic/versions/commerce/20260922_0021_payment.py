"""支付中心（payment 应用）：通道配置 / 支付订单 / 退款 / 回调日志

revision: 20260922_0021_payment
down_revision: 20260922_0020_commerce

背景：平台需要一套「可插拔的统一支付能力」，供 CRM / MES / ERP / CMS 等
各业务应用复用。此前 184 张表里没有任何通用在线收单能力（crm_payment_plans
是收款计划、erp_payments 是应付单，都不是在线支付）。

设计要点：
1. scene_key 是隔离维度 —— 同一个后台里每个业务应用（crm / mes / store ...）
   拥有各自独立的通道配置与订单流水，互不干扰。
2. 金额一律以「分」为单位存整数，展示层再换算，避免浮点误差。
3. pay_channels.config 里的敏感字段（私钥 / AppSecret）以 Fernet 密文存储，
   密文带 `enc:v1:` 前缀，明文与密文可安全混存。
4. pay_notify_logs 保留第三方回调和主动查单的原始报文 —— 对账和客诉排查
   全靠它，宁多存不可少存。
5. 本迁移只新增表，不触碰任何既有表与数据。

downgrade 直接删表。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from cenkor_admin.core.compat import alembic_json

revision = "20260922_0021_payment"
down_revision = "20260922_0020_commerce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = alembic_json()
    now = sa.text("now()")

    # ---------------- 通道配置 ----------------
    op.create_table(
        "pay_channels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scene_key", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("sub_type", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("title", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="live"),
        sa.Column("config", json_type, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pay_channels_scene", "pay_channels", ["scene_key", "enabled"])

    # ---------------- 支付订单 ----------------
    op.create_table(
        "pay_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("out_trade_no", sa.String(length=64), nullable=False),
        sa.Column("scene_key", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("sub_type", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("subject", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="CNY"),
        sa.Column("refunded_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("pay_mode", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("pay_payload", json_type, nullable=True),
        sa.Column("trade_no", sa.String(length=128), nullable=True),
        sa.Column("biz_type", sa.String(length=64), nullable=True),
        sa.Column("biz_id", sa.String(length=64), nullable=True),
        sa.Column("extra", json_type, nullable=True),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column("return_url", sa.String(length=512), nullable=True),
        sa.Column("expire_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notify_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_notify_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creator_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("out_trade_no", name="uq_pay_orders_out_trade_no"),
    )
    op.create_index("ix_pay_orders_channel", "pay_orders", ["channel_id"])
    op.create_index("ix_pay_orders_trade_no", "pay_orders", ["trade_no"])
    op.create_index("ix_pay_orders_biz_type", "pay_orders", ["biz_type"])
    op.create_index("ix_pay_orders_biz_id", "pay_orders", ["biz_id"])
    op.create_index("ix_pay_orders_scene_status", "pay_orders", ["scene_key", "status"])
    op.create_index("ix_pay_orders_created", "pay_orders", ["created_at"])

    # ---------------- 退款 ----------------
    op.create_table(
        "pay_refunds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("out_refund_no", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("out_trade_no", sa.String(length=64), nullable=False),
        sa.Column("scene_key", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("amount_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("refund_trade_no", sa.String(length=128), nullable=True),
        sa.Column("raw", json_type, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("operator_id", sa.Integer(), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("out_refund_no", name="uq_pay_refunds_out_refund_no"),
    )
    op.create_index("ix_pay_refunds_order", "pay_refunds", ["order_id"])
    op.create_index("ix_pay_refunds_out_trade_no", "pay_refunds", ["out_trade_no"])

    # ---------------- 回调日志 ----------------
    op.create_table(
        "pay_notify_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scene_key", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("direction", sa.String(length=16), nullable=False, server_default="notify"),
        sa.Column("out_trade_no", sa.String(length=64), nullable=True),
        sa.Column("headers", json_type, nullable=True),
        sa.Column("raw", json_type, nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pay_notify_out_trade_no", "pay_notify_logs", ["out_trade_no"])
    op.create_index("ix_pay_notify_scene_created", "pay_notify_logs", ["scene_key", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_pay_notify_scene_created", table_name="pay_notify_logs")
    op.drop_index("ix_pay_notify_out_trade_no", table_name="pay_notify_logs")
    op.drop_table("pay_notify_logs")

    op.drop_index("ix_pay_refunds_out_trade_no", table_name="pay_refunds")
    op.drop_index("ix_pay_refunds_order", table_name="pay_refunds")
    op.drop_table("pay_refunds")

    op.drop_index("ix_pay_orders_created", table_name="pay_orders")
    op.drop_index("ix_pay_orders_scene_status", table_name="pay_orders")
    op.drop_index("ix_pay_orders_biz_id", table_name="pay_orders")
    op.drop_index("ix_pay_orders_biz_type", table_name="pay_orders")
    op.drop_index("ix_pay_orders_trade_no", table_name="pay_orders")
    op.drop_index("ix_pay_orders_channel", table_name="pay_orders")
    op.drop_table("pay_orders")

    op.drop_index("ix_pay_channels_scene", table_name="pay_channels")
    op.drop_table("pay_channels")
