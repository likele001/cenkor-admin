"""cloud binding: 实例凭证 + 一次性绑定码

应用市场闭环（对齐 FastAdmin「官网买 → 后台登录官网账号 → 在线安装」）的数据基础。
购买始终发生在官方门户，客户实例只负责「认领 + 安装」。

- cloud_device_codes  一次性绑定码（设备码流程的官方云侧）：
  device_code 只在实例与云之间传递、user_code 给人看，10 分钟过期，
  换发令牌后置 consumed，防止同一个码被重复兑换。
- cloud_instances    官方云侧的「已绑定实例」：只存实例令牌的 sha256，可随时吊销。
- cloud_client       客户实例侧的本地凭证（单行表，id 恒 1）：
  只存实例令牌，不存任何门户账号密码；解绑即删行。
  用独立表而非 system_settings，是为了让「凭证」有明确的表级边界与清理路径。

Revision ID: 20260924_0025_cloud
Revises: 20260923_0024_promo
Create Date: 2026-09-24
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260924_0025_cloud"
down_revision = "20260923_0024_promo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- 一次性绑定码 ----------
    op.create_table(
        "cloud_device_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_code", sa.String(length=80), nullable=False),
        sa.Column("user_code", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("instance_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("instance_url", sa.String(length=255), nullable=True),
        sa.Column("instance_uid", sa.String(length=64), nullable=True),
        sa.Column("portal_user_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("device_code", name="uq_cloud_device_code"),
        sa.UniqueConstraint("user_code", name="uq_cloud_user_code"),
    )
    op.create_index("ix_cloud_device_codes_device_code", "cloud_device_codes", ["device_code"])
    op.create_index("ix_cloud_device_codes_user_code", "cloud_device_codes", ["user_code"])
    op.create_index("ix_cloud_device_codes_status", "cloud_device_codes", ["status"])
    op.create_index("ix_cloud_device_codes_instance_uid", "cloud_device_codes", ["instance_uid"])
    op.create_index("ix_cloud_device_codes_portal_user_id", "cloud_device_codes", ["portal_user_id"])

    # ---------- 官方云侧：已绑定实例 ----------
    op.create_table(
        "cloud_instances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instance_uid", sa.String(length=64), nullable=False),
        sa.Column("portal_user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("instance_url", sa.String(length=255), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("instance_uid", name="uq_cloud_instance_uid"),
        sa.UniqueConstraint("token_hash", name="uq_cloud_instance_token"),
    )
    op.create_index("ix_cloud_instances_instance_uid", "cloud_instances", ["instance_uid"])
    op.create_index("ix_cloud_instances_portal_user_id", "cloud_instances", ["portal_user_id"])
    op.create_index("ix_cloud_instances_token_hash", "cloud_instances", ["token_hash"])

    # ---------- 客户实例侧：本地凭证（单行） ----------
    op.create_table(
        "cloud_client",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hub_url", sa.String(length=255), nullable=False),
        sa.Column("instance_uid", sa.String(length=64), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("account", sa.String(length=200), nullable=True),
        sa.Column("bound_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_poll_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("cloud_client")
    op.drop_table("cloud_instances")
    op.drop_table("cloud_device_codes")
