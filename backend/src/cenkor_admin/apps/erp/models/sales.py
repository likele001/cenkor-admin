"""ERP 销售订单模块 ORM 模型"""
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


class ErpQuotation(Base):
    """报价单"""
    __tablename__ = "erp_quotations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_customers.id", ondelete="SET NULL"), nullable=False, index=True
    )
    contact_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_customer_contacts.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="draft")
    quote_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, server_default="CNY")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    tax_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    discount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    owner_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items = relationship(
        "ErpQuotationItem", back_populates="quotation", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("code", name="uq_erp_quotations_code"),)


class ErpQuotationItem(Base):
    """报价单明细"""
    __tablename__ = "erp_quotation_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quotation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_quotations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_products.id", ondelete="SET NULL"), nullable=True
    )
    product_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    spec: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, server_default="0")
    sort: Mapped[int] = mapped_column(Integer, default=0)

    quotation = relationship("ErpQuotation", back_populates="items")


class ErpSalesOrder(Base):
    """销售订单"""
    __tablename__ = "erp_sales_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_customers.id", ondelete="SET NULL"), nullable=False, index=True
    )
    contact_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_customer_contacts.id", ondelete="SET NULL"), nullable=True
    )
    quotation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_quotations.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="draft")
    order_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, server_default="CNY")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    tax_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    discount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    payment_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="unpaid")
    owner_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items = relationship(
        "ErpSalesOrderItem", back_populates="order", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("code", name="uq_erp_sales_orders_code"),)


class ErpSalesOrderItem(Base):
    """销售订单明细"""
    __tablename__ = "erp_sales_order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sales_order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_sales_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_products.id", ondelete="SET NULL"), nullable=True
    )
    product_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    spec: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, server_default="0")
    sort: Mapped[int] = mapped_column(Integer, default=0)

    order = relationship("ErpSalesOrder", back_populates="items")


class ErpShipment(Base):
    """出货单"""
    __tablename__ = "erp_shipments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    sales_order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_sales_orders.id", ondelete="SET NULL"), nullable=False, index=True
    )
    # warehouse_id 为普通索引列；erp_warehouses 在 Phase 5 建表
    warehouse_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    ship_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    receiver: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tracking_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items = relationship(
        "ErpShipmentItem", back_populates="shipment", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("code", name="uq_erp_shipments_code"),)


class ErpShipmentItem(Base):
    """出货明细"""
    __tablename__ = "erp_shipment_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shipment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_shipments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)

    shipment = relationship("ErpShipment", back_populates="items")