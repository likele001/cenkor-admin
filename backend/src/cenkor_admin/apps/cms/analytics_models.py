"""内容运营闭环 · 埋点与分发 ORM 模型。

为什么单独一个文件：``models.py`` 已经九百多行，再塞进去找东西越来越难。
这四张表有个共同点 —— 它们都服务于「内容上线**之后**发生了什么」，
而 ``models.py`` 管的是「内容怎么写」。两类问题分开住，改的时候不容易踩错。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from cenkor_admin.core.compat import json_column
from cenkor_admin.core.db import Base


class CmsTrackEvent(Base):
    """埋点原始事件。

    保留原始事件而不是只存汇总，是为了「换个口径重算」这件事可持续。
    只存日汇总的话，哪天运营说「我想看按来源渠道拆分的次留」，就得
    从那天起重新攒数据。

    ``stat_date`` 冗余存业务时区（Asia/Shanghai）算好的自然日：聚合时
    不用反复做时区转换，且能直接走索引。用 UTC 切日会在北京时间早上 8 点
    断一天，运营看报表会以为数据丢了。
    """

    __tablename__ = "cms_track_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    site_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    entry_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # pv / heartbeat / scroll / conversion
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    visitor_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    path: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    referrer: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    utm_source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(80), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(120), nullable=True)
    device: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    # 存摘要不存原文：埋点表是唯一会被第三方脚本大量写入的表，
    # 明文旅客 IP 一旦泄露，性质比内容泄露严重得多。
    ip_hash: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    ua_hash: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scroll_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    stat_date: Mapped[date] = mapped_column(Date, nullable=False)
    meta: Mapped[dict[str, Any] | None] = mapped_column(json_column(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_track_events_entry_date", "entry_id", "stat_date"),
        Index("ix_track_events_stat_date", "stat_date"),
        Index("ix_track_events_site_date", "site_id", "stat_date"),
        Index("ix_track_events_type_date", "event_type", "stat_date"),
        Index("ix_track_events_ip_date", "ip_hash", "stat_date"),
    )


class CmsEntryStatsDaily(Base):
    """内容日汇总。

    ``source`` 是「预留第三方通道」的落点：self=自建埋点，baidu/ga=第三方
    接口拉取，manual=人工导入。同一篇同一天可以并存多来源，看板按来源拆分
    或合并都行，将来接百度统计不用改表结构。
    """

    __tablename__ = "cms_entry_stats_daily"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    site_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    entry_id: Mapped[int] = mapped_column(Integer, nullable=False)
    stat_date: Mapped[date] = mapped_column(Date, nullable=False)
    pv: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uv: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_scroll_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    bounce_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conversion_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="self")
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("entry_id", "stat_date", "source", name="uq_entry_stats_daily"),
        Index("ix_entry_stats_date", "stat_date"),
        Index("ix_entry_stats_site_date", "site_id", "stat_date"),
        Index("ix_entry_stats_entry", "entry_id", "stat_date"),
    )


class CmsPublishChannel(Base):
    """分发渠道配置。

    ``config`` 里放凭据（公众号 AppID/Secret 等），写入前必须走
    ``core.secrets.encrypt_secret``，不能明文落库。
    """

    __tablename__ = "cms_publish_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    channel_key: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    # builtin / webhook / wechat / export
    channel_type: Mapped[str] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config: Mapped[dict[str, Any]] = mapped_column(json_column(), default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("channel_key", name="uq_publish_channel_key"),)


class CmsPublishJob(Base):
    """分发任务。

    一个条目发到 N 个渠道 = N 条任务，各自独立重试。渠道 A 失败不该拦住
    渠道 B，否则公众号 Secret 配错一次，整篇内容就永远发不出去。
    """

    __tablename__ = "cms_publish_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    entry_id: Mapped[int] = mapped_column(Integer, nullable=False)
    channel_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # pending / running / success / failed / skipped
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(json_column(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_publish_jobs_entry", "entry_id"),
        Index("ix_publish_jobs_status", "status", "scheduled_at"),
        Index("ix_publish_jobs_channel", "channel_id"),
    )
