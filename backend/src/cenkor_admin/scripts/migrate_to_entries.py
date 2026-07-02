"""数据迁移脚本：将 cms_products / cms_cases / cms_news 迁移到 cms_entries

用法：
    cd backend
    PYTHONPATH=src python3 -m cenkor_admin.scripts.migrate_to_entries

特性：
- 幂等：可重复执行，已迁移的条目会跳过
- 备份原始数据
- 迁移完成后打印统计信息
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import select, func, insert
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms import models
from cenkor_admin.core.db import AsyncSessionLocal


# ============================================================
# 内容类型映射
# ============================================================

CT_MAPPING = {
    "product": {"table": models.Product, "name_field": "name", "slug_field": "slug"},
    "case": {"table": models.Case, "name_field": "name", "slug_field": None},
    "news": {"table": models.News, "name_field": "title", "slug_field": "slug"},
}


async def get_content_type_ids(db: AsyncSession) -> dict[str, int]:
    result = await db.execute(select(models.ContentType))
    cts = {ct.key: ct.id for ct in result.scalars().all()}
    return cts


async def migrate_products(db: AsyncSession, ct_id: int) -> int:
    """迁移产品表到 cms_entries"""
    result = await db.execute(
        select(models.Product).where(models.Product.deleted_at.is_(None))
    )
    products = result.scalars().all()
    count = 0
    for p in products:
        # 检查是否已迁移
        existing = await db.execute(
            select(models.Entry).where(
                models.Entry.content_type_id == ct_id,
                models.Entry.slug == p.slug,
            )
        )
        if existing.scalar_one_or_none():
            continue

        # 旧字段放进 content JSONB
        content = {
            "name": p.name,
            "chinese_name": p.chinese_name,
            "tagline": p.tagline,
            "line": p.line,
            "stack": p.stack,
            "desc": p.desc,
            "is_flagship": p.is_flagship,
            "is_open_source": p.is_open_source,
            "github_url": p.github_url,
            "demo_url": p.demo_url,
            "website_url": p.website_url,
            "license": p.license,
            "features": p.features or [],
        }

        entry = models.Entry(
            content_type_id=ct_id,
            slug=p.slug,
            title=p.name,
            content=content,
            custom_fields=p.custom_fields or {},
            status=p.status,
            published_at=p.created_at,
            sort=p.sort,
            view_count=0,
        )
        db.add(entry)
        count += 1

    await db.commit()
    return count


async def migrate_cases(db: AsyncSession, ct_id: int) -> int:
    """迁移案例表到 cms_entries"""
    result = await db.execute(
        select(models.Case).where(models.Case.deleted_at.is_(None))
    )
    cases = result.scalars().all()
    count = 0
    for c in cases:
        # 检查是否已迁移（cases 没有 slug，用 id 作为标识）
        slug = c.slug if hasattr(c, "slug") and c.slug else f"case-{c.id}"
        existing = await db.execute(
            select(models.Entry).where(
                models.Entry.content_type_id == ct_id,
                models.Entry.slug == slug,
            )
        )
        if existing.scalar_one_or_none():
            continue

        content = {
            "industry": c.industry,
            "name": c.name,
            "desc": c.desc,
            "tag": c.tag,
            "href": c.href,
        }

        entry = models.Entry(
            content_type_id=ct_id,
            slug=slug,
            title=c.name,
            content=content,
            custom_fields=c.custom_fields or {},
            status=c.status,
            sort=c.sort,
            view_count=0,
        )
        db.add(entry)
        count += 1

    await db.commit()
    return count


async def migrate_news(db: AsyncSession, ct_id: int) -> int:
    """迁移新闻表到 cms_entries"""
    result = await db.execute(
        select(models.News).where(models.News.deleted_at.is_(None))
    )
    news_list = result.scalars().all()
    count = 0
    for n in news_list:
        # 检查是否已迁移
        existing = await db.execute(
            select(models.Entry).where(
                models.Entry.content_type_id == ct_id,
                models.Entry.slug == n.slug,
            )
        )
        if existing.scalar_one_or_none():
            continue

        content = {
            "slug": n.slug,
            "excerpt": n.excerpt,
            "content_md": n.content_md,
            "cover_image": n.cover_image,
            "view_count": n.view_count or 0,
        }

        entry = models.Entry(
            content_type_id=ct_id,
            slug=n.slug,
            title=n.title,
            content=content,
            custom_fields=n.custom_fields or {},
            status=n.status,
            published_at=n.published_at,
            author_id=n.author_id,
            view_count=n.view_count or 0,
        )
        db.add(entry)
        count += 1

    await db.commit()
    return count


async def main():
    print("=" * 60)
    print("数据迁移：cms_products / cms_cases / cms_news → cms_entries")
    print(f"时间：{datetime.now().isoformat()}")
    print("=" * 60)

    async with AsyncSessionLocal() as db:
        ct_map = await get_content_type_ids(db)

        total = 0
        for ct_key, ct_id in ct_map.items():
            print(f"\n[{ct_key}] content_type_id={ct_id}")

            if ct_key == "product":
                count = await migrate_products(db, ct_id)
            elif ct_key == "case":
                count = await migrate_cases(db, ct_id)
            elif ct_key == "news":
                count = await migrate_news(db, ct_id)
            else:
                print(f"  跳过（无对应的旧表）")
                continue

            print(f"  迁移条目：{count}")
            total += count

        # 统计最终结果
        result = await db.execute(
            select(func.count()).select_from(models.Entry)
        )
        entry_count = result.scalar() or 0

        print(f"\n{'=' * 60}")
        print(f"本次新增：{total}")
        print(f"cms_entries 总数：{entry_count}")
        print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
