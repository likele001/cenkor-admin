"""知识库：独立语料的入库、切分、向量化与检索。

## 为什么要有这个东西

现有 RAG 的语料只有 `cms_entries` —— **AI 只能读自己写过的文章**。
产品手册、FAQ、历史方案、售后问答这些真正的内容依据进不来，
起草时模型只能靠预训练知识自由发挥，写出来的东西"像那么回事但不落地"。

知识库就是把这批资料变成可检索的依据：起草时按选题召回相关段落，
连同出处一起塞进提示词，让模型引用事实而不是编事实。

## 三个关键取舍

**按 chunk 存，不按文档存。**
一本 5 万字的手册整篇一个向量，召回后塞给模型的是整本手册 ——
一半篇幅与问题无关，还白烧 token。切到 1200 字一段，召回才精准。
（与 `rag.py` 同一套切分口径，两处结果对得上。）

**抽取出的全文必须落库。**
换 embedding 模型要重切片、详情页要预览、改标题要重算 heading_path ——
不存原文，这三件事都得让用户重新上传一遍。

**索引是异步的，但状态必须可恢复。**
向量化 40 个分片要几十秒，不能让上传接口干等。用后台任务跑；
同时留 `pending` 这个状态让调度器能捞回来 —— 服务重启导致后台任务丢失时，
文档不会永久卡在「排队中」。这是最常见的"功能好像坏了"。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.ai.embedding import content_hash
from cenkor_admin.apps.cms.ai.ingest import extract_attachment
from cenkor_admin.apps.cms.ai.rag import chunk_entry
from cenkor_admin.apps.cms.knowledge_models import KbChunk, KbDoc
from cenkor_admin.core.hooks import hook
from cenkor_admin.core.llm import LLMNotConfiguredError, get_llm_for

# 单文档最多切多少块。一本 20 万字的手册能切出 160 段，
# 全量向量化要调 160 次接口、花掉几块钱，而且召回质量并不会更好 ——
# 手册里真正被问到的是那几十段。超出部分截断并明确告知。
KB_MAX_CHUNKS = 40
# 单文档正文上限（字符）。检索质量随时间线性下降，但成本是线性的，
# 超过 30 万字的单一文档本来就该拆成多份（《实施手册》《常见问题》分开传）。
KB_MAX_CHARS = 300_000

# 召回门槛。
#
# 0.35 是拿真实查询量出来的，不是拍脑袋：
#   相关查询的 Top1 分数在 0.63~0.75，次高在 0.38~0.49；
#   无关查询的 Top1 在 0.09~0.27（「公司年会什么时候开」对 MES 手册 0.27
#   是最高的一个，因为中文里"什么时候"这类时间词会带来虚假相似度）。
#
# 取 0.35：无关最高 0.27 上方留 0.08 安全间隙，相关次高 0.38 以上能保留。
# 门槛定低了，模型会把不相关段落硬接成论据；定高了，一问就"没找到资料"，
# 等于白建。0.2 时实测「今天天气怎么样」也能召回三段 MES 手册 —— 这就是误召。
KB_MIN_SCORE = 0.35

# 正在索引的文档（进程内）。调度器每 30 秒捞一次待索引入库的文档，
# 没有这层锁的话，一个耗时 60 秒的大文档会被捞起来跑两遍。
_INFLIGHT: set[int] = set()

# 后台任务强引用集合。asyncio 只持弱引用，不存一份任务跑一半会被 GC 掉 ——
# 这是 asyncio.create_task 最常见的静默失败。
_BG: set[Any] = set()


def _vector_literal(vec: list[float]) -> str:
    """转成 pgvector 认的字面量。

    直接传 list 给 asyncpg 会被当成 SQL 数组，`<=>` 运算符不认；
    CAST(:q AS vector) 需要字符串形态。
    """
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


# ---------------------------------------------------------------------------
# 入库
# ---------------------------------------------------------------------------


async def find_duplicate(session: AsyncSession, site_id: int, digest: str) -> KbDoc | None:
    """按文本指纹找同一份文档。

    不去重的话，「产品手册 v2」和它的副本会各占一半召回名额，
    用户看到的结果里同一段话出现两次 —— 这比召回不到更让人困惑。
    """
    if not digest:
        return None
    return (
        await session.execute(
            select(KbDoc).where(
                KbDoc.site_id == site_id,
                KbDoc.content_hash == digest,
                KbDoc.deleted_at.is_(None),
                KbDoc.status != "failed",
            )
        )
    ).scalars().first()


async def create_doc(
    session: AsyncSession,
    *,
    title: str,
    content: str,
    source_type: str = "paste",
    file_name: str = "",
    mime: str = "",
    size_bytes: int = 0,
    category: str = "",
    note: str = "",
    created_by: int | None = None,
    site_id: int = 1,
) -> tuple[KbDoc, bool]:
    """落库一份待索引文档，返回 (doc, 是否新建)。

    只做落库，不做向量化 —— 向量化由调用方决定用后台任务还是同步跑。
    """
    body = (content or "").strip()
    if not body:
        raise ValueError("文档没有可用文本")

    truncated = False
    if len(body) > KB_MAX_CHARS:
        body = body[:KB_MAX_CHARS].rstrip()
        truncated = True

    digest = content_hash(body)
    dup = await find_duplicate(session, site_id, digest)
    if dup is not None:
        return dup, False

    doc = KbDoc(
        site_id=site_id,
        title=(title or file_name or "未命名文档").strip()[:200],
        source_type=source_type,
        file_name=(file_name or "")[:255],
        mime=(mime or "")[:120],
        size_bytes=int(size_bytes or 0),
        category=(category or "")[:60],
        note=(note or "")[:2000] + ("（正文超长已截断）" if truncated else ""),
        status="pending",
        content_text=body,
        chars=len(body),
        content_hash=digest,
        created_by=created_by or None,
    )
    session.add(doc)
    await session.flush()
    logger.info("cms.kb.doc_created", doc_id=doc.id, chars=len(body), truncated=truncated)
    return doc, True


async def create_from_upload(
    session: AsyncSession,
    *,
    data: bytes,
    filename: str,
    title: str = "",
    category: str = "",
    note: str = "",
    created_by: int | None = None,
    site_id: int = 1,
) -> tuple[KbDoc, bool]:
    """上传文件 → 抽取文本 → 落库。格式与大小校验在 `ingest` 里，异常直接抛。"""
    result = await extract_attachment(session, data, filename, created_by=created_by)
    extract_note = "；".join(result.warnings) if result.warnings else ""
    merged_note = "；".join(x for x in (note.strip(), extract_note) if x)
    return await create_doc(
        session,
        title=title or filename,
        content=result.text,
        source_type="upload",
        file_name=filename,
        mime=result.kind,
        size_bytes=len(data),
        category=category,
        note=merged_note,
        created_by=created_by,
        site_id=site_id,
    )


# ---------------------------------------------------------------------------
# 索引（切分 + 向量化）
# ---------------------------------------------------------------------------


async def index_doc(session: AsyncSession, doc: KbDoc, *, force: bool = False) -> dict[str, Any]:
    """切分并向量化一份文档。可重复调用：内容没变的分片不重复花钱。"""
    body = (doc.content_text or "").strip()
    if not body:
        doc.status = "failed"
        doc.error = "文档没有可索引的文本（可能是扫描件 PDF 或纯图片）"
        return {"doc_id": doc.id, "ok": False, "error": doc.error}

    doc.status = "indexing"
    await session.flush()

    pieces = chunk_entry(doc.title, {"text": body}, max_chunks=KB_MAX_CHUNKS)
    if not pieces:
        doc.status = "failed"
        doc.error = "切分后没有有效内容"
        return {"doc_id": doc.id, "ok": False, "error": doc.error}

    existing = {
        c.seq: c
        for c in (
            await session.execute(select(KbChunk).where(KbChunk.doc_id == doc.id))
        ).scalars().all()
    }

    try:
        llm = get_llm_for("embedding")
    except LLMNotConfiguredError:
        doc.status = "failed"
        doc.error = "未配置 embedding 能力，无法建立知识库索引"
        raise

    indexed = 0
    calls = 0
    tokens = 0
    for piece in pieces:
        seq = int(piece["index"])
        digest = content_hash(piece["text"])
        row = existing.get(seq)

        # 内容没变且已有向量：直接跳过，零成本
        if row is not None and not force and row.content_hash == digest and row.vector is not None:
            indexed += 1
            continue

        try:
            vec, meta = await llm.embed_one_meta(piece["text"])
        except LLMNotConfiguredError:
            raise
        except Exception as exc:  # noqa: BLE001
            # 单个分片失败不放弃整篇：其余分片仍可检索，报告里说明缺几段
            logger.warning("cms.kb.embed_failed", doc_id=doc.id, seq=seq, error=str(exc))
            continue

        calls += 1
        tokens += int(meta.get("prompt_tokens") or 0)

        if row is None:
            row = KbChunk(doc_id=doc.id, seq=seq)
            session.add(row)
        row.heading = (piece.get("heading") or "")[:200]
        row.heading_path = (piece.get("heading_path") or "")[:400]
        row.text = piece["text"]
        row.chars = int(piece.get("chars") or len(piece["text"]))
        row.vector = vec
        row.dim = len(vec)
        row.content_hash = digest
        row.model = llm.embed_model or ""
        indexed += 1

    # 文档变短了：把多余的旧分片删掉，否则召回里会留着已经删掉的段落
    for seq, row in existing.items():
        if seq >= len(pieces):
            await session.delete(row)

    doc.chunk_count = len(pieces)
    doc.indexed_chunks = indexed
    doc.chars = len(body)
    doc.embed_model = llm.embed_model or ""
    doc.status = "ready" if indexed > 0 else "failed"
    doc.error = "" if indexed == len(pieces) else f"{len(pieces) - indexed} 个分片向量化失败，可重建索引重试"

    if calls:
        await _record_embedding_cost(
            session, doc, provider=llm.provider or "", model=llm.embed_model or "",
            tokens=tokens, calls=calls,
        )

    logger.info(
        "cms.kb.indexed",
        doc_id=doc.id,
        chunks=len(pieces),
        indexed=indexed,
        api_calls=calls,
    )
    return {"doc_id": doc.id, "ok": indexed > 0, "chunks": len(pieces), "indexed": indexed}


async def _record_embedding_cost(
    session: AsyncSession, doc: KbDoc, *, provider: str, model: str, tokens: int, calls: int
) -> None:
    """知识库向量化同样按 token 计费。

    不记账的话「AI 用量」页会漏掉这块 —— 导一本手册看着一次没调，
    实际账单已经在涨，这种账最容易被当成 bug 报上来。
    记账失败不能影响向量落库，所以整段包 try。
    """
    try:
        from cenkor_admin.apps.cms.ai import pricing as ai_pricing
        from cenkor_admin.apps.cms.ai.models import CmsAiGeneration

        cost = None
        currency = "CNY"
        try:
            cost, currency = await ai_pricing.snapshot_cost(
                session,
                kind="embedding",
                provider=provider,
                model=model,
                tokens_in=tokens,
                tokens_out=0,
                tokens_cache=0,
                calls=1,
            )
        except Exception:  # noqa: BLE001
            cost = None

        session.add(
            CmsAiGeneration(
                site_id=doc.site_id or 1,
                kind="embedding",
                target=f"kb:{doc.id}",
                provider=provider,
                model=model,
                prompt_digest="",
                params={"api_calls": calls, "doc_id": doc.id},
                tokens_in=tokens,
                tokens_out=0,
                cost=cost,
                currency=currency,
                latency_ms=0,
                status="ok",
                error=None,
                created_by=doc.created_by,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("cms.kb.cost_record_failed", doc_id=doc.id, error=str(exc))


# ---------------------------------------------------------------------------
# 检索
# ---------------------------------------------------------------------------


async def search(
    session: AsyncSession,
    query: str,
    *,
    site_id: int = 1,
    limit: int = 6,
    min_score: float = KB_MIN_SCORE,
) -> list[dict[str, Any]]:
    """按语义召回知识分片。返回带出处（文档标题 + 章节路径）的段落。

    设计上只做向量召回，不做关键词混合：知识库的语料是「参考依据」，
    用户问的是自然语言问题，词面根本不重合（「交期怎么算」vs「生产周期说明」）。
    混合检索的收益在结构化条目上更明显，这里加进来只会引入噪声。
    """
    q = (query or "").strip()
    if not q:
        return []

    llm = get_llm_for("embedding")
    vec, _meta = await llm.embed_one_meta(q)
    literal = _vector_literal(vec)

    rows = (
        await session.execute(
            text(
                """
                SELECT c.id, c.doc_id, d.title, c.heading_path, c.text,
                       c.chars, 1 - (c.vector <=> CAST(:q AS vector)) AS score
                  FROM cms_kb_chunks c
                  JOIN cms_kb_docs d ON d.id = c.doc_id
                 WHERE d.deleted_at IS NULL
                   AND d.status = 'ready'
                   AND d.site_id = :sid
                   AND c.vector IS NOT NULL
                 ORDER BY c.vector <=> CAST(:q AS vector)
                 LIMIT :n
                """
            ),
            {"q": literal, "sid": int(site_id), "n": int(max(limit * 2, 8))},
        )
    ).all()

    hits = [
        {
            "chunk_id": int(r[0]),
            "doc_id": int(r[1]),
            "doc_title": r[2] or "",
            "heading_path": r[3] or "",
            "text": r[4] or "",
            "chars": int(r[5] or 0),
            "score": round(float(r[6]), 4),
            "passed": float(r[6]) >= min_score,
            "source": "kb",
        }
        for r in rows
    ]
    return [h for h in hits if h["score"] >= min_score][: max(1, limit)]


async def context_for_prompt(
    session: AsyncSession,
    query: str,
    *,
    site_id: int = 1,
    limit: int = 4,
    max_chars: int = 4000,
) -> tuple[str, list[dict[str, Any]]]:
    """整理成可直接拼进提示词的参考材料 + 出处列表。

    返回 (文本块, 出处明细)。没有任何命中时返回 ("", [])，
    调用方据此保持原有提示词不变 —— 知识库为空不该让起草质量变差。
    """
    try:
        hits = await search(session, query, site_id=site_id, limit=limit)
    except LLMNotConfiguredError:
        return "", []
    except Exception as exc:  # noqa: BLE001
        # 检索挂了不能连带把起草搞挂：起草本身可能用的是别的能力
        logger.warning("cms.kb.context_failed", error=str(exc))
        return "", []

    if not hits:
        return "", []

    blocks: list[str] = []
    used: list[dict[str, Any]] = []
    total = 0
    for h in hits:
        piece = f"【{h['heading_path'] or h['doc_title']}】\n{h['text'].strip()}"
        if total + len(piece) > max_chars:
            break
        blocks.append(piece)
        used.append(
            {
                "doc_id": h["doc_id"],
                "doc_title": h["doc_title"],
                "heading_path": h["heading_path"],
                "score": h["score"],
                "chars": h["chars"],
            }
        )
        total += len(piece)

    if not blocks:
        return "", []
    return "\n\n".join(blocks), used


# ---------------------------------------------------------------------------
# 管理
# ---------------------------------------------------------------------------


async def doc_chunks(session: AsyncSession, doc_id: int, *, limit: int = 60) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(KbChunk)
            .where(KbChunk.doc_id == doc_id)
            .order_by(KbChunk.seq)
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "seq": c.seq,
            "heading": c.heading,
            "heading_path": c.heading_path,
            "chars": c.chars,
            "text": c.text,
            "has_vector": c.vector is not None,
            "model": c.model,
        }
        for c in rows
    ]


async def stats(session: AsyncSession, *, site_id: int = 1) -> dict[str, Any]:
    """概览：这份知识库到底建没建起来。"""
    base = select(KbDoc).where(KbDoc.site_id == site_id, KbDoc.deleted_at.is_(None))
    docs = (await session.execute(base)).scalars().all()

    by_status: dict[str, int] = {}
    for d in docs:
        by_status[d.status] = by_status.get(d.status, 0) + 1

    chunk_total = await session.scalar(
        select(func.count(KbChunk.id)).join(KbDoc, KbDoc.id == KbChunk.doc_id).where(
            KbDoc.site_id == site_id, KbDoc.deleted_at.is_(None)
        )
    )
    chunk_indexed = await session.scalar(
        select(func.count(KbChunk.id)).join(KbDoc, KbDoc.id == KbChunk.doc_id).where(
            KbDoc.site_id == site_id,
            KbDoc.deleted_at.is_(None),
            KbChunk.vector.is_not(None),
        )
    )

    cats: dict[str, int] = {}
    for d in docs:
        key = d.category or "未分类"
        cats[key] = cats.get(key, 0) + 1

    model = next((d.embed_model for d in docs if d.embed_model), "")

    return {
        "docs": len(docs),
        "by_status": by_status,
        "ready_docs": by_status.get("ready", 0),
        "chunks": int(chunk_total or 0),
        "indexed_chunks": int(chunk_indexed or 0),
        "chars": sum(d.chars for d in docs),
        "embed_model": model,
        "categories": sorted(
            ({"name": k, "count": v} for k, v in cats.items()),
            key=lambda x: -x["count"],
        ),
    }


async def recover_stale(session: AsyncSession, *, older_than_minutes: int = 5) -> list[int]:
    """把卡住的待索引文档捞出来。

    只捞 `pending` / `indexing` 且超过 N 分钟没动的：
    正常索引中的文档 `updated_at` 会被 flush 刷新，
    超过 5 分钟没动静基本就是进程重启把后台任务丢了。
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
    rows = (
        await session.execute(
            select(KbDoc.id)
            .where(
                KbDoc.deleted_at.is_(None),
                KbDoc.status.in_(("pending", "indexing")),
                KbDoc.updated_at < cutoff,
            )
            .order_by(KbDoc.id)
            .limit(3)
        )
    ).scalars().all()
    return [int(x) for x in rows]


def spawn_index(doc_id: int, *, force: bool = False) -> bool:
    """起一个后台索引任务。返回是否成功提交。

    路由层只调这个函数，不碰 `_INFLIGHT` / `_BG` 这些内部状态 ——
    否则「哪些文档正在跑」这件事会有两处真相。
    起不来也不是死局：调度器 30 秒内会把 pending 文档捞起来。
    """
    import asyncio

    if doc_id in _INFLIGHT:
        return False
    try:
        task = asyncio.create_task(index_in_background(doc_id, force=force))
    except Exception as exc:  # noqa: BLE001
        logger.warning("cms.kb.spawn_failed", doc_id=doc_id, error=str(exc))
        return False
    _BG.add(task)
    task.add_done_callback(_BG.discard)
    return True


async def index_in_background(doc_id: int, *, force: bool = False) -> None:
    """独立 session 跑索引。

    不能复用请求的 session：请求返回后 session 就被关掉了，
    而后台任务还在等 embedding 接口。
    """
    from cenkor_admin.core.db import AsyncSessionLocal

    if doc_id in _INFLIGHT:
        return
    _INFLIGHT.add(doc_id)
    try:
        async with AsyncSessionLocal() as db:
            doc = (
                await db.execute(select(KbDoc).where(KbDoc.id == doc_id))
            ).scalar_one_or_none()
            if doc is None or doc.deleted_at is not None:
                return
            await index_doc(db, doc, force=force)
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("cms.kb.bg_index_failed", doc_id=doc_id, error=str(exc))
        # 留一条可读的失败原因，别让用户只看到「排队中」
        try:
            from cenkor_admin.core.db import AsyncSessionLocal as _S

            async with _S() as db:
                doc = (await db.execute(select(KbDoc).where(KbDoc.id == doc_id))).scalar_one_or_none()
                if doc is not None:
                    doc.status = "failed"
                    doc.error = str(exc)[:500]
                    await db.commit()
        except Exception:  # noqa: BLE001
            pass
    finally:
        _INFLIGHT.discard(doc_id)


@hook("scheduler.tick")
async def _hook_recover_kb() -> None:
    """调度器兜底：把卡住的文档重新排队。

    为什么需要：后台任务活在进程内存里，宝塔自愈重启后全丢。
    没有这层兜底，用户会在「排队中」一直等，看起来就是功能坏了。
    """
    import asyncio

    from cenkor_admin.core.db import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            ids = [i for i in await recover_stale(db) if i not in _INFLIGHT]
        for doc_id in ids:
            task = asyncio.create_task(index_in_background(doc_id))
            _BG.add(task)
            task.add_done_callback(_BG.discard)
        if ids:
            logger.info("cms.kb.recovered", docs=ids)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cms.kb.recover_failed", error=str(exc))

