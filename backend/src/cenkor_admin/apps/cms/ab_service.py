"""页面级 A/B 分流与计数。

分流规则：cookie `ab{entry_id}` 记住一次分配，后续访问固定同版本 ——
同一访客在两个版本间来回跳会让转化数据完全没法解释。
没有 cookie 时按 weight 随机分配，并立刻写 cookie。
"""

from __future__ import annotations

import random
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.ab_models import AbTest

COOKIE_PREFIX = "abv_"
COOKIE_MAX_AGE = 30 * 86400


def cookie_name(entry_id: int) -> str:
    return f"{COOKIE_PREFIX}{entry_id}"


async def active_test(db: AsyncSession, entry_id: int) -> AbTest | None:
    return (
        await db.execute(
            select(AbTest).where(AbTest.entry_id == entry_id, AbTest.status == "running")
        )
    ).scalars().first()


async def assign(
    db: AsyncSession, entry_id: int, cookie: str | None
) -> tuple[AbTest | None, str]:
    """返回 (测试, 版本)。没有实验时返回 (None, "a")。"""
    test = await active_test(db, entry_id)
    if test is None:
        return None, "a"
    if cookie in ("a", "b"):
        variant = cookie
    else:
        variant = "b" if random.randint(1, 100) <= max(0, min(100, test.weight)) else "a"
    # 计数用 SQL 直接加，别 read-modify-write，并发下会丢曝光
    col = "views_b" if variant == "b" else "views_a"
    await db.execute(
        update(AbTest)
        .where(AbTest.id == test.id, AbTest.site_id == test.site_id)
        .values({col: getattr(AbTest, col) + 1})
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
    return test, variant


def apply(item: dict[str, Any], test: AbTest, variant: str) -> dict[str, Any]:
    """B 版覆盖。只认白名单字段，避免把任意键塞进渲染上下文。"""
    if variant != "b":
        return item
    src = test.variant_b or {}
    out = dict(item)
    if isinstance(src.get("title"), str) and src["title"].strip():
        out["title"] = src["title"].strip()
    if isinstance(src.get("content"), dict) and src["content"]:
        out["content"] = src["content"]
    if isinstance(src.get("seo"), dict) and src["seo"]:
        out["seo"] = {**(item.get("seo") or {}), **src["seo"]}
    for k in ("seo_title", "seo_description"):
        if isinstance(src.get(k), str) and src[k].strip():
            out["seo"] = {**(out.get("seo") or {}), k.replace("seo_", ""): src[k].strip()}
    return out
