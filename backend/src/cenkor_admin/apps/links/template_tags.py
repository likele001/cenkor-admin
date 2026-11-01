"""链接 App 的模板标签 —— 让站点主题直接列友情链接。

主题模板里这样用：

    {% for l in links_list(category='dev', limit=8) %}
      <a href="{{ l.url }}" title="{{ l.description }}">{{ l.title }}</a>
    {% endfor %}

    <span>{{ 'https://www.cenkor.cn/doc'|link_domain }}</span>   {# cenkor.cn #}

约定（框架在启动时自动发现本文件）：
- FUNCTIONS 的函数第一个参数固定是 ctx（TemplateContext），后面才是模板传的实参
- FILTERS 走标准 Jinja 过滤器签名 fn(value, *args)，拿不到 ctx
- 只做只读查询；limit 一律夹上限，别让模板把库拖死
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select

from cenkor_admin.apps.links import models


def _clamp(value: Any, default: int, cap: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(n, cap))


def links_list(
    ctx: Any,
    category: str | None = None,
    limit: int = 10,
    only_favorite: bool = False,
) -> list[dict[str, Any]]:
    """友情链接列表，收藏优先、点击数次之。"""
    stmt = select(models.Link).where(models.Link.deleted_at.is_(None))
    if category:
        stmt = stmt.where(models.Link.category == category)
    if only_favorite:
        stmt = stmt.where(models.Link.is_favorite.is_(True))
    stmt = (
        stmt.order_by(
            models.Link.is_favorite.desc(),
            models.Link.click_count.desc(),
            models.Link.id.desc(),
        )
        .limit(_clamp(limit, 10, 50))
    )
    rows = ctx.session.execute(stmt).scalars().all()
    return [
        {
            "id": r.id,
            "title": r.title,
            "url": r.url,
            "description": r.description or "",
            "category": r.category,
            "favicon": r.favicon or "",
            "is_favorite": bool(r.is_favorite),
        }
        for r in rows
    ]


def link_domain(url: Any) -> str:
    """从 URL 取主机名，去掉 www. —— 显示来源域名用。"""
    try:
        host = urlparse(str(url or "")).netloc
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


FUNCTIONS = {
    "links_list": links_list,
}

FILTERS = {
    "link_domain": link_domain,
}
