"""建站方案编排：一句话需求 → 栏目树 + TDK + 选题 → 确认 → 落库执行。

分工：本模块只做「生成 + 校验 + 差异计算 + 执行」，不碰 HTTP。
好处是 dry-run 与 apply 共用同一套判断，不会出现「预览说 5 个栏目、真跑变 7 个」。
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms import models
from cenkor_admin.apps.cms.ai.models import CmsAiBatchItem, CmsAiBatchJob
from cenkor_admin.apps.cms.site_plan_models import SitePlan, SitePlanItem
from cenkor_admin.core.llm import get_llm

MAX_CATEGORIES = 12
MAX_ARTICLES = 60
MAX_DEPTH = 3

# 上限存在的意义不是限制想象力，是防止一次点错把 LLM 额度烧光，也防止
# 栏目树深到前端画不出来。
_SYSTEM = """你是资深建站策划。根据用户需求产出一个内容站的栏目树与首批选题。

只输出 JSON，不要任何解释文字，结构严格如下：
{
  "summary": "一句话概括站点定位与目标客户",
  "categories": [
    {
      "key": "products",
      "name": "产品中心",
      "parent_key": null,
      "description": "这个栏目放什么内容，40 字内",
      "seo_title": "30 字内，含核心词",
      "seo_description": "80 字内"
    }
  ],
  "articles": [
    {
      "title": "具体、可搜索的标题，不要空话",
      "category_key": "products",
      "keyword": "主打关键词",
      "brief": "写作要点：2-3 句，说明要讲清哪几件事"
    }
  ]
}

硬性约束：
1. 栏目 1-{max_cat} 个，最多 {max_depth} 层，父栏目必须出现在 categories 里；
2. key 只用英文小写字母、数字、下划线；
3. 选题 1-{max_art} 篇，category_key 必须在 categories 里；
4. 标题不得出现「XX 的重要性」「浅谈」「浅析」这类模板话；
5. 每个栏目至少 1 篇选题。"""


def _slugify(text: str, fallback: str) -> str:
    """ASCII slug；中文名转不出东西时用 key 兜底，不生成空 slug。"""
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return (s or fallback)[:80]


def normalize_plan(
    raw: dict[str, Any],
    *,
    max_categories: int = MAX_CATEGORIES,
    max_articles: int = MAX_ARTICLES,
) -> tuple[dict[str, Any], list[str]]:
    """把 LLM 输出削成结构自洽的方案。

    LLM 常见的三种坏输出：父引用指向不存在的 key、父子成环、深度超标。
    这里统一修成合法树并记录 warning，而不是直接 500 —— 用户要的是能用的
    方案，不是「模型输出不合法」的报错。
    """
    warnings: list[str] = []

    cats: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for i, c in enumerate(raw.get("categories") or []):
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        key = re.sub(r"[^a-z0-9_]", "", str(c.get("key") or "").lower()) or f"cat{i + 1}"
        if key in seen_keys:
            key = f"{key}_{i + 1}"
            warnings.append(f"栏目 key 重复，已改为 {key}")
        seen_keys.add(key)
        cats.append(
            {
                "key": key,
                "name": name[:80],
                "slug": _slugify(str(c.get("slug") or name), key),
                "parent_key": (str(c.get("parent_key")).strip() or None)
                if c.get("parent_key")
                else None,
                "description": str(c.get("description") or "")[:200],
                "seo_title": str(c.get("seo_title") or name)[:80],
                "seo_description": str(c.get("seo_description") or "")[:200],
            }
        )
        if len(cats) >= max_categories:
            warnings.append(f"栏目超过上限 {max_categories}，已截断")
            break

    if not cats:
        raise ValueError("方案里没有任何栏目，无法执行")

    # 父引用校验 + 去环 + 限深
    by_key = {c["key"]: c for c in cats}

    def _depth(cat: dict[str, Any]) -> int:
        depth, cur, guard = 1, cat, 0
        while cur.get("parent_key") and guard < 10:
            parent = by_key.get(cur["parent_key"])
            if parent is None or parent is cat:
                return 999
            depth += 1
            cur = parent
            guard += 1
        return depth

    for c in cats:
        parent = c.get("parent_key")
        if parent and parent not in by_key:
            warnings.append(f"栏目「{c['name']}」的父栏目不存在，已提到一级")
            c["parent_key"] = None
            continue
        if parent and _depth(c) > MAX_DEPTH:
            warnings.append(f"栏目「{c['name']}」层级超过 {MAX_DEPTH} 层，已提到一级")
            c["parent_key"] = None

    articles: list[dict[str, Any]] = []
    fallback_cat = cats[0]["key"]
    for a in raw.get("articles") or []:
        if not isinstance(a, dict):
            continue
        title = str(a.get("title") or "").strip()
        if not title:
            continue
        cat_key = str(a.get("category_key") or "").strip()
        if cat_key not in by_key:
            cat_key = fallback_cat
            warnings.append(f"选题「{title[:20]}」的栏目不存在，已归到「{cats[0]['name']}」")
        articles.append(
            {
                "title": title[:200],
                "category_key": cat_key,
                "keyword": str(a.get("keyword") or "")[:60],
                "brief": str(a.get("brief") or "")[:600],
            }
        )
        if len(articles) >= max_articles:
            warnings.append(f"选题超过上限 {max_articles}，已截断")
            break

    if not articles:
        raise ValueError("方案里没有任何选题，无法执行")

    return (
        {
            "summary": str(raw.get("summary") or "")[:200],
            "categories": cats,
            "articles": articles,
            "generated_at": datetime.now(UTC).isoformat(),
        },
        warnings,
    )


async def resolve_content_type(db: AsyncSession, content_type_id: int | None) -> models.ContentType:
    if content_type_id:
        ct = await db.get(models.ContentType, content_type_id)
        if ct is None:
            raise ValueError("内容类型不存在")
        return ct
    # 没指定就跑文章类型，其次任意一个 —— 建站首批内容基本都是文章
    ct = (
        await db.execute(select(models.ContentType).where(models.ContentType.key == "article"))
    ).scalars().first()
    if ct is None:
        ct = (await db.execute(select(models.ContentType).order_by(models.ContentType.id))).scalars().first()
    if ct is None:
        raise ValueError("还没有内容类型，请先到「内容类型」里建一个")
    return ct


async def build_plan(
    db: AsyncSession,
    *,
    brief: str,
    keywords: list[str] | None = None,
    category_count: int = 6,
    article_count: int = 12,
    content_type_id: int | None = None,
    lang: str = "zh-CN",
) -> tuple[dict[str, Any], list[str], models.ContentType]:
    """调 LLM 产出方案。失败抛 RuntimeError，由 router 转成 503。"""
    ct = await resolve_content_type(db, content_type_id)
    prompt = _SYSTEM.format(
        max_cat=min(max(1, category_count), MAX_CATEGORIES),
        max_depth=MAX_DEPTH,
        max_art=min(max(1, article_count), MAX_ARTICLES),
    )
    user_msg = (
        f"站点需求：{brief.strip()}\n"
        f"目标栏目数：{category_count}，目标选题数：{article_count}\n"
    )
    if keywords:
        user_msg += "必须覆盖的关键词：" + "、".join(keywords[:30]) + "\n"
    user_msg += f"内容语言：{lang}"

    try:
        llm = get_llm()
        _raw, result = await llm.chat_json(
            [{"role": "system", "content": prompt}, {"role": "user", "content": user_msg}],
            temperature=0.3,
            max_tokens=3000,
        )
    except Exception as exc:  # 网络/额度/解析，统一成可读错误
        raise RuntimeError(f"AI 生成方案失败：{exc}") from exc

    if not isinstance(result, dict):
        raise RuntimeError("AI 返回的不是 JSON 对象")

    plan, warnings = normalize_plan(
        result,
        max_categories=min(max(1, category_count), MAX_CATEGORIES),
        max_articles=min(max(1, article_count), MAX_ARTICLES),
    )
    return plan, warnings, ct


def plan_items(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """方案 → 待办行（栏目在前、按层级顺序，选题在后）。"""
    items: list[dict[str, Any]] = []
    seq = 0
    for cat in plan.get("categories") or []:
        seq += 1
        items.append(
            {"seq": seq, "kind": "category", "parent_key": cat.get("parent_key"), "payload": cat}
        )
    for art in plan.get("articles") or []:
        seq += 1
        items.append(
            {"seq": seq, "kind": "article", "parent_key": art.get("category_key"), "payload": art}
        )
    return items


async def dry_run(db: AsyncSession, plan: SitePlan) -> dict[str, Any]:
    """只算差异，不写任何业务表。"""
    data = plan.plan_json or {}
    cats = data.get("categories") or []
    arts = data.get("articles") or []
    ct = await resolve_content_type(db, plan.content_type_id)

    slugs = [c["slug"] for c in cats]
    existing: set[str] = set()
    if slugs:
        rows = (
            await db.execute(
                select(models.Category.slug).where(
                    models.Category.content_type_id == ct.id,
                    models.Category.slug.in_(slugs),
                    models.Category.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        existing = set(rows)

    return {
        "content_type": {"id": ct.id, "key": ct.key, "name": ct.name},
        "categories_total": len(cats),
        "categories_new": len([s for s in slugs if s not in existing]),
        "categories_existing": sorted(existing),
        "articles": len(arts),
        "pages": 0,
        "batch_job": True,
        "warnings": [],
    }


async def apply_plan(db: AsyncSession, plan: SitePlan) -> dict[str, Any]:
    """按 栏目 → 选题 的顺序执行。

    栏目：slug 已存在就复用（不覆盖已有栏目内容），只把 key 映射到旧 id，
    这样方案重跑不会产生一堆同名栏目。
    选题：整批塞进现有 AI 批量队列，复用它的并发控制、失败重试与进度展示。
    """
    if plan.status != "confirmed":
        raise ValueError(f"只有已确认的方案可以执行（当前状态 {plan.status}）")

    data = plan.plan_json or {}
    cats = data.get("categories") or []
    arts = data.get("articles") or []
    ct = await resolve_content_type(db, plan.content_type_id)

    plan.status = "running"
    plan.started_at = datetime.now(UTC)
    plan.error = None

    key_to_id: dict[str, int] = {}
    created_cats = 0
    reused_cats = 0

    for i, cat in enumerate(cats):
        slug = cat["slug"]
        old = (
            await db.execute(
                select(models.Category).where(
                    models.Category.content_type_id == ct.id,
                    models.Category.slug == slug,
                    models.Category.deleted_at.is_(None),
                )
            )
        ).scalars().first()
        if old is not None:
            key_to_id[cat["key"]] = old.id
            reused_cats += 1
            continue
        parent_id = key_to_id.get(cat.get("parent_key")) if cat.get("parent_key") else None
        row = models.Category(
            site_id=plan.site_id,
            content_type_id=ct.id,
            parent_id=parent_id,
            slug=slug,
            name=cat["name"],
            sort=i,
            status="active",
        )
        db.add(row)
        await db.flush()
        key_to_id[cat["key"]] = row.id
        created_cats += 1

    # 选题 → 批量队列
    batch_id: int | None = None
    if arts:
        topics: list[str] = []
        for a in arts:
            parts = [a["title"]]
            if a.get("keyword"):
                parts.append(f"关键词：{a['keyword']}")
            if a.get("brief"):
                parts.append(f"要点：{a['brief']}")
            parts.append(f"所属栏目：{a['category_key']}")
            topics.append("\n".join(parts)[:6000])

        job = CmsAiBatchJob(
            site_id=plan.site_id,
            name=(f"{plan.summary or '建站方案'} · 首批 {len(topics)} 篇")[:120],
            content_type_id=ct.id,
            content_type_key=ct.key,
            status="pending",
            lang=plan.lang or "zh-CN",
            total=len(topics),
            concurrency=1,
            created_by=plan.created_by,
        )
        db.add(job)
        await db.flush()
        batch_id = job.id
        for seq, topic in enumerate(topics, start=1):
            db.add(
                CmsAiBatchItem(
                    job_id=job.id,
                    site_id=plan.site_id,
                    seq=seq,
                    brief=topic,
                    status="pending",
                )
            )

    # 待办行回填执行结果，前端能逐条看到「建了 / 复用 / 进批次」
    items = (
        await db.execute(
            select(SitePlanItem).where(SitePlanItem.plan_id == plan.id).order_by(SitePlanItem.seq)
        )
    ).scalars().all()
    for item in items:
        payload = item.payload or {}
        if item.kind == "category":
            tid = key_to_id.get(payload.get("key"))
            if tid:
                item.target_id = tid
                item.status = "created"
            else:
                item.status = "failed"
                item.error = "栏目未能创建"
        elif item.kind == "article":
            item.status = "pending"
            item.error = f"已进入批次 #{batch_id}" if batch_id else "未进批次"
        elif item.kind == "page":
            item.status = "skipped"
            item.error = "页面骨架暂未实现，请在「页面构建」里手动建"

    plan.batch_job_id = batch_id
    plan.status = "done"
    plan.finished_at = datetime.now(UTC)
    await db.commit()

    # 事务提交后再启动批次：启动会起后台任务，先起后提交会读到不存在的 job
    if batch_id:
        from cenkor_admin.apps.cms.ai import batch_runner

        batch_runner.start(batch_id)

    return {
        "categories_created": created_cats,
        "categories_reused": reused_cats,
        "articles": len(arts),
        "batch_job_id": batch_id,
    }
