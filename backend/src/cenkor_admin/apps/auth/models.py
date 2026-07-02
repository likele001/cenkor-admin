"""Auth App · 用户模型"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import String, Integer, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cenkor_admin.core.db import Base

if TYPE_CHECKING:
    from cenkor_admin.apps.rbac.models import Role, UserRole


class User(Base):
    __tablename__ = "auth_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, default=1, index=True)

    username: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    nickname: Mapped[str] = mapped_column(String(80), default="")
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)

    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0)  # 用于撤销 refresh token

    status: Mapped[str] = mapped_column(String(20), default="active")  # active / disabled / locked
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    user_type: Mapped[str] = mapped_column(String(20), default="admin")  # admin / superadmin

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 关联到 RBAC 的 UserRole（单向，UserRole 那边是 FK 持有者）
    # 不在 UserRole 上定义反向，避免循环导入
    roles: Mapped[list["UserRole"]] = relationship(  # type: ignore[name-defined]
        "UserRole",
        primaryjoin="User.id == foreign(UserRole.user_id)",
        cascade="all, delete-orphan",
    )


class UserOAuth(Base):
    """第三方登录绑定（飞书 / 企微 / 微信 / GitHub 等）"""
    __tablename__ = "auth_user_oauth"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), index=True, nullable=False)  # feishu / wechat / github
    open_id: Mapped[str] = mapped_column(String(200), nullable=False)
    union_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    access_token_enc: Mapped[str | None] = mapped_column(String(500), nullable=True)
    refresh_token_enc: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # 一个 provider 同一个 open_id 只能绑一个用户
        # PG: UNIQUE(provider, open_id) - MySQL 也支持
    )


class LoginLog(Base):
    """用户登录历史"""
    __tablename__ = "login_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    provider: Mapped[str] = mapped_column(String(40), default="local", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ApiKey(Base):
    """API Key（用户级访问凭证）"""
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    hash: Mapped[str] = mapped_column(String(128), nullable=False)
    scopes: Mapped[Any | None] = mapped_column("scopes", String(500), nullable=True)  # 简单存逗号分隔字符串
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SystemSetting(Base):
    """系统级 KV（与 cms_site_config 区分）"""
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Any | None] = mapped_column("value", String(2000), nullable=True)  # 存 JSON 字符串
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    group: Mapped[str] = mapped_column(String(40), index=True, nullable=False, default="general")
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
