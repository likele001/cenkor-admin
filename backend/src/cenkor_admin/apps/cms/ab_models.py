"""页面级 A/B 实验表。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cenkor_admin.core.db import Base


class AbTest(Base):
    __tablename__ = "cms_ab_tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("cms_entries.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    # B 版覆盖字段：{"title":..., "content":{...}, "seo_title":..., "seo_description":...}
    variant_b: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # B 版流量占比（0-100），50 即对半分
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    views_a: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    views_b: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
