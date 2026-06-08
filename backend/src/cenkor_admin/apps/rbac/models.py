"""RBAC App · 模型"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Integer, Boolean, ForeignKey, DateTime, func, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cenkor_admin.core.db import Base


# ---- 角色 ----
class Role(Base):
    __tablename__ = "rbac_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, default=1, index=True)
    code: Mapped[str] = mapped_column(String(50), index=True)  # admin / editor / viewer ...
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)  # 系统内置不可删
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    permissions: Mapped[list["RolePermission"]] = relationship(back_populates="role", cascade="all, delete-orphan")
    menus: Mapped[list["RoleMenu"]] = relationship(back_populates="role", cascade="all, delete-orphan")
    users: Mapped[list["UserRole"]] = relationship(back_populates="role", cascade="all, delete-orphan")


# ---- 权限 ----
class Permission(Base):
    __tablename__ = "rbac_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True)  # cms:product:read
    type: Mapped[str] = mapped_column(String(20), default="api")  # menu / api / data / ui
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RolePermission(Base):
    __tablename__ = "rbac_role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("rbac_roles.id", ondelete="CASCADE"), index=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("rbac_permissions.id", ondelete="CASCADE"), index=True)

    role: Mapped[Role] = relationship(back_populates="permissions")
    permission: Mapped[Permission] = relationship()


# ---- 菜单 ----
class Menu(Base):
    __tablename__ = "rbac_menus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("rbac_menus.id", ondelete="CASCADE"), nullable=True)
    title: Mapped[str] = mapped_column(String(80))
    icon: Mapped[str | None] = mapped_column(String(40), nullable=True)
    path: Mapped[str | None] = mapped_column(String(200), nullable=True)
    component: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RoleMenu(Base):
    __tablename__ = "rbac_role_menus"
    __table_args__ = (UniqueConstraint("role_id", "menu_id", name="uq_role_menu"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("rbac_roles.id", ondelete="CASCADE"), index=True)
    menu_id: Mapped[int] = mapped_column(ForeignKey("rbac_menus.id", ondelete="CASCADE"), index=True)

    role: Mapped[Role] = relationship(back_populates="menus")
    menu: Mapped[Menu] = relationship()


# ---- 用户-角色关联 ----
class UserRole(Base):
    __tablename__ = "rbac_user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("auth_users.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("rbac_roles.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # 单向关系：只从 User.roles → UserRole 导航（auth/models.py 里已有反向）
    role: Mapped[Role] = relationship(back_populates="users")
