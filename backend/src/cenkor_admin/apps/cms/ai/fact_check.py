"""AI 事实溯源：给 AI 产出的正文标出「没有依据的具体说法」。

## 为什么单独做一块

`quality.py` 的 accuracy 是**打分**：给一个 0~100 的数，告诉你好不好，
但不告诉你哪句有问题、依据在哪。编辑拿到 72 分只能把全篇重读一遍。
`qa_search.py` 的姿势是对的（引用编号白名单），但那是「访客提问」场景，
产出的是回答，不是要发布的稿子。

要解决的是：**AI 写的这篇稿里，哪些具体说法站不住**。
起草、改写、翻译、再分发四个出口都在产出「读起来像事实」的文本，
但只有起草挂了知识库，另外三个基本靠模型自由发挥 —— 直接发出去就是品牌事故。

## 两段式：先便宜后贵

第一段是规则（零成本、确定性、可解释）：

    抽出正文里的「硬事实」—— 数字+单位、百分比、年月日、英文专名、引号短句，
    拿证据全文做归一化匹配。命中的直接判支持，一分钱不花。

第二段才调模型（**只对规则没兜住的句子**）：

    把这几句连同证据编号交出去，判 supported / unsupported / uncertain，
    并只能引用给定编号。

只把「有硬事实且规则没命中」的句子送去模型，是两个考虑：
一是省钱（一篇稿通常只有几处数字），二是准确 —— 模型判「这句话对不对」
比判「整篇文章有没有事实错误」稳得多。

## 铁律：依据必须是代码给的

同 qa_search —— 模型只准引编号 `[1]`，编号不存在的一律剔除，
并把该句降级为 uncertain。**出处不能由模型说了算。**

## 只告警，不阻断

结论放在 `level`（ok / warn / risk），发布流程不看它。
理由：核验本身有误判空间（模型常识、行业公知、通篇无事实的纯观点文），
拿它硬卡发布，编辑第一周就会把功能关掉。先让人看见，再谈卡不卡。
真要卡，把 `block_publish` 打开即可，逻辑已经留好。

## 「判断不了」不等于「有问题」

三态里 uncertain 是独立的一态，不是 unsupported 的弱化版：

- 支撑率的分母只算 supported + unsupported，**uncertain 不进分母**。
  一篇文章引了几处站外事实（本来就无从核验），要是算进分母，
  分数恒在 20% 附近，弹窗永远红色 —— 恒红指标没有信息量。
- 证据源为空时全部判 uncertain，而不是 unsupported。
  「查无依据」只有在**有证据源且证据里没有**时才等于可疑；
  一个证据源都没有的时候我们什么都不知道，标红就是制造假警报。
- 模型引用编号越界、或者判 supported 却没给出处，同样降级 uncertain。
"""

from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.ai import prompt_registry as prompts
from cenkor_admin.apps.cms.ai.copilot import _as_object, _record
from cenkor_admin.apps.cms.models import Entry
from cenkor_admin.core.llm import LLMNotConfiguredError, get_llm

_KIND_FACT_CHECK = "fact_check"

# 送去模型判定的句子上限。再多说明这篇稿子事实密度异常，
# 该做的是分篇重建，而不是让一次核验吃掉几万 token。
_MAX_SENTENCES = 14
# 单句上限：超长的句子往往是列表被断句器粘连，截断比整段送去更安全
_MAX_SENTENCE_CHARS = 600
# 正文上限：核验是抽样判断，不是全文索引，超了截断并标注
_MAX_BODY_CHARS = 12000
# 证据上限：给多了模型会乱引，给少了容易误判；8 条是实测能覆盖多数场景的数
_MAX_EVIDENCE = 8

# ---------------------------------------------------------------------------
# 断句与事实抽取
# ---------------------------------------------------------------------------

# 中文句末 + 英文句末；不按换行断，因为正文里的换行多半是排版而非语义
_SENT_SPLIT_RE = re.compile(r"(?<=[。！？；!?;])\s*|\n{2,}")

# 硬事实：能被证伪的具体值，不是形容词也不是判断
_FACT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # 百分比：37% / 3.5 %
    ("percent", re.compile(r"\d+(?:\.\d+)?\s*%")),
    # 数量 + 数量级 + 单位，整段一起抽：`2万亿美元` 要抽成 `2万亿美元` 而不是 `2万`。
    # 只抽前半截的话，证据里写「2 万亿美元」归一化后是 `2万亿美元`，
    # 包含 `2万`（能命中），但展示给编辑看的是半截数字，反而看不懂在核什么。
    (
        "quantity",
        re.compile(
            r"\d+(?:\.\d+)?\s*"
            r"(?:万亿|万|亿|千|百)?\s*"
            r"(?:美元|元|人|家|台|套|个|次|倍|天|小时|分钟|秒|年|月|日|"
            r"GB|MB|TB|ms|kg|km|℃|度|条|项|种|款|门|间|亩|吨)"
        ),
    ),
    # 年月日：2026 年 3 月 / 2026-03-15
    ("date", re.compile(r"\d{4}\s*年(?:\s*\d{1,2}\s*月)?|\d{4}-\d{1,2}-\d{1,2}")),
    # 版本号：必须带 v 前缀或三段点号。**不能写成 `\d+\.\d+`** ——
    # 那样 `1.5万亿美元` 会抽出 `1.5`、`3.86亿` 抽出 `3.86`，
    # 一篇文章里凭空多出十几个「版本号」，全是噪音。
    ("version", re.compile(r"[vV]\d+\.\d+(?:\.\d+)?|\b\d+\.\d+\.\d+\b")),
    # 英文专名：OpenAI / GPT-4o / Kubernetes（连续大写起头的词，可含连字符数字）
    ("proper", re.compile(r"\b[A-Z][A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)*(?:\s+[A-Z][A-Za-z0-9]*)*")),
    # 引号内短句：被当成原文引用，必须真有其话
    ("quote", re.compile(r"[「“\"]([^」”\"]{4,40})[」”\"]")),
]

# 句首常见的英文虚词，抽出来当专名纯属噪音
_PROPER_STOPWORDS = {
    "The",
    "A",
    "An",
    "And",
    "But",
    "Or",
    "If",
    "In",
    "On",
    "At",
    "To",
    "For",
    "With",
    "From",
    "By",
    "As",
    "Is",
    "Are",
    "Was",
    "Were",
    "Be",
    "This",
    "That",
    "These",
    "Those",
    "It",
    "We",
    "You",
    "They",
    "Our",
    "Your",
    "However",
    "Also",
    "AI",  # 单独出现时几乎不承载事实，识别成本还高
}

# 归一化：全角转半角 + 去空白 + 小写。只用于「是否出现过」的比对，
# 不做语义判断，所以不需要更复杂的处理。
_FULLWIDTH_OFFSET = 0xFEE0


def _norm(text: str) -> str:
    out = []
    for ch in text or "":
        code = ord(ch)
        if code == 0x3000:
            out.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - _FULLWIDTH_OFFSET))
        else:
            out.append(ch)
    return re.sub(r"\s+", "", "".join(out)).lower()


def _strip_html(raw: str) -> str:
    """正文可能是 HTML，标签不参与核验；块级标签换行，避免两段粘连成一句。"""
    if not raw:
        return ""
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", raw)
    return re.sub(r"<[^>]+>", "", text)


def _entry_text(content: dict[str, Any] | None) -> str:
    """从条目 content 里抽正文。优先 text / body / markdown，都没有才退到整体 dump。"""
    body = content or {}
    for key in ("text", "body", "markdown"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return _strip_html(value)
    # 结构化的自定义字段也承载事实（参数表、价格表），一并纳入
    return _strip_html(json.dumps(body, ensure_ascii=False))


def _sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENT_SPLIT_RE.split(text or "")]
    return [p for p in parts if len(p) >= 8]


def _facts(sentence: str) -> list[tuple[str, str]]:
    """抽一句里的硬事实，返回 [(类型, 原样文本)]。"""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for kind, pattern in _FACT_PATTERNS:
        for match in pattern.finditer(sentence):
            raw = match.group(1) if kind == "quote" and match.groups() else match.group(0)
            raw = raw.strip()
            # 单字母缩写与句首虚词不承载可核验事实，反而全是噪音
            if kind == "proper" and (len(raw) < 2 or raw in _PROPER_STOPWORDS):
                continue
            key = _norm(raw)
            if not key or key in seen:
                continue
            seen.add(key)
            found.append((kind, raw))
    return found


# ---------------------------------------------------------------------------
# 证据收集
# ---------------------------------------------------------------------------


async def _collect_evidence(
    session: AsyncSession,
    *,
    title: str,
    query: str,
    materials: list[str] | None = None,
    site_id: int | None = None,
) -> list[dict[str, Any]]:
    """按可信度收集证据：用户素材 > 企业知识库 > 站内已发布内容。

    顺序有讲究：起草时给的素材是「甲方原话」，权重最高；
    知识库是企业自有资料；站内旧文既可能是依据，也可能是同源的错。
    """
    evidence: list[dict[str, Any]] = []

    for i, piece in enumerate(materials or []):
        text = (piece or "").strip()
        if not text:
            continue
        evidence.append(
            {
                "id": len(evidence) + 1,
                "kind": "material",
                "title": f"素材 {i + 1}",
                "text": text[:4000],
                "url": None,
                "entry_id": None,
            }
        )
        if len(evidence) >= _MAX_EVIDENCE:
            return evidence

    # 知识库：检索挂了不能连带把核验搞挂，降级为「没有这条证据源」
    try:
        from cenkor_admin.apps.cms import knowledge
        from cenkor_admin.core.site_scope import current_site_id

        block, refs = await knowledge.context_for_prompt(
            session,
            query[:500],
            site_id=site_id or current_site_id() or 1,
            limit=3,
            max_chars=3000,
        )
        if block.strip():
            evidence.append(
                {
                    "id": len(evidence) + 1,
                    "kind": "kb",
                    "title": "企业知识库",
                    "text": block[:4000],
                    "url": None,
                    "entry_id": None,
                    "refs": refs[:3],
                }
            )
    except Exception as exc:
        logger.warning("cms.fact_check.kb_failed err={}", exc)

    # 站内既有内容：只拿已发布的，草稿不能当依据
    try:
        from cenkor_admin.apps.cms.ai import rag as rag_mod

        hits = await rag_mod.retrieve(session, query[:500], top_k=3)
        for hit in (hits or {}).get("hits", [])[:3]:
            evidence.append(
                {
                    "id": len(evidence) + 1,
                    "kind": "entry",
                    "title": hit.get("title") or "站内内容",
                    "text": (hit.get("text") or "")[:2000],
                    "url": hit.get("source_url"),
                    "entry_id": hit.get("entry_id"),
                }
            )
            if len(evidence) >= _MAX_EVIDENCE:
                break
    except Exception as exc:
        logger.warning("cms.fact_check.rag_failed err={}", exc)

    return evidence[:_MAX_EVIDENCE]


def _evidence_haystack(evidence: list[dict[str, Any]]) -> str:
    return _norm(" ".join(f"{e.get('title', '')} {e.get('text', '')}" for e in evidence))


def _trace_of(item: dict[str, Any]) -> dict[str, Any]:
    """证据的对外投影：不带全文，前端只拿它渲染出处卡片。"""
    return {
        "id": item["id"],
        "kind": item["kind"],
        "title": item.get("title") or "",
        "url": item.get("url"),
        "entry_id": item.get("entry_id"),
    }


# ---------------------------------------------------------------------------
# 提示词
# ---------------------------------------------------------------------------

_FACT_CHECK_SYSTEM = """你是事实核查员。给定若干句子和一份编号证据，逐句判断是否有依据。

## 判定标准

- supported：句子里的具体说法能在证据里找到对应内容（可同义改写，不要求逐字）
- unsupported：句子里的具体说法在证据里**找不到**任何对应，属于模型自行生成的细节
- uncertain：证据不足以下结论，或说法模糊到无法核验

## 铁律

1. **只能引用证据列表里出现过的编号**。不存在、没把握的编号一律不要写。
2. **判 supported 必须有证据支撑**，不能因为「听起来合理」「符合常识」就判 supported。
   你的常识不是证据。
3. 纯观点、纯描述、无具体事实的句子不要判 unsupported，判 uncertain 或不返回。
4. 只判给定句子，不要改写句子、不要补充解释、不要指出语法问题。
5. 一句一条记录，编号必须与输入一致。

## 输出

严格 JSON：

{
  "items": [
    {"idx": 3, "verdict": "supported|unsupported|uncertain", "evidence": [2], "note": "一句话说明理由"}
  ]
```

JSON 之外不要输出任何文字。"""


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def _level_of(rate: float, judged: int) -> str:
    """阈值：没有可判定句 / 支撑率 ≥0.85 视为 ok，≥0.6 warn，其余 risk。

    `judged` 是**能被判定**的句数（supported + unsupported），不含 uncertain ——
    「我判断不了」不该把一篇文章推进红色区。没有事实主张的稿子（纯观点、公告）
    也不该被判风险，那会把误报率拉满，编辑一旦习惯性忽略告警，这个功能就废了。
    """
    if judged == 0:
        return "ok"
    if rate >= 0.85:
        return "ok"
    if rate >= 0.6:
        return "warn"
    return "risk"


async def check_text(
    session: AsyncSession,
    text: str,
    *,
    title: str = "",
    entry_id: int | None = None,
    materials: list[str] | None = None,
    created_by: int | None = None,
    site_id: int | None = None,
) -> dict[str, Any]:
    """核验一段文本。返回结构见模块尾部 `RESULT_KEYS` 说明。

    分三层降级，任何一层失败都不该让编辑「点了按钮什么也没有」：
        规则层永远跑得通
        → 模型层可选（没配 AI / 调用失败 → degraded=True）
        → 证据层为空时直接判 risk 并说明原因，不去打扰模型
    """
    body = (text or "").strip()
    truncated = len(body) > _MAX_BODY_CHARS
    if truncated:
        body = body[:_MAX_BODY_CHARS]

    if not body:
        return _empty(entry_id, "条目正文为空，无内容可核验")

    sentences = [s[:_MAX_SENTENCE_CHARS] for s in _sentences(body)]
    evidence = await _collect_evidence(
        session,
        title=title,
        query=(title + " " + (sentences[0] if sentences else ""))[:500],
        materials=materials,
        site_id=site_id,
    )

    # ---- 第一段：规则匹配 ----
    claims: list[dict[str, Any]] = []
    for index, sentence in enumerate(sentences):
        facts = _facts(sentence)
        if not facts:
            continue
        claims.append(
            {
                "index": index,
                "sentence": sentence,
                "facts": [raw for _, raw in facts],
                "verdict": None,  # 由规则或模型填
                "evidence": [],
                "note": "",
                "by": "rule",
            }
        )

    haystack = _evidence_haystack(evidence)
    pending: list[dict[str, Any]] = []
    for claim in claims:
        missing = [f for f in claim["facts"] if _norm(f) not in haystack]
        if not missing:
            claim["verdict"] = "supported"
            claim["by"] = "rule"
            claim["note"] = "句中的具体数值/专名均能在证据中找到"
        else:
            # 记下没命中的那部分，模型判定时只针对这些
            claim["missing"] = missing
            pending.append(claim)

    # ---- 证据为空：不调模型，直接给出可解释的结论 ----
    # 判 uncertain 而不是 unsupported —— 这是本条模块最重要的一条口径。
    # 「查无依据」只有在**存在证据源且证据里没有**时才等于可疑；
    # 连一个证据源都没有的时候，我们什么都不知道，标红只会制造假警报。
    # 一篇新闻稿的事实本来就来自原报道，站内不可能有，硬判 unsupported
    # 会让每一篇都变成「风险较高」，编辑第二天就把功能关了。
    if not evidence and claims:
        for claim in pending:
            claim["verdict"] = "uncertain"
            claim["note"] = "没有任何可用依据（素材 / 知识库 / 站内内容均为空），无法判断，需人工确认"
            claim["by"] = "rule"
        pending = []
        degraded_reason = "缺少证据源：知识库为空、站内无相关内容、起草时也未提供素材"
    else:
        degraded_reason = ""

    # ---- 第二段：模型判定（只针对规则没兜住的句子） ----
    degraded = False
    llm_meta: dict[str, Any] = {}
    picked = pending[:_MAX_SENTENCES]
    if picked:
        try:
            llm = get_llm()
            payload = {
                "evidence": [
                    {"id": e["id"], "title": e.get("title"), "text": e.get("text")}
                    for e in evidence
                ],
                "sentences": [
                    {"idx": c["index"], "text": c["sentence"], "new_facts": c["missing"]}
                    for c in picked
                ],
            }
            prompt_text = json.dumps(payload, ensure_ascii=False)
            system = await prompts.get(session, "fact_check", _FACT_CHECK_SYSTEM)
            raw, result = await llm.chat_json(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt_text},
                ],
                temperature=0.0,
                # 16000 不是拍脑袋：推理模型光思考就能吃掉一万多字符，
                # 给 2000 会 100% 抛「输出被 max_tokens 截断」（已经实测踩过一次，
                # 和内链建议那次是同一个坑）。真正的输出只有几条判定，很便宜。
                max_tokens=16000,
            )
            raw = _as_object(raw, "事实核验")
            llm_meta = result.meta()
            await _record(
                session,
                kind=_KIND_FACT_CHECK,
                target=f"entry:{entry_id}" if entry_id else "text",
                result=result,
                params={"sentences": len(picked), "evidence": len(evidence)},
                created_by=created_by,
                prompt=prompt_text,
            )
            _apply_llm_verdicts(picked, raw.get("items"), len(evidence))
        except LLMNotConfiguredError:
            degraded = True
            degraded_reason = degraded_reason or "未配置 AI 模型，仅按规则比对结果"
            _fallback_unsupported(picked)
        except Exception as exc:
            degraded = True
            degraded_reason = f"模型判定失败，仅按规则比对结果：{exc}"
            logger.warning("cms.fact_check.llm_failed err={}", exc)
            await _record(
                session,
                kind=_KIND_FACT_CHECK,
                target=f"entry:{entry_id}" if entry_id else "text",
                result=None,
                status="failed",
                error=str(exc)[:500],
                created_by=created_by,
            )
            _fallback_unsupported(picked)

    # 超出的句子（罕见）按 uncertain 处理，不假装判过
    for claim in pending[len(picked) :]:
        claim["verdict"] = "uncertain"
        claim["note"] = "超过单次核验上限，本次未判定"

    # ---- 聚合 ----
    supported = sum(1 for c in claims if c["verdict"] == "supported")
    unsupported = sum(1 for c in claims if c["verdict"] == "unsupported")
    uncertain = sum(1 for c in claims if c["verdict"] == "uncertain")
    total = len(claims)
    # 分母只算「能被判定」的句子。把 uncertain 也算进去的话，
    # 一篇文章只要引用了几处站外事实（本来就无从核验），分数就被拉到 20%，
    # 弹窗永远显示「风险较高」—— 这种恒红指标没有信息量。
    judged = supported + unsupported
    rate = round(supported / judged, 3) if judged else 1.0

    items = [
        {
            "index": c["index"],
            "sentence": c["sentence"],
            "verdict": c["verdict"],
            "facts": c["facts"],
            "note": c["note"],
            "by": c["by"],
            "evidence": [e for e in (_trace_of(x) for x in evidence) if e["id"] in c["evidence"]],
        }
        for c in claims
        # 只回有问题的句子：全绿的稿子回一堆 supported 只会让编辑滑到眼花
        if c["verdict"] != "supported"
    ]

    result_body: dict[str, Any] = {
        "entry_id": entry_id,
        "title": title,
        "summary": {
            "claims": total,
            "supported": supported,
            "unsupported": unsupported,
            "uncertain": uncertain,
            "support_rate": rate,
            "judged": judged,
            "level": _level_of(rate, judged),
            "evidence_count": len(evidence),
            "evidence_sources": _source_counts(evidence),
            "truncated": truncated,
        },
        "items": items,
        "traces": [_trace_of(e) for e in evidence],
        "degraded": degraded,
        "degraded_reason": degraded_reason,
    }
    if llm_meta:
        result_body["_meta"] = llm_meta
    return result_body


def _apply_llm_verdicts(
    claims: list[dict[str, Any]],
    raw_items: Any,
    evidence_count: int,
) -> None:
    """把模型判定写回 claim，并做编号白名单校验。

    模型引了不存在的编号 → 剔除该编号；如果剔完一条证据都不剩，
    判定降级为 uncertain。理由和 qa_search 一样：出处不能由模型说了算，
    它编一个 `[5]` 出来，前端就会渲染出一个指向空气的引用。
    """
    by_index = {c["index"]: c for c in claims}
    for item in raw_items or []:
        try:
            idx = int(item.get("idx"))
        except (TypeError, ValueError):
            continue
        claim = by_index.get(idx)
        if claim is None:
            continue
        verdict = str(item.get("verdict") or "").strip().lower()
        if verdict not in ("supported", "unsupported", "uncertain"):
            verdict = "uncertain"
        cited: list[int] = []
        for raw_id in item.get("evidence") or []:
            try:
                case_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if 1 <= case_id <= evidence_count and case_id not in cited:
                cited.append(case_id)
        if verdict == "supported" and not cited:
            verdict = "uncertain"
        claim["verdict"] = verdict
        claim["by"] = "model"
        claim["evidence"] = cited
        claim["note"] = str(item.get("note") or "")[:200]


def _fallback_unsupported(claims: list[dict[str, Any]]) -> None:
    """模型不可用时的保守判定：规则没命中就记为 unsupported，并说明依据是规则比对。

    不降级成 uncertain —— 那样等于什么都没说。规则命中的本来就是
    「这个数字在证据里一次都没出现」，这条结论本身是可靠的。
    """
    for claim in claims:
        claim["verdict"] = "unsupported"
        claim["by"] = "rule"
        claim["note"] = claim.get("note") or (
            "未在证据中找到：" + "、".join(claim.get("missing") or [])
        )


def _source_counts(evidence: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {"material": 0, "kb": 0, "entry": 0}
    for e in evidence:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    return counts


def _empty(entry_id: int | None, reason: str) -> dict[str, Any]:
    return {
        "entry_id": entry_id,
        "title": "",
        "summary": {
            "claims": 0,
            "supported": 0,
            "unsupported": 0,
            "uncertain": 0,
            "support_rate": 1.0,
            "judged": 0,
            "level": "ok",
            "evidence_count": 0,
            "evidence_sources": {"material": 0, "kb": 0, "entry": 0},
            "truncated": False,
        },
        "items": [],
        "traces": [],
        "degraded": True,
        "degraded_reason": reason,
    }


async def check_entry(
    session: AsyncSession,
    entry: Entry,
    *,
    materials: list[str] | None = None,
    created_by: int | None = None,
) -> dict[str, Any]:
    """对一条已落库条目做事实核验。不写库、不改条目。"""
    # 标题也参与核验：标题里塞一个「提升 300%」比正文里更危险。
    # 用句号连起来而不是换行 —— 断句器只按句末标点切，换行会把标题和副标题
    # 粘成一句，展示出来就是「标题。\n上市迈出关键一步」这种半截句子。
    text = (entry.title or "") + "。" + _entry_text(entry.content)
    result = await check_text(
        session,
        text,
        title=entry.title,
        entry_id=entry.id,
        materials=materials,
        created_by=created_by,
        site_id=getattr(entry, "site_id", None),
    )
    return result
