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
    total_tokens = 0
    total_latency = 0
    for lang, text in targets:
        if not text.strip():
            continue

        h = content_hash(text)
        row = existing.get((lang, FIELD_COMBINED))
        if row and not force and row.content_hash == h and row.vector:
            continue  # 内容未变，不花钱

        try:
            # 用 embed_one_meta 一次拿到向量与计量：token 和耗时随返回值回来，
            # 不读实例属性 last_embed_usage（并发下会被别的请求覆盖）
            vector, _meta = await llm.embed_one_meta(text)
        except LLMNotConfiguredError:
            raise
        except Exception as exc:
            logger.warning("cms.embedding_failed", entry_id=entry.id, lang=lang, error=str(exc))
            continue

        api_calls += 1
        total_tokens += int(_meta.get("prompt_tokens") or 0)
        total_latency += int(_meta.get("latency_ms") or 0)
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
        # 向量化同样按 token 计费。不记账的话「AI 用量」页会漏掉这块成本 ——
        # 批量补建 50 条时页面看着一次没调，实际账单已经在涨。
        try:
            from cenkor_admin.apps.cms.ai.models import CmsAiGeneration
            from cenkor_admin.core.site_scope import current_site_id

            session.add(
                CmsAiGeneration(
                    site_id=(current_site_id() or 1),
                    kind="embedding",
                    target=f"entry:{entry.id}",
                    provider=(llm.provider or ""),
                    model=(llm.embed_model or ""),
                    prompt_digest="",
                    params={"api_calls": api_calls, "force": bool(force)},
                    tokens_in=total_tokens,
                    tokens_out=0,
                    latency_ms=(total_latency // api_calls) if api_calls else 0,
                    status="ok",
                    error=None,
                    created_by=None,
                )
            )
        except Exception as exc:  # noqa: BLE001
            # 记账失败不能影响向量本身落库
            logger.warning("cms.embedding_record_failed", error=str(exc))
    return api_calls


async def vectorize_pending(session: AsyncSession, *, limit: int = 50) -> dict[str, int]:
    """扫描并补齐缺失/过期的向量（定时任务或手动触发）。

    必须先扫「完全没有向量」的条目，再补可能过期的。
    只按 updated_at desc 取前 limit 条会永远只扫同一批最新的条目：
    站点条目数一旦超过 limit，旧条目永远轮不到，覆盖率会卡死在中间再也上不去。
    """
    # 已有向量的条目：任一 field/lang 存在即算「有」
    has_vec = select(CmsEmbedding.entry_id)

    missing = (
        (
            await session.execute(
                select(Entry)
                .where(Entry.deleted_at.is_(None), Entry.id.not_in(has_vec))
                .order_by(Entry.updated_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    rows = list(missing)
    if len(rows) < limit:
        # 名额还有剩：按最近更新补齐。这些「有向量但内容可能改过」的条目，
        # 要不要真调 API 由 vectorize_entry 内部 content_hash 比对决定（没变就零成本跳过）。
        seen = {e.id for e in rows}
        rest = (
            (
                await session.execute(
                    select(Entry)
                    .where(Entry.deleted_at.is_(None))
                    .order_by(Entry.updated_at.desc())
                    .limit(limit + len(seen))
                )
            )
            .scalars()
            .all()
        )
        for e in rest:
            if e.id in seen:
                continue
            rows.append(e)
            if len(rows) >= limit:
                break

    done = 0
    calls = 0
    created = 0
    for entry in rows:
        try:
            had = await session.scalar(
                select(CmsEmbedding.id).where(CmsEmbedding.entry_id == entry.id).limit(1)
            )
            n = await vectorize_entry(session, entry)
            calls += n
            done += 1
            if had is None and n > 0:
                created += 1
        except LLMNotConfiguredError:
            raise
        except Exception as exc:
            logger.warning("cms.vectorize_skip", entry_id=entry.id, error=str(exc))

    await session.commit()
    # created = 真正补出来的条数（此前完全没有向量）。前端据此说人话，
    # 不能把「扫了 N 条」说成「补了 N 条」，otherwise 用户会以为白花 N 次钱。
    return {"scanned": len(rows), "processed": done, "created": created, "api_calls": calls}


async def drop_entry_vectors(session: AsyncSession, entry_id: int) -> None:
    """条目删除时清理向量（FK 级联之外的双保险）。"""
    await session.execute(delete(CmsEmbedding).where(CmsEmbedding.entry_id == entry_id))
