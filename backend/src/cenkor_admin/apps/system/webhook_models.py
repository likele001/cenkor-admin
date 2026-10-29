"""Webhook 投递日志模型。

单独成文件而不塞进 ``apps/system/models.py``：那张表是「配置」，这张是「流水」，
两者的读写频率、保留策略、清理方式完全不同（流水要按天归档）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from cenkor_admin.core.compat import json_column
from cenkor_admin.core.db import Base


class WebhookDelivery(Base):
    """一次投递尝试的完整记录（M3·P2 3.1 加固）。"""

    __tablename__ = "system_webhook_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 事件唯一 ID：重试不变，下游用它幂等去重
    event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    webhook_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event: Mapped[str] = mapped_column(String(60), nullable=False)
    # 快照：订阅被删/改地址后，历史记录仍能说明当时发给了谁
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(json_column(), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_snippet: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
