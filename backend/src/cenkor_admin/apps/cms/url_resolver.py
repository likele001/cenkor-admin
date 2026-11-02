"""URL 规则的数据库接入层

``permalink.py`` 只做纯计算，这里负责「从库里读出规则、缓存、组装成地址」。

两个入口共享同一份缓存：

    load_rules(db, site_id)          异步 session（公开路由）
    load_rules_sync(session, site_id) 同步 session（模板上下文）

为什么不各查各的：同一次请求里模板层和路由层都要算地址，两边各自查一遍
不只是多两条 SQL —— 缓存刷新时刻不同，会算出**不一致的 canonical 和页面内链**，
这种错只能靠比对源码发现。

规则来源
--------
站点默认    ``cms_site_config`` 的 ``url.*``，全局一张表（与 brand.domain 一致）
栏目覆盖    ``cms_categories.url_pattern``
标签覆盖    ``cms_tags.url_pattern``
单条覆盖    ``cms_entries.url_path``（只在生成时直接采用，反解时查表）

缓存 2 秒：后台改完规则到前台生效最多滞后两秒。
之所以不能只靠保存后调 :func:`invalidate` —— 那是管理进程在清自己的缓存，
跑 Web 请求的 worker 是别的进程，压根看不到。
所以 TTL 必须短到用户无感。
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select

from cenkor_admin.apps.cms import models, permalink

logger = logging.getLogger(__name__)

__all__ = [
    "HISTORY_KEY",
    "URL_KEYS",
    "RuleSet",
    "archive_rule",
    "category_base",
    "category_chain",
    "category_chains",
    "category_url",
    "detail_url",
    "invalidate",
    "list_base",
    "list_url",
    "load_rules",
    "load_rules_sync",
    "normalize_user_path",
    "permalink_page",
    "sample_values",
    "tag_base",
    "tag_url",
    "validate_rule",
]

# SiteConfig 里存站点默认规则的 key。用 `url.` 前缀和品牌/联系方式的 key 分开。
URL_KEYS: dict[str, str] = {
    "article": "url.article",
    "product": "url.product",
    "news": "url.news",
    "case": "url.case",
    "page": "url.page",
    "category": "url.category",
    "tag": "url.tag",
    "_list": "url.list",
}

# 历史规则存档：后台每改一次规则就追加一条旧规则。
# 作用是让已经收录的地址 301 到新地址，而不是变成 404 ——
# 让一个站从搜索引擎消失最快的方式，就是把有排名的页面全部 404 掉。
HISTORY_KEY = "url.history"

# 规则缓存 TTL。
#
# 这里必须是**短 TTL**，不能只靠 `invalidate()`：后台保存规则走的是
# 管理进程，跟跑 Web 请求的 worker 不是同一个进程，
# 管理进程清自己的缓存对 worker 毫无影响 —— 规则改了但站点还在用旧的，
# 表现为「新地址 404、老地址不跳」。
#
# 2 秒的延迟用户无感（改完规则刷新页面基本就生效了），
# 而规则查询是一次 17 行的单表查询，摊到每个 worker 2 秒一次完全无压力。
_CACHE_TTL = 2.0
_cache: dict[int, tuple[float, RuleSet]] = {}
_lock = threading.Lock()


# ---------------------------------------------------------------- 规则集


@dataclass(frozen=True)
class RuleSet:
    """一个站点当前生效的全部规则。"""

    defaults: dict[str, str] = field(default_factory=lambda: dict(permalink.DEFAULT_PATTERNS))
    category_patterns: dict[int, str] = field(default_factory=dict)
    tag_patterns: dict[int, str] = field(default_factory=dict)
    # 栏目级「文章内容页」规则：cms_categories.article_pattern，只管该栏目下
    # 条目的详情页地址，与 category_patterns（栏目页自己的地址）正交。
    category_article_patterns: dict[int, str] = field(default_factory=dict)
    # 历史规则：只用于「旧地址 → 301 到新地址」，不参与正向生成
    history: tuple[permalink.Rule, ...] = ()

    def pattern_for(
        self,
        kind: str,
        *,
        category_id: int | None = None,
        tag_id: int | None = None,
    ) -> str:
        """取某类页面该用的规则。

        覆盖只作用于**同一语义层**：

        - ``category_id`` 只影响 ``kind == "category"``（栏目页自己的地址）
        - ``tag_id`` 只影响 ``kind == "tag"``（标签页自己的地址）

        早期版本里栏目覆盖对任何 kind 都生效，于是「给栏目配一条规则」
        会顺手把该栏目下所有内容的详情地址一起改掉 —— 同一份模板两种含义。
        反向解析更糟：那条规则被当成栏目页规则，反解时拿**内容 slug**
        去查**栏目表**，查不到就整批 404。

        覆盖关系的正确分层是：

            站点默认（``cms_site_config.url.*``）  管全部
            栏目覆盖（``cms_categories.url_pattern``） 只管栏目页
            标签覆盖（``cms_tags.url_pattern``）     只管标签页
            单条钉死（``cms_entries.url_path``）     只管那一条内容
        """
        if kind == "category" and category_id is not None:
            hit = self.category_patterns.get(category_id)
            if hit:
                return hit
        if kind == "tag" and tag_id is not None:
            hit = self.tag_patterns.get(tag_id)
            if hit:
                return hit
        return self.defaults.get(kind) or permalink.DEFAULT_PATTERNS.get(kind, "{type}/{slug}.html")


def _build(
    cfg: dict[str, Any],
    categories: list[tuple[int, str]],
    tags: list[tuple[int, str]],
    category_articles: list[tuple[int, str]] | None = None,
) -> RuleSet:
    defaults = dict(permalink.DEFAULT_PATTERNS)
    for kind, key in URL_KEYS.items():
        raw = cfg.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            # 按各自的 kind 校验：栏目规则只认栏目变量（{parent} 等），
            # 列表页规则只认 {type}。统一按 article 校验会让脏规则混进来，
            # 运行时才发现套不上 —— 那时候规则已经存进库了。
            defaults[kind] = permalink.validate_pattern(raw, kind)
        except permalink.RuleError as exc:
            # 库里存着脏规则不能让整站 500，记日志继续用默认值
            logger.warning("忽略非法 URL 规则 %s=%r：%s", key, raw, exc)

    return RuleSet(
        defaults=defaults,
        category_patterns={cid: p for cid, p in categories if p and p.strip()},
        tag_patterns={tid: p for tid, p in tags if p and p.strip()},
        category_article_patterns={
            cid: p for cid, p in (category_articles or []) if p and p.strip()
        },
        history=_parse_history(cfg.get(HISTORY_KEY)),
    )


def _parse_history(raw: Any) -> tuple[permalink.Rule, ...]:
    """解析历史规则存档。格式：``[{"kind": "article", "pattern": "{type}/{slug}.html"}, …]``。

    脏条目直接跳过：历史规则只用来做 301，错一条不该让整站解析挂掉。
    """
    if not isinstance(raw, list):
        return ()
    out: list[permalink.Rule] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "article").strip().lower()
        pattern = item.get("pattern")
        if not isinstance(pattern, str) or not pattern.strip():
            continue
        try:
            out.append(permalink.Rule(kind, pattern, source="history"))
        except permalink.RuleError:
            continue
    return tuple(out)


async def archive_rule(db, kind: str, old_value: Any) -> None:
    """把被改掉的 URL 规则追加进历史存档。

    只记规则本身，不记内容 —— 历史规则只用来「把老地址反解出来，
    再按当前规则算出新地址，301 过去」，内容还是从库里现查。

    必须在**覆盖之前**调用：旧值一旦被覆盖就找不回来了。

    旧值可能不在库里 —— 默认规则是代码里的 ``DEFAULT_PATTERNS``，
    用户第一次改规则时库里根本没这个 key。这时候要拿默认规则来存档，
    那才是线上正在用的形态。漏掉它意味着「所有已收录的老地址在改规则那一刻集体 404」。
    """
    kind = (kind or "").strip().lower()
    if kind in ("", "_list", "history"):
        return

    if isinstance(old_value, str) and old_value.strip():
        effective_old = old_value.strip()
    else:
        effective_old = permalink.DEFAULT_PATTERNS.get(kind)
    if not effective_old:
        return

    try:
        permalink.validate_pattern(effective_old, kind)
    except permalink.RuleError:
        # 旧规则本身就不合法（可能是手改库改坏的），存了也没法反解，跳过
        return

    row = (
        await db.execute(
            select(models.SiteConfig).where(models.SiteConfig.key == HISTORY_KEY)
        )
    ).scalars().first()
    raw = row.value if row is not None else None
    history: list[dict[str, str]] = []
    if isinstance(raw, list):
        history = [h for h in raw if isinstance(h, dict)]
    elif isinstance(raw, str) and raw.strip():
        # 兼容早期存成 JSON 字符串的脏数据
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            parsed = []
        if isinstance(parsed, list):
            history = [h for h in parsed if isinstance(h, dict)]

    entry = {"kind": kind, "pattern": effective_old}
    # 同一条规则已经在存档里就不重复记，避免存档越滚越长
    if any(h.get("kind") == kind and h.get("pattern") == effective_old for h in history):
        return
    history.append(entry)
    # 只留最近 50 条：存档是给「刚改过的规则」用的，不是无限追溯
    history = history[-50:]

    if row is None:
        db.add(models.SiteConfig(key=HISTORY_KEY, value=history))
    else:
        row.value = history


# ---------------------------------------------------------------- 加载与缓存


def _read_cache(site_id: int) -> RuleSet | None:
    now = time.monotonic()
    with _lock:
        hit = _cache.get(site_id)
        if hit and hit[0] > now:
            return hit[1]
        return None


def _write_cache(site_id: int, rules: RuleSet) -> None:
    with _lock:
        _cache[site_id] = (time.monotonic() + _CACHE_TTL, rules)


def invalidate(site_id: int | None = None) -> None:
    """清缓存。后台保存规则后调用，让改动立刻生效。"""
    with _lock:
        if site_id is None:
            _cache.clear()
        else:
            _cache.pop(site_id, None)


def _cfg_dict(rows: list[Any]) -> dict[str, Any]:
    return {r.key: r.value for r in rows}


async def load_rules(db, site_id: int = 1) -> RuleSet:
    """异步加载（公开路由用）。"""
    hit = _read_cache(site_id)
    if hit is not None:
        return hit

    try:
        cfg_rows = (await db.execute(select(models.SiteConfig))).scalars().all()
        cats = (
            await db.execute(
                select(models.Category.id, models.Category.url_pattern).where(
                    models.Category.site_id == site_id,
                    models.Category.url_pattern.is_not(None),
                )
            )
        ).all()
        cat_articles = (
            await db.execute(
                select(models.Category.id, models.Category.article_pattern).where(
                    models.Category.site_id == site_id,
                    models.Category.article_pattern.is_not(None),
                )
            )
        ).all()
        tags = (
            await db.execute(
                select(models.Tag.id, models.Tag.url_pattern).where(
                    models.Tag.site_id == site_id,
                    models.Tag.url_pattern.is_not(None),
                )
            )
        ).all()
        rules = _build(_cfg_dict(list(cfg_rows)), list(cats), list(tags), list(cat_articles))
    except Exception:
        logger.warning("加载 URL 规则失败，退回内置默认规则 site_id=%s", site_id, exc_info=True)
        rules = RuleSet()

    _write_cache(site_id, rules)
    return rules


def load_rules_sync(session, site_id: int = 1) -> RuleSet:
    """同步加载（模板上下文用）。"""
    hit = _read_cache(site_id)
    if hit is not None:
        return hit

    try:
        cfg_rows = session.execute(select(models.SiteConfig)).scalars().all()
        cats = session.execute(
            select(models.Category.id, models.Category.url_pattern).where(
                models.Category.site_id == site_id,
                models.Category.url_pattern.is_not(None),
            )
        ).all()
        cat_articles = session.execute(
            select(models.Category.id, models.Category.article_pattern).where(
                models.Category.site_id == site_id,
                models.Category.article_pattern.is_not(None),
            )
        ).all()
        tags = session.execute(
            select(models.Tag.id, models.Tag.url_pattern).where(
                models.Tag.site_id == site_id,
                models.Tag.url_pattern.is_not(None),
            )
        ).all()
        rules = _build(_cfg_dict(list(cfg_rows)), list(cats), list(tags), list(cat_articles))
    except Exception:
        logger.warning("加载 URL 规则失败，退回内置默认规则 site_id=%s", site_id, exc_info=True)
        rules = RuleSet()

    _write_cache(site_id, rules)
    return rules


# ---------------------------------------------------------------- 正向生成


async def category_chains(db, site_id: int = 1) -> dict[int, str]:
    """``category_id -> 完整目录链``（``hangye/xinwen``）。

    一次查全表在内存里拼，而不是逐条走 ``category.parent``：
    async session 下懒加载关系会直接炸 MissingGreenlet，而且栏目总数也就几十条，
    一次查完比 N+1 快得多。
    """
    try:
        rows = (
            await db.execute(
                select(
                    models.Category.id,
                    models.Category.slug,
                    models.Category.parent_id,
                ).where(models.Category.site_id == site_id)
            )
        ).all()
    except Exception:
        logger.warning("查询栏目目录链失败 site_id=%s", site_id, exc_info=True)
        return {}

    by_id: dict[int, tuple[str, int | None]] = {r[0]: (r[1], r[2]) for r in rows}
    out: dict[int, str] = {}
    for cid in by_id:
        parts: list[str] = []
        cur: int | None = cid
        guard = 0
        while cur is not None and guard < 6 and cur in by_id:
            slug, parent = by_id[cur]
            parts.append(slug)
            cur = parent
            guard += 1
        if parts:
            out[cid] = "/".join(reversed(parts))
    return out


async def category_chain(db, category_id: int | None, site_id: int = 1) -> str | None:
    """单个栏目的完整目录链。详情页只有一条内容，不值得查全表。

    层级最多 6 层，正常 1~2 次查询就到底（库里目前几乎都是单级）。
    """
    if not category_id:
        return None
    parts: list[str] = []
    cur: int | None = int(category_id)
    guard = 0
    while cur is not None and guard < 6:
        try:
            row = (
                await db.execute(
                    select(models.Category.slug, models.Category.parent_id).where(
                        models.Category.id == cur,
                        models.Category.site_id == site_id,
                    )
                )
            ).first()
        except Exception:
            logger.warning("查询栏目链失败 category_id=%s", cur, exc_info=True)
            return None
        if row is None:
            break
        parts.append(str(row[0]))
        cur = row[1]
        guard += 1
    return "/".join(reversed(parts)) or None


def sample_values(
    kind: str,
    *,
    slug: str | None = None,
    entry_id: int | None = None,
    catdir: str | None = None,
    cat: str | None = None,
    published: datetime | None = None,
) -> dict[str, Any]:
    """给外部（后台预览接口）用的变量取值。

    为什么不直接暴露 :func:`_values`：那个函数的参数是位置参数，
    调用方一不小心就会把 catdir 传成 cat。规则模板拼错变量的后果是
    「地址看起来对，点进去 404」，很难查。
    """
    return _values(kind, slug, entry_id, catdir, cat, published)


def _values(
    kind: str,
    slug: str | None,
    entry_id: int | None,
    catdir: str | None,
    cat: str | None,
    published: datetime | None,
) -> dict[str, Any]:
    # {type} 填的是**URL 前缀**，不是内容类型 key —— 单页类型 key 是 "page"，
    # 但它的地址前缀是 "/p/"。反向编译时 {type} 也按同一张表绑成字面量，
    # 两边必须一致，否则同一个地址正向生成和反向解析对不上。
    values = {
        "type": permalink.TYPE_PREFIX.get(kind, kind),
        "slug": slug,
        "id": entry_id,
        "catdir": catdir,
        "cat": cat,
        "year": published.year if published else None,
        "month": f"{published.month:02d}" if published else None,
        "day": f"{published.day:02d}" if published else None,
    }
    # {parent} 只对栏目页有意义（父栏目链，不含自身）。
    # 顶层栏目没有父级 → None → 规则套不上就回落默认，不拼出脏地址。
    if catdir and "/" in catdir:
        values["parent"] = catdir.rsplit("/", 1)[0]
    else:
        values["parent"] = None
    return values


def _try_patterns(patterns: list[str], values: dict[str, Any], kind: str) -> str:
    for pattern in patterns:
        try:
            return permalink.build_url(pattern, values)
        except permalink.RuleNotApplicable:
            # 比如规则要 {catdir} 但这条内容没归栏目 —— 换下一条，不拼脏地址
            continue
        except permalink.RuleError:
            continue
    fallback = permalink.DEFAULT_PATTERNS.get(kind, "{type}/{slug}.html")
    return permalink.build_url(fallback, values)


def normalize_user_path(raw: str) -> str:
    """把用户手填的路径收敛成 `/a/b.html` 形态。

    用户可能填 ``mes/abc.html``、``/mes/abc.html``、``//mes//abc.html``，
    统一成单前导斜杠、无重复斜杠、不带查询串。查询串和锚点在路径里没有意义，
    留着会让唯一索引形同虚设（``/a.html?x=1`` 和 ``/a.html?x=2`` 是两个值）。
    """
    p = (raw or "").strip()
    p = p.split("?", 1)[0].split("#", 1)[0]
    if not p:
        return ""
    p = "/" + p.strip("/")
    while "//" in p:
        p = p.replace("//", "/")
    return p


def detail_url(
    rules: RuleSet,
    kind: str,
    *,
    slug: str | None,
    entry_id: int | None = None,
    catdir: str | None = None,
    cat: str | None = None,
    category_id: int | None = None,
    published: datetime | None = None,
    url_path: str | None = None,
) -> str:
    """内容详情页地址。

    手填路径优先于一切规则 —— 用户在编辑页明确钉死的地址，后台改规则不该动它。

    栏目级规则分两个字段，互不越界：

    - ``cms_categories.url_pattern``  只管栏目页自己的地址（category_base 用）
    - ``cms_categories.article_pattern`` 只管**该栏目下条目**的详情页地址。
      只认条目直接所属栏目（``category_id``），与反解侧的归属核对严格对称：
      正向用哪条规则生成，反向就只用同一条规则认领，认领后回库核对归属，
      对不上换下一条 —— 不会重演早期版本「正反两向各说各话 → 整批 404」。

    ``{catdir}`` 要不要带，由这里传入的 ``catdir`` 决定（调用方已按栏目链算好）。
    """
    if url_path and str(url_path).strip():
        return normalize_user_path(str(url_path))

    values = _values(kind, slug, entry_id, catdir, cat, published)
    if category_id is not None:
        cat_pattern = rules.category_article_patterns.get(int(category_id))
        if cat_pattern:
            return _try_patterns([cat_pattern], values, kind)
    return _try_patterns([rules.pattern_for(kind)], values, kind)


def list_url(rules: RuleSet, kind: str, page: int = 1) -> str:
    """列表页地址，翻页走路径式 `/{base}page/{n}/`。"""
    return permalink_page(list_base(rules, kind), page)


def list_base(rules: RuleSet, kind: str) -> str:
    """列表页基路径（不含页码）。

    列表页规则只有一条（``url.list``），靠 ``{type}`` 区分内容类型：
    ``{type}/`` → ``/article/``、``/product/``……
    """
    values = _values(kind, None, None, None, None, None)
    base = _try_patterns([rules.pattern_for("_list")], values, "_list")
    return base


def category_base(
    rules: RuleSet,
    *,
    slug: str,
    catdir: str | None = None,
    category_id: int | None = None,
    type_key: str = "article",
) -> str:
    """栏目页基路径（不含页码）。分页页在它后面接 ``page/{n}/``。

    栏目级规则（``cms_categories.url_pattern``）**只管栏目页**，
    跟标签级规则一个层级。它不管该栏目下内容的详情页地址 ——
    那是站点默认规则的活儿（用不用 ``{catdir}`` 决定带不带栏目目录）。
    """
    values = _values(type_key, slug, category_id, catdir, slug, None)
    return _try_patterns([rules.pattern_for("category", category_id=category_id)], values, "category")


def category_url(
    rules: RuleSet,
    *,
    slug: str,
    catdir: str | None = None,
    category_id: int | None = None,
    type_key: str = "article",
    page: int = 1,
) -> str:
    """栏目页地址（含页码）。"""
    return permalink_page(category_base(rules, slug=slug, catdir=catdir,
                                        category_id=category_id, type_key=type_key), page)


def tag_base(
    rules: RuleSet,
    *,
    slug: str,
    tag_id: int | None = None,
    type_key: str = "article",
) -> str:
    """标签页基路径（不含页码）。标签级规则只管标签页，跟栏目级对称。"""
    values = _values(type_key, slug, tag_id, None, None, None)
    return _try_patterns([rules.pattern_for("tag", tag_id=tag_id)], values, "tag")


def tag_url(
    rules: RuleSet,
    *,
    slug: str,
    tag_id: int | None = None,
    type_key: str = "article",
    page: int = 1,
) -> str:
    """标签页地址（含页码）。"""
    return permalink_page(tag_base(rules, slug=slug, tag_id=tag_id, type_key=type_key), page)


def permalink_page(base: str, page: int) -> str:
    """第 1 页就是基路径本身，第 N 页接 `page/N/`。

    和 ``template_context.page_url`` 同一套规则 —— 两份实现分叉过一次
    （一份生成 ``/article/``、一份生成 ``/article/page/1/``），两种地址都能开，
    于是同一页有了两个可收录地址。
    """
    b = "/" + (base or "/").strip("/")
    b = b + "/" if b != "/" else "/"
    n = int(page or 1)
    return b if n <= 1 else f"{b}page/{n}/"


# ---------------------------------------------------------------- 校验（后台保存用）


def validate_rule(pattern: str, kind: str, *, others: list[permalink.Rule] | None = None) -> str:
    """后台保存前的完整校验：语法 + 与其他规则的冲突。

    返回规范化后的规则；不合法抛 :class:`permalink.RuleError`，
    消息直接可以展示给用户。

    只拦**同层级**的冲突：栏目规则盖过站点默认是设计好的覆盖关系，
    不是错误。跨层级只作为提醒返回，不抛异常。
    """
    body = permalink.validate_pattern(pattern, kind)
    if others:
        mine = permalink.Rule(kind, body, source="pending")
        for conflict in permalink.classify_conflicts([*others, mine]):
            if conflict.severity != "block":
                continue
            if mine not in (conflict.a, conflict.b):
                continue
            other = conflict.b if conflict.a is mine else conflict.a
            other_label = "站点默认规则" if other.source == "site" else other.source
            raise permalink.RuleError(
                f"该规则与{other_label}的 `{other.pattern}` 冲突，"
                f"两者都会认领 `{conflict.sample}`，请先调整其中一条"
            )
    return body
