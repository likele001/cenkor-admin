"""AI 提示词加载 · DB 为真相源，代码常量为出厂默认。

## 为什么不直接用代码里的字符串

改一句措辞要发版、重启、回归，客户说「语气太官方」就得排一次发布窗口。
落库后运营自己在后台就能调，改坏了回滚上一版。

## 回退规则

    DB 有激活版本  → 用 DB 的
    DB 无该 key    → 用代码常量（新加的 prompt 不用强制写迁移）
    查询异常       → 用代码常量 + warning，绝不让 AI 功能因提示词表挂掉

## 缓存

30 秒 TTL，与站点缓存同节奏。管理端写入后调 `invalidate(key)` 立即失效 ——
单进程部署下即时生效，多 worker 时最迟 30 秒收敛（TTL 是兜底）。
"""

from __future__ import annotations

import time
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# key → 展示名。管理端按这个顺序展示，未登记的 key 排最后。
PROMPT_LABELS: dict[str, str] = {
    "ct": "内容建模",
    "draft": "草稿起草",
    "draft_stream": "草稿起草（流式）",
    "draft_extra": "草稿补充元数据",
    "translate": "内容翻译",
    "auto_tag": "自动打标签",
    "internal_link": "内链建议",
    "redistribute": "多渠道再分发",
    "qa_ask": "问答式站内搜索",
    "topic_gap": "选题 Gap 分析",
    "ab_run": "模型 A/B 起草",
    "illustration": "AI 配图提示词",
    "seo": "SEO/GEO 元数据",
    "rewrite": "文本改写",
}

TTL = 30.0

# key -> (content, monotonic_ts)
_cache: dict[str, tuple[str, float]] = {}


def invalidate(key: str | None = None) -> None:
    """清缓存。不传 key 清全部。"""
    if key is None:
        _cache.clear()
    else:
        _cache.pop(key, None)


async def get(session: AsyncSession, key: str, default: str) -> str:
    """取生效中的提示词；DB 没配就用 default。"""
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None and now - hit[1] < TTL:
        return hit[0]

    from cenkor_admin.apps.cms.ai.models import CmsAiPrompt

    try:
        content = (
            await session.execute(
                select(CmsAiPrompt.content)
                .where(CmsAiPrompt.prompt_key == key, CmsAiPrompt.is_active.is_(True))
                .limit(1)
            )
        ).scalar()
    except Exception as exc:  # noqa: BLE001
        # 表不存在 / 连接抖动都不该让 AI 功能整个不可用
        logger.warning("cms.ai.prompt_load_failed", key=key, error=str(exc))
        return default

    resolved = (content or "").strip() or default
    _cache[key] = (resolved, now)
    return resolved


async def active_versions(session: AsyncSession) -> dict[str, dict[str, Any]]:
    """管理端用：各 key 当前生效版本信息（不含正文，避免响应过大）。"""
    from cenkor_admin.apps.cms.ai.models import CmsAiPrompt

    rows = (
        await session.execute(
            select(
                CmsAiPrompt.prompt_key,
                CmsAiPrompt.version,
                CmsAiPrompt.note,
                CmsAiPrompt.created_at,
                CmsAiPrompt.created_by,
            ).where(CmsAiPrompt.is_active.is_(True))
        )
    ).all()
    return {
        r.prompt_key: {
            "version": r.version,
            "note": r.note,
            "created_at": r.created_at,
            "created_by": r.created_by,
        }
        for r in rows
    }
