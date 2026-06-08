"""CMS App · 公开接口（公网站点读取，无需鉴权）"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms import models
from cenkor_admin.core.compat import order_nulls_last
from cenkor_admin.core.db import AsyncSessionLocal, get_db

router = APIRouter()


async def _increment_news_view_count(news_id: int) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(models.News)
            .where(models.News.id == news_id)
            .values(view_count=models.News.view_count + 1)
        )
        await session.commit()


@router.get("/site", response_model=dict[str, Any], summary="公开站点数据（公网/官网读取）")
async def get_public_site_data(db: AsyncSession = Depends(get_db)):
    """一次性返回官网需要的全部内容：站点配置 + 产品 + 案例。

    公网站点（cenkor.cn）只调这一个端点，简化前端逻辑。
    """
    # 站点配置（KV）
    cfg_result = await db.execute(select(models.SiteConfig))
    site_config = {s.key: s.value for s in cfg_result.scalars().all()}

    # 产品（已发布，按 sort 排序）
    prod_result = await db.execute(
        select(models.Product)
        .where(models.Product.deleted_at.is_(None), models.Product.status == "published")
        .order_by(models.Product.sort, models.Product.id)
    )
    products = [
        {
            "key": p.slug,
            "name": p.name,
            "chineseName": p.chinese_name,
            "tagline": p.tagline,
            "line": p.line,
            "stack": p.stack,
            "desc": p.desc,
            "features": p.features or [],
            "isFlagship": p.is_flagship,
            "isOpenSource": p.is_open_source,
            "github": p.github_url,
            "demo": p.demo_url,
            "website": p.website_url,
            "license": p.license,
        }
        for p in prod_result.scalars().all()
    ]

    # 案例
    case_result = await db.execute(
        select(models.Case)
        .where(models.Case.deleted_at.is_(None), models.Case.status == "published")
        .order_by(models.Case.sort, models.Case.id)
    )
    cases = [
        {
            "industry": c.industry,
            "name": c.name,
            "desc": c.desc,
            "tag": c.tag,
            "href": c.href,
        }
        for c in case_result.scalars().all()
    ]

    return {
        "site_config": site_config,
        "products": products,
        "cases": cases,
    }


@router.get("/products", response_model=list[dict[str, Any]], summary="公开产品列表")
async def get_public_products(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(models.Product)
        .where(models.Product.deleted_at.is_(None), models.Product.status == "published")
        .order_by(models.Product.sort, models.Product.id)
    )
    return [
        {
            "key": p.slug,
            "name": p.name,
            "chineseName": p.chinese_name,
            "tagline": p.tagline,
            "line": p.line,
            "stack": p.stack,
            "desc": p.desc,
            "features": p.features or [],
            "isFlagship": p.is_flagship,
            "isOpenSource": p.is_open_source,
            "github": p.github_url,
            "demo": p.demo_url,
            "website": p.website_url,
            "license": p.license,
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
        {
            "industry": c.industry,
            "name": c.name,
            "desc": c.desc,
            "tag": c.tag,
            "href": c.href,
        }
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
            "id": n.id,
            "slug": n.slug,
            "title": n.title,
            "excerpt": n.excerpt,
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
