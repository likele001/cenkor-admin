"""CMS AI 能力 HTTP 接口

端点分组：
    /ai/content-types/*   对话式建模
    /ai/entries/*         AI 起草 / 翻译 / SEO
    /ai/search            语义检索
    /ai/vectors/rebuild   向量重建
    /ai/usage             AI 用量与成本

鉴权：全部要求登录用户（Depends(get_current_user)）。
AI 未配置时统一返回 503 并给出明确指引，前端据此隐藏 AI 入口。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms.ai import copilot
from cenkor_admin.apps.cms.ai.admin_router import router as admin_router
from cenkor_admin.apps.cms.ai.embedding import vectorize_entry, vectorize_pending
from cenkor_admin.apps.cms.ai.search import semantic_search, similar_entries
from cenkor_admin.apps.cms.models import Entry
from cenkor_admin.core.config import get_settings
from cenkor_admin.core.db import get_db
from cenkor_admin.core.llm import LLMError, LLMNotConfiguredError

router = APIRouter(prefix="/ai", tags=["cms-ai"])

# 配置管理（服务商 / 能力绑定 / 连通性测试）拆独立模块，
# 本文件只保留「用 AI 干活」的端点，避免一个文件越滚越大。
router.include_router(admin_router)


def _require_ai() -> None:
    if not get_settings().ai_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI 未启用：请在 .env 设置 AI_ENABLED=true 与 AI_API_KEY",
        )


def _map_llm_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LLMNotConfiguredError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=502, detail=f"AI 服务调用失败：{exc}")


# ---------------------------------------------------------------------------
# 对话式建模
# ---------------------------------------------------------------------------
@router.post("/content-types/propose", summary="自然语言生成内容类型草案")
async def propose_content_type(
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    _require_ai()
    description = str(body.get("description") or "").strip()
    if not description:
        raise HTTPException(status_code=400, detail="缺少 description")

    try:
        spec = await copilot.propose_content_type(
            db,
            description,
            locale=str(body.get("locale") or "zh-CN"),
            created_by=user.id,
            extra_hint=str(body.get("extra_hint") or ""),
        )
        await db.commit()
        return spec
    except Exception as exc:
        await db.rollback()
        raise _map_llm_error(exc) from exc


@router.post("/content-types/apply", summary="确认并真正创建内容类型")
async def apply_content_type(
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    _require_ai()
    try:
        ct = await copilot.apply_content_type(db, body, created_by=user.id)
        return {
            "id": ct.id,
            "key": ct.key,
            "name": ct.name,
            "created": True,
        }
    except Exception as exc:
        await db.rollback()
        raise _map_llm_error(exc) from exc


# ---------------------------------------------------------------------------
# AI 起草
# ---------------------------------------------------------------------------
@router.post("/entries/draft", summary="根据素材生成条目草稿（不落库）")
async def draft_entry(
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    _require_ai()
    ct_id = body.get("content_type_id")
    brief = str(body.get("brief") or "").strip()
    if not ct_id or not brief:
        raise HTTPException(status_code=400, detail="需要 content_type_id 与 brief")

    try:
        draft = await copilot.draft_entry(
            db,
            int(ct_id),
            brief,
            created_by=user.id,
            lang=str(body.get("lang") or "zh-CN"),
        )
        await db.commit()
        return draft
    except Exception as exc:
        await db.rollback()
        raise _map_llm_error(exc) from exc


@router.post("/entries/draft/save", summary="把草稿落库为条目（强制 draft 状态）")
async def save_draft(
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    _require_ai()
    try:
        entry = await copilot.create_entry_from_draft(db, body, created_by=user.id)
        return {"entry_id": entry.id, "status": entry.status, "title": entry.title}
    except Exception as exc:
        await db.rollback()
        raise _map_llm_error(exc) from exc


# ---------------------------------------------------------------------------
# 翻译 / SEO
# ---------------------------------------------------------------------------
async def _load_entry(db: AsyncSession, entry_id: int) -> Entry:
    entry = (
        await db.execute(select(Entry).where(Entry.id == entry_id, Entry.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail=f"条目 {entry_id} 不存在")
    return entry


@router.post("/entries/{entry_id}/translate", summary="AI 翻译条目到多语言")
async def translate_entry(
    entry_id: int,
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    _require_ai()
    langs = body.get("langs")
    if not isinstance(langs, list) or not langs:
        raise HTTPException(status_code=400, detail='需要 langs 数组，如 ["en-US"]')

    entry = await _load_entry(db, entry_id)
    try:
        result = await copilot.translate_entry(
            db,
            entry,
            [str(lg) for lg in langs],
            created_by=user.id,
            overwrite=bool(body.get("overwrite", False)),
        )
        return {"entry_id": entry_id, "results": result}
    except Exception as exc:
        await db.rollback()
        raise _map_llm_error(exc) from exc


@router.post("/entries/{entry_id}/seo", summary="生成 SEO 元数据建议")
async def suggest_seo(
    entry_id: int,
    body: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    _require_ai()
    entry = await _load_entry(db, entry_id)
    try:
        result = await copilot.suggest_seo(
            db, entry, created_by=user.id, lang=str(body.get("lang") or "zh-CN")
        )
        await db.commit()
        # 默认只给建议，不覆盖现有 SEO；需要写入时前端再调 entries 更新接口
        return {"entry_id": entry_id, **result}
    except Exception as exc:
        await db.rollback()
        raise _map_llm_error(exc) from exc


# ---------------------------------------------------------------------------
# 字段级改写（编辑页内嵌）
# ---------------------------------------------------------------------------
@router.post("/text/rewrite", summary="字段级 AI 改写（润色/扩写/精简/标题/摘要）")
async def rewrite_text(
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """改写用户已写下的文字，**不落库**。

    - 单块：`{"text": "...", "action": "polish"}`
    - 多块（HTML 正文由前端拆好）：`{"blocks": ["...", "..."], "action": "polish"}`

    正文之所以走多块，是为了让模型不产出 HTML —— 标签结构由前端 DOM 负责，
    模型只回文本，既不会破坏格式也没有 XSS 面。
    """
    _require_ai()
    action = str(body.get("action") or "polish")
    blocks = body.get("blocks")
    if blocks is not None and not isinstance(blocks, list):
        raise HTTPException(status_code=400, detail="blocks 必须是字符串数组")

    try:
        return await copilot.rewrite_text(
            db,
            action=action,
            text=(str(body.get("text")) if body.get("text") is not None else None),
            blocks=([str(b) for b in blocks] if blocks is not None else None),
            instruction=(str(body.get("instruction")) if body.get("instruction") else None),
            lang=str(body.get("lang") or "zh-CN"),
            context=(str(body.get("context"))[:1000] if body.get("context") else None),
            created_by=user.id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        raise _map_llm_error(exc) from exc


# ---------------------------------------------------------------------------
# 语义检索
# ---------------------------------------------------------------------------
@router.get("/search", summary="语义 + 关键词混合检索")
async def ai_search(
    q: str = Query(..., min_length=1, description="自然语言查询"),
    content_type_id: int | None = Query(default=None),
    content_type_key: str | None = Query(default=None),
    lang: str = Query(default="base"),
    limit: int = Query(default=10, ge=1, le=50),
    include_drafts: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    _require_ai()
    try:
        hits = await semantic_search(
            db,
            q,
            content_type_id=content_type_id,
            content_type_key=content_type_key,
            lang=lang,
            limit=limit,
            include_drafts=include_drafts,
        )
        return {"query": q, "count": len(hits), "results": [h.as_dict() for h in hits]}
    except Exception as exc:
        raise _map_llm_error(exc) from exc


@router.get("/entries/{entry_id}/similar", summary="找相似内容")
async def ai_similar(
    entry_id: int,
    lang: str = Query(default="base"),
    limit: int = Query(default=5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    _require_ai()
    hits = await similar_entries(db, entry_id, lang=lang, limit=limit)
    return {"entry_id": entry_id, "count": len(hits), "results": [h.as_dict() for h in hits]}


# ---------------------------------------------------------------------------
# 向量维护
# ---------------------------------------------------------------------------
@router.post("/vectors/rebuild", summary="批量补齐/重建条目向量")
async def rebuild_vectors(
    body: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    _require_ai()
    limit = int(body.get("limit") or 50)
    force = bool(body.get("force", False))
    entry_id = body.get("entry_id")

    try:
        if entry_id:
            entry = await _load_entry(db, int(entry_id))
            calls = await vectorize_entry(db, entry, force=force)
            await db.commit()
            return {"entry_id": int(entry_id), "api_calls": calls}

        result = await vectorize_pending(db, limit=limit)
        return result
    except LLMError as exc:
        await db.rollback()
        raise _map_llm_error(exc) from exc


# ---------------------------------------------------------------------------
# 用量统计
# ---------------------------------------------------------------------------
@router.get("/usage", summary="AI 调用量与 token 消耗汇总")
async def ai_usage(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    rows = await copilot.usage_summary(db, days=days)
    return {
        "days": days,
        "enabled": get_settings().ai_ready,
        "items": rows,
        "total_calls": sum(r["calls"] for r in rows),
        "total_tokens": sum(r["tokens_in"] + r["tokens_out"] for r in rows),
    }
