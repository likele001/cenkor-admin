"""Builder App · ORM 模型（M3·P2 3.2）"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from cenkor_admin.core.compat import json_column
from cenkor_admin.core.db import Base


class Page(Base):
    """页面（区块 schema：blocks: [{type, data}]）。"""

    __tablename__ = "cms_pages"
    __table_args__ = (UniqueConstraint("site_id", "key", name="uq_pages_site_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", index=True)
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    schema: Mapped[list[Any]] = mapped_column(json_column(), default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    # 落地页 / 子站扩展：seo 存 head 元信息，kind 区分独立页与子站内页，
    # site_key 把同一子站的多页归到一起，nav 存该子站的导航（子站内共用）
    seo: Mapped[dict[str, Any]] = mapped_column(json_column(), default=dict)
    kind: Mapped[str] = mapped_column(String(20), default="page", index=True)
    site_key: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    nav: Mapped[list[Any]] = mapped_column(json_column(), default=list)
    ai_generation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
