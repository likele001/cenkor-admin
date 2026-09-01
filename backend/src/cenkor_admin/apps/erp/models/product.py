"""ERP 商品模块 ORM 模型"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
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


class ErpProductCategory(Base):
    """商品分类"""
    __tablename__ = "erp_product_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_product_categories.id", ondelete="SET NULL"), nullable=True
    )
    sort: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    parent = relationship("ErpProductCategory", remote_side=[id], back_populates="children")
    children = relationship("ErpProductCategory", back_populates="parent", cascade="all, delete-orphan")

    __table_args__ = {"comment": "商品分类"}


class ErpProduct(Base):
    """商品主数据"""
    __tablename__ = "erp_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_product_categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    unit: Mapped[str] = mapped_column(String(16), nullable=False, server_default="件")
    barcode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sale_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    purchase_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    cost_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    min_stock: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    category = relationship("ErpProductCategory", backref="products")

    __table_args__ = (
        UniqueConstraint("code", name="uq_erp_products_code"),
        {"comment": "商品主数据"},
    )