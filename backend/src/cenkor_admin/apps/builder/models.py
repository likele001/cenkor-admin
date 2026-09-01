"""Builder App · ORM 模型（M3·P2 3.2）"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import String, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from cenkor_admin.core.compat import json_column
from cenkor_admin.core.db import Base


class Page(Base):
    """页面（区块 schema：blocks: [{type, data}]）。"""

    __tablename__ = "cms_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    schema: Mapped[list[Any]] = mapped_column(json_column(), default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
