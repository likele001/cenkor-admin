"""CMS App · 公开接口（公网站点读取，无需鉴权）"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms import models
from cenkor_admin.core.compat import order_nulls_last
from cenkor_admin.core.db import AsyncSessionLocal, get_db
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
                  "custom_fields": e.custom_fields or {}, "status": e.status,
                  "published_at": e.published_at.isoformat() if e.published_at else None,
                  "sort": e.sort, "view_count": e.view_count} for e in entries]

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/site/{content_type_key}/{id_or_slug}", response_model=dict[str, Any])
async def get_public_entry_detail(
    content_type_key: str,
    id_or_slug: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """获取公开内容详情（自动路由到对应专用表）"""
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
        return _product_to_item(p)
    elif content_type_key == "case":
        if id_or_slug.isdigit():
            c = (await db.execute(select(models.Case).where(models.Case.id == int(id_or_slug)))).scalar_one_or_none()
        else:
            c = (await db.execute(select(models.Case).where(models.Case.name == id_or_slug))).scalar_one_or_none()
        if not c:
            raise HTTPException(404, "Case not found")
        return _case_to_item(c)
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
        return _news_to_item(n)
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
        return {"id": entry.id, "slug": entry.slug, "title": entry.title, "content": entry.content or {},
                "custom_fields": entry.custom_fields or {}, "status": entry.status,
                "published_at": entry.published_at.isoformat() if entry.published_at else None,
                "sort": entry.sort, "view_count": (entry.view_count or 0) + 1}


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
    return {
        "id": n.id, "slug": n.slug, "title": n.title, "excerpt": n.excerpt,
        "content_md": n.content_md, "cover_image": n.cover_image,
        "published_at": n.published_at.isoformat() if n.published_at else None,
        "view_count": view_count,
    }


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
