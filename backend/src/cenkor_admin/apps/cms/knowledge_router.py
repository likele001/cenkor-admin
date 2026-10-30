"""知识库 HTTP 接口。

端点分组：
    POST /kb/docs/upload      上传文件入库（PDF/Word/Excel/图片/视频/文本）
    POST /kb/docs/paste       粘贴文本入库
    GET  /kb/docs             文档列表
    GET  /kb/docs/{id}        详情 + 分片预览
    DELETE /kb/docs/{id}      删除（软删，级联保留分片但检索立即排除）
    POST /kb/docs/{id}/reindex 重建索引
    POST /kb/search           检索测试（看到底命中了哪几段）
    GET  /kb/stats            概览

一个刻意的设计：**上传接口不等向量化**。
一份 40 段的文档要调 40 次 embedding，几十秒起步；让 HTTP 请求干等
的结果是前端转圈到超时，用户以为传失败了又传一遍。所以上传立刻返回
doc_id（status=pending），前端轮询列表看状态变化。
"""

from __future__ import annotations

from datetime import UTC
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms import knowledge
from cenkor_admin.apps.cms.knowledge_models import KbDoc
from cenkor_admin.core.db import get_db
from cenkor_admin.core.llm import LLMNotConfiguredError
from cenkor_admin.core.site_scope import current_site_id

router = APIRouter()


def _site() -> int:
    return current_site_id() or 1


def _doc_out(doc: KbDoc, *, with_text: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": doc.id,
        "title": doc.title,
        "source_type": doc.source_type,
        "file_name": doc.file_name,
        "mime": doc.mime,
        "size_bytes": doc.size_bytes,
        "category": doc.category,
        "note": doc.note,
        "status": doc.status,
        "error": doc.error,
        "chars": doc.chars,
        "chunk_count": doc.chunk_count,
        "indexed_chunks": doc.indexed_chunks,
        "embed_model": doc.embed_model,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    }
    if with_text:
        data["content_text"] = doc.content_text
    return data


class PasteIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1)
    category: str = Field(default="", max_length=60)
    note: str = Field(default="", max_length=2000)


@router.post("/kb/docs/upload", summary="知识库：上传文件入库（异步索引）")
async def kb_upload(
    file: UploadFile = File(..., description="PDF / Word / Excel / 图片 / 视频 / 文本"),
    title: str = Form(default=""),
    category: str = Form(default=""),
    note: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """文件 → 抽取文本 → 落库 → 后台向量化。

    落库阶段就会把格式错误（不支持的扩展名、超大文件、扫描件无文字）报出来，
    用户不用等索引完才知道传错了。
    """
    data = await file.read()
    try:
        doc, created = await knowledge.create_from_upload(
            db,
            data=data,
            filename=file.filename or "upload.bin",
            title=title,
            category=category,
            note=note,
            created_by=getattr(user, "id", None),
            site_id=_site(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not created:
        return {
            "doc": _doc_out(doc),
            "created": False,
            "message": "这份文档已经存在（内容完全一致），没有重复入库",
        }

    await db.commit()
    await db.refresh(doc)

    # 后台索引：不阻塞响应，前端轮询列表看状态从 pending → ready。
    # 起不来也不是死局 —— 调度器 30 秒内会把 pending 文档捞起来。
    knowledge.spawn_index(doc.id)

    return {"doc": _doc_out(doc), "created": True, "message": "已入库，正在后台建立索引"}


@router.post("/kb/docs/paste", summary="知识库：粘贴文本入库（异步索引）")
async def kb_paste(
    payload: PasteIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        doc, created = await knowledge.create_doc(
            db,
            title=payload.title,
            content=payload.text,
            source_type="paste",
            category=payload.category,
            note=payload.note,
            created_by=getattr(user, "id", None),
            site_id=_site(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not created:
        return {
            "doc": _doc_out(doc),
            "created": False,
            "message": "这段内容已经存在（内容完全一致），没有重复入库",
        }

    await db.commit()
    await db.refresh(doc)

    knowledge.spawn_index(doc.id)

    return {"doc": _doc_out(doc), "created": True, "message": "已入库，正在后台建立索引"}


@router.get("/kb/docs", summary="知识库：文档列表")
async def kb_list(
    q: str = Query(default="", description="按标题/文件名模糊搜索"),
    category: str = Query(default="", description="按分类过滤"),
    status_filter: str = Query(default="", alias="status", description="按索引状态过滤"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    stmt = select(KbDoc).where(KbDoc.site_id == _site(), KbDoc.deleted_at.is_(None))
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(KbDoc.title.ilike(like), KbDoc.file_name.ilike(like)))
    if category.strip():
        stmt = stmt.where(KbDoc.category == category.strip())
    if status_filter.strip():
        stmt = stmt.where(KbDoc.status == status_filter.strip())

    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (
        await db.execute(
            stmt.order_by(KbDoc.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return {
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
        "items": [_doc_out(d) for d in rows],
    }


@router.get("/kb/docs/{doc_id}", summary="知识库：文档详情与分片预览")
async def kb_detail(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    doc = (
        await db.execute(
            select(KbDoc).where(
                KbDoc.id == doc_id, KbDoc.site_id == _site(), KbDoc.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    chunks = await knowledge.doc_chunks(db, doc_id)
    return {
        "doc": _doc_out(doc),
        # 全文可能几万字，详情页只回前 4000 字，够判断内容对不对
        "text_preview": (doc.content_text or "")[:4000],
        "chunks": chunks,
    }


@router.delete("/kb/docs/{doc_id}", summary="知识库：删除文档")
async def kb_delete(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """软删文档。

    分片不做物理删除：保留是为了「删错了能不能救回来」这件事有个余地。
    检索侧按 `deleted_at IS NULL` 过滤，删掉立刻不进召回。
    """
    from datetime import datetime

    doc = (
        await db.execute(
            select(KbDoc).where(
                KbDoc.id == doc_id, KbDoc.site_id == _site(), KbDoc.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    doc.deleted_at = datetime.now(UTC)
    await db.commit()
    logger.info("cms.kb.doc_deleted", doc_id=doc_id, by=getattr(user, "id", None))
    return {"deleted": True, "doc_id": doc_id}


@router.post("/kb/docs/{doc_id}/reindex", summary="知识库：重建索引")
async def kb_reindex(
    doc_id: int,
    force: bool = Query(default=False, description="true 时忽略指纹强制重算向量（换模型后用）"),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    doc = (
        await db.execute(
            select(KbDoc).where(
                KbDoc.id == doc_id, KbDoc.site_id == _site(), KbDoc.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    # 先落状态再起任务：反过来的话，后台任务可能先读到旧的 ready 状态
    # 直接跳过，用户点了「重建」却什么都没发生
    if force:
        doc.content_hash = ""
        doc.error = ""
    doc.status = "pending"
    await db.commit()

    if not knowledge.spawn_index(doc_id, force=force):
        # 已经在跑了：告诉调用方实情，别假装排上队了
        return {"queued": False, "doc_id": doc_id, "force": force, "message": "该文档正在索引中"}

    return {"queued": True, "doc_id": doc_id, "force": force}


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=6, ge=1, le=20)


@router.post("/kb/search", summary="知识库：检索测试")
async def kb_search(
    payload: SearchIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """直接看「这个问题会召回哪几段」。

    这不是给终端用户用的搜索框，是给运营确认「知识库到底有没有用」的 ——
    上传了 20 份手册，问一句能不能召回对的段落，比看索引状态有用得多。
    """
    try:
        hits = await knowledge.search(
            db, payload.query, site_id=_site(), limit=payload.limit, min_score=0.0
        )
    except LLMNotConfiguredError as exc:
        raise HTTPException(
            status_code=503, detail="未配置 embedding 能力，知识库检索不可用"
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"检索失败：{exc}") from exc

    # 低于门槛的也返回，但标 passed=false —— 让人看见「召回了但不会用」，
    # 比直接藏起来有用：门槛没调好时，这一屏就是调门槛的依据
    for h in hits:
        h["passed"] = h["score"] >= knowledge.KB_MIN_SCORE

    return {
        "query": payload.query,
        "count": len(hits),
        "effective_count": sum(1 for h in hits if h["passed"]),
        "threshold": knowledge.KB_MIN_SCORE,
        "hits": hits,
        "note": "低于 threshold 的分片只展示，不会被用于 AI 起草与问答",
    }


@router.get("/kb/stats", summary="知识库：概览")
async def kb_stats(
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    stats = await knowledge.stats(db, site_id=_site())
    stats["limits"] = {
        "max_chunks_per_doc": knowledge.KB_MAX_CHUNKS,
        "max_chars_per_doc": knowledge.KB_MAX_CHARS,
        "min_score": knowledge.KB_MIN_SCORE,
    }
    return stats
