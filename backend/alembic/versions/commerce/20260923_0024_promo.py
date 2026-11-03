"""app_pricing: list price + limited-time promotion

应用定价增加「原价（划线价）」与「限时促销价」：
- list_price_cents   原价，仅展示，不参与结算
- promo_price_cents  促销价，促销期内取代售价成交
- promo_start_at / promo_end_at  促销时间窗（NULL = 该侧不限制）
- promo_label        活动名，如「双十一 5 折」

Revision ID: 20260923_0024_promo
Revises: 20260923_0023_payout
Create Date: 2026-09-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260923_0024_promo"
down_revision = "20260923_0023_payout"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_pricing", sa.Column(
        "list_price_cents", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("app_pricing", sa.Column(
        "promo_price_cents", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("app_pricing", sa.Column(
        "promo_start_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("app_pricing", sa.Column(
        "promo_end_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("app_pricing", sa.Column(
        "promo_label", sa.String(length=60), nullable=True))

    # 订单侧：留一份划线价与活动名快照，历史订单才能还原「原价 → 实付」
    op.add_column("app_orders", sa.Column(
        "list_unit_price_cents", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("app_orders", sa.Column(
        "promo_label", sa.String(length=60), nullable=True))


def downgrade() -> None:
    op.drop_column("app_orders", "promo_label")
    op.drop_column("app_orders", "list_unit_price_cents")
    for col in ("promo_label", "promo_end_at", "promo_start_at",
                "promo_price_cents", "list_price_cents"):
        op.drop_column("app_pricing", col)
