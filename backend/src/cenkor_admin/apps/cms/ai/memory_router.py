"""站点记忆与内容记忆的管理接口。

设计取向：**能看见 AI 吃了什么**比「AI 自动变聪明」更重要。
所以除了增删改查，还提供：
- `/memory/preview` —— 直接把「下次起草会注入的文本」原样打印出来
- 每条记忆的 `injection_count` —— 写了但从来轮不到注入的条目一眼可见
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms.ai import memory as mem
from cenkor_admin.apps.cms.ai.models import MEMORY_SCOPE_LABEL, MEMORY_SCOPES
from cenkor_admin.core.db import get_db
from cenkor_admin.core.llm import LLMError

router = APIRouter(tags=["cms-ai-memory"])


@router.get("/memory", summary="站点记忆列表 + 统计")
async def list_memory(
    status: str | None = Query(default=None, description="approved | pending | rejected"),
    scope: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    items = await mem.list_memory(db, status=status, scope=scope)
    return {
        "items": items,
        "stats": await mem.memory_stats(db),
        "scopes": [
            {"value": s, "label": MEMORY_SCOPE_LABEL.get(s, s)} for s in MEMORY_SCOPES
        ],
        "note": (
            "人工维护的记忆是硬事实，直接生效；AI 提炼的是软风格，默认待审。"
            "权重决定预算内谁先进提示词。"
        ),
    }


@router.post("/memory", summary="新增或更新一条站点记忆")
async def upsert_memory(
    body: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        row = await mem.upsert_memory(
            db,
            scope=str(body.get("scope") or "").strip(),
            content=str(body.get("content") or ""),
            key=str(body.get("key") or "").strip(),
            weight=int(body.get("weight") or 50),
            enabled=bool(body.get("enabled", True)),
            source=str(body.get("source") or "manual"),
            status=str(body.get("status") or "approved"),
            created_by=getattr(user, "id", None),
            memory_id=int(body["id"]) if body.get("id") else None,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "memory": row, "stats": await mem.memory_stats(db)}


@router.patch("/memory/{memory_id}", summary="审核 / 启停一条记忆")
async def patch_memory(
    memory_id: int,
    body: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    if "status" in body:
        try:
            row = await mem.set_memory_status(db, memory_id, str(body["status"]))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"ok": True, "memory": row, "stats": await mem.memory_stats(db)}

    if "enabled" in body:
        row = await db.get(mem.CmsAiMemory, memory_id)
        if row is None:
            raise HTTPException(404, "记忆不存在")
        row.enabled = bool(body["enabled"])
        await db.commit()
        await db.refresh(row)
        return {"ok": True, "memory": mem._row_out(row), "stats": await mem.memory_stats(db)}

    raise HTTPException(400, "请提供 status 或 enabled")


@router.delete("/memory/{memory_id}", summary="删除一条记忆")
async def delete_memory(
    memory_id: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    ok = await mem.delete_memory(db, memory_id)
    if not ok:
        raise HTTPException(404, "记忆不存在")
    return {"ok": True, "deleted": memory_id}


@router.get("/memory/preview", summary="预览下次起草会注入的记忆文本")
async def preview_memory(
    budget: int = Query(default=mem.DEFAULT_BUDGET, ge=200, le=8000),
    with_content: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """把实际注入的文本原样返回。

    为什么要这个接口：记忆配错了最难发现 —— AI 输出「怪怪的」，
    你不知道是提示词问题还是记忆里有一条相反的指令。能直接看见原文，
    排查从「猜」变成「读」。
    """
    block, meta = await mem.render_prompt_block(
        db, budget=budget, with_content_memory=with_content, count_hits=False
    )
    return {"block": block, **meta}


# ---------------------------------------------------------------- 内容记忆


@router.get("/memory/digests", summary="内容记忆（已发布内容的摘要索引）")
async def list_digests(
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "items": await mem.recent_digests(db, limit=limit),
        "stats": await mem.memory_stats(db),
    }


@router.post("/memory/digests/rebuild", summary="重建内容记忆索引")
async def rebuild_digests(
    limit: int = Query(default=30, ge=1, le=200),
    force: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """为已发布内容生成 120 字摘要 + 话题。

    正文改过会自动重做 —— 旧摘要是**错误的记忆**，比没有记忆更糟。
    """
    try:
        result = await mem.digest_entries(db, limit=limit, force=force)
    except LLMError as exc:
        raise HTTPException(503, f"AI 服务不可用：{exc}") from exc
    return {"ok": True, **result, "stats": await mem.memory_stats(db)}


@router.post("/memory/distill", summary="AI 提炼本站写作风格（写入待审）")
async def distill(
    sample: int = Query(default=12, ge=3, le=40),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        result = await mem.distill_style(db, sample=sample)
    except LLMError as exc:
        raise HTTPException(503, f"AI 服务不可用：{exc}") from exc
    return {**result, "stats": await mem.memory_stats(db)}


# ---------------------------------------------------------------- 会话记忆
# 会话记忆按「一篇内容的完整 AI 流水线」组织（起草 → 改写 → SEO → 翻译 → 再分发），
# 不是按聊天窗口。所以这里没有「新建会话」接口 —— 会话由业务动作自动产生，
# 人在这里只能看、加备注、删错记。


@router.get("/sessions", summary="会话记忆列表")
async def list_sessions(
    limit: int = Query(default=50, ge=1, le=200),
    keyword: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    from cenkor_admin.apps.cms.ai import session_memory as sess_mem

    return {
        "items": await sess_mem.list_sessions(db, limit=limit, keyword=keyword),
        "stats": await sess_mem.session_stats(db),
    }


@router.get("/sessions/{session_id}", summary="会话记忆详情（完整时间线）")
async def get_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    from cenkor_admin.apps.cms.ai import session_memory as sess_mem

    detail = await sess_mem.get_session_detail(db, session_id)
    if detail is None:
        raise HTTPException(404, "会话不存在")
    return detail


@router.post("/sessions/{session_id}/notes", summary="给会话加一条人工备注（下轮原样注入）")
async def add_session_note(
    session_id: int,
    content: str = Body(..., embed=True, min_length=1, max_length=1000),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """人工备注是会话记忆里唯一「说了就一定生效」的部分。

    AI 提炼的产出要点是二手信息，会跑偏；人写的「这篇不要提竞品参数」
    是一手指令，必须原样带进提示词。
    """
    from cenkor_admin.apps.cms.ai import session_memory as sess_mem

    detail = await sess_mem.get_session_detail(db, session_id)
    if detail is None:
        raise HTTPException(404, "会话不存在")
    entry_id = detail.get("entry_id")
    if not entry_id:
        raise HTTPException(400, "该会话没有关联条目，无法写入备注")
    await sess_mem.add_turn(
        db, int(entry_id),
        kind="note", content=content.strip(), role="user",
        created_by=getattr(user, "id", None),
    )
    return {"ok": True, "session": await sess_mem.get_session_detail(db, session_id)}


@router.delete("/sessions/{session_id}", summary="删除一个会话（连同其时间线）")
async def delete_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    from cenkor_admin.apps.cms.ai import session_memory as sess_mem

    ok = await sess_mem.delete_session(db, session_id)
    if not ok:
        raise HTTPException(404, "会话不存在")
    return {"ok": True}


@router.delete("/sessions/turns/{turn_id}", summary="删除会话里的一条记录")
async def delete_turn(
    turn_id: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    from cenkor_admin.apps.cms.ai import session_memory as sess_mem

    ok = await sess_mem.delete_turn(db, turn_id)
    if not ok:
        raise HTTPException(404, "记录不存在")
    return {"ok": True}
