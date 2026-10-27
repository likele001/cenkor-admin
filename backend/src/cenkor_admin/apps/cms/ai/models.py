"""CMS AI 层 · 数据模型

四张表：
- cms_embeddings     条目向量（增量维护，content_hash 判断是否需要重算）
- cms_ai_generations AI 生成溯源（谁在什么时候用什么模型生成了什么，成本多少）
- cms_ai_providers    服务商通道（base_url + 加密密钥 + 连接参数），后台可视化维护
- cms_ai_capabilities 能力绑定（chat / embedding / vision / image ... 各用哪个服务商哪个模型）

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
    Boolean,
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


class CmsAiProvider(Base):
    """AI 服务商通道。

    一家服务商 = 一个 base_url + 一把密钥 + 一套连接参数。
    密钥以 Fernet 密文存 ``api_key_enc``，明文只在内存里存在一次；
    列表页永远只读 ``api_key_hint``（``****a1b2``），不做解密。
    """

    __tablename__ = "cms_ai_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 唯一标识，形如 openai / deepseek / qwen-local，供接口与日志引用
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    # 协议族：openai（兼容 OpenAI 协议）/ azure / anthropic / gemini / ollama
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="openai")
    base_url: Mapped[str] = mapped_column(String(400), nullable=False)

    api_key_enc: Mapped[str] = mapped_column(Text, nullable=False, default="")
    api_key_hint: Mapped[str] = mapped_column(String(16), nullable=False, default="")

    # 自定义请求头（部分网关要求额外鉴权头，如 X-Api-Version）
    extra_headers: Mapped[dict[str, Any] | None] = mapped_column(json_column(), nullable=True)

    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # 连通性测试结果留痕：界面上直接显示「上次测试成功/失败」
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_test_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 由 .env 自动导入的初始配置标记，便于界面区分「环境变量带来的」与「手动加的」
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (Index("ix_cms_ai_providers_enabled", "enabled"),)


class CmsAiCapability(Base):
    """能力绑定：每类能力当前生效的服务商 + 模型 + 参数。

    以 ``capability`` 作主键（单例语义）——每类能力只有一套生效配置，
    结构简单、读取零歧义。将来要做多模型轮询或故障转移，
    另加一张 fallback 表即可，不必改这张。

    params 里按能力放不同键：
      chat      temperature / max_tokens / top_p
      embedding dim / batch
      vision    max_tokens / detail(low|high|auto)
      image     size / quality / n
    """

    __tablename__ = "cms_ai_capabilities"

    capability: Mapped[str] = mapped_column(String(32), primary_key=True)
    # 服务商被误删会静默让能力失效，用 RESTRICT 挡在删除那一步
    provider_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("cms_ai_providers.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    model: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    params: Mapped[dict[str, Any] | None] = mapped_column(json_column(), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
