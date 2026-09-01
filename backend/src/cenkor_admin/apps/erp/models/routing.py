"""ERP 制造深化模型：工作中心 / 工艺路线 / 工艺步骤 / 生产排程"""
from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cenkor_admin.core.db import Base


class ErpWorkCenter(Base):
    """工作中心 / 设备 / 产线"""
    __tablename__ = "erp_work_centers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    wc_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="machine")  # machine/labor/line
    location: Mapped[str | None] = mapped_column(String(128), nullable=True)
    capacity: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default="8")  # 每日产能/工时
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    labor_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")  # active/inactive/maintenance
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("code", name="uq_erp_work_centers_code"), {"comment": "工作中心"})


class ErpRouting(Base):
    """工艺路线头（带版本）"""
    __tablename__ = "erp_routings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    version: Mapped[str] = mapped_column(String(16), nullable=False, server_default="V1")
    is_active: Mapped[bool] = mapped_column(Integer, nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    output_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="1")
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    lead_time_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default="0")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    steps = relationship("ErpRoutingStep", back_populates="routing", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("product_id", "version", name="uq_erp_routings_product_version"),
        {"comment": "工艺路线"},
    )


class ErpRoutingStep(Base):
    """工艺路线工序步骤"""
    __tablename__ = "erp_routing_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    routing_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_routings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")  # 工序顺序
    process_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    process_name: Mapped[str] = mapped_column(String(64), nullable=False)
    work_center_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_work_centers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    work_center_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    std_time: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, server_default="0")  # 单件标准工时(h)
    setup_minutes: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default="0")  # 准备分钟
    time_type: Mapped[str] = mapped_column(String(8), nullable=False, server_default="per_unit")  # per_unit/per_lot
    yield_rate: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, server_default="100")  # 良率%
    is_last: Mapped[bool] = mapped_column(Integer, nullable=False, server_default="0")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)

    routing = relationship("ErpRouting", back_populates="steps")

    __table_args__ = ({"comment": "工艺路线步骤"},)


class ErpProductionSchedule(Base):
    """生产排程（工单 × 工序 × 工作中心的排产记录）"""
    __tablename__ = "erp_production_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    work_order_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_work_orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    work_order_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    product_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    routing_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    step_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    step_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    process_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    work_center_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_work_centers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    work_center_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    plan_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    plan_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    done_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    plan_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="planned")  # planned/in_progress/completed/skipped
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("code", name="uq_erp_production_schedules_code"), {"comment": "生产排程"})