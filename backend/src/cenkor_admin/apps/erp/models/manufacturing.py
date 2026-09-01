"""ERP 制造基础模型：BOM / 生产工单 / 工单用料 / 报工 / 质检"""
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


class ErpBom(Base):
    """BOM 头（带版本）"""
    __tablename__ = "erp_boms"

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
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items = relationship("ErpBomItem", back_populates="bom", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("product_id", "version", name="uq_erp_boms_product_version"),
        {"comment": "BOM 头"},
    )


class ErpBomItem(Base):
    """BOM 明细（替代料管理：primary=1 为主料）"""
    __tablename__ = "erp_bom_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bom_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_boms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    component_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_products.id", ondelete="SET NULL"), nullable=True
    )
    component_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    component_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    spec: Mapped[str | None] = mapped_column(String(128), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    loss_rate: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, server_default="0")
    is_substitute: Mapped[bool] = mapped_column(Integer, nullable=False, server_default="0")
    substitute_for: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)

    bom = relationship("ErpBom", back_populates="items")

    __table_args__ = ({"comment": "BOM 明细"},)


class ErpWorkOrder(Base):
    """生产工单"""
    __tablename__ = "erp_work_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    bom_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sales_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warehouse_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_warehouses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="draft")  # draft/released/in_progress/completed/cancelled
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    produced_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items = relationship("ErpWorkOrderItem", back_populates="order", cascade="all, delete-orphan")
    reports = relationship("ErpOpReport", back_populates="order")

    __table_args__ = (UniqueConstraint("code", name="uq_erp_work_orders_code"), {"comment": "生产工单"})


class ErpWorkOrderItem(Base):
    """工单用料明细"""
    __tablename__ = "erp_work_order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_work_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    component_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_products.id", ondelete="SET NULL"), nullable=True
    )
    component_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    component_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    need_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    issued_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")

    order = relationship("ErpWorkOrder", back_populates="items")

    __table_args__ = ({"comment": "工单用料明细"},)


class ErpOpReport(Base):
    """工序报工"""
    __tablename__ = "erp_op_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_work_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    process_name: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 工序/工站
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    qualified_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    reject_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    work_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default="0")
    operator: Mapped[str | None] = mapped_column(String(64), nullable=True)
    report_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="reported")
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    order = relationship("ErpWorkOrder", back_populates="reports")

    __table_args__ = ({"comment": "工序报工"},)


class ErpQualityCheck(Base):
    """质检单（IQC/IPQC/FQC 统一）"""
    __tablename__ = "erp_quality_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    check_type: Mapped[str] = mapped_column(String(8), nullable=False)  # IQC/IPQC/FQC
    product_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    product_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ref_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # receipt/work_order/shipment
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    check_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    qualified_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    reject_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    result: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")  # pending/pass/fail
    inspector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    check_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("code", name="uq_erp_quality_checks_code"), {"comment": "质检单"})