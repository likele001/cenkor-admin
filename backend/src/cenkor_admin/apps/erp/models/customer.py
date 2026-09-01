"""ERP - 客户模块 ORM 模型"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cenkor_admin.core.db import Base


class ErpCustomer(Base):
    """客户主数据"""
    __tablename__ = "erp_customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    customer_type: Mapped[str] = mapped_column(String(16), nullable=False, server_default="company")
    tax_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, server_default="CNY")
    payment_terms: Mapped[str | None] = mapped_column(String(32), nullable=True)
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    industry: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scale: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    owner_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    contacts = relationship(
        "ErpCustomerContact",
        back_populates="customer",
        cascade="all, delete-orphan",
    )
    addresses = relationship(
        "ErpCustomerAddress",
        back_populates="customer",
        cascade="all, delete-orphan",
    )
    follow_ups = relationship(
        "ErpFollowUp",
        back_populates="customer",
        cascade="all, delete-orphan",
    )


class ErpCustomerContact(Base):
    """客户联系人"""
    __tablename__ = "erp_customer_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    position: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    wechat: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    birthday: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    customer = relationship("ErpCustomer", back_populates="contacts")
    follow_ups = relationship(
        "ErpFollowUp",
        back_populates="contact",
        cascade="all, delete-orphan",
    )


class ErpCustomerAddress(Base):
    """客户地址（收货/开票多地址）"""
    __tablename__ = "erp_customer_addresses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    address_type: Mapped[str] = mapped_column(String(16), server_default="shipping")
    recipient: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    province: Mapped[str | None] = mapped_column(String(32), nullable=True)
    city: Mapped[str | None] = mapped_column(String(32), nullable=True)
    district: Mapped[str | None] = mapped_column(String(32), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    customer = relationship("ErpCustomer", back_populates="addresses")


class ErpFollowUp(Base):
    """客户跟进记录"""
    __tablename__ = "erp_follow_ups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_customer_contacts.id", ondelete="SET NULL"), nullable=True
    )
    follow_type: Mapped[str] = mapped_column(String(16), nullable=False)
    follow_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_action: Mapped[str | None] = mapped_column(String(255), nullable=True)
    next_follow_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    customer = relationship("ErpCustomer", back_populates="follow_ups")
    contact = relationship("ErpCustomerContact", back_populates="follow_ups")