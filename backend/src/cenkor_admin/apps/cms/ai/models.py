"""CMS AI 层 · 数据模型

两张新表：
- cms_embeddings     条目向量（增量维护，content_hash 判断是否需要重算）
- cms_ai_generations AI 生成溯源（谁在什么时候用什么模型生成了什么，成本多少）

设计取舍：
1. 向量不依赖 pgvector。线上 PG 未必装了该扩展，装扩展要停机重启，
   而「能不能用」不该被一个扩展卡住。所以默认用 PG 原生 `double precision[]`
   存向量，检索在应用侧算余弦；检测到 vector 扩展时 search.py 会自动切原生算子。
2. 一个条目可能有多个向量（title / body / 自定义字段），用 (entry_id, field, lang)
   做唯一键，各字段独立检索、独立失效。
3. 溯源表只存 prompt 摘要不存原文：既够审计，又不会把业务数据再复制一份。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from cenkor_admin.core.compat import json_column
from cenkor_admin.core.db import Base


class CmsEmbedding(Base):
    """条目向量。

    field: 该向量代表条目的哪个部分（title / body / custom:<key> / combined）
    lang:  语言（与 cms_entry_translations 对齐）；原文用 base
    """

    __tablename__ = "cms_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cms_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field: Mapped[str] = mapped_column(String(40), nullable=False, default="combined")
    lang: Mapped[str] = mapped_column(String(16), nullable=False, default="base")

    # 向量本体。PG 原生数组，检索时读到内存做余弦
    vector: Mapped[list[float] | None] = mapped_column(PG_ARRAY(Float), nullable=True)
    dim: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 生成该向量的源文本指纹：内容没变就不重算 embedding（省钱的关键）
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(80), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("entry_id", "field", "lang", name="uq_cms_embedding_target"),
        Index("ix_cms_embeddings_model", "model"),
    )


class CmsAiGeneration(Base):
    """AI 生成记录（溯源 + 成本核算 + 审核依据）。

    kind:    content_type_from_nl | entry_draft | translate | seo | embedding
    status:  ok | failed | skipped
    target:  形如 entry:123 / content_type:7，便于按对象聚合查询
    """

    __tablename__ = "cms_ai_generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    target: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(80), nullable=False, default="")

    # prompt 摘要（sha256 前 32 位）+ 入参快照，避免存全文
    prompt_digest: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    params: Mapped[dict[str, Any] | None] = mapped_column(json_column(), nullable=True)

    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 触发人（后台用户 id）；Agent 调用时可为空
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (Index("ix_cms_ai_gen_target", "kind", "target"),)
