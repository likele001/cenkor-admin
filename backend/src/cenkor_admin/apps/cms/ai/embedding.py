"""条目向量化（增量）。

核心思想：**只给真正变了的条目付 embedding 的钱。**
每条向量旁存一份源文本指纹 content_hash，内容没变就直接跳过。

流程：
    entry  → 抽取可检索文本 → 规范化 → sha256
                                    ↓
                      与 cms_embeddings.content_hash 比对
                                    ↓
                         不同 → 调 embedding 接口 → upsert
                         相同 → 跳过（零 API 成本）
"""

from __future__ import annotations

import hashlib
import html
import re
from typing import Any

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.ai.models import CmsEmbedding
from cenkor_admin.apps.cms.models import Entry, EntryTranslation
from cenkor_admin.core.config import get_settings
from cenkor_admin.core.llm import LLMNotConfiguredError, get_llm_for

# 向量化时参与的字段
FIELD_COMBINED = "combined"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# 向量化输入上限：超长文本对检索召回增益很小，却成倍烧 token
_MAX_CHARS = 6000


def _clean_text(raw: str) -> str:
    """去 HTML 标签、反转义实体、压缩空白。"""
    text = _TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def _collect_strings(obj: Any, out: list[str], depth: int = 0) -> None:
    """递归收集 JSON 里的字符串值（跳过纯 URL / 颜色这类无检索价值的短串）。"""
    if depth > 6 or len(out) > 400:
        return
    if isinstance(obj, str):
        s = obj.strip()
        if len(s) >= 2 and not s.startswith(("http://", "https://", "#")):
            out.append(s)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_strings(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            _collect_strings(v, out, depth + 1)


def entry_to_text(entry: Entry, translation: EntryTranslation | None = None) -> str:
    """把条目压成一段可向量化的文本。

    顺序即重要性：标题 → 正文 → 自定义字段 → SEO 描述。
    translation 非空时优先用 field_values 里的译文（缺字段则回退原文）。

    注意：cms_entry_translations 把所有翻译字段塞在 field_values 一个 JSON 里，
    没有独立的 title/content 列，所以这里必须从 dict 里取。
    """
    fv: dict[str, Any] = (translation.field_values if translation else None) or {}

    parts: list[str] = []

    title = fv.get("title") or entry.title or ""
    parts.append(_clean_text(str(title)))

    content = fv.get("content")
    if not isinstance(content, dict) or not content:
        content = entry.content or {}

    body_bits: list[str] = []
    _collect_strings(content, body_bits)
    parts.extend(_clean_text(b) for b in body_bits)

    custom = fv.get("custom_fields")
    if not isinstance(custom, dict) or not custom:
        custom = entry.custom_fields or {}
    custom_bits: list[str] = []
    _collect_strings(custom, custom_bits)
    parts.extend(_clean_text(b) for b in custom_bits)

    seo = fv.get("seo")
    if not isinstance(seo, dict) or not seo:
        seo = entry.seo or {}
    if isinstance(seo, dict):
        for key in ("title", "description", "keywords"):
            v = seo.get(key)
            if isinstance(v, str) and v.strip():
                parts.append(_clean_text(v))

    text = "\n".join(p for p in parts if p)
    return text[:_MAX_CHARS]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


async def vectorize_entry(
    session: AsyncSession,
    entry: Entry,
    *,
    langs: list[str] | None = None,
    force: bool = False,
) -> int:
    """为单个条目生成/更新向量，返回实际调用 API 的次数。

    langs=None  → 只处理原文（base）
    langs=[...] → 额外处理指定语言的译文（需 cms_entry_translations 有对应记录）
    force=True  → 忽略 content_hash，强制重算（换 embedding 模型后必须用它）
    """
    settings = get_settings()
    llm = get_llm_for("embedding")

    # 目标：(lang, text)
    targets: list[tuple[str, str]] = [("base", entry_to_text(entry))]

    if langs:
        rows = (
            (
                await session.execute(
                    select(EntryTranslation).where(
                        EntryTranslation.entry_id == entry.id,
                        EntryTranslation.lang.in_(langs),
                    )
                )
            )
            .scalars()
            .all()
        )
        for tr in rows:
            targets.append((tr.lang, entry_to_text(entry, tr)))

    # 已存在的向量记录
    existing = {
        (e.lang, e.field): e
        for e in (
            await session.execute(
                select(CmsEmbedding).where(
                    CmsEmbedding.entry_id == entry.id,
                    CmsEmbedding.field == FIELD_COMBINED,
                )
            )
        )
        .scalars()
        .all()
    }

    api_calls = 0
    for lang, text in targets:
        if not text.strip():
            continue

        h = content_hash(text)
        row = existing.get((lang, FIELD_COMBINED))
        if row and not force and row.content_hash == h and row.vector:
            continue  # 内容未变，不花钱

        try:
            vector = await llm.embed_one(text)
        except LLMNotConfiguredError:
            raise
        except Exception as exc:
            logger.warning("cms.embedding_failed", entry_id=entry.id, lang=lang, error=str(exc))
            continue

        api_calls += 1
        if row is None:
            session.add(
                CmsEmbedding(
                    entry_id=entry.id,
                    field=FIELD_COMBINED,
                    lang=lang,
                    vector=vector,
                    dim=len(vector),
                    content_hash=h,
                    model=llm.embed_model,
                )
            )
        else:
            row.vector = vector
            row.dim = len(vector)
            row.content_hash = h
            row.model = llm.embed_model

    if api_calls:
        logger.info("cms.vectorized", entry_id=entry.id, langs=len(targets), api_calls=api_calls)
    _ = settings
    return api_calls


async def vectorize_pending(session: AsyncSession, *, limit: int = 50) -> dict[str, int]:
    """扫描并补齐缺失/过期的向量（定时任务或手动触发）。"""
    rows = (
        (
            await session.execute(
                select(Entry)
                .where(Entry.deleted_at.is_(None))
                .order_by(Entry.updated_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    done = 0
    calls = 0
    for entry in rows:
        try:
            n = await vectorize_entry(session, entry)
            calls += n
            done += 1
        except LLMNotConfiguredError:
            raise
        except Exception as exc:
            logger.warning("cms.vectorize_skip", entry_id=entry.id, error=str(exc))

    await session.commit()
    return {"scanned": len(rows), "processed": done, "api_calls": calls}


async def drop_entry_vectors(session: AsyncSession, entry_id: int) -> None:
    """条目删除时清理向量（FK 级联之外的双保险）。"""
    await session.execute(delete(CmsEmbedding).where(CmsEmbedding.entry_id == entry_id))
