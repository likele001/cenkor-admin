"""模板数据 API（16 个白名单函数）

模板里只能调这里的方法，拿不到任何 ORM 对象或 session。

为什么是同步的：
Jinja 渲染本身是同步调用，渲染又放在 executor 线程里跑，
所以这里直接用同步 engine（settings.DATABASE_URL_SYNC，Alembic 同一个），
不去 await 主事件循环，自然没有死锁风险。
"""
from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from cenkor_admin.apps.cms import models, url_resolver

__all__ = ["TemplateContext", "build_pagination", "cms_api", "get_session_factory"]

_engine = None
_factory: sessionmaker | None = None
_lock = threading.Lock()


def get_session_factory() -> sessionmaker:
    """懒建同步 engine：第一次渲染时才连库，避免启动就多一个连接池。"""
    global _engine, _factory
    if _factory is None:
        with _lock:
            if _factory is None:
                from cenkor_admin.core.config import get_settings

                s = get_settings()
                kwargs: dict[str, Any] = {"pool_pre_ping": True, "future": True}
                if not s.DATABASE_URL_SYNC.startswith("sqlite"):
                    kwargs["pool_size"] = 4
                    kwargs["max_overflow"] = 4
                _engine = create_engine(s.DATABASE_URL_SYNC, **kwargs)
                _factory = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False, future=True)
    return _factory


def cms_api(fn):
    """标记为模板可调用。CmsSandbox.is_safe_callable 只认这个属性。"""
    fn.__cms_api__ = True
    return fn


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _plain(text: Any, limit: int = 0) -> str:
    import re

    if not text:
        return ""
    raw = re.sub(r"<[^>]+>", "", str(text))
    raw = re.sub(r"\s+", " ", raw).strip()
    if limit and len(raw) > limit:
        return raw[:limit] + "…"
    return raw


def _body_html(content: dict) -> str:
    """正文 HTML：优先用存好的 html，退回 markdown 渲染。"""
    if not content:
        return ""
    html = content.get("html")
    if html:
        return str(html)
    text = content.get("text") or content.get("content_md")
    if not text:
        return ""
    from cenkor_admin.core.jinja_env import _f_markdown

    return str(_f_markdown(text))


PAGE_PREFIX = {"product": "product", "news": "news", "case": "case", "article": "article", "page": "p"}


def page_url(base_path: str, n: int) -> str:
    """第 N 页的地址。第 1 页就是列表基路径本身，不给 `/page/1/` 留一份重复内容。"""
    base = "/" + (base_path or "/").strip("/")
    base = base + "/" if base != "/" else "/"
    return base if int(n or 1) <= 1 else f"{base}page/{int(n)}/"


def absolutize_pagination(pg: dict, base: str) -> dict:
    """build_pagination 只产出相对路径（它不该知道站点域名），这里补成可用 href。"""
    prefix = (base or "").rstrip("/")
    for k in ("url", "first_url", "last_url", "prev_url", "next_url"):
        if pg.get(k):
            pg[k] = f"{prefix}{pg[k]}"
    for p in pg.get("pages") or []:
        if p.get("url"):
            p["url"] = f"{prefix}{p['url']}"
    return pg


def build_pagination(
    page: int = 1,
    total: int = 0,
    per_page: int = 20,
    window: int = 5,
    base_path: str | None = None,
) -> dict[str, Any]:
    """分页对象。纯函数，模板 API 与列表页路由共用同一份算法，避免两处算出不同的页码。

    base_path 传列表基路径（如 `/article/`）时会额外生成 url / prev_url / next_url /
    pages，模板直接拿去当 href。不传则这些字段为 None / 空，老模板用 `?page=N`
    自己拼也不会炸 —— 纯函数不该强制要求调用方知道 URL 长什么样。
    """
    page = max(1, int(page or 1))
    per_page = max(1, int(per_page or 20))
    total = max(0, int(total or 0))
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    half = max(1, window // 2)
    start = max(1, page - half)
    end = min(total_pages, start + window - 1)
    start = max(1, end - window + 1)

    def _url(n: int) -> str | None:
        return page_url(base_path, n) if base_path else None

    out = {
        "page": page, "per_page": per_page, "total": total,
        "total_pages": total_pages, "window": list(range(start, end + 1)),
        "has_prev": page > 1, "has_next": page < total_pages,
        "prev_page": page - 1 if page > 1 else None,
        "next_page": page + 1 if page < total_pages else None,
        "range_start": 0 if total == 0 else (page - 1) * per_page + 1,
        "range_end": min(page * per_page, total),
        "url": _url(page),
        "first_url": _url(1),
        "last_url": _url(total_pages),
        "prev_url": _url(page - 1) if page > 1 else None,
        "next_url": _url(page + 1) if page < total_pages else None,
        "pages": [
            {"n": n, "url": _url(n), "current": n == page}
            for n in range(start, end + 1)
        ],
    }
    return out

_SORT_FIELDS = {
    "published_at": "published_at",
    "updated_at": "updated_at",
    "created_at": "created_at",
    "sort": "sort",
    "view_count": "view_count",
    "id": "id",
}


class TemplateContext:
    """一次渲染一个实例，绑定站点 + 同步 session。"""

    def __init__(self, session: Session, *, site_id: int = 1, base: str = "") -> None:
        self.session = session
        self.site_id = int(site_id or 1)
        self.base = (base or "").rstrip("/")
        # content_type_id → key 的懒加载缓存，一次渲染里最多查一次
        self._ct_keys: dict[int, str] | None = None
        # URL 规则集，同样一次渲染只取一次
        self._rules = None

    # ------------------------------------------------------------ 内部

    def _type_key(self, type_key: str) -> str:
        return (type_key or "article").strip().lower()

    def url_rules(self) -> url_resolver.RuleSet:
        """本站在用的 URL 规则。一次渲染只加载一次。"""
        if self._rules is None:
            self._rules = url_resolver.load_rules_sync(self.session, self.site_id)
        return self._rules

    def _catdir(self, category: Any) -> str | None:
        """栏目从根到自身的目录链（`hangye/xinwen`）。

        层级上限 6 和 permalink 里 `{catdir}` 的正则保持一致。
        脏数据里如果有循环父级，靠 guard 断掉而不是死循环。
        """
        if category is None:
            return None
        parts: list[str] = []
        cur = category
        guard = 0
        while cur is not None and guard < 6:
            slug = getattr(cur, "slug", None)
            if not slug:
                break
            parts.append(str(slug))
            cur = getattr(cur, "parent", None)
            guard += 1
        return "/".join(reversed(parts)) or None

    def _type_keys(self) -> dict[int, str]:
        if self._ct_keys is None:
            rows = self.session.execute(
                select(models.ContentType.id, models.ContentType.key)
            ).all()
            self._ct_keys = dict(rows)
        return self._ct_keys

    def _content_type(self, type_key: str):
        return (
            self.session.execute(
                select(models.ContentType).where(models.ContentType.key == self._type_key(type_key))
            )
            .scalars()
            .first()
        )

    def _entry_card(self, row: models.Entry, *, with_body: bool = False) -> dict[str, Any]:
        content = dict(row.content or {})
        seo = dict(row.seo or {})
        category = row.category
        # 卡片 URL 按条目自己的内容类型拼：case/news 的条目也走 Entry 表，
        # 一律当 article 会把 /case/xxx.html 写成 /article/xxx.html
        ct_key = self._type_keys().get(row.content_type_id) or "article"
        card = {
            "id": row.id,
            "type": ct_key,
            "slug": row.slug,
            "title": row.title,
            "excerpt": seo.get("description") or _plain(content.get("text") or content.get("html"), 160),
            "cover": content.get("cover_image") or seo.get("og_image"),
            "url": self.url(
                ct_key,
                row.slug,
                catdir=self._catdir(category),
                cat=category.slug if category is not None else None,
                entry_id=row.id,
                category_id=category.id if category is not None else None,
                published=row.published_at,
                url_path=row.url_path,
            ),
            "published_at": _iso(row.published_at),
            "updated_at": _iso(row.updated_at),
            "view_count": row.view_count or 0,
            "sort": row.sort or 0,
            "ai_generated": row.ai_origin is not None,
            "content": content,
            "custom_fields": dict(row.custom_fields or {}),
            "seo": seo,
            "category": (
                {
                    "id": category.id,
                    "slug": category.slug,
                    "name": category.name,
                    "url": self.url(
                        "category",
                        category.slug,
                        catdir=self._catdir(category),
                        category_id=category.id,
                    ),
                }
                if category is not None else None
            ),
            "tags": [],
        }
        if with_body:
            card["body_html"] = _body_html(content)
        return card

    def _attach_tags(self, cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ids = [c["id"] for c in cards if c.get("type") == "article" and c.get("id")]
        if not ids:
            return cards
        rows = self.session.execute(
            select(models.ContentTag.content_id, models.Tag.name, models.Tag.slug)
            .join(models.Tag, models.Tag.id == models.ContentTag.tag_id)
            .where(models.ContentTag.content_id.in_(ids))
        ).all()
        bucket: dict[int, list[str]] = {}
        for cid, name, _slug in rows:
            bucket.setdefault(cid, []).append(name)
        for card in cards:
            if card.get("type") == "article":
                card["tags"] = bucket.get(card["id"], [])
        return cards

    def _product_card(self, row: models.Product) -> dict[str, Any]:
        return {
            "id": row.id, "type": "product", "slug": row.slug, "title": row.name,
            "excerpt": _plain(row.tagline or row.desc, 160),
            "cover": None, "url": self.url("product", row.slug, entry_id=row.id),
            "published_at": None, "updated_at": None,
            "view_count": 0, "sort": row.sort or 0, "ai_generated": False,
            "content": {
                "tagline": row.tagline, "line": row.line, "stack": row.stack,
                "desc": row.desc, "features": row.features or [],
                "chinese_name": row.chinese_name,
            },
            "custom_fields": dict(row.custom_fields or {}),
            "seo": {}, "category": None, "tags": [],
            "is_flagship": row.is_flagship, "is_open_source": row.is_open_source,
            "github": row.github_url, "demo": row.demo_url,
            "website": row.website_url, "license": row.license,
        }

    def _news_card(self, row: models.News) -> dict[str, Any]:
        return {
            "id": row.id, "type": "news", "slug": row.slug, "title": row.title,
            "excerpt": row.excerpt or _plain(row.content_md, 160),
            "cover": row.cover_image, "url": self.url("news", row.slug, entry_id=row.id),
            "published_at": _iso(row.published_at), "updated_at": None,
            "view_count": row.view_count or 0, "sort": 0, "ai_generated": False,
            "content": {"excerpt": row.excerpt, "text": row.content_md, "cover_image": row.cover_image},
            "custom_fields": dict(row.custom_fields or {}),
            "seo": {}, "category": None, "tags": [],
        }

    def _case_card(self, row: models.Case) -> dict[str, Any]:
        return {
            "id": row.id, "type": "case", "slug": row.name, "title": row.name,
            "excerpt": _plain(row.desc, 160), "cover": None,
            "url": self.url("case", row.name, entry_id=row.id),
            "published_at": None, "updated_at": None,
            "view_count": 0, "sort": row.sort or 0, "ai_generated": False,
            "content": {"industry": row.industry, "desc": row.desc, "tag": row.tag, "href": row.href},
            "custom_fields": dict(row.custom_fields or {}),
            "seo": {}, "category": None, "tags": [],
        }

    # ------------------------------------------------------------ 1. content_list

    @cms_api
    def content_list(
        self,
        type: str = "article",
        limit: int = 20,
        offset: int = 0,
        category: str | None = None,
        tag: str | None = None,
        sort: str = "-published_at",
        exclude: int | None = None,
    ) -> list[dict[str, Any]]:
        """按类型取条目列表。limit 上限 100，防止模板一次拉爆。"""
        limit = max(1, min(int(limit or 20), 100))
        offset = max(0, int(offset or 0))
        kind = self._type_key(type)

        if kind == "product":
            # 产品有独立目录表，和 /product/{slug}.html 同源，不走内容引擎
            stmt = (
                select(models.Product)
                .where(
                    models.Product.site_id == self.site_id,
                    models.Product.deleted_at.is_(None),
                    models.Product.status == "published",
                )
                .order_by(models.Product.sort.asc(), models.Product.id.desc())
            )
            rows = self.session.execute(stmt.limit(limit).offset(offset)).scalars().all()
            return [self._product_card(r) for r in rows]

        cards = self._entries_of(kind, limit, offset, category, tag, sort, exclude)
        if cards or kind not in ("news", "case"):
            return cards

        # case / news 在内容引擎里一条都没有时，兜底查传统表。
        # News 表目前是空的、Case 表没有 slug 列，正常情况下走不到这里。
        model = models.News if kind == "news" else models.Case
        stmt = select(model).where(
            model.site_id == self.site_id,
            model.deleted_at.is_(None),
            model.status == "published",
        )
        if kind == "news":
            stmt = stmt.order_by(model.published_at.desc().nullslast(), model.id.desc())
        else:
            stmt = stmt.order_by(model.sort.asc(), model.id.desc())
        rows = self.session.execute(stmt.limit(limit).offset(offset)).scalars().all()
        builder = self._news_card if kind == "news" else self._case_card
        return [builder(r) for r in rows]

    def _entries_of(
        self,
        kind: str,
        limit: int,
        offset: int,
        category: str | None,
        tag: str | None,
        sort: str,
        exclude: int | None,
    ) -> list[dict[str, Any]]:
        """内容引擎条目查询（article / case / news 共用一套）。"""
        ct = self._content_type(kind)
        if ct is None:
            return []
        stmt = select(models.Entry).where(
            models.Entry.site_id == self.site_id,
            models.Entry.content_type_id == ct.id,
            models.Entry.status == "published",
            models.Entry.deleted_at.is_(None),
            or_(models.Entry.expire_at.is_(None), models.Entry.expire_at > datetime.now(tz=UTC)),
        )
        if category:
            cat = self.session.execute(
                select(models.Category).where(
                    models.Category.site_id == self.site_id,
                    models.Category.slug == category,
                )
            ).scalars().first()
            if cat is None:
                return []
            stmt = stmt.where(models.Entry.category_id == cat.id)
        if tag:
            sub = (
                select(models.ContentTag.content_id)
                .join(models.Tag, models.Tag.id == models.ContentTag.tag_id)
                .where(models.Tag.slug == tag)
            )
            stmt = stmt.where(models.Entry.id.in_(sub))
        if exclude:
            stmt = stmt.where(models.Entry.id != int(exclude))

        desc = sort.startswith("-")
        field = _SORT_FIELDS.get(sort.lstrip("-"), "published_at")
        col = getattr(models.Entry, field, models.Entry.published_at)
        stmt = stmt.order_by(col.desc().nullslast() if desc else col.asc().nullsfirst(), models.Entry.id.desc())
        rows = self.session.execute(stmt.limit(limit).offset(offset)).scalars().all()
        cards = [self._entry_card(r) for r in rows]
        return self._attach_tags(cards)

    # ------------------------------------------------------------ 2. content

    @cms_api
    def content(self, type: str = "article", slug: str = "") -> dict[str, Any] | None:
        """取单条详情，含 body_html。"""
        if not slug:
            return None
        kind = self._type_key(type)
        if kind == "product":
            row = self.session.execute(
                select(models.Product).where(
                    models.Product.slug == slug, models.Product.deleted_at.is_(None)
                )
            ).scalars().first()
            if row is None:
                return None
            card = self._product_card(row)
            card["body_html"] = _body_html(card["content"])
            return card

        ct = self._content_type(kind) if kind else None
        if ct is not None:
            row = self.session.execute(
                select(models.Entry).where(
                    models.Entry.site_id == self.site_id,
                    models.Entry.content_type_id == ct.id,
                    models.Entry.slug == slug,
                    models.Entry.status == "published",
                    models.Entry.deleted_at.is_(None),
                )
            ).scalars().first()
            if row is not None:
                card = self._entry_card(row, with_body=True)
                return self._attach_tags([card])[0]
            if kind not in ("news", "case"):
                return None

        # case / news 兜底：传统表（News 表为空、Case 表用中文名当 key）
        model = models.News if kind == "news" else models.Case
        key_col = model.name if kind == "case" else model.slug
        row = self.session.execute(
            select(model).where(key_col == slug, model.deleted_at.is_(None))
        ).scalars().first()
        if row is None:
            return None
        card = (self._news_card if kind == "news" else self._case_card)(row)
        card["body_html"] = _body_html(card["content"])
        return card

    # ------------------------------------------------------------ 3. related

    @cms_api
    def related(self, item: Any, limit: int = 4) -> list[dict[str, Any]]:
        """相关推荐：同分类优先，不够用同类型最新补齐。"""
        limit = max(1, min(int(limit or 4), 12))
        if not isinstance(item, dict):
            return []
        kind = item.get("type") or "article"
        cat = item.get("category") or {}
        out: list[dict[str, Any]] = []
        if cat.get("slug"):
            out = self.content_list(kind, limit=limit, category=cat["slug"], exclude=item.get("id"))
        if len(out) < limit:
            seen = {c["id"] for c in out} | {item.get("id")}
            extra = self.content_list(kind, limit=limit * 2)
            out.extend([c for c in extra if c["id"] not in seen][: limit - len(out)])
        return out

    # ------------------------------------------------------------ 4. search

    @cms_api
    def search(self, kw: str = "", limit: int = 20, page: int = 1) -> dict[str, Any]:
        """全站搜索（标题 + 正文 ILIKE）。P0 够用，后续接 pgvector 语义检索。"""
        kw = (kw or "").strip()
        limit = max(1, min(int(limit or 20), 50))
        page = max(1, int(page or 1))
        if not kw:
            return {"items": [], "total": 0, "page": page, "total_pages": 0, "kw": kw}
        like = f"%{kw}%"
        base = select(models.Entry).where(
            models.Entry.site_id == self.site_id,
            models.Entry.status == "published",
            models.Entry.deleted_at.is_(None),
            or_(
                models.Entry.title.ilike(like),
                models.Entry.slug.ilike(like),
            ),
        )
        total = self.session.execute(select(func.count()).select_from(base.subquery())).scalar_one()
        rows = self.session.execute(
            base.order_by(models.Entry.published_at.desc().nullslast())
            .limit(limit)
            .offset((page - 1) * limit)
        ).scalars().all()
        cards = self._attach_tags([self._entry_card(r) for r in rows])
        return {
            "items": cards,
            "total": int(total or 0),
            "page": page,
            "per_page": limit,
            "total_pages": (int(total or 0) + limit - 1) // limit,
            "kw": kw,
        }

    # ------------------------------------------------------------ 5. categories

    @cms_api
    def categories(self, type: str = "article") -> list[dict[str, Any]]:
        ct = self._content_type(type)
        if ct is None:
            return []
        rows = self.session.execute(
            select(models.Category)
            .where(
                models.Category.site_id == self.site_id,
                models.Category.content_type_id == ct.id,
                models.Category.status == "active",
            )
            .order_by(models.Category.sort.asc(), models.Category.id.asc())
        ).scalars().all()
        counts = dict(
            self.session.execute(
                select(models.Entry.category_id, func.count(models.Entry.id))
                .where(
                    models.Entry.site_id == self.site_id,
                    models.Entry.content_type_id == ct.id,
                    models.Entry.status == "published",
                    models.Entry.deleted_at.is_(None),
                )
                .group_by(models.Entry.category_id)
            ).all()
        )
        return [
            {
                "id": r.id, "slug": r.slug, "name": r.name, "icon": r.icon,
                "color": r.color, "parent_id": r.parent_id,
                "count": int(counts.get(r.id, 0)),
                "url": self.url(
                    "category", r.slug, catdir=self._catdir(r), category_id=r.id
                ),
            }
            for r in rows
        ]

    # ------------------------------------------------------------ 6. category_tree

    @cms_api
    def category_tree(self, type: str = "article") -> list[dict[str, Any]]:
        flat = self.categories(type)
        by_id = {c["id"]: {**c, "children": []} for c in flat}
        roots: list[dict[str, Any]] = []
        for node in by_id.values():
            parent = by_id.get(node.get("parent_id"))
            (parent["children"] if parent else roots).append(node)
        return roots

    # ------------------------------------------------------------ 7. tags

    @cms_api
    def tags(self, type: str = "article", limit: int = 50) -> list[dict[str, Any]]:
        ct = self._content_type(type)
        if ct is None:
            return []
        limit = max(1, min(int(limit or 50), 200))
        rows = self.session.execute(
            select(models.Tag)
            .where(models.Tag.site_id == self.site_id, models.Tag.content_type_id == ct.id)
            .order_by(models.Tag.id.asc())
            .limit(limit)
        ).scalars().all()
        return [
            {"id": r.id, "slug": r.slug, "name": r.name, "color": r.color,
             "url": self.url("tag", r.slug, entry_id=r.id)}
            for r in rows
        ]

    # ------------------------------------------------------------ 8. nav

    @cms_api
    def nav(self, key: str = "main") -> list[dict[str, Any]]:
        """菜单：优先读站点配置 nav.<key>，没有就用顶部分类兜底。"""
        cfg = self._site_config()
        raw = cfg.get(f"nav.{key}") or cfg.get("nav") or None
        if isinstance(raw, list) and raw:
            return [
                {
                    "label": str(item.get("label") or item.get("name") or ""),
                    "url": str(item.get("url") or "#"),
                    "target": item.get("target") or "_self",
                    "children": item.get("children") or [],
                }
                for item in raw
                if isinstance(item, dict)
            ]
        cats = [c for c in self.categories("article") if not c.get("parent_id")]
        return [{"label": c["name"], "url": c["url"], "target": "_self", "children": []} for c in cats]

    # ------------------------------------------------------------ 9. site

    @cms_api
    def site_meta(self, key: str | None = None) -> Any:
        """站点设置。不传 key 返回全部，传 key 返回扁平值（brand.name 用点号）。

        模板里更常用的是 ``{{ site.name }}`` —— 那走的是 as_globals 里预注入的
        同名 dict，不是这个函数。
        """
        data = self._site_dict()
        if key:
            return data.get(key)
        return data

    def _site_dict(self) -> dict[str, Any]:
        if getattr(self, "_site_cache", None) is not None:
            return self._site_cache
        data: dict[str, Any] = {}
        row = self.session.execute(
            select(models.Site).where(models.Site.id == self.site_id)
        ).scalars().first()
        if row is not None:
            data.update({
                "id": row.id, "key": row.key, "name": row.name, "kind": row.kind,
                "domain": row.domain, "locale": row.locale, "site_mode": row.site_mode,
                "geo": row.geo or {},
            })
            data.update(row.settings or {})
            data.update({f"seo.{k}": v for k, v in (row.seo_defaults or {}).items()})
        data.update(self._site_config())
        data["base_url"] = self.base
        self._site_cache = data
        return data

    def _site_config(self) -> dict[str, Any]:
        rows = self.session.execute(select(models.SiteConfig)).scalars().all()
        return {r.key: r.value for r in rows}

    # ------------------------------------------------------------ 10. pagination

    @cms_api
    def pagination(self, page: int = 1, total: int = 0, per_page: int = 20, window: int = 5,
                   base_path: str | None = None) -> dict[str, Any]:
        """分页对象。传 base_path（如 `/article/`）才会生成可点的翻页链接。"""
        pg = build_pagination(page, total, per_page, window, base_path=base_path)
        return absolutize_pagination(pg, self.base) if base_path else pg

    # ------------------------------------------------------------ 11. asset

    @cms_api
    def asset(self, path: str = "") -> str:
        if not path:
            return self.base + "/"
        p = str(path)
        if p.startswith(("http://", "https://", "//", "data:")):
            return p
        return f"{self.base}/{p.lstrip('/')}"

    # ------------------------------------------------------------ 12. url

    @cms_api
    def url(
        self,
        kind: str = "home",
        slug: str | None = None,
        page: int | None = None,
        *,
        catdir: str | None = None,
        cat: str | None = None,
        entry_id: int | None = None,
        category_id: int | None = None,
        published: datetime | None = None,
        url_path: str | None = None,
    ) -> str:
        """按后台配置的 URL 规则生成地址。

        规则优先级：手填路径 > 栏目规则 > 站点默认 > 内置兜底，
        细节见 ``apps/cms/url_resolver.py``。

        ``catdir`` 要传栏目从根到自身的完整链（``hangye/xinwen``）：规则里
        一旦用到 ``{catdir}``，只给 slug 是拼不出正确地址的。模板里直接用
        ``url('article', 'x')`` 仍然可用，只是走站点默认规则。
        """
        kind = (kind or "home").strip().lower()
        if kind == "home":
            return f"{self.base}/" if self.base else "/"
        if kind == "search":
            q = f"?kw={slug}" if slug else ""
            tail = f"&page={page}" if page else ""
            # 带尾斜杠：/search 是 JSON 接口，HTML 搜索页在 /search/
            return f"{self.base}/search/{q}{tail}"

        rules = self.url_rules()

        if kind == "category":
            path = url_resolver.category_url(
                rules,
                slug=slug or "",
                catdir=catdir,
                category_id=category_id,
                page=page or 1,
            )
            return f"{self.base}{path}"

        if kind == "tag":
            path = url_resolver.tag_url(rules, slug=slug or "", page=page or 1)
            return f"{self.base}{path}"

        if not slug:
            # 列表页翻页走路径式：/article/page/2/，不是 ?page=2
            return f"{self.base}{url_resolver.list_url(rules, kind, page or 1)}"

        # 详情页再挂 ?page= 没有意义，忽略掉比生成一个脏链接好
        path = url_resolver.detail_url(
            rules,
            kind,
            slug=slug,
            entry_id=entry_id,
            catdir=catdir,
            cat=cat,
            category_id=category_id,
            published=published,
            url_path=url_path,
        )
        return f"{self.base}{path}"

    # ------------------------------------------------------------ 13. comments

    @cms_api
    def comments(self, target: Any = None, limit: int = 20) -> list[dict[str, Any]]:
        """评论：P0 先返回空（评论表尚未建），接口先占位，模板可以照着写。"""
        _ = (target, limit)
        return []

    # ------------------------------------------------------------ 14. form

    @cms_api
    def form(self, key: str = "contact") -> dict[str, Any] | None:
        """表单定义：从站点配置 form.<key> 读，没有就回到内置联系表单。"""
        raw = self._site_config().get(f"form.{key}")
        if isinstance(raw, dict):
            return {
                "key": key,
                "title": raw.get("title") or "联系我们",
                "action": raw.get("action") or f"{self.base}/api/v1/public/forms/{key}",
                "fields": raw.get("fields") or [],
            }
        if key == "contact":
            return {
                "key": "contact",
                "title": "联系我们",
                "action": f"{self.base}/api/v1/public/forms/contact",
                "fields": [
                    {"name": "name", "label": "称呼", "type": "text", "required": True},
                    {"name": "email", "label": "邮箱", "type": "email", "required": True},
                    {"name": "message", "label": "留言", "type": "textarea", "required": True},
                ],
            }
        return None

    # ------------------------------------------------------------ 15. media_list

    @cms_api
    def media_list(self, kind: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or 20), 100))
        stmt = select(models.Media).where(models.Media.site_id == self.site_id)
        if kind and hasattr(models.Media, "kind"):
            stmt = stmt.where(models.Media.kind == kind)
        if hasattr(models.Media, "created_at"):
            stmt = stmt.order_by(models.Media.created_at.desc())
        rows = self.session.execute(stmt.limit(limit)).scalars().all()
        return [
            {
                "id": r.id,
                "url": getattr(r, "url", None) or getattr(r, "path", None) or "",
                "name": getattr(r, "name", None) or getattr(r, "filename", None) or "",
                "kind": getattr(r, "kind", None) or getattr(r, "mime_type", None) or "",
                "size": getattr(r, "size", None),
            }
            for r in rows
        ]

    # ------------------------------------------------------------ 16. trans

    @cms_api
    def trans(self, key: str = "", lang: str | None = None) -> str:
        """多语言文案：读站点配置 i18n.<lang>.<key>，没有就回原文。"""
        if not key:
            return ""
        cfg = self._site_config()
        code = lang or cfg.get("i18n.current") or "zh-CN"
        table = cfg.get(f"i18n.{code}") or {}
        if isinstance(table, dict) and key in table:
            return str(table[key])
        return str(key)

    # ------------------------------------------------------------ 上下文打包

    def as_globals(self) -> dict[str, Any]:
        """16 个 API + 预注入的 site dict（模板里 {{ site.name }} 直接可用）。"""
        return {
            "content_list": self.content_list,
            "content": self.content,
            "related": self.related,
            "search": self.search,
            "categories": self.categories,
            "category_tree": self.category_tree,
            "tags": self.tags,
            "nav": self.nav,
            "site": self._site_dict(),
            "site_meta": self.site_meta,
            "pagination": self.pagination,
            "asset": self.asset,
            "url": self.url,
            "comments": self.comments,
            "form": self.form,
            "media_list": self.media_list,
            "trans": self.trans,
        }
