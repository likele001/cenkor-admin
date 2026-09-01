"""ERP 采购申请（PR）+ 审批流模型：申请头 / 明细 / 审批记录"""
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


class ErpPurchaseRequest(Base):
    """采购申请单（PR）"""
    __tablename__ = "erp_purchase_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    # draft/pending_approval/approved/rejected/converting/converted/cancelled
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    requester: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 申请人
    department: Mapped[str | None] = mapped_column(String(64), nullable=True)
    required_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    urgency: Mapped[str] = mapped_column(String(8), nullable=False, server_default="normal")  # normal/urgent/emergency
    expected_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, server_default="CNY")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 审批流
    current_level: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    approver_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approver_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    purchase_order_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_purchase_orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owner_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items = relationship(
        "ErpPurchaseRequestItem", back_populates="request", cascade="all, delete-orphan"
    )
    approvals = relationship(
        "ErpApprovalRecord", back_populates="request", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("code", name="uq_erp_purchase_requests_code"), {"comment": "采购申请单"})


class ErpPurchaseRequestItem(Base):
    """采购申请明细"""
    __tablename__ = "erp_purchase_request_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_purchase_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_products.id", ondelete="SET NULL"), nullable=True
    )
    product_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    spec: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    converted_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    expected_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    need_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)

    request = relationship("ErpPurchaseRequest", back_populates="items")

    __table_args__ = ({"comment": "采购申请明细"},)


class ErpApprovalRecord(Base):
    """通用审批记录（PR 审批流使用，支持多级审批）"""
    __tablename__ = "erp_approval_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_purchase_requests.id", ondelete="CASCADE"), nullable=True, index=True
    )
    ref_type: Mapped[str] = mapped_column(String(32), nullable=False, default="purchase_request")  # purchase_request/...
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    # approved/rejected
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approver_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approver_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    request = relationship("ErpPurchaseRequest", back_populates="approvals")

    __table_args__ = ({"comment": "审批记录"},)