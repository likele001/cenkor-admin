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
from cenkor_admin.apps.cms import domain_setup, static_cache
from cenkor_admin.apps.cms.models import (
    Case,
    Category,
    Entry,
    Media,
    News,
    Product,
    Site,
    SiteConfig,
    Tag,
)
from cenkor_admin.apps.forms.models import Form
from cenkor_admin.core.config import get_settings
from cenkor_admin.core.db import DBSession
from cenkor_admin.core.site_scope import invalidate_site_cache, site_scope_bypass

settings = get_settings()
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


# ---------------------------------------------------------------- 站点配置继承


# 哪些 key 不该被复制到新站：
# - url.* 是「历史规则存档」，存的是老地址到新地址的映射，属于该站的历史，
#   复制过去会让新站的 301 表凭空多出一堆不存在的旧路径。
# - 其余（brand.* / seo.* / contact.* / web.*）都该继承，否则新站首页没有
#   品牌名、没有 SEO 默认值，等于建了个空壳。
_NO_COPY_PREFIXES: tuple[str, ...] = ("url.",)


async def _copy_site_config(db: DBSession, from_site_id: int, to_site_id: int) -> int:
    """把一个站点的配置复制给另一个站点。返回复制条数。

    幂等：目标站已有的 key 不覆盖（只在目标站完全没有配置时调用，但即使
    重复调用也不会破坏已有值）。
    """
    src_rows = (
        (
            await db.execute(
                select(SiteConfig).where(SiteConfig.site_id == from_site_id)
            )
        )
        .scalars()
        .all()
    )
    if not src_rows:
        return 0

    existing = set(
        (
            await db.execute(
                select(SiteConfig.key).where(SiteConfig.site_id == to_site_id)
            )
        )
        .scalars()
        .all()
    )

    n = 0
    for row in src_rows:
        if any(row.key.startswith(p) for p in _NO_COPY_PREFIXES):
            continue
        if row.key in existing:
            continue
        db.add(
            SiteConfig(
                site_id=to_site_id,
                key=row.key,
                value=row.value,
                description=row.description,
            )
        )
        n += 1
    return n


async def _main_site_id(db: DBSession) -> int | None:
    """主站 = id 最小的站点。与迁移脚本的口径一致。"""
    return (await db.execute(select(func.min(Site.id)))).scalar()


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
    await db.flush()  # 拿到 site.id，但先别提交

    # 从主站复制配置作为初始值。新建的站如果没有品牌名/SEO 默认值，
    # 后台会是一片空白，运营得手填 70 多项才能用 —— 复制一份最省事，
    # 且之后各站独立，主站再改不影响这里。
    copied = 0
    main_id = await _main_site_id(db)
    if main_id is not None and main_id != site.id:
        copied = await _copy_site_config(db, main_id, site.id)

    await db.commit()
    await db.refresh(site)
    await invalidate_site_cache()
    log.info(
        "cms.site.created",
        site_id=site.id,
        key=site.key,
        domain=domain,
        config_copied=copied,
    )
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
    old_domain = site.domain
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
    # 域名变了要立刻丢掉 site_domain() 的 60s 缓存，否则前端「保存后重新检测」
    # 会读到旧值，看起来像没保存成功。
    if "domain" in data:
        static_cache.forget_domain(site_id)
    # [P2] 站点信息（域名/品牌名）会进详情页的 title 与 canonical，
    # 旧域名下的静态目录直接撤掉，新域名第一次访问时重建。
    if static_cache.cache_enabled():
        try:
            static_cache.purge_site_domain(old_domain)
            static_cache.purge_site_domain(site.domain)
        except Exception as exc:
            log.warning("cms.site.static_purge_failed", site_id=site_id, error=str(exc))
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
    static_cache.forget_domain(site_id)
    # [P2] 站点没了，静态文件不该还活着
    if static_cache.cache_enabled() and site.domain:
        static_cache.purge_site_domain(site.domain)
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


# ---------------------------------------------------------------- 站点自动化开关
class SiteFeaturesIn(BaseModel):
    """只允许改这五个键，未知键在 service 层拒绝。"""

    auto_publish: bool | None = None
    auto_image: bool | None = None
    auto_seo: bool | None = None
    auto_push: bool | None = None
    auto_translate: bool | None = None


# ---------------------------------------------------------------- 域名绑定


# nginx 与证书的落盘位置。这台机器是宝塔面板布局，路径固定；
# 换成裸机部署时需要跟着改（或改成从 settings 读）。
_NGINX_VHOST_DIR = settings.CMS_NGINX_VHOST_DIR
_CERT_DIR = settings.CMS_CERT_DIR
# 后端自己的监听端口。反代要把 host 原样传给它，否则后端认不出站点。
_BACKEND_PORT = settings.CMS_DOMAIN_BACKEND_PORT


def _nginx_has_server(domain: str) -> bool:
    """nginx 里是否已有该域名的 server 块。

    直接看文件存在不够：宝塔会把 site 配置写成 <域名>.conf，但约定俗成
    不代表一定如此。这里做内容匹配，认出「某个 .conf 里 server_name 含它」。
    """
    import pathlib

    d = domain_setup._normalize(domain)
    if not d:
        return False
    p = pathlib.Path(_NGINX_VHOST_DIR)
    # 宝塔把这些目录设成 root-only（700）时，www 用户连 stat 都会抛
    # PermissionError。探测失败只能当作「看不到」，绝不能把 500 抛给前端。
    try:
        if not p.is_dir():
            return False
    except OSError:
        return False
    # 先看同名文件（最常见），省一次全目录扫描
    try:
        if (p / f"{d}.conf").is_file():
            return True
    except OSError:
        pass
    try:
        for conf in p.glob("*.conf"):
            try:
                text = conf.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            # 只在 server_name 行里找，避免命中注释或别处的域名
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                # and 短路：非 server_name 行不会走到 split()，语义与嵌套 if 相同
                if stripped.startswith("server_name") and d in stripped.split():
                    return True
    except OSError:
        return False
    return False


def _cert_exists(domain: str) -> bool:
    import pathlib

    d = domain_setup._normalize(domain)
    if not d:
        return False
    base = pathlib.Path(_CERT_DIR) / d
    # 同上：vhost/cert 通常是 root:root 700，www 用户 stat 直接 PermissionError。
    # 探测不到 ≠ 证书不存在，但这里已无法分辨，只能按「探测不到」处理，
    # 由 hint 文案引导用户自己确认（命令块里本来就有续期检查）。
    try:
        return (base / "fullchain.pem").is_file() and (base / "privkey.pem").is_file()
    except OSError:
        return False


@router.get(
    "/{site_id}/domain",
    summary="域名绑定状态与下一步操作",
)
async def get_site_domain_status(site_id: int, db: DBSession) -> dict[str, Any]:
    """当前域名处于哪个阶段，以及下一步该做什么。

    这是方案 A 的核心：后台不再只是「存一个字符串」，而是明确告诉运营
    「DNS 还没解析」还是「nginx 还没配」，并给出可直接粘贴的命令。
    配置错误从静默降级变成显式可见。

    域名取值与线上渲染保持同一口径（``static_cache.site_domain``）：
    先看 ``cms_sites.domain``，为空再回退 ``cms_site_config['brand.domain']``。
    只认前者会让主站永远显示「未绑定」—— 它线上一直是靠 brand.domain 跑的。
    """
    site = await _one(db, site_id)
    effective = await static_cache.site_domain(db, site_id)
    normalized = domain_setup._normalize(effective)

    # 不传 nginx_has_server / cert_exists：让 domain_setup 自己从本机 HTTP 探测。
    # 宝塔的 vhost/nginx 与 vhost/cert 都是 root:root 700，后端跑在 www 下读不到，
    # 交给文件系统判断只会永远报「缺失」，不如问「本机能不能打开这个域名」。
    info = await domain_setup.domain_status(effective)
    # 由状态反推两个布尔量，语义明确：nginx_ok 之后（含）说明 nginx 已有该站，
    # live 说明证书也通了。直接读 info["nginx_ok"] 会漏掉 nginx_ok/live 两种状态
    # —— 那时 domain_status 判断已完成，不再回填这两个键。
    st = info["status"]
    has_server = st in ("nginx_ok", "live")
    has_cert = st == "live"
    info["nginx_has_server"] = has_server
    info["cert_exists"] = has_cert
    info["site_id"] = site.id
    # 让运营知道这个域名是从哪读出来的：字段为空但回退命中时，
    # 「保存域名」按钮的光标位置会让人以为没配。
    info["domain_source"] = (
        "site" if domain_setup._normalize(site.domain) else ("config" if normalized else None)
    )
    info["site_key"] = site.key
    info["site_name"] = site.name
    info["hint"] = domain_setup.hint_for(info["status"])
    info["commands"] = (
        domain_setup.build_commands(
            normalized or "",
            site_key=site.key,
            backend_port=_BACKEND_PORT,
            status=info["status"],
        )
        if normalized
        else []
    )
    return info


@router.get("/{site_id}/features", summary="站点自动化开关")
async def get_site_features(site_id: int, db: DBSession) -> dict[str, Any]:
    from cenkor_admin.apps.cms.feature_flags import FEATURES, get_features

    try:
        feats = await get_features(db, site_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "features": feats,
        "labels": {k: v["label"] for k, v in FEATURES.items()},
        "defaults": {k: v["default"] for k, v in FEATURES.items()},
    }


@router.put("/{site_id}/features", summary="修改站点自动化开关")
async def put_site_features(
    site_id: int, body: SiteFeaturesIn, db: DBSession
) -> dict[str, Any]:
    from cenkor_admin.apps.cms.feature_flags import FEATURES, set_features

    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        feats = await set_features(db, site_id, patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"features": feats, "labels": {k: v["label"] for k, v in FEATURES.items()}}
