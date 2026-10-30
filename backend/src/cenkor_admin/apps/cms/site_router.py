"""站点管理 API（多站点 / 站群）。

## 为什么要 bypass

这个 router 天生要「跨站」：列站点、改任意站点、统计各站内容量。所以整个
router 挂 `site_scope_bypass()` —— 否则 `GET /sites` 会被过滤成只返回当前站。

反过来，这里的每个查询都必须**显式**带 site_id 条件（统计内容数时），
因为自动过滤被关掉了。

## 删除保护

DB 上 `cms_entries.site_id` 是 `ON DELETE RESTRICT`，硬删会被外键拦住。
但那样报的是数据库错误（500），所以这里先查内容量，有内容就返回 409 +
明确提示，让运营知道该先迁走还是先删内容。
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from cenkor_admin.apps.builder.models import Page
from cenkor_admin.apps.cms.models import Case, Category, Entry, Media, News, Product, Site, Tag
from cenkor_admin.apps.forms.models import Form
from cenkor_admin.core.db import DBSession
from cenkor_admin.core.site_scope import invalidate_site_cache, site_scope_bypass

log = structlog.get_logger(__name__)


async def _no_site_scope() -> AsyncIterator[None]:
    """路由级依赖：本 router 内所有查询都不受站点过滤影响。"""
    with site_scope_bypass():
        yield


router = APIRouter(prefix="/sites", tags=["cms-sites"], dependencies=[Depends(_no_site_scope)])


# ---------------------------------------------------------------- schemas

_KEY_RE = r"^[a-z][a-z0-9_-]*$"
_KINDS = {"main", "blog", "city", "landing"}
_MODES = {"article", "structured"}
_STATUSES = {"active", "paused", "archived"}


class SiteIn(BaseModel):
    key: str = Field(..., max_length=64, pattern=_KEY_RE)
    name: str = Field(..., max_length=120)
    kind: str = Field("main", max_length=20)
    domain: str | None = Field(None, max_length=255)
    locale: str = Field("zh-CN", max_length=20)
    default_lang: str | None = Field(None, max_length=20)
    site_mode: str = Field("article", max_length=20)
    geo: dict[str, Any] | None = None
    seo_defaults: dict[str, Any] | None = None
    settings: dict[str, Any] | None = None
    status: str = Field("active", max_length=20)
    sort: int = 0


class SiteUpdate(BaseModel):
    name: str | None = Field(None, max_length=120)
    kind: str | None = Field(None, max_length=20)
    domain: str | None = Field(None, max_length=255)
    locale: str | None = Field(None, max_length=20)
    default_lang: str | None = Field(None, max_length=20)
    site_mode: str | None = Field(None, max_length=20)
    geo: dict[str, Any] | None = None
    seo_defaults: dict[str, Any] | None = None
    settings: dict[str, Any] | None = None
    status: str | None = Field(None, max_length=20)
    sort: int | None = None


class SiteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    name: str
    kind: str
    domain: str | None
    locale: str
    default_lang: str | None
    site_mode: str
    geo: dict[str, Any] | None
    seo_defaults: dict[str, Any] | None
    settings: dict[str, Any] | None
    status: str
    sort: int


class SiteStats(BaseModel):
    """站点内容量。

    口径与列表页保持一致：**不含回收站**。回收站单独给 `trashed`，
    否则站点卡片显示 26 篇、点进列表只有 23 篇，运营会以为丢了数据。
    """

    entries: int
    categories: int
    tags: int
    media: int
    pages: int
    forms: int
    trashed: int = 0


class SiteWithStats(SiteOut):
    stats: SiteStats


# ---------------------------------------------------------------- 校验


def _check_enum(value: str, allowed: set[str], field: str) -> str:
    if value not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"{field} 必须是 {sorted(allowed)} 之一，收到 {value!r}",
        )
    return value


def _normalize_domain(domain: str | None) -> str | None:
    """域名统一成小写无协议无路径，便于中间件按 Host 精确匹配。"""
    if domain is None:
        return None
    d = domain.strip().lower()
    if not d:
        return None
    d = re.sub(r"^https?://", "", d)
    d = d.split("/")[0].split(":")[0]
    return d or None


# ---------------------------------------------------------------- 查询


async def _one(db: DBSession, site_id: int) -> Site:
    site = (await db.execute(select(Site).where(Site.id == site_id))).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail=f"站点 {site_id} 不存在")
    return site


_STAT_FIELDS: dict[str, tuple[Any, tuple[Any, ...]]] = {
    "entries": (Entry, (Entry.deleted_at.is_(None),)),
    "categories": (Category, (Category.deleted_at.is_(None),)),
    "tags": (Tag, ()),
    "media": (Media, (Media.deleted_at.is_(None),)),
    "pages": (Page, ()),
    "forms": (Form, ()),
}

# 回收站单独统计，语义上不算「有效内容量」
_TRASH_FIELD = (Entry, (Entry.deleted_at.is_not(None),))


async def _stats_map(db: DBSession, site_ids: list[int]) -> dict[int, SiteStats]:
    """批量统计各站内容量。

    本 router 关掉了自动过滤，所以必须显式指定 site_id —— 不写就是全站合计。
    按模型做一次 group by（共 7 次查询）而不是每个站点 7 次，站点多了也不会
    退化成 N+1。

    软删除的模型（entries/categories/media）带 `deleted_at IS NULL`，
    与列表页 total 口径对齐。
    """
    if not site_ids:
        return {}
    acc: dict[int, dict[str, int]] = {sid: {} for sid in site_ids}
    plan: list[tuple[str, Any, tuple[Any, ...]]] = [
        *((f, m, w) for f, (m, w) in _STAT_FIELDS.items()),
        ("trashed", *_TRASH_FIELD),
    ]
    for field, model, conds in plan:
        stmt = (
            select(model.site_id, func.count())
            .where(model.site_id.in_(site_ids))
            .group_by(model.site_id)
        )
        for cond in conds:
            stmt = stmt.where(cond)
        rows = (await db.execute(stmt)).all()
        for sid, n in rows:
            acc.setdefault(int(sid), {})[field] = int(n)

    all_fields = [*_STAT_FIELDS, "trashed"]
    return {
        sid: SiteStats(**{f: acc.get(sid, {}).get(f, 0) for f in all_fields})
        for sid in site_ids
    }


async def _stats(db: DBSession, site_id: int) -> SiteStats:
    return (await _stats_map(db, [site_id]))[site_id]


async def _ensure_keys_free(db: DBSession, key: str, domain: str | None, exclude: int | None) -> None:
    stmt = select(Site.id).where(Site.key == key)
    if exclude is not None:
        stmt = stmt.where(Site.id != exclude)
    if (await db.execute(stmt)).first() is not None:
        raise HTTPException(status_code=409, detail=f"站点标识 {key!r} 已存在")

    if domain:
        stmt = select(Site.id, Site.key).where(func.lower(Site.domain) == domain)
        if exclude is not None:
            stmt = stmt.where(Site.id != exclude)
        hit = (await db.execute(stmt)).first()
        if hit is not None:
            raise HTTPException(
                status_code=409, detail=f"域名 {domain!r} 已被站点 {hit.key!r} 占用"
            )


# ---------------------------------------------------------------- 端点


@router.get("", response_model=list[SiteWithStats], summary="站点列表（含内容统计）")
async def list_sites(db: DBSession) -> list[SiteWithStats]:
    sites = (
        (await db.execute(select(Site).order_by(Site.sort, Site.id))).scalars().all()
    )
    stats = await _stats_map(db, [s.id for s in sites])
    return [
        SiteWithStats(**SiteOut.model_validate(s).model_dump(), stats=stats[s.id]) for s in sites
    ]


@router.post(
    "", response_model=SiteOut, status_code=status.HTTP_201_CREATED, summary="新建站点"
)
async def create_site(body: SiteIn, db: DBSession) -> SiteOut:
    _check_enum(body.kind, _KINDS, "kind")
    _check_enum(body.site_mode, _MODES, "site_mode")
    _check_enum(body.status, _STATUSES, "status")
    domain = _normalize_domain(body.domain)
    await _ensure_keys_free(db, body.key, domain, exclude=None)

    site = Site(
        key=body.key,
        name=body.name,
        kind=body.kind,
        domain=domain,
        locale=body.locale,
        default_lang=body.default_lang or body.locale,
        site_mode=body.site_mode,
        geo=body.geo,
        seo_defaults=body.seo_defaults,
        settings=body.settings,
        status=body.status,
        sort=body.sort,
    )
    db.add(site)
    await db.commit()
    await db.refresh(site)
    await invalidate_site_cache()
    log.info("cms.site.created", site_id=site.id, key=site.key, domain=domain)
    return SiteOut.model_validate(site)


@router.get("/{site_id}", response_model=SiteWithStats, summary="站点详情")
async def get_site(site_id: int, db: DBSession) -> SiteWithStats:
    site = await _one(db, site_id)
    return SiteWithStats(
        **SiteOut.model_validate(site).model_dump(), stats=await _stats(db, site_id)
    )


@router.put("/{site_id}", response_model=SiteOut, summary="更新站点")
async def update_site(site_id: int, body: SiteUpdate, db: DBSession) -> SiteOut:
    site = await _one(db, site_id)
    data = body.model_dump(exclude_unset=True)

    if "kind" in data and data["kind"] is not None:
        _check_enum(data["kind"], _KINDS, "kind")
    if "site_mode" in data and data["site_mode"] is not None:
        _check_enum(data["site_mode"], _MODES, "site_mode")
    if "status" in data and data["status"] is not None:
        _check_enum(data["status"], _STATUSES, "status")
    if "domain" in data:
        data["domain"] = _normalize_domain(data["domain"])
        await _ensure_keys_free(db, site.key, data["domain"], exclude=site_id)

    for k, v in data.items():
        setattr(site, k, v)
    await db.commit()
    await db.refresh(site)
    await invalidate_site_cache()
    log.info("cms.site.updated", site_id=site.id, fields=sorted(data))
    return SiteOut.model_validate(site)


@router.delete("/{site_id}", summary="删除站点（站点内有内容时拒绝）")
async def delete_site(site_id: int, db: DBSession) -> dict[str, Any]:
    site = await _one(db, site_id)
    stats = await _stats(db, site_id)
    used = stats.model_dump()
    blocking = {k: v for k, v in used.items() if v > 0}
    if blocking:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "站点下还有内容，删除会丢数据。请先迁移或清空。",
                "site": site.key,
                "blocking": blocking,
            },
        )

    total = (await db.execute(select(func.count()).select_from(Site))).scalar() or 0
    if int(total) <= 1:
        raise HTTPException(status_code=409, detail="至少保留一个站点")

    await db.delete(site)
    await db.commit()
    await invalidate_site_cache()
    log.info("cms.site.deleted", site_id=site_id, key=site.key)
    return {"deleted": True, "site_id": site_id, "key": site.key}


@router.get("/{site_id}/stats", response_model=SiteStats, summary="站点内容统计")
async def site_stats(site_id: int, db: DBSession) -> SiteStats:
    await _one(db, site_id)
    return await _stats(db, site_id)


@router.get("/{site_id}/content", summary="站点内容清单（跨站排查用）")
async def site_content(
    site_id: int, db: DBSession, limit: int = 20
) -> dict[str, Any]:
    await _one(db, site_id)
    rows = (
        await db.execute(
            select(Entry.id, Entry.title, Entry.slug, Entry.status)
            .where(Entry.site_id == site_id)
            .order_by(Entry.id.desc())
            .limit(max(1, min(limit, 100)))
        )
    ).all()
    return {
        "site_id": site_id,
        "items": [
            {"id": r.id, "title": r.title, "slug": r.slug, "status": r.status} for r in rows
        ],
    }


# 旧三条线也带 site_id，单独列出来便于站群巡检
@router.get("/{site_id}/legacy", summary="站点旧内容统计（products/cases/news）")
async def site_legacy(site_id: int, db: DBSession) -> dict[str, int]:
    await _one(db, site_id)

    async def _count(model: Any) -> int:
        n = (
            await db.execute(
                select(func.count()).select_from(model).where(model.site_id == site_id)
            )
        ).scalar()
        return int(n or 0)

    return {
        "products": await _count(Product),
        "cases": await _count(Case),
        "news": await _count(News),
    }


__all__ = ["router"]
