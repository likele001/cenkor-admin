"""payment 应用数据模型。

设计要点：
- 所有配置与订单按 scene_key 隔离，scene_key = 业务应用 key（crm / mes / erp / cms / store ...）
- 通道敏感字段（私钥、密钥）加密后存入 config，出参一律脱敏
- 金额一律存「分」，展示层再换算
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from cenkor_admin.core.compat import json_column
from cenkor_admin.core.db import Base


class PayChannel(Base):
    """支付通道配置。

    同一 scene 下可挂多条通道（微信官方 / 支付宝官方 / 虎皮椒），
    下单时按 is_default + sort 选路，也支持调用方显式指定 channel_id。
    """

    __tablename__ = "pay_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scene_key: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    sub_type: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="live")
    config: Mapped[Any] = mapped_column(json_column(), nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    __table_args__ = (
        Index("ix_pay_channels_scene", "scene_key", "enabled"),
    )


class PayOrder(Base):
    """支付订单。"""

    __tablename__ = "pay_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    out_trade_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    scene_key: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    channel_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    sub_type: Mapped[str] = mapped_column(String(16), nullable=False, default="")

    subject: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="CNY")
    refunded_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    pay_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    pay_payload: Mapped[Any] = mapped_column(json_column(), nullable=True)
    trade_no: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    biz_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    biz_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    extra: Mapped[Any] = mapped_column(json_column(), nullable=True)

    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    return_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    expire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notify_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_notify_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_pay_orders_scene_status", "scene_key", "status"),
        Index("ix_pay_orders_created", "created_at"),
    )


class PayRefund(Base):
    """退款单。"""

    __tablename__ = "pay_refunds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    out_refund_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    order_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    out_trade_no: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scene_key: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    channel_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="")

    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    refund_trade_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw: Mapped[Any] = mapped_column(json_column(), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    operator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class PayNotifyLog(Base):
    """第三方回调 / 查询原始日志，排查对账问题必备。"""

    __tablename__ = "pay_notify_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scene_key: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="notify")
    out_trade_no: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    headers: Mapped[Any] = mapped_column(json_column(), nullable=True)
    raw: Mapped[Any] = mapped_column(json_column(), nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_pay_notify_scene_created", "scene_key", "created_at"),
    )
