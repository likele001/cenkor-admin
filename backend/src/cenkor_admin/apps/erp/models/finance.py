"""ERP 财务模块 ORM 模型"""
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


class ErpInvoice(Base):
    """销售发票"""
    __tablename__ = "erp_invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    sales_order_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_sales_orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_customers.id", ondelete="SET NULL"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="issued")
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, server_default="CNY")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    tax_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("code", name="uq_erp_invoices_code"), {"comment": "销售发票"})


class ErpPurchaseInvoice(Base):
    """采购发票"""
    __tablename__ = "erp_purchase_invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    purchase_order_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_purchase_orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    supplier_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_suppliers.id", ondelete="SET NULL"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="issued")
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, server_default="CNY")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    tax_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("code", name="uq_erp_purchase_invoices_code"), {"comment": "采购发票"})


class ErpPayment(Base):
    """收付款记录（direction: in=收款 out=付款）"""
    __tablename__ = "erp_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # in / out
    method: Mapped[str | None] = mapped_column(String(32), nullable=True)  # bank/cash/wechat/alipay
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    paid_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    ref_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # invoice / purchase_invoice
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    supplier_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operator_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("code", name="uq_erp_payments_code"), {"comment": "收付款记录"})


class ErpAccountReceivable(Base):
    """应收账款"""
    __tablename__ = "erp_accounts_receivable"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    invoice_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # invoice
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="open")  # open/partial/settled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = ({"comment": "应收账款"},)


class ErpAccountPayable(Base):
    """应付账款"""
    __tablename__ = "erp_accounts_payable"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplier_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    invoice_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # purchase_invoice
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="open")  # open/partial/settled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = ({"comment": "应付账款"},)