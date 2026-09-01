"""ERP 总账（GL）模型：会计科目 / 记账凭证 / 分录 / 会计期间 / 期末结转"""
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


class ErpAccount(Base):
    """会计科目"""
    __tablename__ = "erp_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. 1001 库存现金
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)  # asset/liability/equity/revenue/expense
    direction: Mapped[str] = mapped_column(String(8), nullable=False, server_default="debit")  # debit/credit
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_leaf: Mapped[bool] = mapped_column(Integer, nullable=False, server_default="1")  # 1=明细 0=汇总
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    initial_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    seq: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("code", name="uq_erp_accounts_code"),
        {"comment": "会计科目"},
    )


class ErpAccountingPeriod(Base):
    """会计期间（月度，用于结账/报表）"""
    __tablename__ = "erp_accounting_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="open")  # open/closed
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("period", name="uq_erp_accounting_periods_period"),
        {"comment": "会计期间"},
    )


class ErpVoucher(Base):
    """记账凭证"""
    __tablename__ = "erp_vouchers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    voucher_date: Mapped[date] = mapped_column(Date, nullable=False)
    word: Mapped[str | None] = mapped_column(String(16), nullable=True)  # 记/收/付/转
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # manual/sales_invoice/payment/...
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="draft")  # draft/posted
    total_debit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    total_credit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    entries = relationship(
        "ErpVoucherEntry", back_populates="voucher", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("code", name="uq_erp_vouchers_code"), {"comment": "记账凭证"})


class ErpVoucherEntry(Base):
    """凭证分录"""
    __tablename__ = "erp_voucher_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    voucher_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_vouchers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("erp_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    account_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    account_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    debit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    credit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")

    voucher = relationship("ErpVoucher", back_populates="entries")

    __table_args__ = ({"comment": "凭证分录"},)