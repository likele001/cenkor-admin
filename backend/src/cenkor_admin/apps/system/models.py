"""已安装 App 注册表 + Webhook 配置 + URL 重定向（M3·P2）"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import String, DateTime, func, Integer, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from cenkor_admin.core.compat import json_column
from cenkor_admin.core.db import Base


class InstalledApp(Base):
    __tablename__ = "platform_apps"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    version: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="installed")  # installed / uninstalled
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uninstalled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # 委派权限给其他角色：{"role_code": ["permission_code", ...]}
    permissions_grants: Mapped[dict[str, Any] | None] = mapped_column(
        json_column(), nullable=True, default=dict
    )
    # 是否有前端资源
    has_frontend: Mapped[bool] = mapped_column(default=False)


class Webhook(Base):
    """Webhook 订阅（M3·P2 3.1）：事件推送外部系统。"""

    __tablename__ = "system_webhooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    events: Mapped[list[Any]] = mapped_column(json_column(), default=list)  # ["entry.saved", ...]
    secret: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Redirect(Base):
    """URL 重定向（M3·P2 3.3）：from_path → to_path。"""

    __tablename__ = "system_redirects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_path: Mapped[str] = mapped_column(String(500), unique=True, nullable=False, index=True)
    to_path: Mapped[str] = mapped_column(String(500), nullable=False)
    code: Mapped[int] = mapped_column(Integer, default=301)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
