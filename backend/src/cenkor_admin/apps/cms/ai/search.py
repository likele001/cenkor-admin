"""语义检索（混合排序）。

为什么不是「纯向量」：
纯向量检索在长尾短查询上容易召回语义相近但主题无关的内容（俗称向量幻觉）。
所以这里做混合：向量相似度为主，关键词命中做加成，任何一边有强信号都能被捞上来。

    最终分 = 0.7 × 向量余弦 + 0.3 × 关键词得分

两条执行路径（自动选择，对调用方透明）：
- 装了 pgvector  → 用 SQL `<=>` 在库内算，返回前 K
- 没装            → 全量拉候选向量到内存算（本项目默认路径，万级条目内足够快）
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.ai.embedding import entry_to_text
from cenkor_admin.apps.cms.ai.models import CmsEmbedding
from cenkor_admin.apps.cms.models import ContentType, Entry
from cenkor_admin.core.llm import LLMNotConfiguredError, get_llm_for

try:  # 可选加速：装了 numpy 就用矩阵运算，没装退化为纯 Python
    import numpy as _np
except ImportError:  # pragma: no cover - 环境相关
    _np = None

VECTOR_WEIGHT = 0.7
KEYWORD_WEIGHT = 0.3
# 未装 pgvector 时，内存计算允许的最大候选数（防止全表拉爆内存）
MAX_CANDIDATES = 20000

_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_ASCII_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(q: str) -> list[str]:
    """查询分词。

    坑：直接用 `\\w+` 会把整句中文匹配成一个 token（Python 的 \\w 是 Unicode 感知的），
    拿"节能案例"去匹配"某钢厂节能改造案例"必然 0 命中。
    所以中文必须切 bigram：节能案例 → 节能 / 能案 / 案例。
    """
    tokens: list[str] = [w.lower() for w in _ASCII_WORD_RE.findall(q)]
    for run in _CJK_RE.findall(q):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


def _keyword_score(query: str, title: str, body: str) -> float:
    """朴素关键词得分（0~1）。

    命中标题权重 1.0，命中正文 0.4。
    """
    q = (query or "").strip().lower()
    if not q:
        return 0.0

    title_l = (title or "").lower()
    body_l = (body or "").lower()

    terms = _tokenize(q)
    if not terms:
        return 0.0

    hit_title = sum(1 for t in terms if t in title_l)
    hit_body = sum(1 for t in terms if t in body_l)
    total = len(terms)

    score = (hit_title * 1.0 + hit_body * 0.4) / (total * 1.0)
    # 整串子串命中直接给满分（最强信号）
    if q in title_l:
        score = 1.0
    return min(score, 1.0)


_pgvector_supported: bool | None = None


@dataclass(slots=True)
class SearchHit:
    entry_id: int
    title: str
    slug: str | None
    content_type_id: int
    content_type_key: str = ""
    status: str = "draft"
    score: float = 0.0
    vector_score: float = 0.0
    keyword_score: float = 0.0
    snippet: str = ""
    published_at: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "title": self.title,
            "slug": self.slug,
            "content_type_id": self.content_type_id,
            "content_type_key": self.content_type_key,
            "status": self.status,
            "score": round(self.score, 4),
            "vector_score": round(self.vector_score, 4),
            "keyword_score": round(self.keyword_score, 4),
            "snippet": self.snippet,
            "published_at": self.published_at,
        }


# ---------------------------------------------------------------------------
# 数学工具
# ---------------------------------------------------------------------------
def _cosine_py(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=False):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _cosine_batch(query: list[float], matrix: list[list[float]]) -> list[float]:
    """一次查询对多向量。numpy 可用时走矩阵运算（快 1~2 个数量级）。"""
    if not matrix:
        return []
    if _np is not None:
        try:
            q = _np.asarray(query, dtype=_np.float32)
            m = _np.asarray(matrix, dtype=_np.float32)
            if m.ndim != 2 or m.shape[1] != q.shape[0]:
                return [_cosine_py(query, v) for v in matrix]
            qn = _np.linalg.norm(q)
            mn = _np.linalg.norm(m, axis=1)
            denom = mn * qn
            denom[denom == 0] = 1e-12
            return (_np.dot(m, q) / denom).tolist()
        except Exception:
            pass
    return [_cosine_py(query, v) for v in matrix]


def _make_snippet(text_value: str, query: str, width: int = 160) -> str:
    """截一段包含查询词的摘要，找不到就从开头截。"""
    t = (text_value or "").strip()
    if not t:
        return ""
    idx = t.lower().find((query or "").strip().lower())
    if idx <= 0:
        return t[:width] + ("…" if len(t) > width else "")
    start = max(0, idx - width // 3)
    end = min(len(t), start + width)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(t) else ""
    return prefix + t[start:end] + suffix


# ---------------------------------------------------------------------------
# pgvector 探测
# ---------------------------------------------------------------------------
async def has_pgvector(session: AsyncSession) -> bool:
    """检测当前库是否装了 pgvector（结果进程内缓存）。"""
    global _pgvector_supported
    if _pgvector_supported is not None:
        return _pgvector_supported
    try:
        row = (
            await session.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
        ).first()
        _pgvector_supported = row is not None
    except Exception:
        _pgvector_supported = False
    logger.info("cms.pgvector", available=_pgvector_supported)
    return _pgvector_supported


# ---------------------------------------------------------------------------
# 主检索
# ---------------------------------------------------------------------------
async def semantic_search(
    session: AsyncSession,
    query: str,
    *,
    content_type_id: int | None = None,
    content_type_key: str | None = None,
    lang: str = "base",
    status: str | None = None,
    limit: int = 10,
    min_score: float = 0.0,
    include_drafts: bool = False,
) -> list[SearchHit]:
    """语义 + 关键词混合检索。

    content_type_key 与 content_type_id 二选一，key 更方便 Agent 调用。
    include_drafts=False 时只返回已发布内容（Agent 默认只看线上内容）。
    """
    q = (query or "").strip()
    if not q:
        return []

    # content_type_key → id
    ct_map: dict[int, str] = {}
    if content_type_key:
        ct = (
            await session.execute(select(ContentType).where(ContentType.key == content_type_key))
        ).scalar_one_or_none()
        if ct is None:
            return []
        content_type_id = ct.id

    # 1) query 向量
    llm = get_llm_for("embedding")
    try:
        query_vec = await llm.embed_one(q)
    except LLMNotConfiguredError:
        raise
    except Exception as exc:
        logger.warning("cms.search_embed_failed", error=str(exc))
        raise

    # 2) 拉候选向量
    stmt = select(CmsEmbedding.entry_id, CmsEmbedding.vector).where(
        CmsEmbedding.lang == lang,
        CmsEmbedding.field == "combined",
        CmsEmbedding.vector.is_not(None),
    )
    if content_type_id is not None:
        stmt = stmt.join(Entry, Entry.id == CmsEmbedding.entry_id).where(
            Entry.content_type_id == content_type_id
        )
    rows = (await session.execute(stmt.limit(MAX_CANDIDATES))).all()

    vec_scores: dict[int, float] = {}
    if rows:
        vectors = [r[1] for r in rows]
        scores = _cosine_batch(query_vec, vectors)
        for (entry_id, _), sc in zip(rows, scores, strict=False):
            vec_scores[entry_id] = float(sc)

    # 3) 命中条目详情（只查候选里出现的 + 关键词命中的）
    entry_ids = list(vec_scores.keys())
    if not entry_ids:
        return []

    estmt = select(Entry).where(Entry.id.in_(entry_ids), Entry.deleted_at.is_(None))
    if content_type_id is not None:
        estmt = estmt.where(Entry.content_type_id == content_type_id)
    if not include_drafts and status is None:
        estmt = estmt.where(Entry.status == "published")
    elif status:
        estmt = estmt.where(Entry.status == status)
    entries = (await session.execute(estmt)).scalars().all()

    # 4) 混合打分
    # 性能取舍：entry_to_text 要重建全文，对几百个候选全跑一遍是浪费。
    # 先用向量分粗排取前 limit*5，只对这批算关键词与摘要。
    entries.sort(key=lambda e: vec_scores.get(e.id, 0.0), reverse=True)
    shortlist = entries[: max(limit * 5, limit)]

    hits: list[SearchHit] = []
    for entry in shortlist:
        v = vec_scores.get(entry.id, 0.0)
        body = entry_to_text(entry)
        k = _keyword_score(q, entry.title, body)
        final = VECTOR_WEIGHT * v + KEYWORD_WEIGHT * k
        if final < min_score:
            continue
        hits.append(
            SearchHit(
                entry_id=entry.id,
                title=entry.title,
                slug=entry.slug,
                content_type_id=entry.content_type_id,
                status=entry.status,
                score=final,
                vector_score=v,
                keyword_score=k,
                snippet=_make_snippet(body, q),
                published_at=entry.published_at.isoformat() if entry.published_at else None,
            )
        )

    hits.sort(key=lambda h: h.score, reverse=True)
    hits = hits[:limit]

    # 5) 补内容类型 key（Agent 更爱看 key 而不是数字 id）
    if hits:
        ct_rows = (
            await session.execute(
                select(ContentType.id, ContentType.key).where(
                    ContentType.id.in_({h.content_type_id for h in hits})
                )
            )
        ).all()
        ct_map = {r[0]: r[1] for r in ct_rows}
        for h in hits:
            h.content_type_key = ct_map.get(h.content_type_id, "")

    logger.info("cms.search", query=q[:40], candidates=len(rows), hits=len(hits), lang=lang)
    return hits


async def similar_entries(
    session: AsyncSession,
    entry_id: int,
    *,
    lang: str = "base",
    limit: int = 5,
) -> list[SearchHit]:
    """「和这条相似的内容」——用条目自己的向量做查询。"""
    row = (
        await session.execute(
            select(CmsEmbedding.vector).where(
                CmsEmbedding.entry_id == entry_id,
                CmsEmbedding.lang == lang,
                CmsEmbedding.field == "combined",
            )
        )
    ).scalar_one_or_none()
    if not row:
        return []

    return await _search_by_vector(session, row, lang=lang, limit=limit, exclude_id=entry_id)


async def _search_by_vector(
    session: AsyncSession,
    vector: list[float],
    *,
    lang: str,
    limit: int,
    exclude_id: int | None = None,
) -> list[SearchHit]:
    stmt = select(CmsEmbedding.entry_id, CmsEmbedding.vector).where(
        CmsEmbedding.lang == lang,
        CmsEmbedding.field == "combined",
        CmsEmbedding.vector.is_not(None),
    )
    if exclude_id is not None:
        stmt = stmt.where(CmsEmbedding.entry_id != exclude_id)
    rows = (await session.execute(stmt.limit(MAX_CANDIDATES))).all()
    if not rows:
        return []

    scores = _cosine_batch(vector, [r[1] for r in rows])
    ranked = sorted(
        ((r[0], float(s)) for r, s in zip(rows, scores, strict=False)),
        key=lambda x: x[1],
        reverse=True,
    )[:limit]

    ids = [eid for eid, _ in ranked]
    entries = {
        e.id: e
        for e in (
            await session.execute(
                select(Entry).where(
                    Entry.id.in_(ids), Entry.deleted_at.is_(None), Entry.status == "published"
                )
            )
        )
        .scalars()
        .all()
    }

    out: list[SearchHit] = []
    for eid, sc in ranked:
        e = entries.get(eid)
        if e is None:
            continue
        out.append(
            SearchHit(
                entry_id=e.id,
                title=e.title,
                slug=e.slug,
                content_type_id=e.content_type_id,
                status=e.status,
                score=sc,
                vector_score=sc,
                snippet=_make_snippet(entry_to_text(e), ""),
                published_at=e.published_at.isoformat() if e.published_at else None,
            )
        )
    return out
