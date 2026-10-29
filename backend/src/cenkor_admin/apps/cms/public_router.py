"""CMS App · 公开接口（公网站点读取，无需鉴权）"""
from __future__ import annotations

from datetime import UTC, datetime
import re
import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import Text, cast, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms import models
from cenkor_admin.core.compat import order_nulls_last
from cenkor_admin.core.db import AsyncSessionLocal, get_db
from cenkor_admin.core.storage import s3
from cenkor_admin.core.template_engine import render_template_safe

router = APIRouter()


async def _increment_news_view_count(news_id: int) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(models.News)
            .where(models.News.id == news_id)
            .values(view_count=models.News.view_count + 1)
        )
        await session.commit()


async def _apply_entry_translation(db: AsyncSession, item: dict, lang: str | None) -> dict:
    """多语言 i18n：指定 lang 且存在翻译时，用翻译覆盖 title/content/custom_fields/slug。"""
    if not lang:
        return item
    tr = (await db.execute(
        select(models.EntryTranslation).where(
            models.EntryTranslation.entry_id == item["id"],
            models.EntryTranslation.lang == lang,
        )
    )).scalar_one_or_none()
    if not tr:
        return item
    fv = tr.field_values or {}
    out = dict(item)
    for k in ("title", "slug", "content", "custom_fields"):
        if k in fv and fv[k] is not None:
            out[k] = fv[k]
    out["lang"] = lang
    return out


def _build_og(item: dict) -> dict:
    """M4·P3 4.1 Open Graph：从内容/SEO 字段推导 og 元数据。"""
    seo = item.get("seo") or {}
    content = item.get("content") or {}
    title = (seo.get("og_title") or seo.get("seo_title") or item.get("title") or "")
    description = (
        seo.get("og_description") or seo.get("seo_description")
        or item.get("excerpt") or content.get("text") or content.get("excerpt") or ""
    )
    if isinstance(description, str) and len(description) > 200:
        description = description[:200] + "…"
    image = (
        seo.get("og_image") or item.get("cover_image")
        or content.get("image") or content.get("cover_image") or ""
    )
    return {
        "og_type": seo.get("og_type", "article"),
        "og_title": str(title or "")[:200],
        "og_description": str(description or ""),
        "og_image": image or None,
        "twitter_card": seo.get("twitter_card", "summary_large_image"),
    }


def _strip_html(text: str, limit: int = 300) -> str:
    """去 HTML 标签取纯文本（JSON-LD / llms.txt 摘要用）。"""
    import re as _re

    return _re.sub(r"<[^>]+>", " ", text or "")[:limit].strip()


_VIDEO_TAG_RE = re.compile(r'<video[^>]+src="([^"]+)"', re.I)


def _first_video_src(item: dict) -> str | None:
    """取正文里第一个 <video> 的 src（用于 og:video）。

    只认 <video> 标签，不认裸 .mp4 链接 —— 后者可能只是文中的下载引用，
    塞进 og:video 会让分享卡片显示一个跟文章无关的片子。
    """
    content = item.get("content") or {}
    html = ""
    for key in ("text", "html", "body", "content_md"):
        val = content.get(key)
        if isinstance(val, str) and val:
            html = val
            break
    if not html:
        return None
    match = _VIDEO_TAG_RE.search(html)
    return match.group(1) if match else None


def _abs_url(base: str, url: str | None) -> str | None:
    """把站内相对路径补成绝对 URL。

    `og:image` 与 JSON-LD 的 `image` 都要求绝对 URL；正文配图存的是
    `/api/v1/public/media/{id}/thumb?w=1200` 这种相对路径，原样写进 meta
    抓取端无法解析，分享卡片就是空图。
    """
    if not url:
        return None
    s = str(url).strip()
    if not s:
        return None
    if s.startswith(("http://", "https://")):
        return s
    return f"{base}/{s.lstrip('/')}"


def _build_json_ld(item: dict, *, url: str | None = None, kind: str = "article") -> dict[str, Any]:
    """GEO P1-5：从内容/SEO 字段推导 schema.org JSON-LD。

    kind: article（新闻/案例/内容引擎条目）| product。字段缺失就省略，
    不编造 —— schema.org 对空值容忍，但对错误值会拉低信任分。
    """
    seo = item.get("seo") or {}
    content = item.get("content") or {}
    title = str(item.get("title") or "")
    description = (
        seo.get("seo_description") or seo.get("og_description")
        or _strip_html(
            str(content.get("excerpt") or content.get("desc")
                or content.get("text") or content.get("content_md") or "")
        )
    )
    image = seo.get("og_image") or item.get("cover_image") or content.get("cover_image")

    if kind == "product":
        ld: dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": title,
        }
        if description:
            ld["description"] = description
        if image:
            ld["image"] = image
        if url:
            ld["url"] = url
        if item.get("website"):
            ld["sameAs"] = item["website"]
        return ld

    ld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title[:110],
        "inLanguage": item.get("lang") or "zh-CN",
    }
    if description:
        ld["description"] = description
    if image:
        ld["image"] = image if isinstance(image, str) else image[0]
    if item.get("published_at"):
        ld["datePublished"] = item["published_at"]
    if url:
        ld["url"] = url
    # 正文有 <video> 时补 VideoObject：schema.org 的 Article 支持 video 属性，
    # 搜索引擎用它识别「这篇内容含视频」。缺了不影响抓取，但有了更完整。
    video_src = _first_video_src(item)
    if video_src:
        ld["video"] = {
            "@type": "VideoObject",
            "contentUrl": video_src,
            "thumbnailUrl": image if isinstance(image, str) else (image[0] if image else None),
        }
    return ld


# ============================================================
# 公共内容类型 API
# ============================================================

@router.get("/content-types", response_model=list[dict[str, Any]])
async def get_public_content_types(
    db: AsyncSession = Depends(get_db),
):
    """获取所有激活的公开内容类型（供 portal-web 头部切换使用）"""
    result = await db.execute(
        select(models.ContentType)
        .where(models.ContentType.deleted_at.is_(None))
        .order_by(models.ContentType.id)
    )
    items = result.scalars().all()
    return [
        {
            "key": ct.key,
            "name": ct.name,
            "icon": ct.icon or "",
        }
        for ct in items
    ]


# ============================================================
# 公共分类 API
# ============================================================

@router.get("/categories", response_model=list[dict[str, Any]])
async def get_public_categories(
    db: AsyncSession = Depends(get_db),
    content_type_key: str = Query(...),
    status: str = Query("active"),
):
    """获取指定内容类型的分类列表"""
    ct = (await db.execute(
        select(models.ContentType).where(models.ContentType.key == content_type_key)
    )).scalar_one_or_none()
    if not ct:
        return []
    result = await db.execute(
        select(models.Category)
        .where(
            models.Category.content_type_id == ct.id,
            models.Category.status == status,
            models.Category.deleted_at.is_(None),
        )
        .order_by(models.Category.sort)
    )
    return [
        {"id": c.id, "name": c.name, "slug": c.slug, "icon": c.icon, "color": c.color, "parent_id": c.parent_id, "sort": c.sort}
        for c in result.scalars().all()
    ]


@router.get("/categories/tree", response_model=list[dict[str, Any]])
async def get_public_category_tree(
    db: AsyncSession = Depends(get_db),
    content_type_key: str = Query(...),
    status: str = Query("active"),
):
    """获取分类树"""
    ct = (await db.execute(
        select(models.ContentType).where(models.ContentType.key == content_type_key)
    )).scalar_one_or_none()
    if not ct:
        return []
    result = await db.execute(
        select(models.Category)
        .where(
            models.Category.content_type_id == ct.id,
            models.Category.status == status,
            models.Category.deleted_at.is_(None),
        )
        .order_by(models.Category.sort)
    )
    all_cats = result.scalars().all()

    def build_tree(parent_id=None):
        tree = []
        for c in all_cats:
            if c.parent_id == parent_id:
                node = {"id": c.id, "name": c.name, "slug": c.slug, "icon": c.icon, "color": c.color, "sort": c.sort}
                children = build_tree(c.id)
                if children:
                    node["children"] = children
                tree.append(node)
        return tree

    return build_tree(None)


# ============================================================
# 公共标签 API
# ============================================================

@router.get("/tags", response_model=list[dict[str, Any]])
async def get_public_tags(
    db: AsyncSession = Depends(get_db),
    content_type_key: str = Query(...),
):
    """获取指定内容类型的标签列表"""
    ct = (await db.execute(
        select(models.ContentType).where(models.ContentType.key == content_type_key)
    )).scalar_one_or_none()
    if not ct:
        return []
    result = await db.execute(
        select(models.Tag).where(models.Tag.content_type_id == ct.id).order_by(models.Tag.name)
    )
    return [
        {"id": t.id, "name": t.name, "slug": t.slug, "color": t.color}
        for t in result.scalars().all()
    ]


# ============================================================
# 公共内容查询 API
# ============================================================

def _product_to_item(p: models.Product) -> dict[str, Any]:
    return {
        "id": p.id, "slug": p.slug, "title": p.name,
        "content": {"tagline": p.tagline, "line": p.line, "stack": p.stack,
                     "desc": p.desc, "features": p.features or [],
                     "chineseName": p.chinese_name},
        "custom_fields": p.custom_fields or {},
        "status": p.status, "published_at": None, "sort": p.sort, "view_count": 0,
        "is_flagship": p.is_flagship, "is_open_source": p.is_open_source,
        "github": p.github_url or None, "demo": p.demo_url or None,
        "website": p.website_url or None, "license": p.license or None,
    }


def _case_to_item(c: models.Case) -> dict[str, Any]:
    return {
        "id": c.id, "slug": c.name, "title": c.name,
        "content": {"industry": c.industry, "desc": c.desc, "tag": c.tag, "href": c.href},
        "custom_fields": c.custom_fields or {},
        "status": c.status, "published_at": None, "sort": c.sort, "view_count": 0,
    }


def _news_to_item(n: models.News) -> dict[str, Any]:
    return {
        "id": n.id, "slug": n.slug, "title": n.title,
        "content": {"excerpt": n.excerpt, "content_md": n.content_md, "cover_image": n.cover_image},
        "custom_fields": n.custom_fields or {},
        "status": n.status,
        "published_at": n.published_at.isoformat() if n.published_at else None,
        "sort": 0, "view_count": n.view_count or 0,
    }


@router.get("/site/{content_type_key}", response_model=dict[str, Any])
async def get_public_entries(
    content_type_key: str,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    lang: str | None = Query(None, description="语言代码（如 en-US），仅对内容引擎类型生效"),
):
    """按内容类型获取公开内容列表（自动路由到对应专用表）"""
    from sqlalchemy import func as sqlfunc

    if content_type_key == "product":
        stmt = (select(models.Product)
                .where(models.Product.deleted_at.is_(None), models.Product.status == "published")
                .order_by(models.Product.sort, models.Product.id)
                .offset((page - 1) * page_size).limit(page_size))
        items = [_product_to_item(p) for p in (await db.execute(stmt)).scalars().all()]
        total = (await db.execute(select(sqlfunc.count()).select_from(models.Product)
                .where(models.Product.deleted_at.is_(None), models.Product.status == "published"))).scalar() or 0
    elif content_type_key == "case":
        stmt = (select(models.Case)
                .where(models.Case.deleted_at.is_(None), models.Case.status == "published")
                .order_by(models.Case.sort, models.Case.id)
                .offset((page - 1) * page_size).limit(page_size))
        items = [_case_to_item(c) for c in (await db.execute(stmt)).scalars().all()]
        total = (await db.execute(select(sqlfunc.count()).select_from(models.Case)
                .where(models.Case.deleted_at.is_(None), models.Case.status == "published"))).scalar() or 0
    elif content_type_key == "news":
        stmt = (select(models.News)
                .where(models.News.deleted_at.is_(None), models.News.status == "published")
                .order_by(models.News.published_at.desc(), models.News.id.desc())
                .offset((page - 1) * page_size).limit(page_size))
        items = [_news_to_item(n) for n in (await db.execute(stmt)).scalars().all()]
        total = (await db.execute(select(sqlfunc.count()).select_from(models.News)
                .where(models.News.deleted_at.is_(None), models.News.status == "published"))).scalar() or 0
    else:
        ct = (await db.execute(
            select(models.ContentType).where(models.ContentType.key == content_type_key)
        )).scalar_one_or_none()
        if not ct:
            raise HTTPException(404, f"Content type '{content_type_key}' not found")
        conds = [models.Entry.content_type_id == ct.id, models.Entry.status == "published",
                 models.Entry.deleted_at.is_(None)]
        total = (await db.execute(select(sqlfunc.count()).select_from(models.Entry).where(*conds))).scalar() or 0
        stmt = (select(models.Entry).where(*conds)
                .order_by(models.Entry.sort, models.Entry.published_at.desc())
                .offset((page - 1) * page_size).limit(page_size))
        entries = (await db.execute(stmt)).scalars().all()
        items = [{"id": e.id, "slug": e.slug, "title": e.title, "content": e.content or {},
                  "custom_fields": e.custom_fields or {}, "seo": e.seo or {}, "status": e.status,
                  "published_at": e.published_at.isoformat() if e.published_at else None,
                  "sort": e.sort, "view_count": e.view_count,
                  "ai_generated": e.ai_origin is not None} for e in entries]
        if lang:
            items = [await _apply_entry_translation(db, it, lang) for it in items]
        for it in items:
            it["og"] = _build_og(it)

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/site/{content_type_key}/{id_or_slug}", response_model=dict[str, Any])
async def get_public_entry_detail(
    content_type_key: str,
    id_or_slug: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    lang: str | None = Query(None, description="语言代码（如 en-US），仅对内容引擎类型生效"),
):
    """获取公开内容详情（自动路由到对应专用表）。响应带 json_ld（GEO）与 ai_generated 标记。"""
    base = str(request.base_url).rstrip("/")
    if content_type_key == "product":
        if id_or_slug.isdigit():
            p = (await db.execute(select(models.Product).where(models.Product.id == int(id_or_slug)))).scalar_one_or_none()
        else:
            p = (await db.execute(select(models.Product).where(models.Product.slug == id_or_slug))).scalar_one_or_none()
        if not p:
            raise HTTPException(404, "Product not found")
        async def increment_product_view():
            async with AsyncSessionLocal() as session:
                await session.execute(update(models.Product).where(models.Product.id == p.id).values(
                    view_count=models.Product.view_count + 1))
                await session.commit()
        background_tasks.add_task(increment_product_view)
        item = _product_to_item(p)
        item["json_ld"] = _build_json_ld(
            item, url=f"{base}{_page_path('product', p.slug)}" if p.slug else None, kind="product"
        )
        return item
    elif content_type_key == "case":
        if id_or_slug.isdigit():
            c = (await db.execute(select(models.Case).where(models.Case.id == int(id_or_slug)))).scalar_one_or_none()
        else:
            c = (await db.execute(select(models.Case).where(models.Case.name == id_or_slug))).scalar_one_or_none()
        if not c:
            raise HTTPException(404, "Case not found")
        item = _case_to_item(c)
        item["json_ld"] = _build_json_ld(
            item, url=f"{base}{_page_path('case', c.name)}" if c.name else None, kind="article"
        )
        return item
    elif content_type_key == "news":
        if id_or_slug.isdigit():
            n = (await db.execute(select(models.News).where(models.News.id == int(id_or_slug)))).scalar_one_or_none()
        else:
            n = (await db.execute(select(models.News).where(models.News.slug == id_or_slug))).scalar_one_or_none()
        if not n:
            raise HTTPException(404, "News not found")
        async def increment_news_view():
            async with AsyncSessionLocal() as session:
                await session.execute(update(models.News).where(models.News.id == n.id).values(
                    view_count=models.News.view_count + 1))
                await session.commit()
        background_tasks.add_task(increment_news_view)
        item = _news_to_item(n)
        item["json_ld"] = _build_json_ld(
            item, url=f"{base}{_page_path('news', n.slug)}" if n.slug else None, kind="article"
        )
        return item
    else:
        ct = (await db.execute(select(models.ContentType).where(models.ContentType.key == content_type_key))).scalar_one_or_none()
        if not ct:
            raise HTTPException(404, f"Content type '{content_type_key}' not found")
        conds = [models.Entry.content_type_id == ct.id, models.Entry.status == "published", models.Entry.deleted_at.is_(None)]
        if id_or_slug.isdigit():
            conds.append(models.Entry.id == int(id_or_slug))
        else:
            conds.append(models.Entry.slug == id_or_slug)
        entry = (await db.execute(select(models.Entry).where(*conds))).scalar_one_or_none()
        if not entry:
            raise HTTPException(404, "Entry not found")
        item = {"id": entry.id, "slug": entry.slug, "title": entry.title, "content": entry.content or {},
                "custom_fields": entry.custom_fields or {}, "seo": entry.seo or {}, "status": entry.status,
                "published_at": entry.published_at.isoformat() if entry.published_at else None,
                "sort": entry.sort, "view_count": (entry.view_count or 0) + 1,
                # AI 内容对外标记（P1-6）：合规与信任需要
                "ai_generated": entry.ai_origin is not None}
        item = await _apply_entry_translation(db, item, lang)
        item["og"] = _build_og(item)
        item["json_ld"] = _build_json_ld(
            item, url=f"{base}{_page_path('article', entry.slug)}" if entry.slug else None, kind="article"
        )
        return item


@router.get("/field-definitions", response_model=list[dict[str, Any]])
async def get_public_field_definitions(
    db: AsyncSession = Depends(get_db),
    content_type_key: str = Query(...),
):
    """获取字段定义（供前台渲染动态字段）"""
    ct = (await db.execute(
        select(models.ContentType).where(models.ContentType.key == content_type_key)
    )).scalar_one_or_none()
    if not ct:
        return []

    stmt = (
        select(models.FieldDefinition)
        .where(
            models.FieldDefinition.content_type_id == ct.id,
            models.FieldDefinition.status == "active",
        )
        .order_by(models.FieldDefinition.sort)
    )
    result = await db.execute(stmt)
    fields = result.scalars().all()

    items = []
    for fd in fields:
        opts_result = await db.execute(
            select(models.FieldOption)
            .where(models.FieldOption.definition_id == fd.id)
            .order_by(models.FieldOption.sort)
        )
        options = [
            {"value": o.value, "label": o.label, "color": o.color}
            for o in opts_result.scalars().all()
        ]
        items.append({
            "id": fd.id,
            "field_key": fd.field_key,
            "label": fd.label,
            "field_type": fd.field_type,
            "required": fd.required,
            "default_value": fd.default_value,
            "options": fd.options,
            "validation": fd.validation,
            "group_id": fd.group_id,
            "sort": fd.sort,
            "field_options": options,
        })
    return items


# ============================================================
# 现有公开接口（保持兼容）
# ============================================================

@router.get("/site", response_model=dict[str, Any], summary="公开站点数据（公网/官网读取）")
async def get_public_site_data(db: AsyncSession = Depends(get_db)):
    """一次性返回官网需要的全部内容：站点配置 + 产品 + 案例。"""
    cfg_result = await db.execute(select(models.SiteConfig))
    site_config = {s.key: s.value for s in cfg_result.scalars().all()}

    prod_result = await db.execute(
        select(models.Product)
        .where(models.Product.deleted_at.is_(None), models.Product.status == "published")
        .order_by(models.Product.sort, models.Product.id)
    )
    products = [
        {
            "id": p.id, "key": p.slug, "name": p.name, "chineseName": p.chinese_name,
            "tagline": p.tagline, "line": p.line, "stack": p.stack,
            "desc": p.desc, "features": p.features or [],
            "isFlagship": p.is_flagship, "isOpenSource": p.is_open_source,
            "github": p.github_url, "demo": p.demo_url,
            "website": p.website_url, "license": p.license,
            "custom_fields": p.custom_fields or {},
        }
        for p in prod_result.scalars().all()
    ]

    case_result = await db.execute(
        select(models.Case)
        .where(models.Case.deleted_at.is_(None), models.Case.status == "published")
        .order_by(models.Case.sort, models.Case.id)
    )
    cases = [
        {"industry": c.industry, "name": c.name, "desc": c.desc, "tag": c.tag, "href": c.href}
        for c in case_result.scalars().all()
    ]

    return {"site_config": site_config, "products": products, "cases": cases}


@router.get("/products", response_model=list[dict[str, Any]], summary="公开产品列表")
async def get_public_products(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(models.Product)
        .where(models.Product.deleted_at.is_(None), models.Product.status == "published")
        .order_by(models.Product.sort, models.Product.id)
    )
    return [
        {
            "key": p.slug, "name": p.name, "chineseName": p.chinese_name,
            "tagline": p.tagline, "line": p.line, "stack": p.stack,
            "desc": p.desc, "features": p.features or [],
            "isFlagship": p.is_flagship, "isOpenSource": p.is_open_source,
            "github": p.github_url, "demo": p.demo_url,
            "website": p.website_url, "license": p.license,
            "custom_fields": p.custom_fields or {},
        }
        for p in result.scalars().all()
    ]


@router.get("/cases", response_model=list[dict[str, Any]], summary="公开案例列表")
async def get_public_cases(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(models.Case)
        .where(models.Case.deleted_at.is_(None), models.Case.status == "published")
        .order_by(models.Case.sort, models.Case.id)
    )
    return [
        {"industry": c.industry, "name": c.name, "desc": c.desc, "tag": c.tag, "href": c.href}
        for c in result.scalars().all()
    ]


@router.get("/news", response_model=list[dict[str, Any]], summary="公开新闻列表")
async def get_public_news(db: AsyncSession = Depends(get_db), limit: int = 20):
    result = await db.execute(
        select(models.News)
        .where(models.News.deleted_at.is_(None), models.News.status == "published")
        .order_by(*order_nulls_last(models.News.published_at), models.News.id.desc())
        .limit(limit)
    )
    return [
        {
            "id": n.id, "slug": n.slug, "title": n.title, "excerpt": n.excerpt,
            "cover_image": n.cover_image,
            "published_at": n.published_at.isoformat() if n.published_at else None,
        }
        for n in result.scalars().all()
    ]


@router.get("/news/{slug}", response_model=dict[str, Any], summary="公开新闻详情")
async def get_public_news_detail(
    slug: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.News)
        .where(models.News.deleted_at.is_(None), models.News.slug == slug, models.News.status == "published")
    )
    n = result.scalar_one_or_none()
    if not n:
        raise HTTPException(status_code=404, detail="News not found")

    background_tasks.add_task(_increment_news_view_count, n.id)
    view_count = (n.view_count or 0) + 1
    item = {
        "id": n.id, "slug": n.slug, "title": n.title, "excerpt": n.excerpt,
        "content_md": n.content_md, "cover_image": n.cover_image,
        "published_at": n.published_at.isoformat() if n.published_at else None,
        "view_count": view_count,
    }
    item["json_ld"] = _build_json_ld(
        item, url=f"{str(request.base_url).rstrip('/')}/news/{n.slug}" if n.slug else None,
        kind="article",
    )
    return item


# ============================================================
# 暂存预览（M4·P3 4.4 staging）
# ============================================================

async def _resolve_preview_entry(db: AsyncSession, token: str):
    """解析预览 token → entry；已过期/已发布/不存在返回 None。"""
    from datetime import datetime
    pv = (await db.execute(
        select(models.EntryPreview).where(models.EntryPreview.token == token)
    )).scalar_one_or_none()
    if not pv:
        return None, "预览不存在"
    if pv.expires_at and pv.expires_at < datetime.now(UTC):
        return None, "预览已过期"
    entry = await db.get(models.Entry, pv.entry_id)
    if not entry or entry.deleted_at:
        return None, "内容不存在"
    if entry.status == "published":
        return None, "内容已发布，预览链接失效"
    return entry, None


@router.get("/preview/{token}.json", include_in_schema=False)
async def preview_entry_json(token: str, db: AsyncSession = Depends(get_db)):
    """暂存预览（JSON 数据）。"""
    entry, err = await _resolve_preview_entry(db, token)
    if not entry:
        raise HTTPException(404 if "失效" not in (err or "") else 410, err or "预览不可用")
    item = {"id": entry.id, "slug": entry.slug, "title": entry.title,
            "content": entry.content or {}, "custom_fields": entry.custom_fields or {},
            "seo": entry.seo or {}, "status": entry.status,
            "published_at": entry.published_at.isoformat() if entry.published_at else None,
            "sort": entry.sort, "view_count": entry.view_count}
    item["og"] = _build_og(item)
    item["preview"] = True
    return item


def _render_preview_html(entry: models.Entry) -> str:
    """把条目渲染成完整 HTML 文档（彩排页，顶部带预览横幅）。"""
    import html as _h

    item = {"title": entry.title, "slug": entry.slug, "content": entry.content or {},
            "custom_fields": entry.custom_fields or {}, "seo": entry.seo or {}}
    og = _build_og(item)
    title = _h.escape(item.get("title") or "")
    content = item.get("content") or {}
    body_html = str(content.get("text") or content.get("html") or "")
    desc = _h.escape(str(og.get("og_description") or ""))
    img = og.get("og_image") or ""
    img_meta = f'<meta property="og:image" content="{_h.escape(img)}" />' if img else ""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>预览 · {title}</title>
<meta property="og:title" content="{title}" />
<meta property="og:description" content="{desc}" />
{img_meta}
<style>
body{{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;margin:0;color:#1f2937;background:#f3f4f6;line-height:1.75}}
.banner{{background:#6366f1;color:#fff;text-align:center;padding:8px;font-size:13px;position:sticky;top:0;z-index:10}}
.wrap{{max-width:800px;margin:24px auto;background:#fff;border-radius:12px;padding:32px 40px;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
h1{{font-size:28px;margin:0 0 8px}}
.slug{{color:#9ca3af;font-size:13px;margin-bottom:16px}}
img{{max-width:100%;border-radius:8px}}
table{{border-collapse:collapse;width:100%;margin:12px 0}}
th,td{{border:1px solid #d1d5db;padding:6px 10px}}
blockquote{{border-left:3px solid #d1d5db;padding-left:12px;color:#6b7280}}
pre{{background:#1f2937;color:#f9fafb;padding:12px;border-radius:8px;overflow:auto}}
code{{background:#f3f4f6;padding:1px 5px;border-radius:4px}}
</style>
</head>
<body>
<div class="banner">🖥 暂存预览 · 非正式页面（内容为草稿/待审核状态）</div>
<div class="wrap">
<h1>{title}</h1>
<div class="slug">{_h.escape(entry.slug or '')}</div>
<div>{body_html}</div>
</div>
</body>
</html>"""


# ============================================================
# GEO 落地页：服务端渲染的公开内容页
#
# 为什么必须有这几条路由：AI 爬虫（GPTBot / PerplexityBot / ClaudeBot）
# 抓的是 HTML 源码，既不执行 JS，也不会去调 `/api/v1/public/...` 拿 json_ld。
# 官网是纯静态站、没有文章页，`/llms.txt` 里列出去的链接只会回落到首页 ——
# 结构化数据只有写进页面本身才算数。
# ============================================================

_PAGE_CSS = """
*,*::before,*::after{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;margin:0;color:#1f2937;background:#fff;line-height:1.8;font-size:17px;-webkit-font-smoothing:antialiased}
header{border-bottom:1px solid #e5e7eb;padding:14px 20px;display:flex;align-items:center;gap:12px}
header .brand{color:#111827;text-decoration:none;font-weight:600;font-size:15px;letter-spacing:.3px}
header nav{margin-left:auto;font-size:13px}
header nav a{color:#6b7280;text-decoration:none}
main{max-width:760px;margin:0 auto;padding:36px 20px 64px}
h1{font-size:30px;line-height:1.35;margin:0 0 16px;letter-spacing:-.3px;font-weight:700}
.meta{color:#9ca3af;font-size:13px;display:flex;gap:14px;flex-wrap:wrap;align-items:center;padding-bottom:22px;border-bottom:1px solid #f3f4f6;margin-bottom:30px}
.badge{background:#eef2ff;color:#4f46e5;border-radius:999px;padding:2px 10px;font-size:12px;line-height:1.6}
.body img{max-width:100%;height:auto;border-radius:8px;display:block;margin:22px 0}
.body h2{font-size:22px;margin:36px 0 12px;line-height:1.4}
.body h3{font-size:19px;margin:28px 0 10px;line-height:1.4}
.body p{margin:0 0 18px}
.body a{color:#4f46e5}
.body ul,.body ol{padding-left:24px;margin:0 0 18px}
.body li{margin:6px 0}
.body blockquote{border-left:3px solid #d1d5db;margin:22px 0;padding:2px 0 2px 16px;color:#6b7280}
.body pre{background:#1f2937;color:#f9fafb;padding:14px;border-radius:8px;overflow:auto;font-size:14px;line-height:1.6}
.body code{background:#f3f4f6;padding:2px 6px;border-radius:4px;font-size:.92em}
.body pre code{background:none;padding:0}
.body table{border-collapse:collapse;width:100%;margin:20px 0;font-size:15px}
.body th,.body td{border:1px solid #e5e7eb;padding:8px 12px;text-align:left}
.body th{background:#f9fafb}
.body hr{border:none;border-top:1px solid #e5e7eb;margin:32px 0}
footer{max-width:760px;margin:0 auto;padding:24px 20px 56px;color:#9ca3af;font-size:13px;border-top:1px solid #f3f4f6}
footer a{color:#6b7280;text-decoration:none}
@media(max-width:640px){h1{font-size:24px}body{font-size:16px}main{padding:24px 16px 48px}}
"""


def _page_description(item: dict) -> str:
    """页面摘要：优先 SEO 字段，其次正文首段纯文本。

    `_build_og` 里 description 可能直接取 `content.text`（整段 HTML），
    塞进 meta 会带标签，这里单独算一份干净的。
    """
    seo = item.get("seo") or {}
    content = item.get("content") or {}
    desc = (
        seo.get("seo_description") or seo.get("og_description") or seo.get("description")
        or content.get("excerpt") or content.get("desc") or ""
    )
    if not desc:
        desc = _strip_html(str(content.get("text") or content.get("html") or ""), 200)
    return str(desc).strip()[:200]


def _render_page_html(
    item: dict,
    *,
    base: str,
    canonical: str,
    kind: str = "article",
    site_name: str = "Cenkor",
    site_desc: str = "",
) -> str:
    """把一条公开内容渲染成完整 HTML（含 JSON-LD / OG / 正文）。"""
    import html as _h
    import json as _json

    content = item.get("content") or {}
    body_html = str(content.get("text") or content.get("html") or "")

    title = _h.escape(str(item.get("title") or item.get("name") or ""))
    desc = _h.escape(_page_description(item) or site_desc or "")
    full_title = _h.escape(f"{item.get('title') or item.get('name') or ''} · {site_name}")

    pub = item.get("published_at")
    pub_iso, pub_text = None, ""
    if pub:
        if hasattr(pub, "isoformat"):
            pub_iso = pub.isoformat()
            pub_text = pub.strftime("%Y-%m-%d")
        else:
            pub_iso = str(pub)
            pub_text = str(pub)[:10]

    # JSON-LD：字段缺失就省略，不编造
    ld = _build_json_ld(item, url=canonical, kind=kind)
    if ld.get("image"):
        ld["image"] = _abs_url(base, str(ld["image"]))
    if pub_iso:
        ld["datePublished"] = pub_iso
    upd = item.get("updated_at")
    if upd:
        ld["dateModified"] = upd.isoformat() if hasattr(upd, "isoformat") else str(upd)
    ld["publisher"] = {"@type": "Organization", "name": site_name, "url": base}
    ld["mainEntityOfPage"] = {"@type": "WebPage", "@id": canonical}
    # 提前闭合 </script> 会截断页面
    ld_json = _json.dumps(ld, ensure_ascii=False).replace("</", "<\\/")

    og_image = _abs_url(base, (item.get("seo") or {}).get("og_image")
                        or (item.get("content") or {}).get("cover_image"))
    img_meta = (
        f'<meta property="og:image" content="{_h.escape(og_image)}" />\n'
        f'<meta name="twitter:image" content="{_h.escape(og_image)}" />\n'
        if og_image else ""
    )
    # og:video / og:video:type：正文里有 <video> 时补上。
    # 社交平台（微信、抖音、LinkedIn）抓 og:video 才会把视频渲染成可播卡片，
    # 只给 og:image 的话分享出去仍然只是一张封面图 —— 视频白做了。
    og_video = _first_video_src(item)
    video_meta = (
        f'<meta property="og:video" content="{_h.escape(og_video)}" />\n'
        f'<meta property="og:video:type" content="video/mp4" />\n'
        f'<meta property="og:video:width" content="1280" />\n'
        f'<meta property="og:video:height" content="720" />\n'
        if og_video else ""
    )
    ai_origin = item.get("ai_origin") or ("1" if item.get("ai_generated") else None)
    ai_badge = '<span class="badge">AI 辅助生成 · 已人工审核</span>' if ai_origin else ""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{full_title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{_h.escape(canonical)}">
<meta property="og:type" content="{kind}">
<meta property="og:site_name" content="{_h.escape(site_name)}">
<meta property="og:title" content="{title}" />
<meta property="og:description" content="{desc}" />
<meta property="og:url" content="{_h.escape(canonical)}" />
{f'<meta property="article:published_time" content="{pub_iso}" />' if pub_iso else ""}
{img_meta}{video_meta}<meta name="twitter:card" content="summary_large_image" />
<script type="application/ld+json">{ld_json}</script>
<style>{_PAGE_CSS}</style>
</head>
<body>
<header>
<a class="brand" href="{_h.escape(base)}/">{_h.escape(site_name)}</a>
<nav><a href="{_h.escape(base)}/">返回首页</a></nav>
</header>
<main>
<article>
<h1>{title}</h1>
<div class="meta">
{f'<time datetime="{pub_iso}">{pub_text}</time>' if pub_text else ""}
{ai_badge}
</div>
<div class="body">{body_html}</div>
</article>
</main>
<footer>
<p>{_h.escape(site_name)} · <a href="{_h.escape(base)}/llms.txt">llms.txt</a> · 本文内容可被 AI 助手检索与引用</p>
</footer>
</body>
</html>"""


def _render_404_html(base: str, site_name: str = "Cenkor") -> str:
    """内容不存在时返回 HTML 而不是 JSON —— 爬虫和用户看到的都该是个页面。"""
    import html as _h

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>内容不存在 · {_h.escape(site_name)}</title>
<meta name="robots" content="noindex">
<style>{_PAGE_CSS}</style>
</head>
<body>
<header><a class="brand" href="{_h.escape(base)}/">{_h.escape(site_name)}</a></header>
<main><h1>内容不存在</h1><p>该页面可能已下线或链接有误。</p>
<p><a href="{_h.escape(base)}/">返回首页</a></p></main>
</body>
</html>"""


async def _site_meta(db: AsyncSession) -> tuple[str, str]:
    """品牌名与站点简介（llms.txt / 页面标题共用）。"""
    rows = (await db.execute(select(models.SiteConfig))).scalars().all()
    cfg = {r.key: r.value for r in rows}
    name = str(cfg.get("brand.name") or "Cenkor")
    desc = str(cfg.get("brand.description") or cfg.get("seo.default_description") or "")
    return name, desc


async def _load_page_item(db: AsyncSession, slug: str, kind: str) -> dict | None:
    """按类型查出可用于渲染的 item（统一成 `_build_json_ld` 认识的形状）。"""
    if kind == "product":
        row = (await db.execute(
            select(models.Product).where(
                models.Product.slug == slug,
                models.Product.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        return _product_to_item(row) if row else None

    if kind == "news":
        row = (await db.execute(
            select(models.News).where(
                models.News.slug == slug,
                models.News.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        return _news_to_item(row) if row else None

    if kind == "case":
        row = (await db.execute(
            select(models.Case).where(
                models.Case.name == slug,
                models.Case.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        return _case_to_item(row) if row else None

    # article：内容引擎条目，必须已发布
    row = (await db.execute(
        select(models.Entry).where(
            models.Entry.slug == slug,
            models.Entry.status == "published",
            models.Entry.deleted_at.is_(None),
        )
    )).scalars().first()
    if not row:
        return None
    return {
        "id": row.id,
        "slug": row.slug,
        "title": row.title,
        "content": row.content or {},
        "custom_fields": row.custom_fields or {},
        "seo": row.seo or {},
        "status": row.status,
        "published_at": row.published_at,
        "updated_at": row.updated_at,
        "ai_origin": row.ai_origin,
        "ai_generated": row.ai_origin is not None,
    }


def _page_path(kind: str, slug: str) -> str:
    """公开页面路径（llms.txt / sitemap / JSON-LD 共用同一套规则）。"""
    prefix = {"product": "product", "news": "news", "case": "case"}.get(kind, "article")
    return f"/{prefix}/{slug}.html"


async def _serve_public_page(
    request: Request, db: AsyncSession, raw_slug: str, *, kind: str
) -> Response:
    base = str(request.base_url).rstrip("/")
    slug = raw_slug[:-5] if raw_slug.endswith(".html") else raw_slug
    site_name, site_desc = await _site_meta(db)
    item = await _load_page_item(db, slug, kind)
    if not item:
        return Response(
            content=_render_404_html(base, site_name),
            status_code=404,
            media_type="text/html; charset=utf-8",
        )
    canonical = f"{base}{_page_path(kind, slug)}"
    return Response(
        content=_render_page_html(
            item, base=base, canonical=canonical, kind=kind,
            site_name=site_name, site_desc=site_desc,
        ),
        media_type="text/html; charset=utf-8",
        # 内容更新要能反映到爬虫，5 分钟足够；再长会被 AI 索引成旧版
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/article/{slug}", include_in_schema=False)
async def article_page(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    """条目的公开 HTML 页（GEO 落地页）。"""
    return await _serve_public_page(request, db, slug, kind="article")


@router.get("/product/{slug}", include_in_schema=False)
async def product_page(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    return await _serve_public_page(request, db, slug, kind="product")


# 注意：这里**没有** `/news/{slug}` 的 HTML 路由。
# 该路径已被既有的新闻详情 JSON 接口占用（见文件上方 `get_public_news_detail`），
# 同一路径重复注册时先注册者胜出，后加的那个永远不会命中 —— 与其留一个
# 看着存在实则不可达的路由，不如不定义。新闻如需公开页，另起前缀。


@router.get("/case/{slug}", include_in_schema=False)
async def case_page(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    return await _serve_public_page(request, db, slug, kind="case")


@router.get("/preview/{token}", include_in_schema=False)
async def preview_entry_html(token: str, db: AsyncSession = Depends(get_db)):
    """暂存预览（完整 HTML 渲染）。"""
    entry, err = await _resolve_preview_entry(db, token)
    if not entry:
        raise HTTPException(404 if "失效" not in (err or "") else 410, err or "预览不可用")
    return Response(
        content=_render_preview_html(entry),
        media_type="text/html; charset=utf-8",
        headers={"X-Robots-Tag": "noindex"},
    )


@router.get("/media/{media_id}/thumb", include_in_schema=False)
async def media_thumbnail(
    media_id: int,
    # 上限放到 2048：正文配图要 1280 宽才够看，卡在 1024 会让 attach 进正文的图直接 422
    w: int = Query(200, ge=16, le=2048, description="缩略图宽度"),
    db: AsyncSession = Depends(get_db),
):
    """图片缩略图（M4·P3 4.4 打磨）：从云存储取原图，PIL 生成缩略图字节返回。

    公开可用（原图 URL 本就公网可读）；带 1 天缓存头。

    视频也走这里：视频生成时会同步抽一张首帧封面存成图片媒体，优先直接
    返回那张（零成本）；只有在封面缺失（抽帧失败或历史数据）时才现抽一次。
    这样列表页、分享卡片、播放器 poster 都有图可用，不必为视频单开端点。
    """
    import io

    from PIL import Image

    media = await db.get(models.Media, media_id)
    if not media or media.deleted_at:
        raise HTTPException(404, "Media not found")

    if (media.mime or "").startswith("video/"):
        media = await _video_poster_media(db, media)

    if not (media.mime or "").startswith("image/"):
        raise HTTPException(400, "非图片类型")
    try:
        data = await s3.download(media.bucket, media.key)
    except Exception as e:
        raise HTTPException(404, "文件缺失或不可读") from e
    try:
        img = Image.open(io.BytesIO(data))
        img.thumbnail((w, w), Image.LANCZOS)
        fmt = "PNG" if (media.mime or "").endswith("png") else "JPEG"
        if fmt == "JPEG" and img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, fmt, quality=82)
        buf.seek(0)
        return Response(
            content=buf.getvalue(),
            media_type=f"image/{fmt.lower()}",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except Exception as e:
        raise HTTPException(500, "缩略图生成失败") from e


async def _video_poster_media(db: AsyncSession, media: models.Media) -> models.Media:
    """取视频的封面帧媒体。

    优先用任务表里已存的 `cover_media_id` —— 生成视频时就抽好了，这里零成本。
    没有才现抽一次：下载视频、ffmpeg 抽 0.3 秒处的帧、当作临时图片处理。
    现抽只返回内存里的图片路径，不落库（一次性的兜底路径，不值得为它建表）。
    """
    from cenkor_admin.apps.cms.ai.models import CmsAiVideoJob

    job = (
        await db.execute(
            select(CmsAiVideoJob)
            .where(CmsAiVideoJob.media_id == media.id, CmsAiVideoJob.cover_media_id.is_not(None))
            .order_by(CmsAiVideoJob.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if job and job.cover_media_id:
        cover = await db.get(models.Media, job.cover_media_id)
        if cover and not cover.deleted_at:
            return cover
    raise HTTPException(404, "该视频没有封面帧")


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml(request: Request, db: AsyncSession = Depends(get_db)):
    """Sitemap 自动生成（M3·P2 3.3）：聚合已发布内容 URL。"""
    base = str(request.base_url).rstrip("/")
    urls: list[tuple[str, datetime | None]] = []

    # 内容引擎条目（含 slug 的已发布、未过期）
    entries = (await db.execute(
        select(models.Entry).where(
            models.Entry.deleted_at.is_(None),
            models.Entry.status == "published",
            models.Entry.slug.is_not(None),
            or_(models.Entry.expire_at.is_(None), models.Entry.expire_at > func.now()),
        )
    )).scalars().all()
    for e in entries:
        urls.append((f"{base}{_page_path('article', e.slug)}", e.updated_at or e.created_at))

    # 传统产品 / 新闻
    prods = (await db.execute(
        select(models.Product).where(
            models.Product.deleted_at.is_(None), models.Product.status == "published"
        )
    )).scalars().all()
    for p in prods:
        if p.slug:
            urls.append((f"{base}{_page_path('product', p.slug)}", p.updated_at or p.created_at))

    # News 表不进 sitemap：没有对应公开页（见 llms.txt 处的说明）

    items = "\n".join(
        f"  <url><loc>{loc}</loc><lastmod>{last.date().isoformat()}</lastmod></url>"
        for loc, last in urls
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{items}\n"
        "</urlset>"
    )
    return Response(content=xml, media_type="application/xml")


@router.get("/llms.txt", include_in_schema=False)
async def llms_txt(request: Request, db: AsyncSession = Depends(get_db)):
    """GEO P1-5：llms.txt —— 给 AI 爬虫/助手的内容目录（markdown，llimstxt.org 规范）。

    列出全部公开内容：标题 + 一句话摘要 + 可读 URL。与 sitemap.xml 互补：
    sitemap 给搜索引擎，llms.txt 给 ChatGPT/Perplexity 这类答案引擎。
    """
    base = str(request.base_url).rstrip("/")
    cfg_rows = (await db.execute(select(models.SiteConfig))).scalars().all()
    cfg = {r.key: r.value for r in cfg_rows}
    # SiteConfig 是扁平 KV：brand.name / brand.description / seo.default_description
    site_name = str(cfg.get("brand.name") or "Site")
    site_desc = str(cfg.get("brand.description") or cfg.get("seo.default_description") or "")

    sections: list[str] = []

    def sec(title: str, rows: list[tuple[str, str, str]]):
        if not rows:
            return
        lines = [f"## {title}", ""]
        lines += [f"- [{t}]({u})" + (f": {d}" if d else "") for t, u, d in rows]
        sections.append("\n".join(lines))

    # 内容引擎条目（按类型分组）
    cts = (await db.execute(
        select(models.ContentType).where(models.ContentType.deleted_at.is_(None))
    )).scalars().all()
    for ct in cts:
        rows_q = (await db.execute(
            select(models.Entry).where(
                models.Entry.content_type_id == ct.id,
                models.Entry.status == "published",
                models.Entry.deleted_at.is_(None),
                models.Entry.slug.is_not(None),
                or_(models.Entry.expire_at.is_(None), models.Entry.expire_at > func.now()),
            ).order_by(*order_nulls_last(models.Entry.published_at)).limit(100)
        )).scalars().all()
        sec(
            ct.name,
            [
                (
                    e.title,
                    f"{base}{_page_path('article', e.slug)}",
                    _strip_html(str((e.content or {}).get("text") or ""), 120),
                )
                for e in rows_q
            ],
        )

    prods = (await db.execute(
        select(models.Product).where(
            models.Product.deleted_at.is_(None), models.Product.status == "published"
        )
    )).scalars().all()
    # 注意分组名不能用「产品」：上面按 ContentType 遍历时，库里有个
    # content_type.name 就叫「产品」，两节同名会让 AI 助手分不清是
    # 内容条目还是产品目录。
    sec("产品目录", [
        (p.name, f"{base}{_page_path('product', p.slug)}", p.tagline or "")
        for p in prods if p.slug
    ])

    # 新闻（News 表）故意不列：该表没有对应的公开 HTML 页
    # （`/news/{slug}` 被既有 JSON 接口占用），列出来就是死链。

    cases = (await db.execute(
        select(models.Case).where(
            models.Case.deleted_at.is_(None), models.Case.status == "published"
        )
    )).scalars().all()
    sec("客户案例", [(c.name, c.href or base, c.desc or "") for c in cases if c.href])

    body = f"# {site_name}\n\n> {site_desc or ''}\n\n本站内容对 AI 助手与爬虫开放检索。\n\n"
    body += "\n\n".join(sections) + "\n"
    return Response(content=body, media_type="text/plain; charset=utf-8")


@router.get("/search", response_model=dict[str, Any])
async def search_public_entries(
    q: str = Query(..., min_length=1, description="关键词"),
    db: AsyncSession = Depends(get_db),
    content_type_key: str | None = Query(None),
    lang: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """公开全文搜索（M2·P1 2.2，仅已发布内容）。"""
    like = f"%{q}%"
    conds = [
        models.Entry.deleted_at.is_(None),
        models.Entry.status == "published",
        or_(
            models.Entry.title.ilike(like),
            models.Entry.slug.ilike(like),
            cast(models.Entry.content, Text).ilike(like),
        ),
    ]
    if content_type_key:
        ct = (await db.execute(
            select(models.ContentType).where(models.ContentType.key == content_type_key)
        )).scalar_one_or_none()
        if ct:
            conds.append(models.Entry.content_type_id == ct.id)
    total = (await db.execute(select(func.count()).select_from(models.Entry).where(*conds))).scalar() or 0
    stmt = (
        select(models.Entry).where(*conds)
        .order_by(models.Entry.published_at.desc(), models.Entry.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    entries = (await db.execute(stmt)).scalars().all()
    items = [{"id": e.id, "slug": e.slug, "title": e.title, "content": e.content or {},
              "custom_fields": e.custom_fields or {}, "seo": e.seo or {}, "status": e.status,
              "published_at": e.published_at.isoformat() if e.published_at else None,
              "sort": e.sort, "view_count": e.view_count} for e in entries]
    if lang:
        items = [await _apply_entry_translation(db, it, lang) for it in items]
    for it in items:
        it["og"] = _build_og(it)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ============================================================
# 公共模板渲染
# ============================================================

@router.post("/templates/render")
async def render_public_template(
    template: str = Body(..., embed=True),
    data: dict[str, Any] = Body(default_factory=dict, embed=True),
    site: dict[str, Any] | None = Body(default=None, embed=True),
):
    """公共模板渲染（供前台 portal-web 使用）"""
    globals_ = {
        "now": datetime.now().isoformat(),
        "site": site or {},
        "theme": {},
        "current_user": None,
    }
    globals_.update(data or {})
    rendered, error = render_template_safe(template, globals_)
    if error:
        raise HTTPException(400, f"模板渲染失败: {error}")
    return {"rendered": rendered}


# ============================================================
# RAG 检索（对外，供外部 AI 应用 / Agent 接入）
# ============================================================
@router.get("/rag", response_model=dict[str, Any], summary="RAG 检索：返回带出处的片段")
async def rag_retrieve(
    request: Request,
    q: str = Query(..., min_length=1, description="自然语言查询"),
    top_k: int = Query(5, ge=1, le=20, description="返回片段数"),
    content_type_key: str | None = Query(None, description="限定内容类型"),
    include_drafts: bool = Query(False, description="是否包含草稿（默认只检索已发布）"),
    db: AsyncSession = Depends(get_db),
):
    """对外标准 chunk 检索接口：给 query，返回最相关的片段 + 出处。

    响应里每个 hit 都带 `text`（片段正文）、`heading_path`（「文章标题 > 小节」）、
    `source_url`（出处链接），可以直接拼进 RAG 的 prompt 并附引用。

    **鉴权**：配了 `MCP_API_KEY` 就必须带（`X-MCP-Key` 或 `Authorization: Bearer`），
    与 MCP 端点同一把钥匙 —— 同一批接入方（外部 Agent）不用记两套凭据；
    没配 Key 时保持开放，与 `/public/search` 一致。
    """
    from cenkor_admin.apps.cms.ai import rag as rag_mod
    from cenkor_admin.core.config import get_settings

    settings = get_settings()
    expected = (settings.MCP_API_KEY or "").strip()
    if expected:
        provided = (request.headers.get("x-mcp-key") or "").strip()
        if not provided:
            auth = (request.headers.get("authorization") or "").strip()
            if auth.lower().startswith("bearer "):
                provided = auth[7:].strip()
        if provided != expected:
            raise HTTPException(401, "RAG 检索需要有效的 X-MCP-Key（与 MCP 端点同一把钥匙）")

    ct_id: int | None = None
    if content_type_key:
        ct = (
            await db.execute(
                select(models.ContentType).where(models.ContentType.key == content_type_key)
            )
        ).scalar_one_or_none()
        if ct is None:
            raise HTTPException(404, f"内容类型不存在: {content_type_key}")
        ct_id = ct.id

    result = await rag_mod.retrieve(
        db,
        q,
        content_type_id=ct_id,
        top_k=top_k,
        include_drafts=include_drafts,
    )
    base = str(request.base_url).rstrip("/")
    for h in result.get("hits", []):
        h["source_url"] = f"{base}{h['source_url']}" if h.get("source_url") else None
    return result


# ============================================================
# 问答式站内搜索（访客侧：带引用作答）
# ============================================================
# 访客端点必须开放（不挂 MCP Key），所以用 IP 限流兜底成本：
# 一次提问 = 一次 embedding + 一次 chat，被刷就是真金白银。
# 内存计数在多 worker 下不精确，但目的只是压住脚本刷量，不是精确计费。
_ASK_RATE: dict[str, list[float]] = {}
_ASK_RATE_MAX = 10
_ASK_RATE_WINDOW = 60.0
_ASK_RATE_SWEEP = 5000


def _ask_rate_ok(ip: str) -> bool:
    now = time.monotonic()
    hits = [t for t in _ASK_RATE.get(ip, []) if now - t < _ASK_RATE_WINDOW]
    if len(hits) >= _ASK_RATE_MAX:
        _ASK_RATE[ip] = hits
        return False
    hits.append(now)
    _ASK_RATE[ip] = hits
    if len(_ASK_RATE) > _ASK_RATE_SWEEP:
        for k in [k for k, v in _ASK_RATE.items() if not any(now - t < _ASK_RATE_WINDOW for t in v)]:
            _ASK_RATE.pop(k, None)
    return True


@router.post("/ask", response_model=dict[str, Any], summary="问答式站内搜索：带引用作答")
async def public_ask(
    request: Request,
    question: str = Body(..., embed=True, description="访客的自然语言提问"),
    content_type_key: str | None = Body(default=None, embed=True),
    top_k: int = Body(default=5, embed=True),
    db: AsyncSession = Depends(get_db),
):
    """访客提问 → 检索站内已发布内容 → 带出处作答。

    **只检索** `published`，草稿永不外泄（`include_drafts` 固定 False）。

    设计要点：
    - 检索为空时**不调 LLM**，直接返回 no_answer —— 既省钱也断了「编答案」的路
    - `citations[].source_url` 由代码从检索结果回填，模型无权生成 URL
    - 模型未配置 / 调用失败 → 降级为检索片段直出，访客至少能找到原文

    限流：同一 IP 每分钟 10 次，超了 429。
    """
    from cenkor_admin.apps.cms.ai import qa_search

    q = (question or "").strip()
    if not q:
        raise HTTPException(400, "question 不能为空")
    if len(q) > 500:
        raise HTTPException(400, "问题过长（上限 500 字）")

    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (
        request.client.host if request.client else "anon"
    )
    if not _ask_rate_ok(ip):
        raise HTTPException(429, "提问太频繁了，请稍后再试")

    ct_id: int | None = None
    if content_type_key:
        ct_id = (
            await db.execute(
                select(models.ContentType.id).where(models.ContentType.key == content_type_key)
            )
        ).scalar()
        if ct_id is None:
            raise HTTPException(404, f"内容类型不存在: {content_type_key}")

    result = await qa_search.ask(
        db,
        q,
        content_type_id=ct_id,
        top_k=max(1, min(int(top_k or 5), 10)),
        include_drafts=False,
    )

    base = str(request.base_url).rstrip("/")
    for c in result.get("citations", []):
        if c.get("source_url"):
            c["source_url"] = f"{base}{c['source_url']}"
    return result
