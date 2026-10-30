"""知识库数据模型。

与 `cms_embeddings` 的分工：
    条目向量（cms_embeddings）：一条内容一个向量，服务于「找相似文章」。
    知识分片（cms_kb_chunks）：一篇文档多个向量，服务于「按章节召回给模型」。

两者都进 RAG，但检索时是两套逻辑 —— 条目向量召回整篇，
知识分片召回段落。混在一张表里会让「我要整篇上下文」和
「我只要这一段依据」变成同一个查询，哪种都做不好。
"""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from cenkor_admin.core.db import Base


class KbDoc(Base):
    """知识库文档（一份手册 / 一个 FAQ 集合 / 一份历史方案）。"""

    __tablename__ = "cms_kb_docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)

    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="upload")
    file_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    mime: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    category: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # pending → indexing → ready / failed
    # pending 是可以被调度器捞回来重跑的状态：服务重启导致后台任务丢失时，
    # 文档不会永久停在「排队中」—— 这是最常见的「功能好像坏了」。
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")

    content_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    indexed_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    embed_model: Mapped[str] = mapped_column(String(80), nullable=False, default="")

    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_cms_kb_docs_site_live", "site_id", "created_at"),)


class KbChunk(Base):
    """知识分片。检索的最小单位，也是引用出处的单位。"""

    __tablename__ = "cms_kb_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cms_kb_docs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    heading: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    heading_path: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 维度与 cms_embeddings 一致（1024）：HNSW / IVFFlat 索引上限 2000 维，
    # 豆包默认 2048 必须靠 dimensions 参数降下来才能建索引。
    vector: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    dim: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(80), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
