"""问答式站内搜索：访客提问 → 混合检索 → 带引用作答。

## 和 RAG 检索的区别

`rag.retrieve` 是给**机器**用的：返回片段，让外部 Agent 自己拼 prompt。
这里是给**人**用的：要一段能直接读的回答，且每句话都能点回原文。

同一个检索底座，两种交付形态。不做两套检索逻辑——检索质量只该有一个来源。

## 铁律：查不到就说查不到

站内问答最大的风险不是「答得不好」，是**答得好听但库里没有**。
检索有命中但撑不起回答时，宁可返回 no_answer 也不许编。

三道闸：
1. **检索为空直接短路**，连 LLM 都不调（省钱，且物理上不可能编）
2. 提示词限定「只能使用给定片段」，并显式允许输出 no_answer
3. **引用编号白名单校验**：模型引了不存在的编号 → 剔除，并把该句降级标注

## 引用为什么用编号而不是 URL

模型写 URL 会拼错（实测：多一层 `/api/v1`、slug 与 id 混用）。
所以让它只引编号 `[1]`，URL 由代码从 hits 里回填 ——
**出处必须是代码给的，不能是模型说的**。
"""

from __future__ import annotations

import re
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.ai import prompt_registry as prompts
from cenkor_admin.apps.cms.ai import rag as rag_mod
from cenkor_admin.apps.cms.ai.copilot import _as_object, _record
from cenkor_admin.core.llm import LLMError, LLMNotConfiguredError, get_llm

_KIND_ASK = "qa_ask"

# 引用标记：[1] 〔1〕 [1,2] [1][2]
_CITE_RE = re.compile(r"[\[［〔]\s*(\d+(?:\s*[,，、]\s*\d+)*)\s*[\]］〕]")

_ASK_SYSTEM = """你是 Cenkor 官网的内容助理，回答访客提问。

## 铁律

1. **只能用下面提供的「资料片段」回答**。片段里没有的信息，一个字都不许加。
   不许用你自己的常识补充背景、举例、给数字。
2. 如果片段不足以回答问题，就明确说「站内暂时没有相关内容」，并把 content 置空，
   no_answer 置 true。**宁可说不知道，也不要给一个听起来对的答案。**
3. 每句话后面必须标引用编号，格式 `[1]`。一句话用了多个片段就写 `[1][3]`。
   **只能引片段列表里出现过的编号**，不存在的一律不许写。
4. 资料与问题无关时（比如问的是 A，片段讲的是 B），同样 no_answer=true。

## 语气

简洁、直接、给结论。不要「根据您提供的资料」「综上所述」这类填充句。
一段话能说完就一段话，需要列举时才用列表。

## 输出

严格 JSON：
{"answer": "markdown 正文，含 [n] 引用标记", "no_answer": false, "reason": "no_answer 为 true 时说明缺什么信息", "followups": ["访客可能追问的问题，2~3 个"]}
"""


async def _kb_hits(session: AsyncSession, question: str, *, limit: int = 3) -> list[dict[str, Any]]:
    """取知识库命中，转成和站内片段同构的形态。

    为什么单独一路而不是并进 rag.retrieve：
    两路的分数量纲不同（站内是混合分，知识库是纯余弦），混在一起排序会让
    「谁排前面」变成一个没法解释的结果。分批追加、编号连续，至少引用是可追溯的。

    函数内 import：knowledge → ingest → copilot，而本模块也 import copilot，
    顶层导入会撞循环。
    """
    from cenkor_admin.apps.cms import knowledge
    from cenkor_admin.core.site_scope import current_site_id

    try:
        rows = await knowledge.search(
            session, question, site_id=current_site_id() or 1, limit=limit
        )
    except Exception as exc:
        # 知识库挂了不该让站内问答整体不可用
        logger.warning("cms.qa.kb_failed", error=str(exc))
        return []

    return [
        {
            "title": r["doc_title"],
            "heading_path": r["heading_path"],
            "text": r["text"],
            "score": r["score"],
            "source_url": "",
            "source": "kb",
        }
        for r in rows
    ]


def _build_context(hits: list[dict[str, Any]]) -> str:
    """把 chunk 列表拼成带编号的资料块。"""
    lines: list[str] = []
    for i, h in enumerate(hits, start=1):
        heading = h.get("heading_path") or h.get("title") or ""
        # 标出来源，模型才不会把「内部资料」当成「站内文章」来引用；
        # 访客侧也据此区分可点原页 vs 无公开链接
        tag = "企业知识库" if h.get("source") == "kb" else "站内内容"
        lines.append(f"[{i}]（{tag}）《{h.get('title') or '未命名'}》 · {heading}")
        lines.append(str(h.get("text") or "").strip())
        lines.append("")
    return "\n".join(lines).strip()


def _clean_citations(answer: str, n_hits: int) -> tuple[str, list[int]]:
    """剔除越界引用编号，返回 (清洗后正文, 实际用到的编号)。

    模型编造编号是高频失效模式（尤其是它想表达「都说了」的时候）。
    与其报错，不如静默剔除越界的——正文还在，只是那句不再有出处可点。
    """
    used: list[int] = []

    def _repl(m: re.Match[str]) -> str:
        nums = [int(x) for x in re.split(r"[,，、]", m.group(1)) if x.strip().isdigit()]
        keep = [n for n in nums if 1 <= n <= n_hits]
        for n in keep:
            if n not in used:
                used.append(n)
        if not keep:
            return ""  # 整组都越界 → 去掉标记
        return "".join(f"[{n}]" for n in keep)

    cleaned = _CITE_RE.sub(_repl, answer or "")
    return cleaned.strip(), sorted(used)


async def ask(
    session: AsyncSession,
    question: str,
    *,
    content_type_id: int | None = None,
    content_type_key: str | None = None,
    top_k: int = 5,
    include_drafts: bool = False,
    lang: str = "zh-CN",
    created_by: int | None = None,
) -> dict[str, Any]:
    """回答问题。**只读，不写内容表**（AI 调用落 ai_generations 记账）。"""
    q = (question or "").strip()
    if not q:
        return _empty("", "问题为空")

    # 闸一：检索为空直接短路，不花 token
    retrieved = await rag_mod.retrieve(
        session,
        q,
        content_type_id=content_type_id,
        content_type_key=content_type_key,
        top_k=top_k,
        candidates=12,
        include_drafts=include_drafts,
    )
    hits = list(retrieved.get("hits") or [])

    # 站内没有命中不等于答不上来：参数、流程、规格这类事实往往只在知识库里。
    # 所以在短路之前先补一路检索，两路都空才判「没有相关内容」。
    if len(hits) < top_k:
        hits.extend(await _kb_hits(session, q, limit=max(1, top_k - len(hits))))

    if not hits:
        warning = retrieved.get("warning")
        reason = warning or "站内没有检索到相关内容"
        return _empty(q, reason)

    context = _build_context(hits)
    user_msg = f"资料片段（共 {len(hits)} 条）：\n\n{context}\n\n---\n\n访客问题：{q}\n\n输出语言：{lang}"

    messages = [
        {"role": "system", "content": await prompts.get(session, "qa_ask", _ASK_SYSTEM)},
        {"role": "user", "content": user_msg},
    ]

    try:
        llm = get_llm()
        raw, result = await llm.chat_json(messages, temperature=0.2, max_tokens=4000)
    except LLMNotConfiguredError:
        # 没配模型不是错误：退化成「检索结果直出」，访客仍能看到相关片段
        logger.warning("cms.qa.llm_not_configured")
        return _degraded(q, hits, "AI 模型未配置，已降级为检索结果")
    except LLMError as exc:
        await _record(
            session,
            kind=_KIND_ASK,
            target="public",
            result=None,
            status="failed",
            error=str(exc),
            created_by=created_by,
            prompt=user_msg,
        )
        logger.warning("cms.qa.llm_failed err={}", str(exc))
        return _degraded(q, hits, f"AI 作答失败，已降级为检索结果：{exc}")

    obj = _as_object(raw, "问答")
    raw_answer = str(obj.get("answer") or "").strip()
    no_answer = bool(obj.get("no_answer")) or not raw_answer
    answer, used = _clean_citations(raw_answer, len(hits)) if raw_answer else ("", [])

    if no_answer:
        # 模型判「答不上来」时仍可能附一段正文（实测会发生）。一律丢弃 ——
        # 没被判定为可回答的内容，出去就是编。这是站内问答唯一的硬底线。
        if answer:
            logger.info("cms.qa.dropped_answer no_answer q={} chars={}", q[:60], len(answer))
        answer, used = "", []
    elif not used:
        # 有正文但一个引用都没标 → 无法核验出处，按「不可信」降级
        logger.info("cms.qa.uncited_answer q={}", q[:60])
        no_answer = True
        answer = ""
        obj["reason"] = "生成的回答没有可核对的出处，已丢弃"

    citations = [
        {
            "index": i + 1,
            "title": h.get("title"),
            "heading_path": h.get("heading_path"),
            "source_url": h.get("source_url"),
            "snippet": (h.get("text") or "")[:300],
            "score": round(float(h.get("score") or 0.0), 4),
            # 前端据此区分「能点进去的站内文章」与「只能看摘录的内部资料」；
            # 降级路径早就带了这个字段，成功路径漏了会让同一份数据结构有两种形状
            "source": h.get("source") or "entry",
        }
        for i, h in enumerate(hits)
        if (i + 1) in used
    ]

    followups = [str(x).strip()[:80] for x in (obj.get("followups") or []) if str(x).strip()][:3]

    await _record(
        session,
        kind=_KIND_ASK,
        target="public",
        result=result,
        params={"q": q[:120], "hits": len(hits), "cited": len(citations), "no_answer": no_answer},
        created_by=created_by,
        prompt=user_msg,
    )

    logger.info(
        f"[qa] q={q[:50]!r} hits={len(hits)} cited={len(citations)} no_answer={no_answer}"
    )

    return {
        "question": q,
        "answer": answer,
        "citations": citations,
        "no_answer": no_answer,
        # reason 是给人看的：no_answer 时 citations 为空，留着 [1][2] 只会误导
        "reason": (
            None
            if not no_answer
            else _CITE_RE.sub("", str(obj.get("reason") or "站内资料不足以回答该问题")).strip()
            or "站内资料不足以回答该问题"
        ),
        "followups": [] if no_answer else followups,
        "llm_used": True,
        "warning": None,
    }


def _empty(question: str, reason: str) -> dict[str, Any]:
    return {
        "question": question,
        "answer": "",
        "citations": [],
        "no_answer": True,
        "reason": reason,
        "followups": [],
        "llm_used": False,
        "warning": None,
    }


def _degraded(question: str, hits: list[dict[str, Any]], warning: str) -> dict[str, Any]:
    """LLM 不可用时的兜底：把检索片段当结果给出去，至少访客能找到原文。"""
    return {
        "question": question,
        "answer": "",
        "citations": [
            {
                "index": i + 1,
                "title": h.get("title"),
                "heading_path": h.get("heading_path"),
                "source_url": h.get("source_url"),
                "snippet": (h.get("text") or "")[:300],
                "score": round(float(h.get("score") or 0.0), 4),
                "source": h.get("source") or "entry",
            }
            for i, h in enumerate(hits)
        ],
        "no_answer": False,
        "reason": None,
        "followups": [],
        "llm_used": False,
        "warning": warning,
    }
