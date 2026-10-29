"""RAG retrieval API —— 对外标准 chunk 检索。

## 定位

外部 AI 应用（客服机器人、企业知识库、外部 Agent）要接我们的内容，
需要的是**带出处的片段**，而不是整篇文章，更不是一堆 JSON。
本模块对外提供：给一个 query，返回最相关的若干 chunk，每个 chunk 带
标题 / 出处 URL / 锚点 / 得分，可以直接拼进 RAG 的 prompt。

## 两段式检索（为什么不直接对 chunk 建向量）

| 层 | 做什么 | 怎么做的 |
|---|---|---|
| 召回（粗排） | 从全库找出 top-N 篇可能相关的**条目** | 复用现成的 `semantic_search`（条目级向量 + 关键词混合） |
| 精排 | 在候选条目内部找最贴题的**片段** | chunk 切分 + 关键词/短语命中打分 |

为什么不建 chunk 向量表：
- 每条内容多一个向量，embedding 成本与存储翻倍，还要重建全部历史向量
- chunk 切分随正文改动而漂移，向量指纹失效后要全量重算
- 条目级召回已经足够准，精排靠词面命中更稳（用户 query 往往含专有名词）

代价：召回层限制了天花板（query 与条目整体语义不近时召不回）。
这在企业内容库场景可接受 —— 库里内容本身品类集中。

## chunk 切分

按 markdown/HTML 标题切，保留标题作为 chunk 的「上下文标题」，
这样 RAG 引用时能同时给出「这段话出自哪篇文章的哪一节」。
单段过长时按句子边界二次切分。
"""

from __future__ import annotations

import re
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.ai.search import semantic_search
from cenkor_admin.core.llm import LLMNotConfiguredError

# chunk 目标长度（字符）：太小丢上下文，太大稀释语义
_CHUNK_MAX = 1200
# 低于此长度的片段单独作为 chunk 没有引用价值（会并进相邻块或整篇保留）
_CHUNK_MIN = 80

_TAG_RE = re.compile(r"<[^>]+>")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*(.+?)\s*#*\s*$", re.MULTILINE)
_HTML_HEADING_RE = re.compile(
    r"<h([1-6])[^>]*>(.*?)</h\1>", re.IGNORECASE | re.DOTALL
)
_SENT_SPLIT_RE = re.compile(r"(?<=[。！？!?；;\n])")


def _strip_html(raw: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", raw or "")).strip()


def _extract_body(content: dict[str, Any] | None) -> str:
    """从条目 content 里取正文（markdown 或富文本）。"""
    content = content or {}
    for k in ("body", "markdown", "md", "text"):
        v = content.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _split_sections(body: str) -> list[tuple[str, str]]:
    """按标题切分成 [(小节标题, 小节正文)]。无标题时整篇作为一节。"""
    if not body:
        return []

    # HTML 富文本：按 h1~h6 切
    heads = list(_HTML_HEADING_RE.finditer(body))
    if heads:
        sections: list[tuple[str, str]] = []
        prelude = body[: heads[0].start()].strip()
        if prelude:
            sections.append(("", _strip_html(prelude)))
        for i, m in enumerate(heads):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
            title = _strip_html(m.group(2))
            text = _strip_html(body[m.end() : end])
            if text:
                sections.append((title, text))
        return sections

    # Markdown：按 # 标题切
    heads = list(_HEADING_RE.finditer(body))
    if heads:
        sections = []
        prelude = body[: heads[0].start()].strip()
        if prelude:
            sections.append(("", prelude))
        for i, m in enumerate(heads):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
            title = m.group(1).strip()
            text = body[m.end() : end].strip()
            if text:
                sections.append((title, text))
        return sections

    return [("", body.strip())]


def _split_long(text: str, limit: int = _CHUNK_MAX) -> list[str]:
    """长段落按句子边界二次切分，尽量不超 limit。"""
    if len(text) <= limit:
        return [text]
    out: list[str] = []
    buf = ""
    for part in _SENT_SPLIT_RE.split(text):
        if not part:
            continue
        if len(buf) + len(part) > limit and buf:
            out.append(buf.strip())
            buf = part
        else:
            buf += part
    if buf.strip():
        out.append(buf.strip())
    return out


def chunk_entry(
    entry_title: str,
    content: dict[str, Any] | None,
    *,
    max_chunks: int = 12,
) -> list[dict[str, Any]]:
    """把一条内容切成带上下文的 chunk 列表。

    每个 chunk：{index, text, heading, heading_path, chars}
    heading_path = 「文章标题 > 小节标题」，RAG 引用时直接用。

    太短的碎片会并进相邻块 —— 18 个字的片段对 RAG 引用没有价值，
    拼进上下文里反而让模型抓到半句话就作答。
    """
    body = _extract_body(content)
    if not body:
        return []

    # 整篇太短：不做切分，整篇作为唯一 chunk（配上标题上下文才有引用价值）
    if len(body.strip()) < _CHUNK_MIN:
        return [
            {
                "index": 0,
                "text": body.strip(),
                "heading": "",
                "heading_path": entry_title,
                "chars": len(body.strip()),
            }
        ]

    chunks: list[dict[str, Any]] = []
    for sec_title, sec_text in _split_sections(body):
        for piece in _split_long(sec_text):
            piece = piece.strip()
            if not piece:
                continue
            if len(piece) < _CHUNK_MIN and chunks:
                # 太短的碎片并进上一块（同小节优先）
                prev = chunks[-1]
                if prev["heading"] == sec_title and len(prev["text"]) + len(piece) <= _CHUNK_MAX:
                    prev["text"] = f"{prev['text']} {piece}".strip()
                    prev["chars"] = len(prev["text"])
                    continue
            path = entry_title if not sec_title else f"{entry_title} > {sec_title}"
            chunks.append(
                {
                    "index": len(chunks),
                    "text": piece,
                    "heading": sec_title,
                    "heading_path": path,
                    "chars": len(piece),
                }
            )
            if len(chunks) >= max_chunks:
                return chunks
    return chunks


def _score_chunk(query: str, chunk_text: str, entry_score: float) -> float:
    """chunk 级精排得分。

    向量分（条目级，按比例继承）+ 关键词命中加成。
    关键词命中权重更高：RAG query 通常带专有名词，词面命中是强信号。
    """
    q = (query or "").strip().lower()
    if not q:
        return entry_score

    t = chunk_text.lower()
    terms = [w for w in re.split(r"[\s,，。；;、/|]+", q) if len(w) >= 2]
    hits = sum(1 for w in terms if w in t)
    kw = min(hits / max(len(terms), 1), 1.0)

    # 整串命中：query 完整出现在 chunk 里是最强信号
    exact = 1.0 if q and q in t else 0.0
    bonus = 0.45 * kw + 0.25 * exact

    return min(entry_score * 0.7 + bonus, 1.0)


async def retrieve(
    session: AsyncSession,
    query: str,
    *,
    content_type_id: int | None = None,
    content_type_key: str | None = None,
    top_k: int = 5,
    candidates: int = 12,
    include_drafts: bool = False,
    lang: str = "base",
) -> dict[str, Any]:
    """RAG 检索：返回带出处的 chunk 列表。

    返回：{query, hits: [{text, heading, heading_path, score, source_url, title, entry_id, slug, content_type_id}], count}
    """
    q = (query or "").strip()
    if not q:
        return {"query": "", "hits": [], "count": 0}

    try:
        entry_hits = await semantic_search(
            session,
            q,
            content_type_id=content_type_id,
            content_type_key=content_type_key,
            include_drafts=include_drafts,
            limit=candidates,
            lang=lang,
        )
    except LLMNotConfiguredError:
        logger.warning("cms.rag.embed_not_configured")
        return {"query": q, "hits": [], "count": 0, "warning": "embedding 模型未配置"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("cms.rag.search_failed err={}", str(exc))
        return {"query": q, "hits": [], "count": 0, "warning": f"检索失败：{exc}"}

    if not entry_hits:
        return {"query": q, "hits": [], "count": 0}

    # 取候选条目正文，切 chunk 精排
    from sqlalchemy import select

    from cenkor_admin.apps.cms.models import ContentType, Entry

    ids = [h.entry_id for h in entry_hits]
    entries = (
        (
            await session.execute(
                select(Entry).where(Entry.id.in_(ids), Entry.deleted_at.is_(None))
            )
        )
        .scalars()
        .all()
    )
    by_id = {e.id: e for e in entries}
    base_score = {h.entry_id: h.score for h in entry_hits}

    # 出处 URL 用内容类型 key（公开详情路由是 /site/{content_type_key}/{slug}）
    ct_ids = {e.content_type_id for e in entries}
    ct_key_map: dict[int, str] = {}
    if ct_ids:
        ct_rows = (
            await session.execute(
                select(ContentType.id, ContentType.key).where(ContentType.id.in_(ct_ids))
            )
        ).all()
        ct_key_map = {r[0]: r[1] for r in ct_rows}

    scored: list[dict[str, Any]] = []
    for h in entry_hits:
        e = by_id.get(h.entry_id)
        if e is None:
            continue
        chunks = chunk_entry(e.title or "", e.content or {})
        for c in chunks:
            sc = _score_chunk(q, c["text"], base_score.get(h.entry_id, 0.0))
            if sc <= 0.05:
                continue
            scored.append(
                {
                    "text": c["text"],
                    "heading": c["heading"],
                    "heading_path": c["heading_path"],
                    "score": round(sc, 4),
                    "entry_id": e.id,
                    "title": e.title,
                    "slug": e.slug,
                    "content_type_id": e.content_type_id,
                    "content_type_key": ct_key_map.get(e.content_type_id, ""),
                    "status": e.status,
                    "published_at": e.published_at.isoformat() if e.published_at else None,
                }
            )

    scored.sort(key=lambda x: x["score"], reverse=True)
    hits = scored[:top_k]
    for h in hits:
        h["source_url"] = _source_url(h)

    logger.info(
        "cms.rag query={} candidates={} chunks={} hits={}",
        q[:40], len(entry_hits), len(scored), len(hits),
    )
    return {"query": q, "hits": hits, "count": len(hits)}


def _source_url(hit: dict[str, Any]) -> str:
    """出处 URL：必须是**公开可访问**的完整路径。

    公开详情只有一种形态：`/api/v1/public/site/{content_type_key}/{id_or_slug}`。
    slug 可能为 NULL（草稿/测试数据常见），这时用 id 兜底 ——
    出处链接点不开的话，RAG 引用就是废的。
    """
    ct_key = hit.get("content_type_key")
    ident = hit.get("slug") or hit.get("entry_id")
    if ct_key and ident:
        return f"/api/v1/public/site/{ct_key}/{ident}"
    if ident:
        return f"/api/v1/public/site/entry/{ident}"
    return ""


__all__ = ["retrieve", "chunk_entry"]
