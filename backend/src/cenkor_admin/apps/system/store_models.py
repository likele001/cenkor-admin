"""应用商店模型"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import String, Integer, DateTime, Text, func, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from cenkor_admin.core.compat import json_column
from cenkor_admin.core.db import Base


class Developer(Base):
    """开发者账户"""
    __tablename__ = "app_developers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active / banned
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppSubmission(Base):
    """应用提交记录"""
    __tablename__ = "app_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    developer_id: Mapped[int] = mapped_column(Integer, ForeignKey("app_developers.id"), nullable=False, index=True)
    app_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str] = mapped_column(String(10), default="📦")
    category: Mapped[str] = mapped_column(String(50), default="system")
    manifest_data: Mapped[Any] = mapped_column(json_column(), nullable=True)  # manifest 解析后的数据
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)  # ZIP 文件路径
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # SHA256
    status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )  # pending / approved / rejected / installed
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)  # 审核备注
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("app_key", "version", name="uq_app_submission_key_version"),
    )
