"""CMS AI 能力层。

模块划分：
    models     两张新表（cms_embeddings / cms_ai_generations）
    embedding  增量向量化
    search     语义 + 关键词混合检索
    copilot    对话式建模、内容生成、翻译、SEO
    router     HTTP 接口

设计前提：AI 是**可选增强**，不是运行必需。
未配置 AI_API_KEY 时，本包所有 AI 调用抛 LLMNotConfiguredError，
路由层返回 503 并给出明确提示，CMS 的传统能力（建模 UI / REST / GraphQL）完全不受影响。
"""

from __future__ import annotations

from cenkor_admin.apps.cms.ai.models import CmsAiGeneration, CmsEmbedding

__all__ = ["CmsAiGeneration", "CmsEmbedding"]
