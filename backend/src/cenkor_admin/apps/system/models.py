"""已安装 App 注册表 + Webhook 配置 + URL 重定向（M3·P2）"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
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
    # 是否启用：停用后该 App 的菜单隐藏、API 被门禁拦截，数据与角色授权关系保留
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


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


class CodegenRun(Base):
    """代码生成执行历史（后台「系统 > 代码生成」页）。

    每次「下载源码包 / 安装到本系统」写一条，成功与失败都写：失败保留后端原始报错原文；
    成功保留当时的 spec 快照，可直接「再次执行」。只删留痕不影响已安装的 App 与其数据表。
    """

    __tablename__ = "codegen_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    app_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    app_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # generate / install
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")  # ok / failed
    spec: Mapped[dict[str, Any] | None] = mapped_column(json_column(), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    operator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class UpgradeRun(Base):
    """核心平台在线升级执行历史（后台「系统 > 在线升级」页）。

    每次「下载核心包 / 安装 / 失败回滚 / 手动回滚」写一条。
    - status 标识结果（pending/running/success/failed/rolled_back）
    - backup_path 指向 /www/backup/cenkor-admin/snapshot_<时间>/（升级前快照）
    - pkg_path 上传的核心包 / 下载的 URL → 本地路径
    - log 完整 stdout/stderr（每行追加，截断 200KB）
    - error 失败时的后端原始报错
    - duration_ms / operator_id 耗时 + 操作人
    - rollback_from_id 若是「对某次升级的手动回滚」，指向被回滚的 id
    """

    __tablename__ = "upgrade_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="core")  # core（仅主程序）
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # url | tar_upload | git
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="stable")
    from_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    backup_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    pkg_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    log: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    operator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rollback_from_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
