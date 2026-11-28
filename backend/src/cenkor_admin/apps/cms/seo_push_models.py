"""搜索引擎收录推送队列。

为什么要落库排队而不是发布时直接请求：
- IndexNow/百度接口都有频率限制，发布高峰一次性推几十条会被限流；
- 网络失败必须能重试，而发布事务里不能因为第三方接口超时把发布搞失败。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from cenkor_admin.core.db import Base


class SeoPushJob(Base):
    __tablename__ = "cms_seo_push_queue"
    __table_args__ = (
        Index("ix_seo_push_site_status", "site_id", "status"),
        Index("ix_seo_push_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    # indexnow（必应/Yandex）/ baidu
    engine: Mapped[str] = mapped_column(String(16), nullable=False, default="indexnow")
    # pending / success / failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
