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

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms.ai import copilot
from cenkor_admin.apps.cms.ai import ingest as ingest_mod
from cenkor_admin.apps.cms.ai import pricing
from cenkor_admin.apps.cms.ai.models import CmsAiPrice
from cenkor_admin.apps.cms.ai.admin_router import router as admin_router
from cenkor_admin.apps.cms.ai.prompt_router import router as prompt_router
from cenkor_admin.apps.cms.ai.batch_router import router as batch_router
from cenkor_admin.apps.cms.ai.dashboard import router as dashboard_router
from cenkor_admin.apps.cms.ai.content_health import entry_health, site_health
from cenkor_admin.apps.cms.ai.embedding import vectorize_entry, vectorize_pending
from cenkor_admin.apps.cms.ai.internal_link import suggest_links
from cenkor_admin.apps.cms.ai.redistribute import CHANNELS, channels_meta, redistribute_entry
from cenkor_admin.apps.cms.ai.schema_impact import content_type_impact, field_impact
from cenkor_admin.apps.cms.ai.search import semantic_search, similar_entries
from cenkor_admin.apps.cms.models import Entry
from cenkor_admin.core.db import get_db
from cenkor_admin.core.llm import LLMError, LLMNotConfiguredError, LLMUnsupportedError
from cenkor_admin.core.site_scope import current_site_id

router = APIRouter(prefix="/ai", tags=["cms-ai"])

# 配置管理（服务商 / 能力绑定 / 连通性测试）拆独立模块，
# 本文件只保留「用 AI 干活」的端点，避免一个文件越滚越大。
router.include_router(admin_router)
# 提示词版本化：改一句话不用发版重启
router.include_router(prompt_router)
# 批量生产队列：一次起草 N 篇，逐篇落草稿
router.include_router(batch_router)
# 驾驶舱放最后：它要在所有能力端点注册完之后才能枚举 registry
router.include_router(dashboard_router)


async def _require_ai(db: AsyncSession) -> None:
    """判定 AI 是否可用，以**实际生效的配置**为准。

    不能用 ``settings.ai_ready`` —— 那只看 ``.env``（AI_ENABLED + AI_API_KEY）。
    后台「AI 设置」里绑好服务商与模型后，registry 里已有可用端点，
    但 .env 仍可能是空的，按 .env 判会把配好的 AI 误报成未启用。
    registry.load 在 TTL 内直接返回缓存，每请求调用零开销。
    """
    from cenkor_admin.apps.cms.ai import registry as ai_registry

    reg = await ai_registry.load(db)
    if reg.endpoint("chat") is None:
        reason = reg.last_error or "未绑定对话服务商"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI 未配置（{reason}）：请在后台「AI 设置」里绑定服务商与模型",
        )


def _map_llm_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LLMNotConfiguredError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, LLMUnsupportedError):
        # 服务商拒绝的是「请求本身」，不是服务故障。给运营看原始 JSON 没用，
        # 要说清是模型不支持还是套餐不含 —— 两者的解法完全不同。
        return HTTPException(status_code=400, detail=_explain_unsupported(str(exc)))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=502, detail=f"AI 服务调用失败：{exc}")


def _explain_unsupported(raw: str) -> str:
    """把服务商的拒绝原因翻译成人能看懂的话。

    服务商返回的是 `{"error":{"code":"UnsupportedModel","message":"..."}}`，
    直接透传给运营等于让他看英文 JSON。这里按 code 归类，给出「去改什么」的
    明确指引 —— 运营看到提示要知道下一步做什么，而不是只知道失败了。
    """
    text = raw or ""
    lowered = text.lower()
    if "unsupportedmodel" in lowered or "does not support" in lowered:
        return (
            "当前绑定的模型不支持这个能力（服务商返回 UnsupportedModel）。"
            "请在后台「AI 设置」里把该能力改绑到服务商支持的模型"
            "（视频生成通常要用 Seedance 系列，且账号套餐需包含视频能力）。"
        )
    if "not support the agent plan" in lowered:
        return (
            "当前服务商套餐不包含该能力。请在后台「AI 设置」里改绑到支持该能力的"
            "服务商，或升级该服务商的套餐。"
        )
    if "authentication" in lowered or "invalid" in lowered and "key" in lowered:
        return "AI 服务商密钥无效或已失效，请检查后台「AI 设置」里的密钥。"
    if "quota" in lowered or "rate limit" in lowered or "429" in lowered:
        return "AI 服务商配额已用尽或触发限流，请等待配额重置或升级套餐。"
    if "accessdenied" in lowered or "forbidden" in lowered or "403" in lowered:
        return "AI 服务商拒绝了本次调用：没有该模型的权限。请检查账号权限或改绑模型。"
    return f"AI 服务商拒绝了本次调用：{text[:300]}"


# ---------------------------------------------------------------------------
# 对话式建模
# ---------------------------------------------------------------------------
@router.post("/content-types/propose", summary="自然语言生成内容类型草案")
async def propose_content_type(
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    await _require_ai(db)
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
    await _require_ai(db)
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
# 素材直入：附件 → 文本（再交给下面的起草链路）
# ---------------------------------------------------------------------------
_MAX_FILES = 5
_INGEST_TIMEOUT = 180  # 单文件：视频抽帧 + vision 识别最长给 3 分钟


@router.post("/ingest/extract", summary="解析上传素材为文本（PDF/Word/Excel/图片/视频/文本）")
async def ingest_extract(
    files: list[UploadFile] = File(..., description="最多 5 个，单个 ≤ 20MB"),
    note: str = Form(default="", description="用户补充说明，会放在 brief 最前面"),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """只做解析，不生成内容。

    前端把返回的 ``brief`` 填进素材框（用户可继续编辑/裁剪），再走
    ``POST /ai/entries/draft/stream``。这样起草链路一行不改，
    素材解析也能单独调试。
    """
    await _require_ai(db)
    if not files:
        raise HTTPException(status_code=400, detail="没有上传文件")
    if len(files) > _MAX_FILES:
        raise HTTPException(status_code=400, detail=f"一次最多 {_MAX_FILES} 个文件")

    started = time.monotonic()
    results: list[ingest_mod.ExtractResult] = []
    failures: list[dict[str, str]] = []

    for f in files:
        name = f.filename or "未命名"
        try:
            data = await f.read()
            r = await asyncio.wait_for(
                ingest_mod.extract_attachment(db, data, name, created_by=user.id),
                timeout=_INGEST_TIMEOUT,
            )
            results.append(r)
            await db.commit()  # 逐个提交，保住已成功文件的识别记账
        except asyncio.TimeoutError:
            await db.rollback()
            failures.append({"filename": name, "error": f"解析超时（>{_INGEST_TIMEOUT}s）"})
        except Exception as exc:  # noqa: BLE001 —— 单文件失败不该毁掉整批
            await db.rollback()
            failures.append({"filename": name, "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
        finally:
            await f.close()

    if not results and failures:
        raise HTTPException(status_code=400, detail=failures[0]["error"])

    brief = ingest_mod.build_brief(results, note)
    return {
        "results": [r.to_dict() for r in results],
        "failures": failures,
        "brief": brief,
        "chars": len(brief),
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }


# ---------------------------------------------------------------------------
# AI 起草
# ---------------------------------------------------------------------------
@router.post("/entries/draft", summary="根据素材生成条目草稿（不落库）")
async def draft_entry(
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    await _require_ai(db)
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


@router.post("/entries/draft/stream", summary="流式起草（SSE：meta/delta/extra/done/error）")
async def draft_entry_stream(
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> StreamingResponse:
    """起草流式版：正文 token 边生成边推，告别 45s 白屏。

    SSE 事件序：meta(标题/别名) → delta*(正文) → extra(摘要/字段/SEO) →
    done(完整草稿，与 POST /entries/draft 响应同构) ；失败 error 事件。
    done 里带 _generation_id，前端原样传给 /entries/draft/save 即可保持溯源。
    """
    await _require_ai(db)
    ct_id = body.get("content_type_id")
    brief = str(body.get("brief") or "").strip()
    if not ct_id or not brief:
        raise HTTPException(status_code=400, detail="需要 content_type_id 与 brief")

    async def gen():
        try:
            async for ev, payload in copilot.draft_entry_stream(
                db,
                int(ct_id),
                brief,
                created_by=user.id,
                lang=str(body.get("lang") or "zh-CN"),
            ):
                yield f"event: {ev}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001
            # copilot 内部已兜底；这里是最后一道防线，绝不让连接静默断掉
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001
                pass
            detail = str(exc)[:300] or "AI 服务调用失败"
            yield f"event: error\ndata: {json.dumps({'detail': detail}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx 别缓冲 SSE
        },
    )


@router.post("/entries/draft/save", summary="把草稿落库为条目（强制 draft 状态）")
async def save_draft(
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    await _require_ai(db)
    try:
        entry = await copilot.create_entry_from_draft(db, body, created_by=user.id)
        return {"entry_id": entry.id, "status": entry.status, "title": entry.title}
    except Exception as exc:
        await db.rollback()
        raise _map_llm_error(exc) from exc


@router.get(
    "/entries/{entry_id}/link-suggestions",
    summary="内链建议：找出这篇文章该互链的其它内容",
)
async def entry_link_suggestions(
    entry_id: int,
    max_links: int = Query(default=3, ge=1, le=10),
    candidates: int = Query(default=8, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """内链建议：向量召回候选 + LLM 精选，返回锚文本与插入位置。

    只给建议不自动插入 —— 机器觉得相关不等于读者想点，锚文本也不该由机器定。
    """
    await _require_ai(db)
    entry = await _load_entry(db, entry_id)
    try:
        return await suggest_links(
            db,
            entry,
            created_by=user.id,
            max_links=max_links,
            candidates=candidates,
        )
    except Exception as exc:
        raise _map_llm_error(exc) from exc


@router.get(
    "/schema/field-impact",
    summary="模型变更影响分析：改/删字段前算清会炸多少条已发布内容",
)
async def schema_field_impact(
    content_type_id: int = Query(..., description="内容类型 id"),
    field_key: str = Query(..., description="字段 key"),
    target_field_type: str | None = Query(
        default=None, description="拟改成的目标类型；不传表示「删除该字段」"
    ),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """改字段类型 / 删字段之前，先看清影响面。

    **不调用任何 LLM** —— 纯 SQL 统计 + 类型兼容性判定，所以 AI 未配置也能用。
    兼容性判定复用项目自己的 `validate_field_value`，规则变了这里自动跟着变。
    """
    result = await field_impact(
        db, content_type_id, field_key, target_field_type=target_field_type
    )
    if not result.get("found"):
        raise HTTPException(status_code=404, detail=result.get("reason") or "字段定义不存在")
    return result


@router.get(
    "/schema/content-type-impact",
    summary="模型变更影响分析：整个内容类型的字段影响全景",
)
async def schema_content_type_impact(
    content_type_id: int = Query(..., description="内容类型 id"),
    target_field_type: str | None = Query(default=None, description="拟改成的目标类型"),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """逐字段列出影响面 —— 改 schema 前的总览。同样零 LLM 调用。"""
    return await content_type_impact(
        db, content_type_id, target_field_type=target_field_type
    )


@router.get("/health/report", summary="内容健康度体检：全站问题清单")
async def health_report(
    include_drafts: bool = Query(default=False, description="是否把草稿也纳入体检"),
    limit: int = Query(default=100, ge=1, le=500, description="问题条目明细返回条数"),
    stale_days: int = Query(default=365, ge=30, le=3650, description="多少天未更新算陈旧"),
    thin_chars: int = Query(default=300, ge=50, le=5000, description="正文低于多少字算过薄"),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """七项体检一次算完：过期 / 死链 / 过薄 / SEO 短板 / 孤岛 / 缺图 / 陈旧。

    **零 LLM 调用** —— 纯 SQL + 正则 + 内存分析，AI 未配置也能用。

    分数口径：每条 100 分起扣，站点分 = 各条均值。扫描全站，
    `limit` 只影响明细返回条数（否则分数会随分页漂移，同一站点两次刷新不一致）。
    """
    sid = current_site_id() or 1
    return await site_health(
        db,
        sid,
        include_drafts=include_drafts,
        limit=limit,
        stale_days=stale_days,
        thin_chars=thin_chars,
    )


@router.get("/health/entries/{entry_id}", summary="内容健康度体检：单条明细")
async def health_entry(
    entry_id: int,
    stale_days: int = Query(default=365, ge=30, le=3650),
    thin_chars: int = Query(default=300, ge=50, le=5000),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """单条体检。入度统计取同站点全量已发布条目，避免「局部图谱」误判孤儿。"""
    result = await entry_health(db, entry_id, stale_days=stale_days, thin_chars=thin_chars)
    if result is None:
        raise HTTPException(status_code=404, detail="条目不存在")
    return result


@router.post("/entries/dedup", summary="草稿查重：检测与已有内容是否高度重复")
async def dedup_draft(
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """保存/批量起草前调用：给定标题+正文，返回相似命中。

    命中 is_duplicate=True（score >= threshold，默认 0.8）即视为重复，前端据此预警。
    """
    await _require_ai(db)
    title = str(body.get("title") or "").strip()
    content = body.get("content") or {}
    if not title and not content:
        raise HTTPException(status_code=400, detail="需要 title 或 content")
    threshold = float(body.get("threshold") or 0.8)
    try:
        dups = await copilot.detect_duplicates(
            db,
            title,
            content,
            content_type_id=body.get("content_type_id"),
            content_type_key=body.get("content_type_key"),
            threshold=threshold,
            limit=int(body.get("limit") or 5),
        )
    except Exception as exc:
        raise _map_llm_error(exc) from exc
    top = max((d["score"] for d in dups), default=0.0)
    return {
        "duplicates": dups,
        "has_duplicate": any(d["is_duplicate"] for d in dups),
        "top_score": top,
        "threshold": threshold,
    }


@router.post("/entries/{entry_id}/auto-tag", summary="AI 自动打标签（手动补打/重打）")
async def auto_tag_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """给已有条目补打标签：LLM 优先复用标签池，最多新建 3 个；加法式不动已有标签。

    AI 落库的条目会自动打标（后台任务）；这个端点给老条目/人工条目手动用。
    """
    await _require_ai(db)
    entry = await _load_entry(db, entry_id)
    try:
        info = await copilot.auto_tag_entry(db, entry, created_by=user.id)
    except Exception as exc:
        await db.rollback()
        raise _map_llm_error(exc) from exc
    return info


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


@router.get("/redistribute/channels", summary="多渠道再分发：支持的渠道与限额")
async def redistribute_channels(
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """渠道清单。纯静态元数据，不需要 AI 配置。"""
    return {"channels": channels_meta()}


@router.post("/entries/{entry_id}/redistribute", summary="多渠道再分发：长文改写成渠道体裁")
async def redistribute(
    entry_id: int,
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """把条目改写成指定渠道体裁，**只返回文本不推送平台**。

    平台发布需要各家的凭据与合规授权，且自动发布有明显封号风险，
    因此这一步只做「改写 + 产出可复制成品」，发布动作留给人。
    """
    channel = str(body.get("channel") or "").strip()
    if channel not in CHANNELS:
        raise HTTPException(
            status_code=400,
            detail=f"channel 无效，可选：{'/'.join(CHANNELS)}",
        )
    await _require_ai(db)
    entry = await _load_entry(db, entry_id)
    try:
        result = await redistribute_entry(
            db,
            entry,
            channel=channel,
            lang=str(body.get("lang") or "zh-CN"),
            created_by=user.id,
        )
        await db.commit()
        return result
    except Exception as exc:
        await db.rollback()
        raise _map_llm_error(exc) from exc


@router.post("/entries/{entry_id}/translate", summary="AI 翻译条目到多语言")
async def translate_entry(
    entry_id: int,
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    await _require_ai(db)
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
    await _require_ai(db)
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
    await _require_ai(db)
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
    await _require_ai(db)
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
    await _require_ai(db)
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
    await _require_ai(db)
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
# 用量统计与单价
# ---------------------------------------------------------------------------
@router.get("/usage", summary="AI 调用量、token 消耗与折算金额")
async def ai_usage(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    from cenkor_admin.apps.cms.ai import registry as ai_registry

    summary = await pricing.usage_summary(db, days=days)
    reg = await ai_registry.load(db)
    return {
        "days": days,
        "enabled": reg.endpoint("chat") is not None,
        "embed_ready": reg.endpoint("embedding") is not None,
        **summary,
    }


def _price_out(row: CmsAiPrice) -> dict[str, Any]:
    return {
        "id": row.id,
        "provider": row.provider or "",
        "model": row.model or "",
        "kind": row.kind or "",
        "unit": row.unit or "token",
        "input_per_m": float(row.input_per_m or 0),
        "output_per_m": float(row.output_per_m or 0),
        "currency": row.currency or "CNY",
        "enabled": bool(row.enabled),
        "note": row.note or "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/prices", summary="AI 单价配置列表")
async def list_prices(
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    rows = (
        (
            await db.execute(
                select(CmsAiPrice).order_by(
                    CmsAiPrice.kind, CmsAiPrice.provider, CmsAiPrice.model, CmsAiPrice.id
                )
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [_price_out(r) for r in rows],
        # 下拉候选用库里真实出现过的业务功能，避免手打错字导致规则永远匹配不上
        "kinds": await pricing.distinct_kinds(db),
        "units": list(pricing.UNITS),
        "note": "单价按每百万 token 计。留空 provider/model/kind 表示任意匹配，精确维度越多越优先。",
    }


@router.put("/prices", summary="新增或更新一条 AI 单价")
async def upsert_price(
    body: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    provider = str(body.get("provider") or "").strip()
    model = str(body.get("model") or "").strip()
    kind = str(body.get("kind") or "").strip()
    if provider == "" and model == "" and kind == "":
        # 全通配规则会把所有调用套上同一个单价，等于「假装算过」
        raise HTTPException(400, "服务商和模型不能都留空，至少指定一个")
    if len(kind) > pricing.MAX_KIND_LEN:
        raise HTTPException(400, f"能力类型过长（≤{pricing.MAX_KIND_LEN} 字符）")
    unit = str(body.get("unit") or "token").strip()
    if unit not in pricing.UNITS:
        raise HTTPException(400, f"计价单位非法：{unit}，可选 {pricing.UNITS}")

    try:
        input_per_m = float(body.get("input_per_m") or 0)
        output_per_m = float(body.get("output_per_m") or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "单价必须是数字") from exc
    if input_per_m < 0 or output_per_m < 0:
        raise HTTPException(400, "单价不能为负")
    if input_per_m == 0 and output_per_m == 0:
        # 全 0 的规则会让金额恒为 0，看起来像「已经算了」其实没算，不如直接拒绝
        raise HTTPException(400, "至少填一个非零单价，否则金额恒为 0")

    row = (
        await db.execute(
            select(CmsAiPrice).where(
                CmsAiPrice.provider == provider,
                CmsAiPrice.model == model,
                CmsAiPrice.kind == kind,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = CmsAiPrice(provider=provider, model=model, kind=kind)
        db.add(row)

    row.unit = unit
    row.input_per_m = input_per_m
    # 按张计价没有「输出」的概念，强制归零，避免页面显示一个永远不参与计算的数
    row.output_per_m = 0 if unit == "image" else output_per_m
    row.currency = str(body.get("currency") or "CNY").strip()[:8] or "CNY"
    row.enabled = bool(body.get("enabled", True))
    row.note = str(body.get("note") or "").strip()[:200]
    await db.commit()
    await db.refresh(row)
    return {"ok": True, "price": _price_out(row)}


@router.delete("/prices/{pid}", summary="删除一条 AI 单价")
async def delete_price(
    pid: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    row = await db.get(CmsAiPrice, pid)
    if row is None:
        raise HTTPException(404, "单价规则不存在")
    await db.delete(row)
    await db.commit()
    return {"ok": True, "deleted": pid}


# ---------------------------------------------------------------------------
# 问答式站内搜索
# ---------------------------------------------------------------------------
@router.post("/ask", summary="问答式检索：带引用的作答（后台自查用）")
async def ai_ask(
    body: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """与公开端点 `/public/ask` 同一套逻辑。

    后台单独留一个口子，是因为运营需要**在发布前**确认「访客这么问，我们能答上来吗」——
    对外端只看得到已发布内容，这个口子可以带上草稿自测。
    """
    from cenkor_admin.apps.cms.ai import qa_search

    question = str(body.get("question") or body.get("q") or "").strip()
    if not question:
        raise HTTPException(400, "question 不能为空")
    if len(question) > 500:
        raise HTTPException(400, "问题过长（上限 500 字）")

    ct_id = body.get("content_type_id")
    ct_key = (str(body.get("content_type_key")) if body.get("content_type_key") else None)
    top_k = int(body.get("top_k") or 5)
    if ct_key and not ct_id:
        from cenkor_admin.apps.cms.models import ContentType

        ct_id = (
            await db.execute(select(ContentType.id).where(ContentType.key == ct_key))
        ).scalar()
        if ct_id is None:
            raise HTTPException(404, f"内容类型不存在: {ct_key}")

    try:
        return await qa_search.ask(
            db,
            question,
            content_type_id=int(ct_id) if ct_id else None,
            top_k=max(1, min(top_k, 20)),
            created_by=user.id,
        )
    except Exception as exc:
        await db.rollback()
        raise _map_llm_error(exc) from exc


# ---------------------------------------------------------------------------
# 选题 Gap 分析
# ---------------------------------------------------------------------------
@router.get("/topic-gaps", summary="选题缺口分析：已有 vs 该有")
async def ai_topic_gaps(
    content_type_key: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    from cenkor_admin.apps.cms.ai import topic_gap

    await _require_ai(db)
    if content_type_key:
        from cenkor_admin.apps.cms.models import ContentType

        exists = (
            await db.execute(select(ContentType.id).where(ContentType.key == content_type_key))
        ).scalar()
        if exists is None:
            raise HTTPException(404, f"内容类型不存在: {content_type_key}")
    try:
        return await topic_gap.analyze(
            db, content_type_key=content_type_key, limit=limit, created_by=user.id
        )
    except Exception as exc:
        await db.rollback()
        raise _map_llm_error(exc) from exc


# ---------------------------------------------------------------------------
# 抽样质检与模型 A/B
# ---------------------------------------------------------------------------
@router.get("/quality/samples", summary="随机抽 AI 产出，供人打分")
async def ai_quality_samples(
    size: int = Query(default=5, ge=1, le=20),
    days: int = Query(default=90, ge=1, le=3650),
    content_type_id: int | None = Query(default=None),
    include_reviewed: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    from cenkor_admin.apps.cms.ai import quality

    return await quality.sample_entries(
        db,
        size=size,
        days=days,
        content_type_id=content_type_id,
        include_reviewed=include_reviewed,
        site_id=current_site_id(),
    )


@router.post("/quality/reviews", summary="提交一条质检打分")
async def ai_quality_review(
    body: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    from cenkor_admin.apps.cms.ai import quality
    from cenkor_admin.apps.cms.models import Entry

    entry_id = body.get("entry_id")
    if not entry_id:
        raise HTTPException(400, "entry_id 不能为空")
    # 先查一次再打分：条目不存在是 404，不是「参数错了」（400 会让人去查请求体）
    if await db.get(Entry, int(entry_id)) is None:
        raise HTTPException(404, f"条目不存在：{entry_id}")

    try:
        return await quality.submit_review(
            db,
            entry_id=int(entry_id),
            scores=body.get("scores") or {},
            verdict=str(body.get("verdict") or "pass"),
            note=str(body.get("note") or ""),
            reviewer_id=user.id,
            site_id=current_site_id(),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/quality/stats", summary="质量曲线 / 模型对比 / 覆盖率")
async def ai_quality_stats(
    weeks: int = Query(default=12, ge=1, le=52),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    from cenkor_admin.apps.cms.ai import quality

    return await quality.stats(db, weeks=weeks, site_id=current_site_id())


@router.post("/quality/ab", summary="模型 A/B：同题两版，盲评前不揭晓模型名")
async def ai_quality_ab_run(
    body: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    from cenkor_admin.apps.cms.ai import quality

    await _require_ai(db)
    try:
        return await quality.run_ab(
            db,
            topic=str(body.get("topic") or ""),
            model_a=str(body.get("model_a") or ""),
            model_b=str(body.get("model_b") or ""),
            max_tokens=int(body.get("max_tokens") or 3000),
            created_by=user.id,
            site_id=current_site_id(),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        raise _map_llm_error(exc) from exc


@router.post("/quality/ab/{run_id}/review", summary="提交 A/B 盲评结论并揭晓模型")
async def ai_quality_ab_review(
    run_id: int,
    body: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    from cenkor_admin.apps.cms.ai import quality

    try:
        return await quality.review_ab(
            db,
            run_id=run_id,
            winner=str(body.get("winner") or ""),
            note=str(body.get("note") or ""),
            reviewer_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/quality/ab", summary="A/B 历史（未评的保持盲态）")
async def ai_quality_ab_list(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    from cenkor_admin.apps.cms.ai import quality

    return await quality.list_ab_runs(db, limit=limit, site_id=current_site_id())


@router.get("/quality/ab/{run_id}", summary="单条 A/B 详情（未评时不含模型名）")
async def ai_quality_ab_detail(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    from cenkor_admin.apps.cms.ai import quality

    try:
        return await quality.get_ab_run(db, run_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


# ---------------------------------------------------------------------------
# AI 配图
# ---------------------------------------------------------------------------
@router.get("/illustration/options", summary="配图可选的比例与风格")
async def ai_illustration_options(
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    from cenkor_admin.apps.cms.ai import illustration

    return illustration.options_meta()


@router.post("/entries/{entry_id}/illustration", summary="按正文语义生成配图并落媒体库")
async def ai_entry_illustration(
    entry_id: int,
    body: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    from cenkor_admin.apps.cms.ai import illustration

    entry = await db.get(Entry, entry_id)
    if entry is None or entry.deleted_at is not None:
        raise HTTPException(404, f"条目不存在：{entry_id}")

    try:
        return await illustration.generate_for_entry(
            db,
            entry,
            hint=str(body.get("hint") or ""),
            style=str(body.get("style") or "photo"),
            aspect=str(body.get("aspect") or "wide"),
            apply=str(body.get("apply") or "none"),
            created_by=user.id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        raise _map_llm_error(exc) from exc


@router.post("/media/{media_id}/attach", summary="把已有媒体挂到条目（og_image / 正文首图）")
async def ai_media_attach(
    media_id: int,
    body: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    from cenkor_admin.apps.cms.ai import illustration
    from cenkor_admin.apps.cms.models import Media

    entry_id = body.get("entry_id")
    if not entry_id:
        raise HTTPException(400, "entry_id 不能为空")
    entry = await db.get(Entry, int(entry_id))
    if entry is None or entry.deleted_at is not None:
        raise HTTPException(404, f"条目不存在：{entry_id}")
    media = await db.get(Media, media_id)
    if media is None:
        raise HTTPException(404, f"媒体不存在：{media_id}")

    try:
        applied = await illustration.attach_media(
            db, entry, media, mode=str(body.get("mode") or "og_image")
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"entry_id": entry.id, "media_id": media.id, "applied": applied, "url": media.url}


# ---------------------------------------------------------------------------
# AI 视频
# ---------------------------------------------------------------------------
@router.get("/video/options", summary="视频可选的比例、时长与模式")
async def ai_video_options(
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    from cenkor_admin.apps.cms.ai import video

    return video.options_meta()


@router.post("/entries/{entry_id}/video", summary="提交视频生成任务（异步，立刻返回任务号）")
async def ai_entry_video(
    entry_id: int,
    body: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """提交后立刻返回，不等产物。

    真等 5 分钟的话，nginx `proxy_read_timeout` 60 秒就把连接掐了，
    用户看到的是 504 而不是「生成中」。所以这里只负责提交，进度靠轮询。
    """
    from cenkor_admin.apps.cms.ai import video

    entry = await db.get(Entry, entry_id)
    if entry is None or entry.deleted_at is not None:
        raise HTTPException(404, f"条目不存在：{entry_id}")

    try:
        job = await video.submit(
            db,
            entry,
            mode=str(body.get("mode") or "t2v"),
            source_media_id=body.get("source_media_id"),
            ratio=str(body.get("ratio") or "16:9"),
            duration=int(body.get("duration") or 5),
            hint=str(body.get("hint") or ""),
            prompt=str(body.get("prompt") or ""),
            created_by=user.id,
        )
        return await video.job_to_dict(db, job)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        raise _map_llm_error(exc) from exc


@router.get("/video/jobs/{job_id}", summary="查询视频任务进度（顺便推进一次状态）")
async def ai_video_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    from cenkor_admin.apps.cms.ai import video
    from cenkor_admin.apps.cms.ai.models import CmsAiVideoJob

    job = await db.get(CmsAiVideoJob, job_id)
    if job is None:
        raise HTTPException(404, f"任务不存在：{job_id}")
    # 后台协程丢了（进程重启）时，这里能把状态追回来
    job = await video.refresh(db, job)
    return await video.job_to_dict(db, job)


@router.get("/video/jobs", summary="视频任务列表（按条目或全局）")
async def ai_video_jobs(
    entry_id: int | None = None,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    from cenkor_admin.apps.cms.ai import video

    jobs = await video.list_jobs(db, entry_id=entry_id, limit=limit)
    return {"items": [await video.job_to_dict(db, j) for j in jobs]}


@router.post("/video/jobs/{job_id}/attach", summary="把已完成的视频挂到条目")
async def ai_video_attach(
    job_id: int,
    body: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    from cenkor_admin.apps.cms.ai import video
    from cenkor_admin.apps.cms.ai.models import CmsAiVideoJob

    job = await db.get(CmsAiVideoJob, job_id)
    if job is None:
        raise HTTPException(404, f"任务不存在：{job_id}")
    job = await video.refresh(db, job)
    entry_id = body.get("entry_id") or job.entry_id
    if not entry_id:
        raise HTTPException(400, "entry_id 不能为空")
    entry = await db.get(Entry, int(entry_id))
    if entry is None or entry.deleted_at is not None:
        raise HTTPException(404, f"条目不存在：{entry_id}")
    try:
        applied = await video.attach_video(
            db, entry, job, mode=str(body.get("mode") or "body_head")
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "entry_id": entry.id,
        "job_id": job.id,
        "applied": applied,
        "cover_url": (await video.job_to_dict(db, job)).get("cover_url"),
    }


@router.get("/quality/models", summary="A/B 候选模型（来自当前对话服务商）")
async def ai_quality_models(
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    from cenkor_admin.apps.cms.ai import quality

    await _require_ai(db)
    return await quality.list_models(db)
