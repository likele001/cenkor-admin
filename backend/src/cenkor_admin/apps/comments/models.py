"""Comments App · ORM 模型（M4·P3 4.2）"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from cenkor_admin.core.db import Base


class Comment(Base):
    """内容评论（按 content_type_key + object_id 挂接任意内容）。"""

    __tablename__ = "cms_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_type_key: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    object_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cms_comments.id", ondelete="SET NULL"), nullable=True
    )
    author_name: Mapped[str] = mapped_column(String(80), nullable=False)
    author_email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending/approved/spam/deleted
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_cms_comments_ct_object", "content_type_key", "object_id"),
    )
