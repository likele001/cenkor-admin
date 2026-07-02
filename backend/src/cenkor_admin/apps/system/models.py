"""已安装 App 注册表"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import String, DateTime, func
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
