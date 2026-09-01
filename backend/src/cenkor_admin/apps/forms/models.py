"""Forms App · ORM 模型（M4·P3 4.3）"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import String, Integer, DateTime, Text, Boolean, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from cenkor_admin.core.compat import json_column
from cenkor_admin.core.db import Base


class Form(Base):
    """表单定义。fields: [{key, label, type, required, options?}]"""

    __tablename__ = "cms_forms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    fields: Mapped[list[Any]] = mapped_column(json_column(), default=list)
    success_message: Mapped[str | None] = mapped_column(String(200), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FormSubmission(Base):
    """表单提交记录。data: {field_key: value}"""

    __tablename__ = "cms_form_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    form_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cms_forms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    data: Mapped[dict[str, Any]] = mapped_column(json_column(), default=dict)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
