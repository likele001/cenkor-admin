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
    # 目标产品/宿主：cenkor-admin（平台内置应用）/ cenkormes / lightmes / cenkor-process ...
    # 多产品目录隔离与 app_key 命名空间的维度，默认平台自营。
    product: Mapped[str] = mapped_column(String(32), default="cenkor-admin", nullable=False, index=True)
    # 应用开发方式（交付安装目标）：platform=平台内置(manifest.py) / extension=产品扩展(manifest.json) / standalone=独立整包
    # 取代旧「product != cenkor-admin 即扩展」的隐式判定；校验/安装按钮/门户徽标一律由此驱动。
    dev_method: Mapped[str] = mapped_column(String(16), default="extension", nullable=False, index=True)
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
        UniqueConstraint("product", "app_key", "version", name="uq_app_submission_product_key_version"),
    )


class AppIntro(Base):
    """应用富介绍（详情页长图文）

    独立于 app_submissions 的旁表，按 (product, app_key) 唯一定位，
    这样即便应用尚未提交/审核，也能预置富介绍；门户详情页读取时按
    DB 介绍 > manifest > SHOWCASE 的优先级合并。long_description 为富文本
    HTML（渲染端用 DOMPurify 净化）。
    """
    __tablename__ = "app_intros"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product: Mapped[str] = mapped_column(String(32), default="cenkor-admin", nullable=False, index=True)
    app_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    highlights: Mapped[Any] = mapped_column(json_column(), nullable=True)  # list[str]
    tags: Mapped[Any] = mapped_column(json_column(), nullable=True)  # list[str]
    screenshots: Mapped[Any] = mapped_column(json_column(), nullable=True)  # list[str] 图片 URL
    long_description: Mapped[str | None] = mapped_column(Text, nullable=True)  # 富文本 HTML
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("product", "app_key", name="uq_app_intro_product_key"),
    )
