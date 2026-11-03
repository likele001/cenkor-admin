"""应用生态交易层（P0）：定价 / 订单 / 授权 / 实例绑定

revision: 20260922_0020_commerce
down_revision: 20261103_1200_merge_commerce

背景：平台要从「应用分发」走到「应用生态」，必须能收钱。原有表只覆盖
开发者入驻（app_developers）、提交审核（app_submissions）、安装态（platform_apps），
没有任何价格、交易、授权落地的载体。本次新增四张表补齐收费闭环。

设计要点：
1. 金额一律以「分」为单位存整数（price_cents/amount_cents），避免浮点误差。
2. app_pricing 是商品，app_orders 是交易，app_licenses 是交付凭证，
   app_license_bindings 是授权实际落地的实例 —— 一个授权可绑多台（受 max_instances 限制）。
3. app_licenses.order_id 允许为空：支持运营手工签发（赠送 / 补偿 / 线下大客户）。
4. app_licenses.token 存授权中心私钥签名的凭证。客户端（客户自己的服务器）
   用内置公钥验签，因此改本地缓存无法伪造有效期 —— 这是「底座开源 + 应用收费」
   能成立的前提。

downgrade 直接删表 —— 本迁移只新增表，不触碰任何既有表与数据。
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260922_0020_commerce"
down_revision = "20261103_1200_merge_commerce"
branch_labels = None
depends_on = None


def _json():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "app_pricing",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("app_key", sa.String(50), nullable=False),
        sa.Column("model", sa.String(20), nullable=False, server_default="free"),
        sa.Column("price_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("seat_price_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="CNY"),
        sa.Column("period_days", sa.Integer(), nullable=False, server_default="365"),
        sa.Column("trial_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("min_seats", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_seats", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("require_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("intro", sa.Text(), nullable=True),
        sa.Column("meta", _json(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_app_pricing_app_key", "app_pricing", ["app_key"], unique=True)

    op.create_table(
        "app_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_no", sa.String(40), nullable=False),
        sa.Column("app_key", sa.String(50), nullable=False),
        sa.Column("app_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("buyer_id", sa.Integer(), nullable=False),
        sa.Column("buyer_type", sa.String(16), nullable=False, server_default="portal"),
        sa.Column("buyer_email", sa.String(200), nullable=True),
        sa.Column("buyer_name", sa.String(120), nullable=True),
        sa.Column("model", sa.String(20), nullable=False, server_default="one_time"),
        sa.Column("seats", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("amount_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="CNY"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("channel", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("trade_no", sa.String(128), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("meta", _json(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_app_orders_order_no", "app_orders", ["order_no"], unique=True)
    op.create_index("ix_app_orders_app_key", "app_orders", ["app_key"])
    op.create_index("ix_app_orders_buyer_id", "app_orders", ["buyer_id"])
    op.create_index("ix_app_orders_status", "app_orders", ["status"])

    op.create_table(
        "app_licenses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("license_key", sa.String(40), nullable=False),
        sa.Column("app_key", sa.String(50), nullable=False),
        sa.Column("app_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("app_orders.id"), nullable=True),
        sa.Column("buyer_id", sa.Integer(), nullable=True),
        sa.Column("buyer_type", sa.String(16), nullable=True),
        sa.Column("model", sa.String(20), nullable=False, server_default="one_time"),
        sa.Column("seats", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="issued"),
        sa.Column("bound_domain", sa.String(200), nullable=True),
        sa.Column("instance_fp", sa.String(128), nullable=True),
        sa.Column("max_instances", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_rebind", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("rebind_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(200), nullable=True),
        sa.Column("token", sa.Text(), nullable=True),
        sa.Column("token_issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_app_licenses_license_key", "app_licenses", ["license_key"], unique=True)
    op.create_index("ix_app_licenses_app_key", "app_licenses", ["app_key"])
    op.create_index("ix_app_licenses_status", "app_licenses", ["status"])
    op.create_index("ix_app_licenses_order_id", "app_licenses", ["order_id"])
    op.create_index("ix_app_licenses_buyer_id", "app_licenses", ["buyer_id"])
    op.create_index("ix_app_licenses_instance_fp", "app_licenses", ["instance_fp"])

    op.create_table(
        "app_license_bindings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "license_id", sa.Integer(),
            sa.ForeignKey("app_licenses.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("instance_fp", sa.String(128), nullable=False),
        sa.Column("domain", sa.String(200), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("version", sa.String(40), nullable=True),
        sa.Column("agent", sa.String(200), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", _json(), nullable=True),
        sa.UniqueConstraint("license_id", "instance_fp", name="uq_license_binding_fp"),
    )
    op.create_index("ix_app_license_bindings_license_id", "app_license_bindings", ["license_id"])
    op.create_index("ix_app_license_bindings_instance_fp", "app_license_bindings", ["instance_fp"])


def downgrade() -> None:
    op.drop_table("app_license_bindings")
    op.drop_table("app_licenses")
    op.drop_table("app_orders")
    op.drop_table("app_pricing")
