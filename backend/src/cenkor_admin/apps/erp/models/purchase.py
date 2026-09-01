"""ERP 采购 + 仓库模块 ORM 模型"""
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


class ErpWarehouse(Base):
    """仓库"""
    __tablename__ = "erp_warehouses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    manager: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("code", name="uq_erp_warehouses_code"), {"comment": "仓库"})


class ErpPurchaseOrder(Base):
    """采购订单"""
    __tablename__ = "erp_purchase_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    supplier_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_suppliers.id", ondelete="SET NULL"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="draft")
    order_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
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
        "ErpPurchaseOrderItem", back_populates="order", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("code", name="uq_erp_purchase_orders_code"),)


class ErpPurchaseOrderItem(Base):
    """采购订单明细"""
    __tablename__ = "erp_purchase_order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    purchase_order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_products.id", ondelete="SET NULL"), nullable=True
    )
    product_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    spec: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    received_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, server_default="0")
    sort: Mapped[int] = mapped_column(Integer, default=0)

    order = relationship("ErpPurchaseOrder", back_populates="items")


class ErpPurchaseReceipt(Base):
    """收货单"""
    __tablename__ = "erp_purchase_receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    purchase_order_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_purchase_orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    supplier_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_suppliers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    warehouse_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_warehouses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    receipt_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    carrier: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tracking_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items = relationship("ErpStockMovement", back_populates="receipt", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("code", name="uq_erp_purchase_receipts_code"),)


class ErpStockBalance(Base):
    """库存余额"""
    __tablename__ = "erp_stock_balance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    warehouse_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    product_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    available_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    last_movement_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    warehouse = relationship("ErpWarehouse")

    __table_args__ = (
        UniqueConstraint("warehouse_id", "product_id", name="uq_erp_stock_balance_wh_product"),
        {"comment": "库存余额"},
    )


class ErpStockMovement(Base):
    """出入库流水"""
    __tablename__ = "erp_stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    warehouse_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    product_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    movement_type: Mapped[str] = mapped_column(String(16), nullable=False)  # in / out / adjust
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    ref_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # purchase_receipt / shipment
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    receipt_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_purchase_receipts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operator_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    receipt = relationship("ErpPurchaseReceipt", back_populates="items")

    __table_args__ = ({"comment": "出入库流水"},)