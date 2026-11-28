"""建站方案 API：草稿 → 确认 → 预览差异 → 执行。"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms import site_plan_service as svc
from cenkor_admin.apps.cms.site_plan_models import SitePlan, SitePlanItem
from cenkor_admin.core.db import get_db
from cenkor_admin.core.site_scope import require_site_id

router = APIRouter(prefix="/site-plans", tags=["cms-site-plans"])


class DraftIn(BaseModel):
    brief: str = Field(min_length=2, max_length=3000)
    keywords: list[str] = Field(default_factory=list)
    category_count: int = Field(default=6, ge=1, le=svc.MAX_CATEGORIES)
    article_count: int = Field(default=12, ge=1, le=svc.MAX_ARTICLES)
    content_type_id: int | None = None
    lang: str = Field(default="zh-CN", max_length=20)


class CreatePlanIn(DraftIn):
    plan: dict[str, Any]


def _out(p: SitePlan) -> dict[str, Any]:
    data = p.plan_json or {}
    return {
        "id": p.id,
        "site_id": p.site_id,
        "status": p.status,
        "summary": p.summary,
        "content_type_id": p.content_type_id,
        "lang": p.lang,
        "batch_job_id": p.batch_job_id,
        "categories": len(data.get("categories") or []),
        "articles": len(data.get("articles") or []),
        "error": p.error,
        "created_at": p.created_at,
        "confirmed_at": p.confirmed_at,
        "finished_at": p.finished_at,
    }


async def _get_or_404(db: AsyncSession, plan_id: int) -> SitePlan:
    plan = await db.get(SitePlan, plan_id)
    if plan is None:
        raise HTTPException(404, "方案不存在")
    return plan


@router.post("/draft", summary="一句话需求 → 方案（不落库）")
async def draft(
    body: DraftIn,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    require_site_id()
    try:
        plan, warnings, ct = await svc.build_plan(
            db,
            brief=body.brief,
            keywords=body.keywords,
            category_count=body.category_count,
            article_count=body.article_count,
            content_type_id=body.content_type_id,
            lang=body.lang,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {
        "plan": plan,
        "warnings": warnings,
        "content_type": {"id": ct.id, "key": ct.key, "name": ct.name},
    }


@router.post("", status_code=201, summary="把确认前的方案落库（draft 状态）")
async def create_plan(
    body: CreatePlanIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    site_id = require_site_id()
    try:
        plan, warnings = svc.normalize_plan(
            body.plan,
            max_categories=body.category_count,
            max_articles=body.article_count,
        )
        ct = await svc.resolve_content_type(db, body.content_type_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    row = SitePlan(
        site_id=site_id,
        brief={
            "brief": body.brief,
            "keywords": body.keywords,
            "category_count": body.category_count,
            "article_count": body.article_count,
            "lang": body.lang,
        },
        plan_json=plan,
        status="draft",
        content_type_id=ct.id,
        lang=body.lang,
        summary=plan.get("summary"),
        created_by=getattr(user, "id", None),
    )
    db.add(row)
    await db.flush()

    for item in svc.plan_items(plan):
        db.add(
            SitePlanItem(
                plan_id=row.id,
                site_id=site_id,
                seq=item["seq"],
                kind=item["kind"],
                parent_key=item["parent_key"],
                payload=item["payload"],
                status="pending",
            )
        )
    await db.commit()
    await db.refresh(row)
    return {"plan": _out(row), "warnings": warnings}


@router.get("", summary="方案列表")
async def list_plans(
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(select(SitePlan).order_by(SitePlan.id.desc()).limit(50))
    ).scalars().all()
    return [_out(r) for r in rows]


@router.get("/{plan_id}", summary="方案详情（含完整 JSON）")
async def get_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    plan = await _get_or_404(db, plan_id)
    return {"plan": _out(plan), "plan_json": plan.plan_json}


@router.get("/{plan_id}/items", summary="方案的待办清单与执行结果")
async def get_items(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    await _get_or_404(db, plan_id)
    rows = (
        await db.execute(
            select(SitePlanItem)
            .where(SitePlanItem.plan_id == plan_id)
            .order_by(SitePlanItem.seq)
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "seq": r.seq,
            "kind": r.kind,
            "parent_key": r.parent_key,
            "payload": r.payload,
            "target_id": r.target_id,
            "status": r.status,
            "error": r.error,
        }
        for r in rows
    ]


@router.post("/{plan_id}/confirm", summary="确认方案（确认后才能执行）")
async def confirm_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    plan = await _get_or_404(db, plan_id)
    if plan.status != "draft":
        raise HTTPException(409, f"当前状态 {plan.status} 不能确认")
    plan.status = "confirmed"
    plan.confirmed_by = getattr(user, "id", None)
    plan.confirmed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(plan)
    return {"plan": _out(plan)}


@router.post("/{plan_id}/dry-run", summary="模拟执行（不写业务表）")
async def dry_run(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    plan = await _get_or_404(db, plan_id)
    try:
        return await svc.dry_run(db, plan)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{plan_id}/apply", summary="执行方案：建栏目 + 选题进批量队列")
async def apply(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    plan = await _get_or_404(db, plan_id)
    if plan.status == "running":
        raise HTTPException(409, "方案正在执行")
    try:
        return await svc.apply_plan(db, plan)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        plan = await _get_or_404(db, plan_id)
        plan.status = "failed"
        plan.error = str(exc)[:500]
        await db.commit()
        raise HTTPException(500, f"执行失败：{exc}") from exc


@router.post("/{plan_id}/cancel", summary="取消方案")
async def cancel_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    plan = await _get_or_404(db, plan_id)
    if plan.status in ("done", "cancelled"):
        raise HTTPException(409, f"当前状态 {plan.status} 不能取消")
    plan.status = "cancelled"
    items = (
        await db.execute(
            select(SitePlanItem).where(
                SitePlanItem.plan_id == plan_id, SitePlanItem.status == "pending"
            )
        )
    ).scalars().all()
    for item in items:
        item.status = "skipped"
        item.error = "方案已取消"
    await db.commit()
    await db.refresh(plan)
    return {"plan": _out(plan), "skipped_items": len(items)}


# ---------------------------------------------------------------- 关键词包导入
_KEY_COLS = ("keyword", "关键词", "词", "query")
_HINT_COLS = ("category_hint", "category", "栏目", "分类")


def _pick(row: dict[str, str], names: tuple[str, ...]) -> str:
    """按列名语义取值，容忍中英文表头与常见别名。"""
    for k, v in row.items():
        if not k or v is None:
            continue
        kl = str(k).strip().lower()
        if any(kl == n or kl.startswith(n) for n in names):
            return str(v).strip()
    return ""


@router.post("/import-keywords", summary="CSV 关键词包 → 方案（不落库）")
async def import_keywords(
    file: UploadFile = File(...),
    content_type_id: int | None = None,
    lang: str = "zh-CN",
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    require_site_id()
    raw = await file.read()
    if not raw:
        raise HTTPException(422, "上传的文件是空的")

    text = raw.decode("utf-8-sig", errors="replace")
    header = text.splitlines()[0] if text.strip() else ""
    delim = "\t" if ("\t" in header and "," not in header) else ","
    rows = list(csv.DictReader(io.StringIO(text), delimiter=delim))
    if not rows:
        raise HTTPException(422, "没有解析到数据行")

    buckets: dict[str, list[str]] = {}
    dropped: list[dict[str, str]] = []
    seen: set[str] = set()
    valid = 0
    for i, r in enumerate(rows, start=1):
        kw = _pick(r, _KEY_COLS)
        if not kw:
            dropped.append({"row": str(i), "reason": "缺关键词"})
            continue
        key = kw.lower().replace(" ", "")
        if key in seen:
            dropped.append({"row": str(i), "reason": f"重复：{kw}"})
            continue
        seen.add(key)
        hint = _pick(r, _HINT_COLS) or "关键词内容"
        buckets.setdefault(hint, []).append(kw[:200])
        valid += 1

    if not valid:
        raise HTTPException(422, "没有有效的关键词行")

    cats: list[dict[str, Any]] = []
    arts: list[dict[str, Any]] = []
    for idx, (hint, kws) in enumerate(list(buckets.items())[: svc.MAX_CATEGORIES]):
        key = f"cat{idx + 1}"
        cats.append({"key": key, "name": hint[:80], "slug": svc._slugify(hint, key)})
        for kw in kws:
            arts.append({"title": kw, "category_key": key, "keyword": kw, "brief": ""})
    if len(buckets) > svc.MAX_CATEGORIES:
        dropped.append(
            {"row": "-", "reason": f"栏目超过 {svc.MAX_CATEGORIES} 个，其余归并丢弃"}
        )
    arts = arts[: svc.MAX_ARTICLES]

    try:
        plan, warnings = svc.normalize_plan(
            {"summary": f"关键词包导入 · {len(cats)} 个栏目", "categories": cats, "articles": arts},
            max_categories=svc.MAX_CATEGORIES,
            max_articles=svc.MAX_ARTICLES,
        )
        ct = await svc.resolve_content_type(db, content_type_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    return {
        "plan": plan,
        "warnings": warnings,
        "content_type": {"id": ct.id, "key": ct.key, "name": ct.name},
        "stats": {
            "rows": len(rows),
            "valid": valid,
            "dropped": len(dropped),
            "categories": len(plan["categories"]),
            "articles": len(plan["articles"]),
            "drop_samples": dropped[:10],
        },
    }
