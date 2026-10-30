"""内链建议。

## 为什么不做成「自动插链」

自动插链有三个硬伤：
1. **读者体验差** —— 机器觉得相关，读者觉得跳过去啥也没有
2. **锚文本不自然** —— 生成「点击了解更多」式的锚文本对 SEO 是负优化
3. **错误难回滚** —— 插进去的链接要一条条删

所以本模块只做「建议」，插入动作交给人（或前端一键插入到光标处）。

## 两段式

1. **候选召回**（无 LLM）：用条目自己的向量找语义相近的条目
   —— 复用现成的 `similar_entries`，零额外向量成本
2. **价值判断**（一次 LLM 调用）：把候选的标题+摘要给它，让它挑出
   真正「读者会想知道」的，并给出**自然的锚文本**和**插入位置建议**

LLM 只在最后一步调用一次（批量给候选，不是每个候选一次）。
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.ai import prompt_registry as prompts
from cenkor_admin.apps.cms.ai.embedding import entry_to_text
from cenkor_admin.apps.cms.ai.search import similar_entries
from cenkor_admin.apps.cms.models import Entry
from cenkor_admin.core.llm import LLMNotConfiguredError, get_llm

_INTERNAL_LINK_SYSTEM = """你是内容编辑助手。给你一篇正在编辑的文章，以及几篇候选相关文章。

你的任务：判断哪些候选值得在正文中插入内链。

只输出一个 JSON 对象（不要数组、不要解释、不要代码围栏）：
{"links": [{"entry_id": 123, "anchor_text": "锚文本", "reason": "为什么值得链", "insert_after": "锚点上下文片段"}]}

硬性规则：
1. entry_id 必须来自给定的候选列表，不许编造
2. anchor_text 是正文中会实际出现的短语（如「取向硅钢的电磁性能优势」），
   要贴合候选文章主题，长度 4-16 字，**不要用「点击查看」「了解更多」这类空洞词**
3. insert_after 是正文中适合插入该链接的**上下文片段**（原文里真实出现的连续文字，20-40 字），
   用于定位插入点；找不到合适位置就给空字符串
4. 最多 3 条，宁缺毋滥 —— 语义相近但读者不需要跳转的，不要推荐
5. reason 一句话说明读者点过去能获得什么
6. 绝不推荐与本文主题无关的内容"""

# 同站/跨站都能链，但同站更有 SEO 价值
_DEFAULT_CANDIDATES = 8
_MAX_LINKS = 3


def _excerpt(text: str, limit: int = 160) -> str:
    t = " ".join((text or "").split())
    return t[:limit] + ("…" if len(t) > limit else "")


async def _candidate_entries(
    session: AsyncSession,
    entry: Entry,
    *,
    limit: int,
) -> list[tuple[Entry, str]]:
    """召回候选：语义相近的已发布条目。返回 [(条目, 内容类型 key)]，保持相似度顺序。"""
    hits = await similar_entries(session, entry.id, limit=limit)
    if not hits:
        return []
    ids = [h.entry_id for h in hits]
    rows = (
        (
            await session.execute(
                select(Entry).where(Entry.id.in_(ids), Entry.deleted_at.is_(None))
            )
        )
        .scalars()
        .all()
    )
    by_id = {e.id: e for e in rows}

    # 出处 URL 需要内容类型 key（公开详情路由是 /site/{content_type_key}/{slug}）
    ct_ids = {e.content_type_id for e in by_id.values()}
    ct_key_map: dict[int, str] = {}
    if ct_ids:
        from cenkor_admin.apps.cms.models import ContentType

        ct_rows = (
            await session.execute(
                select(ContentType.id, ContentType.key).where(ContentType.id.in_(ct_ids))
            )
        ).all()
        ct_key_map = {r[0]: r[1] for r in ct_rows}

    out: list[tuple[Entry, str]] = []
    for h in hits:  # 保持相似度顺序
        e = by_id.get(h.entry_id)
        if e is not None:
            out.append((e, ct_key_map.get(e.content_type_id, "")))
    return out


async def suggest_links(
    session: AsyncSession,
    entry: Entry,
    *,
    created_by: int | None = None,
    max_links: int = _MAX_LINKS,
    candidates: int = _DEFAULT_CANDIDATES,
) -> dict[str, Any]:
    """给一条内容找内链建议。

    返回：{entry_id, candidates: [...], links: [...], warning}
    candidates 是召回的候选（含相似度），links 是 LLM 精选后的建议。
    """
    if entry is None:
        return {"entry_id": 0, "candidates": [], "links": [], "warning": "条目不存在"}

    try:
        cands = await _candidate_entries(session, entry, limit=candidates)
    except LLMNotConfiguredError:
        cands = []
    except Exception as exc:
        logger.warning("cms.internal_link.recall_failed entry={} err={}", entry.id, str(exc))
        cands = []

    if not cands:
        return {
            "entry_id": entry.id,
            "candidates": [],
            "links": [],
            "warning": "没有找到语义相近的候选内容",
        }

    cand_payload = [
        {
            "entry_id": c.id,
            "title": c.title,
            "slug": c.slug,
            "content_type_key": ct_key,
            "summary": _excerpt(entry_to_text(c)),
        }
        for c, ct_key in cands
    ]

    # LLM 精选
    try:
        llm = get_llm()
        raw, _result = await llm.chat_json(
            [
                {
                    "role": "system",
                    "content": await prompts.get(session, "internal_link", _INTERNAL_LINK_SYSTEM),
                },
                {
                    "role": "user",
                    "content": (
                        f"【正在编辑的文章】\n标题：{entry.title}\n"
                        f"正文摘录：\n{_excerpt(entry_to_text(entry), 1200) or '（无正文）'}\n\n"
                        f"【候选相关文章】\n{json.dumps(cand_payload, ensure_ascii=False)}"
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=900,
        )
    except LLMNotConfiguredError:
        return {
            "entry_id": entry.id,
            "candidates": cand_payload,
            "links": [],
            "warning": "AI 未配置，无法生成内链建议（候选已召回）",
        }
    except Exception as exc:
        logger.warning("cms.internal_link.llm_failed entry={} err={}", entry.id, str(exc))
        return {
            "entry_id": entry.id,
            "candidates": cand_payload,
            "links": [],
            "warning": f"AI 调用失败：{exc}",
        }

    obj = raw if isinstance(raw, dict) else {}
    items = obj.get("links") if isinstance(obj.get("links"), list) else []

    valid_ids = {c["entry_id"] for c in cand_payload}
    cand_by_id = {c["entry_id"]: c for c in cand_payload}

    links: list[dict[str, Any]] = []
    seen: set[int] = set()
    for it in items[:max_links]:
        if not isinstance(it, dict):
            continue
        try:
            eid = int(it.get("entry_id"))
        except (TypeError, ValueError):
            continue
        if eid not in valid_ids or eid in seen:
            continue
        seen.add(eid)
        anchor = str(it.get("anchor_text") or "").strip()[:60]
        if not anchor:
            continue
        c = cand_by_id[eid]
        links.append(
            {
                "entry_id": eid,
                "title": c["title"],
                "slug": c["slug"],
                "anchor_text": anchor,
                "reason": str(it.get("reason") or "").strip()[:200],
                "insert_after": str(it.get("insert_after") or "").strip()[:200],
                "source_url": (
                    f"/api/v1/public/site/{c['content_type_key']}/{c['slug'] or c['entry_id']}"
                    if c.get("content_type_key")
                    else f"/api/v1/public/site/entry/{c['entry_id']}"
                ),
            }
        )

    logger.info(
        "cms.internal_link entry={} candidates={} links={}",
        entry.id, len(cand_payload), len(links),
    )
    return {
        "entry_id": entry.id,
        "candidates": cand_payload,
        "links": links,
    }


__all__ = ["suggest_links"]
