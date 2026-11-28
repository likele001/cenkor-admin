"""建站方案（site plan）：需求 → 栏目树 + 选题 → 确认 → 执行。

单独放一个模块，不塞进已经三千行的 models.py；Base 是同一个，迁移照常能发现。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from cenkor_admin.core.compat import json_column
from cenkor_admin.core.db import Base


class SitePlan(Base):
    """一次建站方案。

    `status` 流转：draft（已落库待确认）→ confirmed（人确认过）→ running → done / failed
    → cancelled。`apply` 只接受 confirmed，避免「生成完没看就跑了」。
    """

    __tablename__ = "cms_site_plans"
    __table_args__ = (Index("ix_site_plans_site_status", "site_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cms_sites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 需求原文 + 参数（关键词、目标数量、语言），留档方便复现与二次调整
    brief: Mapped[dict[str, Any]] = mapped_column(json_column(), default=dict)
    plan_json: Mapped[dict[str, Any]] = mapped_column(json_column(), default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", index=True)
    content_type_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cms_content_types.id", ondelete="SET NULL"), nullable=True
    )
    lang: Mapped[str] = mapped_column(String(20), nullable=False, default="zh-CN")
    # 执行后指向生成的批量批次，前端据此显示「文章跑了几篇」
    batch_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SitePlanItem(Base):
    """方案里的一条待办：一个栏目、一篇选题（页面骨架预留 kind=page）。"""

    __tablename__ = "cms_site_plan_items"
    __table_args__ = (
        Index("ix_site_plan_items_plan_seq", "plan_id", "seq"),
        Index("ix_site_plan_items_plan_kind", "plan_id", "kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cms_site_plans.id", ondelete="CASCADE"), nullable=False
    )
    site_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="category")
    # 栏目树用 key 关联父子，避免执行前就得知道数据库 id
    parent_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(json_column(), default=dict)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
