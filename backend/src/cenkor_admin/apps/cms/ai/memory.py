"""AI CMS 记忆层 —— 站点记忆 + 内容记忆。

为什么要有它：现在的 CMS 每次起草都是一次性交易 —— 同一个站点，今天写的和
上个月写的没有任何关联。人会越写越像「这家公司的笔」，AI 不会：它每次都从零
开始，术语写法飘、参数口径前后矛盾、同一个选题写三遍。

分两层，来源和可信度刻意分开：

1. **站点记忆**（`cms_ai_memory`）
   - `manual`：硬事实（产品参数、公司口径、禁用词）。错一条就是事故，只能人工写。
   - `ai`：软风格（语言习惯、结构偏好）。AI 从已发布内容里提炼，默认 `pending`，
     人审过才 `approved` —— 提炼出来的东西看着像那么回事、实际上是编的，这很常见。

2. **内容记忆**（`cms_ai_entry_digests`）
   已发布内容的 120 字摘要 + 话题 + 关键实体。起草时带上最近 N 篇，让 AI 知道
   「这个话题我们写过、当时结论是什么」，避免重复选题和自相矛盾。

刻意不做「智能检索」：现在全站几十条内容，向量检索是杀鸡用牛刀，而且检索错一条
就漏一条。直接把最近 15 篇摘要（约 1800 字）塞进提示词更准也更简单。等内容上到
几百条再换向量召回。

注入位置在 system prompt **末尾**：固定部分在前、记忆在后，前缀缓存才能命中。
把记忆塞在最前面会让每次请求的前缀都不一样，缓存全废。
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.ai.models import (
    CmsAiEntryDigest,
    CmsAiMemory,
    MEMORY_SCOPE_LABEL,
    MEMORY_SCOPES,
)

# 渲染顺序 = 重要程度。品牌调性和硬事实必须先进预算，
# 否则一堆术语条目会把最关键的调性挤出预算之外。
_SCOPE_ORDER = ("brand", "fact", "term", "ban", "style", "audience")

# 提示词预算。2000 字符 ≈ 1000 token，对一次起草来说占比很小，
# 但足够装下十几条记忆。超了宁可截断也不全塞 —— 记忆挤掉素材反而更糟。
DEFAULT_BUDGET = 2000

# 内容记忆默认带最近 15 篇
CONTENT_MEMORY_LIMIT = 15


def _site_id() -> int:
    from cenkor_admin.core.site_scope import current_site_id

    return current_site_id() or 1


def _digest(text_value: str) -> str:
    return hashlib.sha256((text_value or "").encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------- 站点记忆读写


def _row_out(row: CmsAiMemory) -> dict[str, Any]:
    return {
        "id": row.id,
        "scope": row.scope,
        "scope_label": MEMORY_SCOPE_LABEL.get(row.scope, row.scope),
        "key": row.key or "",
        "content": row.content,
        "weight": row.weight,
        "enabled": bool(row.enabled),
        "source": row.source,
        "status": row.status,
        "injection_count": row.injection_count,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def list_memory(
    session: AsyncSession,
    *,
    status: str | None = None,
    scope: str | None = None,
    site_id: int | None = None,
) -> list[dict[str, Any]]:
    sid = site_id if site_id is not None else _site_id()
    stmt = select(CmsAiMemory).where(CmsAiMemory.site_id == sid)
    if status:
        stmt = stmt.where(CmsAiMemory.status == status)
    if scope:
        stmt = stmt.where(CmsAiMemory.scope == scope)
    stmt = stmt.order_by(
        CmsAiMemory.status, CmsAiMemory.scope, CmsAiMemory.weight.desc(), CmsAiMemory.id
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_row_out(r) for r in rows]


async def upsert_memory(
    session: AsyncSession,
    *,
    scope: str,
    content: str,
    key: str = "",
    weight: int = 50,
    enabled: bool = True,
    source: str = "manual",
    status: str = "approved",
    created_by: int | None = None,
    memory_id: int | None = None,
    site_id: int | None = None,
) -> dict[str, Any]:
    """新增或更新一条记忆。

    同 (site, scope, key) 且 key 非空时视为同一条（术语、禁用词天然唯一），
    直接覆盖内容而不是堆两条 —— 两条「法兰球阀」互相打架时，AI 只会随机听一条。
    """
    sid = site_id if site_id is not None else _site_id()
    scope = (scope or "").strip()
    if scope not in MEMORY_SCOPES:
        raise ValueError(f"记忆分类非法：{scope}，可选 {MEMORY_SCOPES}")
    content = (content or "").strip()
    if not content:
        raise ValueError("记忆内容不能为空")
    key = (key or "").strip()[:120]
    weight = max(0, min(100, int(weight or 50)))

    row: CmsAiMemory | None = None
    if memory_id:
        row = await session.get(CmsAiMemory, memory_id)
        if row is not None and row.site_id != sid:
            raise ValueError("该记忆不属于当前站点")
    elif key:
        row = (
            await session.execute(
                select(CmsAiMemory).where(
                    CmsAiMemory.site_id == sid,
                    CmsAiMemory.scope == scope,
                    CmsAiMemory.key == key,
                )
            )
        ).scalar_one_or_none()
    else:
        # 没有 key 的条目（品牌调性、写作偏好这类）在库里没有唯一约束，
        # 靠「内容前 40 字」认领同一条。不这么做的话，重复提交一次就多一条，
        # 几天后同一个意思能堆出五六行，AI 反而被自己的记忆搞糊涂。
        row = (
            await session.execute(
                select(CmsAiMemory).where(
                    CmsAiMemory.site_id == sid,
                    CmsAiMemory.scope == scope,
                    CmsAiMemory.key == "",
                    CmsAiMemory.content.startswith(content[:40]),
                )
            )
        ).scalars().first()

    if row is None:
        row = CmsAiMemory(site_id=sid, scope=scope, created_by=created_by)
        session.add(row)

    row.scope = scope
    row.key = key
    row.content = content
    row.weight = weight
    row.enabled = bool(enabled)
    row.source = source
    row.status = status
    await session.commit()
    await session.refresh(row)
    return _row_out(row)


async def delete_memory(session: AsyncSession, memory_id: int) -> bool:
    row = await session.get(CmsAiMemory, memory_id)
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def set_memory_status(session: AsyncSession, memory_id: int, status: str) -> dict[str, Any]:
    if status not in ("approved", "pending", "rejected"):
        raise ValueError(f"状态非法：{status}")
    row = await session.get(CmsAiMemory, memory_id)
    if row is None:
        raise ValueError("记忆不存在")
    row.status = status
    await session.commit()
    await session.refresh(row)
    return _row_out(row)


# ---------------------------------------------------------------- 注入渲染


def _render_line(scope: str, key: str, content: str) -> str:
    """一条记忆 → 提示词里的一行。

    术语和禁用词的 key 是「词本身」，必须显式标出「术语」还是「禁用」——
    早先这里套了「不要写成 {content}」的统一模板，结果渲染出
    「「MES」：不要写成 制造执行系统…」，把规范写成了禁忌，意思完全反了。
    语义标签只能按 scope 给，不能靠模板套。
    """
    if scope == "term" and key:
        return f"- 术语「{key}」：{content}"
    if scope == "ban" and key:
        return f"- 禁用「{key}」：{content}"
    if key:
        return f"- {key}：{content}"
    return f"- {content}"


async def render_prompt_block(
    session: AsyncSession,
    *,
    budget: int = DEFAULT_BUDGET,
    with_content_memory: bool = True,
    content_limit: int = CONTENT_MEMORY_LIMIT,
    count_hits: bool = True,
    site_id: int | None = None,
) -> tuple[str, dict[str, Any]]:
    """把记忆渲染成可直接拼进 system prompt 的文本块。

    返回 `(文本, 元信息)`；元信息里有实际注入了哪些 id、被预算截掉几条 ——
    「记忆写了但从来没被用上」是最难发现的问题，必须能看见。
    """
    sid = site_id if site_id is not None else _site_id()

    rows = (
        (
            await session.execute(
                select(CmsAiMemory)
                .where(
                    CmsAiMemory.site_id == sid,
                    CmsAiMemory.status == "approved",
                    CmsAiMemory.enabled.is_(True),
                )
                .order_by(CmsAiMemory.weight.desc(), CmsAiMemory.id)
            )
        )
        .scalars()
        .all()
    )

    if not rows:
        return "", {"injected": 0, "truncated": 0, "ids": [], "content_memory": 0}

    # 按 scope 分组，但组内保持 weight 顺序
    grouped: dict[str, list[CmsAiMemory]] = {}
    for r in rows:
        grouped.setdefault(r.scope, []).append(r)

    used = 0
    lines: list[str] = ["【本站长期记忆 · 起草时必须遵守，优先级高于通用写作常识】"]
    injected_ids: list[int] = []
    truncated = 0

    for scope in _SCOPE_ORDER:
        items = grouped.get(scope) or []
        if not items:
            continue
        header = f"\n## {MEMORY_SCOPE_LABEL.get(scope, scope)}"
        scope_lines: list[str] = []
        for r in items:
            line = _render_line(scope, r.key or "", r.content)
            # 超预算就停：宁可少注入一条，也不能把后面的素材挤掉
            if used + len(line) + 1 > budget:
                truncated += 1
                continue
            used += len(line) + 1
            scope_lines.append(line)
            injected_ids.append(r.id)
        if scope_lines:
            lines.append(header)
            lines.extend(scope_lines)

    content_count = 0
    if with_content_memory:
        remaining = budget - used
        if remaining > 200:
            digests = await recent_digests(session, limit=content_limit, site_id=sid)
            if digests:
                block: list[str] = [
                    "\n## 已发布内容（避免重复选题；若与上面的事实冲突，以上面为准）"
                ]
                for i, d in enumerate(digests, 1):
                    line = f"{i}. 《{d['title']}》— {d['digest']}"
                    if sum(len(x) + 1 for x in block) + len(line) > remaining:
                        break
                    block.append(line)
                    content_count += 1
                if content_count:
                    lines.extend(block)

    if count_hits and injected_ids:
        # 一次批量自增，别在循环里逐条 UPDATE
        await session.execute(
            update(CmsAiMemory)
            .where(CmsAiMemory.id.in_(injected_ids))
            .values(injection_count=CmsAiMemory.injection_count + 1)
        )
        await session.commit()

    body = "\n".join(lines)
    return body, {
        "injected": len(injected_ids),
        "truncated": truncated,
        "ids": injected_ids,
        "content_memory": content_count,
        "chars": len(body),
    }


# ---------------------------------------------------------------- 内容记忆


def _plain_text(title: str, content: Any) -> str:
    """条目 JSONB 正文 → 纯文本。延迟 import 避免与 copilot 互相依赖。"""
    try:
        from cenkor_admin.apps.cms.ai.copilot import _draft_to_text

        text_value = _draft_to_text("", content or {})
        if text_value.strip():
            return text_value
        return _draft_to_text(title or "", content or {})
    except Exception:
        # 兜底：递归收集字符串值，宁可粗糙也不能抛异常
        parts: list[str] = []

        def walk(node: Any) -> None:
            if isinstance(node, str):
                parts.append(node)
            elif isinstance(node, dict):
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(content or {})
        return "\n".join(parts)


async def recent_digests(
    session: AsyncSession, *, limit: int = CONTENT_MEMORY_LIMIT, site_id: int | None = None
) -> list[dict[str, Any]]:
    sid = site_id if site_id is not None else _site_id()
    rows = (
        (
            await session.execute(
                select(CmsAiEntryDigest)
                .where(CmsAiEntryDigest.site_id == sid)
                .order_by(CmsAiEntryDigest.built_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "entry_id": r.entry_id,
            "title": r.title,
            "digest": r.digest,
            "topics": list(r.topics or []),
            "built_at": r.built_at.isoformat() if r.built_at else None,
        }
        for r in rows
    ]


_DIGEST_SYSTEM = """你是内容运营分析师。读一篇文章，输出它的记忆索引。

只输出 JSON，不要任何解释：
{
  "digest": "100 字以内，说清这篇讲了什么、结论是什么。不要复述标题，不要写「本文介绍了」",
  "topics": ["3-6 个短话题标签，每个 2-8 个字"],
  "entities": {"product": [], "org": [], "metric": []}
}

硬信息（型号、参数、数字、结论）必须保留在 digest 里 —— 记忆的意义就是
让下一篇文章不要和这篇打架。看不出的话题就不写，不要凑数。"""


async def digest_entries(
    session: AsyncSession, *, limit: int = 30, force: bool = False, site_id: int | None = None
) -> dict[str, Any]:
    """为已发布条目的内容记忆建索引。

    只处理「还没有摘要」或「正文改过」的条目 —— 正文一变，旧摘要就是错误记忆，
    AI 会拿上一版的结论写新文章，这比没有记忆更糟。
    """
    from cenkor_admin.apps.cms.ai.copilot import _record  # 延迟 import
    from cenkor_admin.core.llm import get_llm

    sid = site_id if site_id is not None else _site_id()

    rows = (
        await session.execute(
            text(
                """
                SELECT e.id, e.title, e.content, d.content_hash AS old_hash
                FROM cms_entries e
                LEFT JOIN cms_ai_entry_digests d ON d.entry_id = e.id
                WHERE e.site_id = :sid
                  AND e.deleted_at IS NULL
                  AND e.status IN ('published', 'draft', 'review')
                ORDER BY e.updated_at DESC NULLS LAST
                LIMIT :lim
                """
            ),
            {"sid": sid, "lim": max(1, int(limit) * 4)},
        )
    ).mappings().all()

    llm = get_llm()
    built = skipped = failed = degraded = 0
    errors: list[str] = []

    for r in rows:
        if built >= limit:
            break
        body = _plain_text(r["title"], r["content"]).strip()
        if len(body) < 80:
            # 太短的内容不值得建索引，摘要会退化成标题复述
            skipped += 1
            continue
        h = _digest(f"{r['title']}\n{body}")
        if not force and r["old_hash"] == h:
            skipped += 1
            continue

        # 摘要是「这段讲了什么」，不是「逐段复述」。正文截到 3000 字：
        # 一是省 token，二是推理模型的思考长度跟输入正相关，长文必翻车
        prompt = f"标题：{r['title']}\n\n正文：\n{body[:3000]}"
        try:
            data, result = await llm.chat_json(
                [
                    {"role": "system", "content": _DIGEST_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                # 推理模型（如 MiniMax-M3.1）会先吐思考过程，长正文能思考
                # 6000+ 字符，把 max_tokens 全吃光、正文为空。给足 6000 才能
                # 让「思考 + 摘要」都装下。实际只按真实输出计费，不是每次都烧满。
                max_tokens=6000,
            )
            dg = str((data or {}).get("digest") or "").strip()[:400]
            if not dg:
                skipped += 1
                continue
            topics = [
                str(t).strip()[:60]
                for t in ((data or {}).get("topics") or [])
                if str(t).strip()
            ][:8]
            entities = (data or {}).get("entities")
            if not isinstance(entities, dict):
                entities = {}

            exists = (
                await session.execute(
                    select(CmsAiEntryDigest).where(CmsAiEntryDigest.entry_id == r["id"])
                )
            ).scalar_one_or_none()
            if exists is None:
                exists = CmsAiEntryDigest(site_id=sid, entry_id=r["id"])
                session.add(exists)
            exists.title = (r["title"] or "")[:300]
            exists.digest = dg
            exists.topics = topics
            exists.entities = entities
            exists.content_hash = h

            await _record(
                session,
                kind="memory_digest",
                target=f"entry:{r['id']}",
                result=result,
                params={"chars": len(body)},
                prompt=prompt[:500],
            )
            await session.commit()
            built += 1
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            # 降级而不是留洞：一条索引生成失败就整篇没有记忆，这个洞是沉默的 ——
            # 起草时 AI 会以为「这篇没写过」，于是重复选题。用「标题 + 开头」
            # 生成一条粗糙但存在的摘要，并在 entities 里标记 degraded，
            # 之后想重做可以带 force=True 再跑一次。
            try:
                fallback = re.sub(r"\s+", " ", body)[:180].strip()
                exists = (
                    await session.execute(
                        select(CmsAiEntryDigest).where(CmsAiEntryDigest.entry_id == r["id"])
                    )
                ).scalar_one_or_none()
                if exists is None:
                    exists = CmsAiEntryDigest(site_id=sid, entry_id=r["id"])
                    session.add(exists)
                exists.title = (r["title"] or "")[:300]
                exists.digest = fallback or (r["title"] or "")[:180]
                exists.topics = []
                exists.entities = {"degraded": True, "reason": str(exc)[:200]}
                exists.content_hash = h
                await session.commit()
                built += 1
                degraded += 1
            except Exception:  # noqa: BLE001
                await session.rollback()
                failed += 1
            errors.append(f"entry {r['id']}: {type(exc).__name__}: {str(exc)[:100]}")

    return {"scanned": len(rows), "built": built, "skipped": skipped, "failed": failed,
            "degraded": degraded, "errors": errors[:5]}


_DISTILL_SYSTEM = """你是内容风格分析师。读一批本站已发布文章的摘要，归纳本站的**写作习惯**。

只输出 JSON：
{
  "brand":    ["品牌调性：语气、人称、价值主张，2-4 条"],
  "style":    ["写作习惯：句式偏好、段落结构、篇幅、标题写法，3-5 条"],
  "audience": ["目标读者画像：他们是谁、关心什么、什么水平，1-3 条"]
}

铁律：
- 只写**能从样本中明确看出**的。看不出来就少写，不要写「内容专业、质量高」这种
  放之四海皆准的空话
- 不要归纳业务事实（产品参数、公司信息）—— 那些由人工维护，AI 猜错就是事故
- 每条一句话，20-50 字"""


async def distill_style(
    session: AsyncSession, *, sample: int = 12, site_id: int | None = None
) -> dict[str, Any]:
    """从已发布内容里提炼**软风格**，写入 `pending` 等人工审核。

    为什么不直接生效：提炼出来的东西语感上很像真的，实际上经常是编的
    （比如样本里只有产品页，它能归纳出「善用比喻」）。必须人过一眼。
    """
    from cenkor_admin.apps.cms.ai.copilot import _record
    from cenkor_admin.core.llm import get_llm

    sid = site_id if site_id is not None else _site_id()
    digests = await recent_digests(session, limit=sample, site_id=sid)
    if len(digests) < 3:
        return {
            "ok": False,
            "reason": "已索引的内容不足 3 篇，先点「重建内容索引」，样本太少归纳出来的风格没有意义",
            "created": 0,
        }

    catalog = "\n".join(
        f"{i}. 《{d['title']}》— {d['digest']}" for i, d in enumerate(digests, 1)
    )
    llm = get_llm()
    data, result = await llm.chat_json(
        [
            {"role": "system", "content": _DISTILL_SYSTEM},
            {"role": "user", "content": f"本站已发布文章（{len(digests)} 篇）：\n{catalog}"},
        ],
        temperature=0.3,
        max_tokens=2500,
    )
    await _record(
        session,
        kind="memory_distill",
        target=f"site:{sid}",
        result=result,
        params={"sample": len(digests)},
        prompt=catalog[:500],
    )

    created = 0
    items: list[dict[str, Any]] = []
    for scope in ("brand", "style", "audience"):
        for line in (data or {}).get(scope) or []:
            line = str(line).strip()
            if len(line) < 6:
                continue
            # 只有 AI 提炼、没有人工审核，重复提炼会堆一堆近似条目；
            # 同 scope 下内容前 12 字相同就视为重复，不重复写
            dup = (
                await session.execute(
                    select(CmsAiMemory).where(
                        CmsAiMemory.site_id == sid,
                        CmsAiMemory.scope == scope,
                        CmsAiMemory.content.startswith(line[:12]),
                    )
                )
            ).scalar_one_or_none()
            if dup is not None:
                continue
            row = CmsAiMemory(
                site_id=sid,
                scope=scope,
                key="",
                content=line[:400],
                weight=60,
                enabled=True,
                source="ai",
                status="pending",
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            created += 1
            items.append(_row_out(row))

    return {"ok": True, "created": created, "sample": len(digests), "items": items}


async def memory_stats(session: AsyncSession, *, site_id: int | None = None) -> dict[str, Any]:
    sid = site_id if site_id is not None else _site_id()
    rows = (
        await session.execute(
            text(
                """
                SELECT scope, status, count(*) AS n, coalesce(sum(injection_count), 0) AS hits
                FROM cms_ai_memory WHERE site_id = :sid GROUP BY scope, status
                """
            ),
            {"sid": sid},
        )
    ).mappings().all()

    by_scope: dict[str, int] = {}
    approved = pending = 0
    hits = 0
    for r in rows:
        if r["status"] == "approved":
            approved += int(r["n"])
            by_scope[r["scope"]] = by_scope.get(r["scope"], 0) + int(r["n"])
        elif r["status"] == "pending":
            pending += int(r["n"])
        hits += int(r["hits"])

    digest_n = (
        await session.execute(
            text("SELECT count(*) FROM cms_ai_entry_digests WHERE site_id = :sid"),
            {"sid": sid},
        )
    ).scalar() or 0
    entry_n = (
        await session.execute(
            text(
                "SELECT count(*) FROM cms_entries "
                "WHERE site_id = :sid AND deleted_at IS NULL"
            ),
            {"sid": sid},
        )
    ).scalar() or 0

    return {
        "approved": approved,
        "pending": pending,
        "injection_total": hits,
        "by_scope": [
            {"scope": s, "label": MEMORY_SCOPE_LABEL.get(s, s), "count": by_scope.get(s, 0)}
            for s in _SCOPE_ORDER
            if by_scope.get(s)
        ],
        "digests": int(digest_n),
        "entries": int(entry_n),
        "coverage": round(digest_n / entry_n, 3) if entry_n else 0.0,
    }


async def clear_site_memory(session: AsyncSession, *, site_id: int) -> int:
    r = await session.execute(sa_delete(CmsAiMemory).where(CmsAiMemory.site_id == site_id))
    await session.commit()
    return r.rowcount or 0


def parse_memory_json(raw: str) -> Any:
    """给前端/脚本用的宽松 JSON 解析（去掉 ```json 围栏）。"""
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip(), flags=re.I)
    return json.loads(s)
