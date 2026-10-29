"""CMS AI 层 · 数据模型

五张表：
- cms_embeddings     条目向量（增量维护，content_hash 判断是否需要重算）
- cms_ai_generations AI 生成溯源（谁在什么时候用什么模型生成了什么，成本多少）
- cms_ai_providers    服务商通道（base_url + 加密密钥 + 连接参数），后台可视化维护
- cms_ai_capabilities 能力绑定（chat / embedding / vision / image ... 各用哪个服务商哪个模型）
- cms_ai_prompts      提示词版本（运营可改、可对比、可回滚，代码常量为出厂默认）

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

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
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

    # 向量本体。pgvector 原生类型：距离在库内算，并走 HNSW 索引。
    # 1024 维不是随手定的：HNSW / IVFFlat 索引上限 2000 维，
    # 豆包默认 2048 维刚好超线，得靠 dimensions=1024 降下来才能建索引。
    vector: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
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
    # 站点归属：驾驶舱按站点看账单。脚本/CLI 取不到上下文时落默认站 1，
    # 不留 NULL —— 否则统计里会多出一个「不归属任何站点」的黑洞分类。
    site_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cms_sites.id", ondelete="RESTRICT"),
        nullable=False, default=1, index=True,
    )
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


class CmsAiPrompt(Base):
    """AI 提示词版本。

    为什么落库而不是留在代码里：改一句措辞要发版、重启、回归测试，
    客户说「语气太官方」就得排一次发布窗口。落库后运营自己就能调，
    改坏了回滚上一版即可。

    三条约束保证可治理：
    - `(prompt_key, version)` 唯一 —— 版本号单调递增，不覆盖历史
    - `is_active` 部分唯一索引（见迁移 006）—— 每个 key 同时只有一个生效版本
    - `content` 不允许为空 —— 空提示词会让模型行为完全失控，挡在入口
    """

    __tablename__ = "cms_ai_prompts"
    __table_args__ = (
        UniqueConstraint("prompt_key", "version", name="uq_ai_prompt_key_ver"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prompt_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------------------
# 批量生产队列
# ---------------------------------------------------------------------------
class CmsAiBatchJob(Base):
    """一批选题的批量起草任务。

    为什么是 DB 队列而不是 Celery：本机跑着的 worker 属于其它项目，为本项目
    单开一个 worker + supervisord 配置的成本高于收益。批量任务「长但不密集」
    （每篇 10-30s 纯等 LLM），进程内 asyncio 足够；状态全落 DB，进程重启后
    pending 项可续跑，不会像纯内存队列那样一重启全丢。

    每个站点同时只允许一个 running 批次（部分唯一索引保障）：两批同时跑会抢
    LLM 配额，前端进度也互相干扰，出问题极难定位。
    """

    __tablename__ = "cms_ai_batch_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cms_sites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    content_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cms_content_types.id", ondelete="RESTRICT"), nullable=False
    )
    # 冗余 key：列表页免 join，内容类型改名也不影响历史批次的可读性
    content_type_key: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    lang: Mapped[str] = mapped_column(String(20), nullable=False, default="zh-CN")
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CmsAiBatchItem(Base):
    """批次里的一个选题。

    `brief` 是喂给 draft_entry 的素材/大纲原文；成功后 `entry_id` 指向落库的
    草稿条目。失败只记 `error` 不删行，便于「只重试失败的」。
    """

    __tablename__ = "cms_ai_batch_items"
    __table_args__ = (
        UniqueConstraint("job_id", "seq", name="uq_batch_item_seq"),
        Index("ix_batch_items_job_status", "job_id", "status", "seq"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cms_ai_batch_jobs.id", ondelete="CASCADE"), nullable=False
    )
    site_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    brief: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    entry_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cms_entries.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CmsAiReview(Base):
    """一条 AI 产出的质检打分（人评）。

    为什么必须存**模型快照**（`provider` / `model`）而不是每次 join
    `cms_ai_generations`：条目可能被删、记账可能被清理，而质量曲线要能回溯
    「三个月前那个模型到底行不行」。快照两列成本极低，丢了的结论补不回来。

    `scores` 用 JSONB 而不是四个独立列：评分维度会随业务调整（今天看
    「准确性/可读性」，明天可能加「事实密度」），加维度不该改表。
    `overall` 单独冗余一份，是因为曲线和图表的查询只用到它，避免每行都去
    解析 JSON。
    """

    __tablename__ = "cms_ai_reviews"
    __table_args__ = (
        Index("ix_ai_reviews_entry", "entry_id", "created_at"),
        Index("ix_ai_reviews_model", "model", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)
    entry_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cms_entries.id", ondelete="SET NULL"), nullable=True
    )
    generation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # sample（随机抽样）/ ab（A/B 盲评）—— 两类打分的分布不可混在一起算均分
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="sample")
    ab_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, default="entry_draft")
    provider: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    overall: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    scores: Mapped[dict[str, Any] | None] = mapped_column(json_column(), nullable=True)
    verdict: Mapped[str] = mapped_column(String(20), nullable=False, default="pass")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reviewer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class CmsAiAbRun(Base):
    """一次模型 A/B：同一输入，两个模型各出一份，盲评后揭晓。

    盲评的关键在**左右位置随机**：人能看见「左边/右边」，看不见模型名。
    如果固定 A 在左，评分者会不知不觉形成位置偏好，对比结果就废了。
    `left_model` / `right_model` 是随机化之后的落位，不是参数顺序。
    """

    __tablename__ = "cms_ai_ab_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    left_model: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    right_model: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    left_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    right_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    left_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    right_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    left_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    right_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # left / right / tie；未评分为 NULL
    winner: Mapped[str | None] = mapped_column(String(10), nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CmsAiVideoJob(Base):
    """一次视频生成任务。

    ## 为什么要落库而不是留在内存

    视频生成是**分钟级**的：提交后要轮询 60~300 秒才有产物。这期间
    进程重启、请求断开、用户关页面都是常态。任务状态只存内存的话，
    一次发布就全丢，而服务商那边还在照常计费 —— 钱花了、视频找不到。

    所以状态全部落 DB，轮询由进程内后台协程推进，同时前端每次查询也
    会顺手推一次（`refresh`）。两条路互为兜底：后台协程丢了，前端一刷
    就能把状态追回来；没人看页面时后台协程自己也会跑完。

    ## 为什么存 cover_media_id

    视频不能当 og_image —— 社交平台抓分享卡片只认图片。所以落视频时
    同步用 ffmpeg 抽首帧存成一张图片媒体，分享卡片和列表缩略图都用它。
    抽帧失败不算任务失败（视频本身是好的），封面留空，前端显示占位。
    """

    __tablename__ = "cms_ai_video_jobs"
    __table_args__ = (
        Index("ix_cms_ai_video_entry", "entry_id", "id"),
        Index("ix_cms_ai_video_status", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)
    entry_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cms_entries.id", ondelete="SET NULL"), nullable=True
    )
    # t2v=文生视频 / i2v=图生视频（首帧取 source_media_id）
    mode: Mapped[str] = mapped_column(String(8), nullable=False, default="t2v")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="queued", index=True
    )
    # 服务商侧任务 id。空串表示还没提交成功
    provider_task_id: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # ratio / duration / resolution / watermark ...
    params: Mapped[dict[str, Any] | None] = mapped_column(json_column(), nullable=True)
    # 图生视频的首帧来源
    source_media_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cms_media.id", ondelete="SET NULL"), nullable=True
    )
    media_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cms_media.id", ondelete="SET NULL"), nullable=True
    )
    cover_media_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cms_media.id", ondelete="SET NULL"), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 服务商产物 URL，仅作排查线索：24 小时就失效，不能当引用用
    upstream_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CmsAiPrice(Base):
    """AI 调用单价，把 token 用量换算成金额。

    为什么是可配置表而不是写死价目表：embedding / chat / 图像三类单价差一个
    数量级，各家还会随时调价。写死在代码里迟早算错钱，而**算错钱比不算钱更糟**。
    所以默认空表，没配置就明确显示「未配置单价」，绝不猜。

    匹配规则：`provider` / `model` / `kind` 三个维度，空串表示「任意」。
    精确维度越多的规则优先级越高，同分时 id 小的先配先生效。
    """

    __tablename__ = "cms_ai_prices"
    __table_args__ = (
        UniqueConstraint("provider", "model", "kind", name="uq_cms_ai_prices"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    # chat / embedding / image，空串 = 任意
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    # token=按百万 token 计价；image=按张计价（生图没有 token，按 token 折算恒为 0）
    unit: Mapped[str] = mapped_column(String(8), nullable=False, default="token")
    # 每百万 token / 每张的单价
    input_per_m: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0)
    output_per_m: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="CNY")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    note: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
