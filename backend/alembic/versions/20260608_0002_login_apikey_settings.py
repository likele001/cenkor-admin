"""add login_log + api_keys + system_settings tables

Revision ID: 20260608_0002_apikey
Revises: 20260608_0001_notif
Create Date: 2026-06-08 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260608_0002_apikey"
down_revision: str | Sequence[str] | None = "20260608_0001_notif"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- login_log：用户登录历史 ----
    op.create_table(
        "login_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("auth_users.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reason", sa.String(200), nullable=True),  # 失败原因
        sa.Column("provider", sa.String(40), nullable=True, server_default="local"),  # local / feishu
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )

    # ---- api_keys：API Key 管理 ----
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("auth_users.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("prefix", sa.String(16), index=True, nullable=False),  # 用于识别（ck_xxx）
        sa.Column("hash", sa.String(128), nullable=False),  # sha256(token)
        sa.Column("scopes", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ---- system_settings：系统级 KV（与 cms_site_config 区分） ----
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column("value", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column("group", sa.String(40), index=True, nullable=False, server_default="general"),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # 种子：常用系统设置
    op.execute(
        "INSERT INTO system_settings (key, value, description, \"group\") VALUES "
        "('site.title', '\"Cenkor Admin\"', '站点标题', 'general'), "
        "('security.login_max_attempts', '5', '登录最大失败次数（0=不限）', 'security'), "
        "('security.login_lock_minutes', '15', '登录锁定时长（分钟）', 'security'), "
        "('security.password_min_length', '8', '密码最小长度', 'security'), "
        "('security.captcha_required', 'true', '登录/注册是否启用滑动验证', 'security'), "
        "('upload.max_size_mb', '10', '上传最大体积（MB）', 'upload'), "
        "('upload.allowed_types', '\"image/*,application/pdf\"', '允许的 MIME 类型', 'upload'), "
        "('notification.poll_interval_sec', '30', '通知轮询间隔（秒）', 'notification'), "
        "('email.from', '\"noreply@cenkor.cn\"', '发件人邮箱', 'email'), "
        "('email.enabled', 'false', '是否启用邮件', 'email')"
    )

    # 新增权限
    op.execute(
        "INSERT INTO rbac_permissions (code, type, name) VALUES "
        "('apikey:read', 'API', '查看 API Key'), "
        "('apikey:write', 'API', '管理 API Key'), "
        "('settings:read', 'API', '查看系统设置'), "
        "('settings:write', 'API', '编辑系统设置'), "
        "('task:read', 'API', '查看定时任务'), "
        "('task:write', 'API', '管理定时任务') "
        "ON CONFLICT (code) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM rbac_permissions WHERE code IN ('apikey:read', 'apikey:write', 'settings:read', 'settings:write', 'task:read', 'task:write')")
    op.drop_table("system_settings")
    op.drop_table("api_keys")
    op.drop_table("login_logs")
