"""CMS App · URL 伪静态规则管理接口（后台）

这个模块只做一件事：把「规则怎么配」这件事暴露成可用的 API。

为什么单独一个文件
----------------
``router.py`` 是通用后台 CRUD，``content_engine_router.py`` 是内容引擎。
URL 规则有自己的生命周期（校验 → 存档旧值 → 生效 → 可回滚），
塞进任何一个都会把那边的结构撑变形。

四层规则（优先级从低到高）
--------------------------
1. 站点默认    ``cms_site_config`` 的 ``url.*``
2. 栏目覆盖    ``cms_categories.url_pattern``
3. 标签覆盖    ``cms_tags.url_pattern``
4. 单条钉死    ``cms_entries.url_path``（最高，规则再改也不动它）

改规则时旧规则会被存档（``url.history``），老地址因此能 301 到新地址，
而不是直接 404 —— 让一个站从搜索引擎消失最快的方式就是把所有页面 404 掉。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import get_current_user, require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms import models, permalink, url_resolver
from cenkor_admin.core.db import get_db

log = structlog.get_logger(__name__)
router = APIRouter()

# 规则种类 → 后台展示名。跟 URL_KEYS 的 key 一一对应。
KIND_LABELS: dict[str, str] = {
    "article": "文章详情",
    "product": "产品详情",
    "news": "新闻详情",
    "case": "案例详情",
    "page": "单页",
    "category": "栏目页",
    "tag": "标签页",
    "_list": "列表页",
}

# 每类规则允许用的变量说明，给前端提示用。
KIND_VAR_HINTS: dict[str, list[dict[str, str]]] = {
    "article": [
        {"name": "type", "desc": "内容类型前缀（article/product/news/case/p）"},
        {"name": "catdir", "desc": "栏目目录链，如 mes/quality"},
        {"name": "cat", "desc": "栏目 slug"},
        {"name": "slug", "desc": "内容别名"},
        {"name": "id", "desc": "内容 ID"},
        {"name": "year", "desc": "发布年份"},
        {"name": "month", "desc": "发布月份"},
        {"name": "day", "desc": "发布日"},
    ],
    "category": [
        {"name": "type", "desc": "内容类型前缀"},
        {"name": "catdir", "desc": "栏目目录链"},
        {"name": "cat", "desc": "栏目 slug"},
        {"name": "parent", "desc": "父栏目目录链"},
        {"name": "slug", "desc": "栏目 slug"},
        {"name": "id", "desc": "栏目 ID"},
    ],
    "tag": [
        {"name": "type", "desc": "内容类型前缀"},
        {"name": "slug", "desc": "标签 slug"},
        {"name": "id", "desc": "标签 ID"},
    ],
    "_list": [{"name": "type", "desc": "内容类型前缀"}],
}


class UrlRulePreviewIn(BaseModel):
    """预览一条规则会产生什么地址。"""

    kind: str = Field(..., description="规则种类：article/category/tag/_list 等")
    pattern: str = Field(..., description="规则模板")
    slug: str | None = Field(None, description="示例内容的 slug")
    category_id: int | None = Field(None, description="示例内容的栏目 ID")
    entry_id: int | None = Field(None, description="示例内容的 ID")
    published: str | None = Field(None, description="示例发布时间，ISO 格式")


class UrlRuleSaveIn(BaseModel):
    """保存一条站点级默认规则。"""

    kind: str = Field(..., description="规则种类")
    pattern: str = Field("", description="规则模板，空串表示恢复默认")


class UrlResolveIn(BaseModel):
    """按当前规则算出某条内容的规范地址（文章编辑页实时预览用）。"""

    kind: str = Field("article", description="内容类型：article/product/news/case/page")
    slug: str | None = Field(None, description="内容别名")
    category_id: int | None = Field(None, description="所属栏目 ID")
    entry_id: int | None = Field(None, description="内容 ID")
    published: str | None = Field(None, description="发布时间，ISO 格式")
    url_path: str | None = Field(None, description="用户手填的固定路径（有则优先）")


def _kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind, kind)


@router.get("/url-rules", response_model=dict[str, Any])
async def list_url_rules(
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("cms:site:read")),
):
    """列出当前生效的全部规则（站点默认 + 栏目覆盖 + 标签覆盖）。"""
    site_id = 1
    cfg_rows = (await db.execute(select(models.SiteConfig))).scalars().all()
    cfg = {r.key: r.value for r in cfg_rows}

    cats = (
        await db.execute(
            select(models.Category.id, models.Category.name, models.Category.slug, models.Category.url_pattern)
            .where(models.Category.site_id == site_id, models.Category.deleted_at.is_(None))
            .order_by(models.Category.sort)
        )
    ).all()
    tags = (
        await db.execute(
            select(models.Tag.id, models.Tag.name, models.Tag.slug, models.Tag.url_pattern)
            .where(models.Tag.site_id == site_id)
            .order_by(models.Tag.id)
        )
    ).all()

    defaults: list[dict[str, Any]] = []
    for kind, key in url_resolver.URL_KEYS.items():
        raw = cfg.get(key)
        effective = permalink.DEFAULT_PATTERNS.get(kind, "")
        source = "default"
        if isinstance(raw, str) and raw.strip():
            try:
                effective = permalink.validate_pattern(raw.strip(), kind)
                source = "custom"
            except permalink.RuleError:
                # 库里存着非法规则：如实标出来，别装作没事
                effective = raw.strip()
                source = "invalid"
        defaults.append(
            {
                "kind": kind,
                "label": _kind_label(kind),
                "config_key": key,
                "pattern": effective,
                "builtin": permalink.DEFAULT_PATTERNS.get(kind, ""),
                "source": source,
                "vars": KIND_VAR_HINTS.get(kind, KIND_VAR_HINTS.get("article", [])),
            }
        )

    history_raw = cfg.get(url_resolver.HISTORY_KEY)
    history: list[dict[str, str]] = []
    if isinstance(history_raw, list):
        history = [h for h in history_raw if isinstance(h, dict)]

    return {
        "defaults": defaults,
        "categories": [
            {"id": c[0], "name": c[1], "slug": c[2], "url_pattern": c[3]} for c in cats
        ],
        "tags": [{"id": t[0], "name": t[1], "slug": t[2], "url_pattern": t[3]} for t in tags],
        "history": history,
    }


@router.post("/url-rules/preview", response_model=dict[str, Any])
async def preview_url_rule(
    body: UrlRulePreviewIn,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("cms:site:read")),
):
    """预览一条规则：校验合法性 + 列出示例地址 + 检测与现有规则的冲突。

    前端在用户还没保存时就能看到「这条规则长什么样」，
    避免存下去才发现跟别的规则撞车。
    """
    kind = body.kind.strip().lower()
    if kind not in url_resolver.URL_KEYS:
        raise HTTPException(400, f"未知的规则类型 `{kind}`")

    pattern = body.pattern.strip()
    if not pattern:
        return {"ok": True, "pattern": "", "samples": [], "conflicts": [], "message": "空规则表示使用默认"}

    try:
        normalized = permalink.validate_pattern(pattern, kind)
    except permalink.RuleError as exc:
        raise HTTPException(400, f"URL 规则不合法：{exc}") from exc

    # 冲突检测：拿现有全部规则 + 这条待保存的规则一起对撞
    rules = await url_resolver.load_rules(db, 1)
    others: list[permalink.Rule] = []
    for k, p in rules.defaults.items():
        if k == "_list":
            continue
        try:
            others.append(permalink.Rule(k, p, source="site"))
        except permalink.RuleError:
            continue
    for cid, p in rules.category_patterns.items():
        try:
            others.append(permalink.Rule("category", p, source=f"category:{cid}", priority=1))
        except permalink.RuleError:
            continue
    for tid, p in rules.tag_patterns.items():
        try:
            others.append(permalink.Rule("tag", p, source=f"tag:{tid}", priority=1))
        except permalink.RuleError:
            continue

    conflicts: list[dict[str, str]] = []
    try:
        pending = permalink.Rule(kind, normalized, source="pending")
    except permalink.RuleError as exc:
        raise HTTPException(400, f"URL 规则不合法：{exc}") from exc
    for c in permalink.classify_conflicts([*others, pending]):
        if pending not in (c.a, c.b):
            continue
        other = c.b if c.a is pending else c.a
        conflicts.append(
            {
                "sample": c.sample,
                "severity": c.severity,
                "reason": c.reason,
                "other_source": other.source,
                "other_pattern": other.pattern,
            }
        )

    blocking = [c for c in conflicts if c["severity"] == "block"]

    # 示例地址：用假数据把变量填上，看这条规则实际长什么样
    samples: list[str] = []
    catdir = None
    if body.category_id is not None:
        catdir = await url_resolver.category_chain(db, body.category_id, 1)
    published = None
    if body.published:
        try:
            published = datetime.fromisoformat(body.published)
        except ValueError:
            published = None
    values = url_resolver.sample_values(
        kind,
        slug=body.slug or "demo-slug",
        entry_id=body.entry_id or 42,
        catdir=catdir or "mes",
        cat=body.slug or "demo-slug",
        published=published,
    )
    try:
        samples.append(permalink.build_url(normalized, values))
    except permalink.RuleNotApplicable:
        samples.append("（该规则要求栏目，但示例内容没有栏目）")
    except permalink.RuleError as exc:
        samples.append(f"（无法生成示例：{exc}）")
    # 再补几条不同 slug 的样本，看路径形态是否稳定
    for alt in ("another-post", "third-post"):
        v2 = dict(values)
        v2["slug"] = alt
        try:
            s = permalink.build_url(normalized, v2)
            if s not in samples:
                samples.append(s)
        except (permalink.RuleNotApplicable, permalink.RuleError):
            continue

    return {
        "ok": not blocking,
        "pattern": normalized,
        "samples": samples,
        "conflicts": conflicts,
        "message": "与同层级规则冲突" if blocking else ("与其它层级有重叠（覆盖关系）" if conflicts else "规则可用"),
    }


@router.post("/url-rules/save", response_model=dict[str, Any])
async def save_url_rule(
    body: UrlRuleSaveIn,
    db: AsyncSession = Depends(get_db),
    # 写接口必须收紧到 cms:site:write：规则是全站生效的，
    # 只读角色（viewer）能改的话，一次误操作全站地址全变。
    current: auth_models.User = Depends(require_permission("cms:site:write")),
):
    """保存站点级默认规则，并存档旧规则。

    存档是为了让老地址能 301 到新地址。少了这一步，
    一改规则所有已收录的页面立刻 404 —— 搜索引擎的排名会掉得很快。
    """
    kind = body.kind.strip().lower()
    key = url_resolver.URL_KEYS.get(kind)
    if not key:
        raise HTTPException(400, f"未知的规则类型 `{kind}`")

    pattern = body.pattern.strip()
    old_row = await db.get(models.SiteConfig, key)
    old_value = old_row.value if old_row is not None else None

    if not pattern:
        # 空串 = 恢复内置默认：删掉这条配置
        if old_row is not None:
            await db.delete(old_row)
        await db.commit()
        url_resolver.invalidate()
        return {"saved": True, "kind": kind, "pattern": "", "restored_default": True}

    try:
        normalized = permalink.validate_pattern(pattern, kind)
    except permalink.RuleError as exc:
        raise HTTPException(400, f"URL 规则不合法：{exc}") from exc

    # 冲突检测：不通过就不让存
    rules = await url_resolver.load_rules(db, 1)
    others: list[permalink.Rule] = []
    for k, p in rules.defaults.items():
        if k == "_list" or k == kind:
            # 站点默认里被替换掉的那条不参与对撞
            continue
        try:
            others.append(permalink.Rule(k, p, source="site"))
        except permalink.RuleError:
            continue
    for cid, p in rules.category_patterns.items():
        try:
            others.append(permalink.Rule("category", p, source=f"category:{cid}", priority=1))
        except permalink.RuleError:
            continue
    for tid, p in rules.tag_patterns.items():
        try:
            others.append(permalink.Rule("tag", p, source=f"tag:{tid}", priority=1))
        except permalink.RuleError:
            continue
    try:
        pending = permalink.Rule(kind, normalized, source="pending")
    except permalink.RuleError as exc:
        raise HTTPException(400, f"URL 规则不合法：{exc}") from exc
    for c in permalink.classify_conflicts([*others, pending]):
        # 只拦同层级的冲突。栏目规则盖过站点默认是设计好的覆盖，不是错误。
        if c.severity != "block" or pending not in (c.a, c.b):
            continue
        other = c.b if c.a is pending else c.a
        label = "站点默认规则" if other.source == "site" else other.source
        raise HTTPException(
            400,
            f"该规则与{label}的 `{other.pattern}` 冲突，"
            f"两者都会认领 `{c.sample}`，请先调整其中一条",
        )

    # 存档旧规则（覆盖之前拿，拿到就晚了）
    await url_resolver.archive_rule(db, kind, old_value)

    if old_row is not None:
        old_row.value = normalized
    else:
        db.add(models.SiteConfig(key=key, value=normalized))
    await db.commit()
    # 缓存必须在 commit 之后清：commit 前清的话，并发请求会在 commit 前
    # 把**旧**规则重新写回缓存，改动等于没生效。
    url_resolver.invalidate()
    return {"saved": True, "kind": kind, "pattern": normalized, "restored_default": False}


@router.post("/url-rules/resolve", response_model=dict[str, Any])
async def resolve_entry_url(
    body: UrlResolveIn,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    """按**当前**规则算出某条内容的规范地址。

    文章编辑页用它做实时预览：用户在 slug / 栏目 / 自定义路径上改动时，
    立刻能看到这条内容最终会以什么地址对外暴露 —— 不用保存、
    不用刷新前台去猜。

    返回两套地址：
    - ``url``：最终地址（用户填了自定义路径就是它，否则按规则算）
    - ``rule_url``：忽略自定义路径、按规则算出来的地址
      （用户填自定义路径时还能看出「如果我删掉自定义地址会变成什么」）
    """
    kind = (body.kind or "article").strip().lower()
    if kind not in ("article", "product", "news", "case", "page"):
        # 没有独立 URL 规则的内容类型（目前是 video）走文章规则。
        # 这跟反解侧 `_KNOWN_DETAIL_KINDS` 的兜底一致 ——
        # 两边算法不同的话，预览出来的地址跟前台实际地址对不上。
        kind = "article"

    site_id = 1
    rules = await url_resolver.load_rules(db, site_id)

    catdir = None
    cat = None
    if body.category_id is not None:
        catdir = await url_resolver.category_chain(db, body.category_id, site_id)
        cat_row = await db.get(models.Category, body.category_id)
        cat = cat_row.slug if cat_row is not None else None

    published = None
    if body.published:
        try:
            published = datetime.fromisoformat(body.published)
        except ValueError:
            published = None

    rule_url = url_resolver.detail_url(
        rules,
        kind,
        slug=body.slug,
        entry_id=body.entry_id,
        catdir=catdir,
        cat=cat,
        category_id=body.category_id,
        published=published,
    )

    user_path = None
    if body.url_path and str(body.url_path).strip():
        user_path = url_resolver.normalize_user_path(str(body.url_path).strip())

    final_url = user_path or rule_url
    return {
        "url": final_url,
        "rule_url": rule_url,
        "user_path": user_path,
        "customized": bool(user_path),
        "pattern": rules.pattern_for(kind),
    }
