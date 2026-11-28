"""敏感词库。

为什么这张表**不在** site_scope 的自动过滤清单里：
它要同时支持「全站通用词」和「单站专属词」，全站词没有 site_id（或为 NULL），
自动过滤会把这些词直接滤掉，等于敏感词库凭空失效。所以查询统一在 service 层
显式写 `scope='global' OR site_id=当前站`，比一刀切的过滤更准确。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from cenkor_admin.core.db import Base


class SensitiveWord(Base):
    __tablename__ = "cms_sensitive_words"
    __table_args__ = (
        Index("ix_sensitive_words_site", "site_id"),
        Index("ix_sensitive_words_level", "level"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # scope=global 时为 NULL；scope=site 时必填
    site_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(8), nullable=False, default="site")
    word: Mapped[str] = mapped_column(String(120), nullable=False)
    # block：命中即拒绝提交；warn：允许保存，审核页标红
    level: Mapped[str] = mapped_column(String(8), nullable=False, default="warn")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
