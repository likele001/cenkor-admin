"""initial auth + rbac schema

Revision ID: 20260107_0002_auth_rbac
Revises: 20260107_0001_initial
Create Date: 2026-01-07 00:01:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260107_0002_auth_rbac"
down_revision: str | Sequence[str] | None = "20260107_0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- Auth ----
    op.create_table(
        "auth_users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, nullable=False, server_default="1", index=True),
        sa.Column("username", sa.String(80), unique=True, nullable=False, index=True),
        sa.Column("email", sa.String(120), unique=True, nullable=False, index=True),
        sa.Column("phone", sa.String(40), nullable=True, index=True),
        sa.Column("nickname", sa.String(80), nullable=False, server_default=""),
        sa.Column("avatar", sa.String(500), nullable=True),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("token_version", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("is_superuser", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_ip", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "auth_user_oauth",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False, index=True),
        sa.Column("provider", sa.String(40), nullable=False, index=True),
        sa.Column("open_id", sa.String(200), nullable=False),
        sa.Column("union_id", sa.String(200), nullable=True),
        sa.Column("access_token_enc", sa.String(500), nullable=True),
        sa.Column("refresh_token_enc", sa.String(500), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "open_id", name="uq_oauth_provider_openid"),
    )

    # ---- RBAC ----
    op.create_table(
        "rbac_roles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, nullable=False, server_default="1", index=True),
        sa.Column("code", sa.String(50), nullable=False, index=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    op.create_table(
        "rbac_permissions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("type", sa.String(20), nullable=False, server_default="api"),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "rbac_role_permissions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("role_id", sa.Integer, sa.ForeignKey("rbac_roles.id", ondelete="CASCADE"), index=True),
        sa.Column("permission_id", sa.Integer, sa.ForeignKey("rbac_permissions.id", ondelete="CASCADE"), index=True),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )

    op.create_table(
        "rbac_menus",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String(80), unique=True, nullable=False, index=True),
        sa.Column("parent_id", sa.Integer, sa.ForeignKey("rbac_menus.id", ondelete="CASCADE"), nullable=True),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("icon", sa.String(40), nullable=True),
        sa.Column("path", sa.String(200), nullable=True),
        sa.Column("component", sa.String(200), nullable=True),
        sa.Column("sort", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "rbac_role_menus",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("role_id", sa.Integer, sa.ForeignKey("rbac_roles.id", ondelete="CASCADE"), index=True),
        sa.Column("menu_id", sa.Integer, sa.ForeignKey("rbac_menus.id", ondelete="CASCADE"), index=True),
        sa.UniqueConstraint("role_id", "menu_id", name="uq_role_menu"),
    )

    op.create_table(
        "rbac_user_roles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("auth_users.id", ondelete="CASCADE"), index=True),
        sa.Column("role_id", sa.Integer, sa.ForeignKey("rbac_roles.id", ondelete="CASCADE"), index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_role"),
    )


def downgrade() -> None:
    op.drop_table("rbac_user_roles")
    op.drop_table("rbac_role_menus")
    op.drop_table("rbac_menus")
    op.drop_table("rbac_role_permissions")
    op.drop_table("rbac_permissions")
    op.drop_table("rbac_roles")
    op.drop_table("auth_user_oauth")
    op.drop_table("auth_users")
