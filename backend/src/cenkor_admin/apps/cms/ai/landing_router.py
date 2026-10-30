"""AI 落地页 / 官网子站 HTTP 接口。

    POST /landing/draft              一句话 → 草稿（不落库，先给前端预览）
    POST /landing/save               草稿落库（建表单 + 建页面，均 draft）
    GET  /landing/pages              页面列表（含访问/留资数）
    GET  /landing/pages/{id}/preview 预览整页 HTML
    POST /landing/pages/{id}/publish 发布 / 下线
    DELETE /landing/pages/{id}       删除页面（连带孤立表单）
    GET  /landing/stats              概览

为什么草稿与保存分两步：生成要 30~60 秒，用户得先看到东西才有判断。
一步到位直接落库的结果是每次重试都在库里留一版垃圾。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.builder.models import Page
from cenkor_admin.apps.builder.renderer import render_page
from cenkor_admin.apps.cms.ai import landing
from cenkor_admin.apps.cms.ai.landing_blocks import clean_blocks
from cenkor_admin.apps.forms.models import Form, FormSubmission
from cenkor_admin.core.db import get_db
from cenkor_admin.core.llm import LLMNotConfiguredError
from cenkor_admin.core.site_scope import current_site_id

router = APIRouter()


def _site() -> int:
    return current_site_id() or 1


def _form_keys(blocks: list[dict[str, Any]]) -> list[str]:
    return [
        str((b.get("data") or {}).get("form_key") or "")
        for b in blocks or []
        if b.get("type") == "form"
    ]


def _page_out(p: Page, subs: int = 0, leads: int = 0) -> dict[str, Any]:
    return {
        "id": p.id,
        "key": p.key,
        "title": p.title,
        "kind": p.kind or "page",
        "site_key": p.site_key,
        "status": p.status,
        "url": f"/lp/{p.key}",
        "block_count": len(p.schema or []),
        "form_keys": [k for k in _form_keys(p.schema or []) if k],
        "submissions": subs,
        "leads": leads,
        "published_at": p.published_at.isoformat() if p.published_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


async def _load_forms(db: AsyncSession, blocks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    keys = [k for k in _form_keys(blocks) if k]
    if not keys:
        return {}
    rows = (
        await db.execute(select(Form).where(Form.key.in_(keys)))
    ).scalars().all()
    return {
        f.key: {"fields": f.fields or [], "success_message": f.success_message}
        for f in rows
    }


@router.post("/landing/draft", summary="落地页：一句话生成草稿（不落库）")
async def landing_draft(
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    brief = str(body.get("brief") or "").strip()
    if not brief:
        raise HTTPException(400, "brief 不能为空")
    if len(brief) > 500:
        raise HTTPException(400, "需求描述太长（上限 500 字）")

    try:
        payload = await landing.draft(
            db,
            brief,
            mode=str(body.get("mode") or "page"),
            goal=str(body.get("goal") or "获取线索"),
            tone=str(body.get("tone") or "专业、克制"),
            brand=str(body.get("brand") or ""),
            use_kb=bool(body.get("use_kb", True)),
            created_by=user.id,
        )
        await db.commit()
        return payload
    except LLMNotConfiguredError as exc:
        await db.rollback()
        raise HTTPException(503, "AI 模型未配置，无法生成") from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.warning("cms.landing.draft_failed", error=str(exc))
        raise HTTPException(502, f"生成失败：{str(exc)[:200]}") from exc


@router.post("/landing/save", summary="落地页：草稿落库（建表单 + 页面，均为 draft）")
async def landing_save(
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    payload = body.get("payload") or body
    if not isinstance(payload, dict) or not payload.get("pages"):
        raise HTTPException(400, "payload.pages 不能为空")

    # 人手改过的区块再校验一次：人可以改坏，但不该把渲染器改崩
    for p in payload["pages"]:
        blocks, _dropped = clean_blocks(p.get("blocks") or [], limit=landing.MAX_BLOCKS_PER_PAGE)
        p["blocks"] = blocks

    try:
        result = await landing.save(
            db, payload, site_id=_site(),
            site_key=str(body.get("site_key") or "").strip() or None,
            page_key=str(body.get("page_key") or "").strip() or None,
            created_by=user.id,
        )
        await db.commit()
        return result
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.warning("cms.landing.save_failed", error=str(exc))
        raise HTTPException(500, f"保存失败：{str(exc)[:200]}") from exc


@router.get("/landing/pages", summary="落地页：列表（含留资数）")
async def landing_pages(
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(Page)
            .where(Page.site_id == _site())
            .order_by(Page.kind.asc(), Page.id.desc())
            .limit(200)
        )
    ).scalars().all()

    # 一次查完所有表单的提交数，避免 N+1
    sub_by_form: dict[int, int] = {}
    forms = (await db.execute(select(Form.id, Form.key))).all()
    if forms:
        ids = [r[0] for r in forms]
        for fid, cnt in (
            await db.execute(
                select(FormSubmission.form_id, func.count())
                .where(FormSubmission.form_id.in_(ids))
                .group_by(FormSubmission.form_id)
            )
        ).all():
            sub_by_form[fid] = int(cnt)

    items = []
    for p in rows:
        subs = sum(sub_by_form.get(fid, 0) for fid in _form_ids_for(p, forms))
        items.append(_page_out(p, subs=subs))
    return {"items": items, "total": len(items)}


def _form_ids_for(page: Page, forms: list) -> list[int]:
    keys = set(k for k in _form_keys(page.schema or []) if k)
    return [r[0] for r in forms if r[1] in keys]


@router.get("/landing/pages/{page_id}/preview", response_class=HTMLResponse, summary="落地页：预览整页 HTML")
async def landing_preview(
    page_id: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> HTMLResponse:
    page = await db.get(Page, page_id)
    if not page:
        raise HTTPException(404, "页面不存在")
    forms = await _load_forms(db, page.schema or [])
    html = render_page(
        {
            "key": page.key,
            "title": page.title,
            "schema": page.schema or [],
            "seo": page.seo or {},
            "nav": page.nav or [],
            "kind": page.kind,
            "site_key": page.site_key,
        },
        forms=forms,
        canonical=f"/lp/{page.key}",
        track=False,  # 预览不该污染统计数据
        noindex=True,
    )
    return HTMLResponse(content=html)


@router.post("/landing/pages/{page_id}/publish", summary="落地页：发布 / 下线")
async def landing_publish(
    page_id: int,
    body: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    page = await db.get(Page, page_id)
    if not page:
        raise HTTPException(404, "页面不存在")
    want = bool(body.get("published", True))
    page.status = "published" if want else "draft"
    if want:
        page.published_at = page.published_at or datetime.now(UTC)
    # 子站是一整个站点：发布首页就把同站点其它页一起带上去，
    # 否则访客从首页点进「产品」会 404 —— 这类问题上线后才被发现很丢人
    siblings: list[Page] = []
    if page.site_key:
        siblings = list(
            (
                await db.execute(
                    select(Page).where(
                        Page.site_id == page.site_id,
                        Page.site_key == page.site_key,
                        Page.id != page.id,
                    )
                )
            ).scalars().all()
        )
        for s in siblings:
            if s.id == page.id:
                continue
            s.status = page.status
            if want:
                s.published_at = s.published_at or datetime.now(UTC)
    await db.commit()
    return {"ok": True, "published": want, "affected": 1 + len(siblings), "url": f"/lp/{page.key}"}


@router.delete("/landing/pages/{page_id}", summary="落地页：删除页面")
async def landing_delete(
    page_id: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    page = await db.get(Page, page_id)
    if not page:
        raise HTTPException(404, "页面不存在")
    # 只删本页挂的表单，且仅当没有别的页在用它（普通页 1:1，子站内可能共用）
    form_keys = set(k for k in _form_keys(page.schema or []) if k)
    await db.delete(page)
    await db.flush()
    if form_keys:
        still = (
            await db.execute(select(Page).where(Page.site_id == _site(), Page.id != page_id))
        ).scalars().all()
        used = {k for p in still for k in _form_keys(p.schema or [])}
        for k in form_keys - used:
            f = (await db.execute(select(Form).where(Form.key == k))).scalar_one_or_none()
            if f:
                await db.delete(f)
    await db.commit()
    return {"ok": True, "deleted": page_id}


@router.get("/landing/stats", summary="落地页：概览")
async def landing_stats(
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    total = await db.scalar(
        select(func.count()).select_from(Page).where(Page.site_id == _site())
    )
    published = await db.scalar(
        select(func.count()).select_from(Page).where(
            Page.site_id == _site(), Page.status == "published"
        )
    )
    sites = await db.scalar(
        select(func.count(func.distinct(Page.site_key))).where(
            Page.site_id == _site(), Page.site_key.is_not(None)
        )
    )
    forms_lead = await db.scalar(
        select(func.count()).select_from(Form).where(Form.create_lead.is_(True))
    )
    subs = await db.scalar(select(func.count()).select_from(FormSubmission))
    return {
        "pages": int(total or 0),
        "published": int(published or 0),
        "sites": int(sites or 0),
        "lead_forms": int(forms_lead or 0),
        "submissions": int(subs or 0),
        "limits": {"max_pages_per_gen": landing.MAX_PAGES, "max_blocks": landing.MAX_BLOCKS_PER_PAGE},
    }
