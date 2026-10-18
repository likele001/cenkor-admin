"""库存管理 — ORM 模型（由 scripts/gen-app.py 生成，可按需手改）"""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from cenkor_admin.core.db import Base


class Warehouse(Base):
    __tablename__ = "inventory_warehouse"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    enable: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    creator_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Location(Base):
    __tablename__ = "inventory_location"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    warehouse_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    capacity: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    creator_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
