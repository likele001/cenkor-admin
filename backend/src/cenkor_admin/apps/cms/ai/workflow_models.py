"""AI 工作流编排 · 数据模型

三张表：
- cms_workflows      工作流定义（节点 + 连线整张图存 JSONB）
- cms_workflow_runs  一次执行（输入变量、累计上下文、整体状态）
- cms_workflow_steps 每个节点的执行日志（同一次执行内 node_id 唯一，重试覆盖）

## 为什么图存 JSONB，而不是 nodes / edges 两张表

编排图的读写永远是「整张图一起」：画布加载一次读全图，保存一次写全图，
执行时一次遍历。拆成关系表后每次保存都要做差量对比、保序、处理删节点时的
孤儿连线 —— 全是自己的麻烦，换不来任何查询能力（没有「查所有用了起草步骤
的工作流」这种需求，真要有，JSONB 也能 `@>` 查）。

## 为什么 steps 是 UNIQUE(run_id, node_id)

「重跑失败的那一步」是最常见的动作。如果按追加写，一次失败的流水线会出现
三四条同名节点记录，用户得自己分辨哪条是最后一次。用 UPSERT 覆盖同一条，
执行详情页永远是一节点一行，读起来和画布一一对应。

## 状态机

run: pending → running → succeeded / failed / halted / cancelled
halted 是独立状态，不复用 failed：查重命中、质检不达标这类「主动叫停」不是
故障，混进失败率里会让流水线的健康度指标失真。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from cenkor_admin.core.compat import json_column
from cenkor_admin.core.db import Base


class CmsWorkflow(Base):
    __tablename__ = "cms_workflows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cms_sites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    graph: Mapped[dict] = mapped_column(json_column(), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    cron: Mapped[str | None] = mapped_column(String(80), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_run_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CmsWorkflowRun(Base):
    __tablename__ = "cms_workflow_runs"
    __table_args__ = (Index("ix_cms_wf_runs_wf", "workflow_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cms_workflows.id", ondelete="CASCADE"), nullable=False
    )
    site_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    input: Mapped[dict] = mapped_column(json_column(), nullable=False)
    vars: Mapped[dict] = mapped_column(json_column(), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CmsWorkflowStep(Base):
    __tablename__ = "cms_workflow_steps"
    __table_args__ = (Index("ix_cms_wf_steps_run", "run_id", "seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cms_workflow_runs.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[str] = mapped_column(String(60), nullable=False)
    node_type: Mapped[str] = mapped_column(String(60), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    input: Mapped[dict] = mapped_column(json_column(), nullable=False)
    output: Mapped[dict] = mapped_column(json_column(), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
