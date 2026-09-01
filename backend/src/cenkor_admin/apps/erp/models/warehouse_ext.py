"""ERP 仓储深度模型：库位 / 物品批次 / 序列号 / 盘点单 / 安全库存"""
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


class ErpStockLocation(Base):
    """库位"""
    __tablename__ = "erp_stock_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    warehouse_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    area: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("warehouse_id", "code", name="uq_erp_stock_locations_wh_code"),
        {"comment": "库位"},
    )


class ErpBatch(Base):
    """物品批次"""
    __tablename__ = "erp_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_no: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    product_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    production_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")  # active/expired/frozen/used
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("batch_no", name="uq_erp_batches_batch_no"),
        {"comment": "物品批次"},
    )


class ErpSerial(Base):
    """序列号"""
    __tablename__ = "erp_serials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    serial_no: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    product_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warehouse_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_warehouses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    location_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="in_stock")  # in_stock/out_stock/scrapped
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("serial_no", name="uq_erp_serials_serial_no"),
        {"comment": "序列号"},
    )


class ErpStocktake(Base):
    """盘点单"""
    __tablename__ = "erp_stocktakes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    warehouse_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_warehouses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    location_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="draft")  # draft/processing/done
    take_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items = relationship(
        "ErpStocktakeItem", back_populates="stocktake", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("code", name="uq_erp_stocktakes_code"), {"comment": "盘点单"})


class ErpStocktakeItem(Base):
    """盘点明细"""
    __tablename__ = "erp_stocktake_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stocktake_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_stocktakes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_products.id", ondelete="SET NULL"), nullable=True
    )
    product_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    book_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    actual_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    diff_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default="0")
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)

    stocktake = relationship("ErpStocktake", back_populates="items")

    __table_args__ = ({"comment": "盘点明细"},)