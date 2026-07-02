from datetime import datetime
from cenkor_admin.core.db import Base
from sqlalchemy import String, Integer, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column


class CloudStorageConfig(Base):
    """云存储全局配置：当前激活的 provider + 凭据密文"""
    __tablename__ = "cloud_storage_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    active_provider: Mapped[str] = mapped_column(String(20), default="tencent")
    # 凭据按 provider 分开存，值为 AES 加密后的密文 (Base64)
    # 各字段：access_key / secret_key / bucket / region / endpoint / cdn_domain / prefix / extra
    creds_tencent: Mapped[str | None] = mapped_column(Text, nullable=True)
    creds_aliyun:  Mapped[str | None] = mapped_column(Text, nullable=True)
    creds_qiniu:   Mapped[str | None] = mapped_column(Text, nullable=True)
    creds_upyun:   Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CloudStorageMigrationJob(Base):
    """迁移任务状态：把现有 MinIO 上的对象复制到新 provider"""
    __tablename__ = "cloud_storage_migration_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(20), default="minio")
    target: Mapped[str] = mapped_column(String(20), nullable=False)
    total: Mapped[int] = mapped_column(Integer, default=0)
    done: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/running/done/failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
