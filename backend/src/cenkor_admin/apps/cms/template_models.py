"""CMS 模板主题模型

独立文件定义、由 models.py 末尾 import 注册进 Base.metadata，
与 analytics_models / knowledge_models 保持同一套组织方式。

一条记录 = 主题里的一个文件。渲染时 DB 优先，缺失的文件回落到内置主题，
所以用户只需要覆盖想改的那几个文件，不用整包托管。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from cenkor_admin.core.db import Base

__all__ = ["THEME_FILE_KINDS", "CmsTemplate"]

# layout 骨架 / list 列表 / detail 详情 / page 自定义页 / partial 片段 / macro 宏 / asset 样式脚本
THEME_FILE_KINDS = ("layout", "list", "detail", "page", "partial", "macro", "asset")


class CmsTemplate(Base):
    """主题文件（Jinja2 源码）"""

    __tablename__ = "cms_templates"
    __table_args__ = (
        UniqueConstraint("site_id", "theme", "path", name="uq_cms_templates_site_theme_path"),
        Index("ix_cms_templates_site_theme", "site_id", "theme"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cms_sites.id", ondelete="CASCADE"), nullable=False, default=1, index=True
    )
    theme: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="partial")

    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # 是否为站点当前生效主题（同一站点同一时刻只应有一个 True）
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
