"""AI 工作流 · 步骤注册表

## 这一层解决什么问题

引擎只认「契约」，不认业务。每个步骤用 `StepSpec` 声明自己吃什么、吐什么，
引擎据此在画布上做参数表单、在保存时做连线校验、在执行时做变量插值。
新增一个步骤 = 在 `_REGISTRY` 里注册一个函数，引擎一行不用改。

## 契约

```python
async def _my_step(ctx: StepCtx) -> dict[str, Any]:
    ...            # 只做事，不提交事务（引擎统一提交）
    return {...}   # 键名必须与 StepSpec.outputs 一致
```

- 参数已经从 `{{...}}` 插值完，步骤里拿到的就是最终值
- 要「主动叫停整条流水线」就在返回值里带 `"_halt": "原因"`。引擎会把 run 记为
  `halted` 而不是 `failed` —— 查重命中不是故障，不该污染失败率
- 抛异常 = 这一步失败，由引擎决定重试还是终止

## 为什么起草（draft.write）和落库（entry.save）拆成两步

起草只调模型、不写库；落库才建 Entry。拆开后：
1. 查重、质检可以卡在落库**之前**，避免往库里丢垃圾
2. 起草结果完整留在 step.output 里，落库失败可以直接原地重跑，不用再花一次模型钱
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.ai import copilot, illustration
from cenkor_admin.apps.cms.models import ContentType, Entry
from cenkor_admin.core.llm import get_llm


class StepError(RuntimeError):
    """步骤级可读错误（消息会原样展示给用户）。"""


# ---------------------------------------------------------------------------
# 上下文与注册结构
# ---------------------------------------------------------------------------
@dataclass
class StepCtx:
    db: AsyncSession
    site_id: int
    user_id: int | None
    params: dict[str, Any]
    outputs: dict[str, Any] = field(default_factory=dict)

    def p(self, key: str, default: Any = None) -> Any:
        v = self.params.get(key)
        return default if v is None or v == "" else v

    def text(self, key: str, default: str = "") -> str:
        v = self.p(key, default)
        return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)

    def num(self, key: str, default: float) -> float:
        try:
            return float(self.p(key, default))
        except (TypeError, ValueError):
            return default


@dataclass
class FieldSpec:
    key: str
    label: str
    kind: str = "text"  # text / textarea / number / bool / select / entry
    required: bool = False
    default: Any = None
    help: str = ""
    choices: list[dict[str, str]] = field(default_factory=list)


@dataclass
class StepSpec:
    key: str
    title: str
    group: str
    desc: str
    inputs: list[FieldSpec]
    outputs: list[str]
    retryable: bool = True


_REGISTRY: dict[str, tuple[StepSpec, Callable[[StepCtx], Awaitable[dict[str, Any]]]]] = {}


def _step(spec: StepSpec):
    def deco(fn):
        _REGISTRY[spec.key] = (spec, fn)
        return fn

    return deco


def all_specs() -> list[dict[str, Any]]:
    """画布左栏用：步骤清单 + 参数定义。"""
    order = {
        "选题": 0,
        "大纲": 1,
        "起草": 2,
        "校验": 3,
        "落库": 4,
        "增强": 5,
        "发布": 6,
    }
    items = []
    for spec, _ in _REGISTRY.values():
        items.append(
            {
                "key": spec.key,
                "title": spec.title,
                "group": spec.group,
                "desc": spec.desc,
                "retryable": spec.retryable,
                "inputs": [
                    {
                        "key": f.key,
                        "label": f.label,
                        "kind": f.kind,
                        "required": f.required,
                        "default": f.default,
                        "help": f.help,
                        "choices": f.choices,
                    }
                    for f in spec.inputs
                ],
                "outputs": spec.outputs,
            }
        )
    items.sort(key=lambda x: (order.get(x["group"], 99), x["title"]))
    return items


def get_runner(key: str) -> Callable[[StepCtx], Awaitable[dict[str, Any]]]:
    entry = _REGISTRY.get(key)
    if entry is None:
        raise StepError(f"未知步骤类型：{key}")
    return entry[1]


def is_retryable(key: str) -> bool:
    """有副作用的步骤（落库、发布）不重试，重试只会多造一条脏数据。"""
    entry = _REGISTRY.get(key)
    return bool(entry[0].retryable) if entry else True


def has_step(key: str) -> bool:
    return key in _REGISTRY


def validate_node(node_type: str, params: dict[str, Any]) -> list[str]:
    """保存时的轻校验：只查「必填但空」，插值过的引用不在这里判（运行时才知道值）。"""
    entry = _REGISTRY.get(node_type)
    if entry is None:
        return [f"未知步骤类型：{node_type}"]
    spec = entry[0]
    missing = [
        f.label
        for f in spec.inputs
        if f.required and not str(params.get(f.key) or "").strip()
    ]
    return [f"缺少必填参数：{'、'.join(missing)}"] if missing else []


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------
async def _json_chat(
    system: str, user: str, *, temperature: float = 0.5, max_tokens: int = 2600
) -> tuple[dict[str, Any], Any]:
    """要一个 JSON 对象。模型偶尔返回数组或包了代码围栏，这里统一兜住。"""
    llm = get_llm()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    raw, result = await llm.chat_json(messages, temperature=temperature, max_tokens=max_tokens)
    if isinstance(raw, list):  # 模型直接给了数组，包一层
        raw = {"items": raw}
    if not isinstance(raw, dict):
        raise StepError("模型没有返回 JSON 对象")
    return raw, result


def _plain(content: Any) -> str:
    """草稿正文可能是 dict / markdown / HTML，统一压成纯文本喂给下游。"""
    if content is None:
        return ""
    if isinstance(content, str):
        text = content
    elif isinstance(content, dict):
        parts = [
            str(content.get(k) or "")
            for k in ("body", "markdown", "md", "text", "summary")
            if content.get(k)
        ]
        text = "\n".join(parts) if parts else json.dumps(content, ensure_ascii=False)
    else:
        text = json.dumps(content, ensure_ascii=False)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


async def _content_type(db: AsyncSession, site_id: int, key: str) -> ContentType:
    # cms_content_types 没有 site_id / status 字段：内容类型是全局字典，
    # 站点隔离靠 cms_entries.site_id，不在类型这一层。
    ct = (
        await db.execute(
            select(ContentType).where(
                ContentType.key == key,
                ContentType.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if ct is None:
        raise StepError(f"内容类型不存在：{key}")
    return ct


async def _load_entry(db: AsyncSession, entry_id: Any) -> Entry:
    try:
        eid = int(entry_id)
    except (TypeError, ValueError):
        raise StepError("entry_id 无效，请检查上游是否已生成条目") from None
    entry = await db.get(Entry, eid)
    if entry is None or getattr(entry, "deleted_at", None) is not None:
        raise StepError(f"条目不存在：{eid}")
    return entry


_LANG = FieldSpec("lang", "语言", "text", default="zh-CN")
_CT_KEY = FieldSpec("content_type_key", "内容类型 key", "text", True, help="如 news / product / case")


# ---------------------------------------------------------------------------
# 1. 选题
# ---------------------------------------------------------------------------
_TOPIC_SYSTEM = """你是 B2B 制造业内容策划。根据给定的主题方向，产出可以直接开写的选题。

只输出一个 JSON 对象：
{"topics": [{"title": "选题标题", "keyword": "核心关键词", "angle": "切入角度一句话"}]}

硬性规则：
1. 选题必须是「一个具体问题或一条具体做法」，不要「XX 的重要性」这类空泛命题
2. 标题不超过 30 字，不加书名号引号，不用「浅谈」「解析」「探析」
3. 关键词 2~6 个字，是采购/工程师真实会搜的词
4. 不编造数据、客户名、标准号"""


@_step(
    StepSpec(
        key="topic.pick",
        title="选题生成",
        group="选题",
        desc="给一个主题方向，产出 N 个可直接开写的选题",
        inputs=[
            FieldSpec("direction", "主题方向", "textarea", True, help="越具体越好，如「MES 在注塑车间的落地」"),
            FieldSpec("count", "数量", "number", default=3),
            _LANG,
        ],
        outputs=["topics", "count", "topic"],
    )
)
async def _topic_pick(ctx: StepCtx) -> dict[str, Any]:
    count = max(1, min(10, int(ctx.num("count", 3))))
    raw, _ = await _json_chat(
        _TOPIC_SYSTEM,
        f"主题方向：{ctx.text('direction')}\n语言：{ctx.p('lang', 'zh-CN')}\n数量：{count}",
        max_tokens=3000,
    )
    topics: list[dict[str, str]] = []
    for t in raw.get("topics") or raw.get("items") or []:
        if isinstance(t, str):
            t = {"title": t}
        if not isinstance(t, dict):
            continue
        title = str(t.get("title") or "").strip()[:120]
        if title:
            topics.append(
                {
                    "title": title,
                    "keyword": str(t.get("keyword") or "").strip()[:40],
                    "angle": str(t.get("angle") or "").strip()[:200],
                }
            )
    if not topics:
        raise StepError("模型没有给出可用选题")
    topics = topics[:count]
    return {"topics": topics, "count": len(topics), "topic": topics[0]["title"]}


# ---------------------------------------------------------------------------
# 2. 大纲
# ---------------------------------------------------------------------------
_OUTLINE_SYSTEM = """你是资深技术编辑。把选题扩成可直接照着写的大纲。

只输出一个 JSON 对象：
{"title": "成稿标题", "summary": "全文主旨一句话", "sections": [{"h2": "二级标题", "points": ["要点1", "要点2"]}], "keywords": ["关键词"]}

硬性规则：
1. 3~6 个小节，每节 2~4 个要点，要点写成「要讲什么」，不要写成句子
2. 小节之间要有推进关系（是什么 → 怎么做 → 怎么验收），不要并列堆砌
3. 不编造数据、客户名、标准号；需要数据的地方在要点里写明「需补充实测数据」"""


@_step(
    StepSpec(
        key="outline.gen",
        title="大纲生成",
        group="大纲",
        desc="选题 → 结构化大纲（小节 + 要点 + 关键词）",
        inputs=[
            FieldSpec("topic", "选题", "textarea", True, help="可引用上游：{{n1.topic}}"),
            FieldSpec("sections", "小节数", "number", default=5),
            _LANG,
        ],
        outputs=["title", "summary", "sections", "keywords", "outline_text"],
    )
)
async def _outline_gen(ctx: StepCtx) -> dict[str, Any]:
    raw, _ = await _json_chat(
        _OUTLINE_SYSTEM,
        f"选题：{ctx.text('topic')}\n小节数：{int(ctx.num('sections', 5))}\n语言：{ctx.p('lang', 'zh-CN')}",
        max_tokens=4000,
    )
    sections = []
    for s in raw.get("sections") or []:
        if not isinstance(s, dict):
            continue
        h2 = str(s.get("h2") or s.get("title") or "").strip()[:120]
        if not h2:
            continue
        points = [str(p).strip()[:200] for p in (s.get("points") or []) if str(p).strip()]
        sections.append({"h2": h2, "points": points[:5]})
    if not sections:
        raise StepError("模型没有给出可用大纲")

    title = str(raw.get("title") or ctx.text("topic")).strip()[:200]
    summary = str(raw.get("summary") or "").strip()[:400]
    keywords = [str(k).strip()[:40] for k in (raw.get("keywords") or []) if str(k).strip()][:8]

    # 渲染成纯文本：起草步骤吃的就是这段 brief
    lines = [f"标题：{title}", f"主旨：{summary}", ""]
    for i, s in enumerate(sections, 1):
        lines.append(f"{i}. {s['h2']}")
        lines.extend(f"   - {p}" for p in s["points"])
    if keywords:
        lines.append("")
        lines.append("目标关键词：" + "、".join(keywords))

    return {
        "title": title,
        "summary": summary,
        "sections": sections,
        "keywords": keywords,
        "outline_text": "\n".join(lines),
    }


# ---------------------------------------------------------------------------
# 3. 起草
# ---------------------------------------------------------------------------
@_step(
    StepSpec(
        key="draft.write",
        title="起草正文",
        group="起草",
        desc="大纲/素材 → 条目草稿（只生成不落库，模型产出强制 draft）",
        inputs=[
            FieldSpec("outline", "大纲/素材", "textarea", True, help="可引用上游：{{n2.outline_text}}"),
            FieldSpec("extra", "补充要求", "textarea", help="语气、长度、必须包含的点"),
            _CT_KEY,
            FieldSpec("max_tokens", "最大 token", "number", default=20000),
            _LANG,
        ],
        outputs=["draft", "title", "slug", "word_count", "kb_sources"],
    )
)
async def _draft_write(ctx: StepCtx) -> dict[str, Any]:
    """起草走**流式**，不是一次性请求。

    为什么：当前 chat 模型是 MiniMax-M3.1-Flash（推理型）。它对复杂提示词
    会先花掉上万 token 思考，非流式请求的结果是
    「思考过程占满 max_tokens，一个正文字符都没有」——实测 6000 预算时
    reasoning 吃了 19283 字符，耗时 49 秒后被截断。

    流式有两个好处：
      1. 推理过程是持续吐 chunk 的，连接不会空闲，60 秒的读超时打不着它；
      2. 预算给到 20000，思考完还剩得下正文。
    非流式只在流式整体失败时兜底一次。
    """
    ct = await _content_type(ctx.db, ctx.site_id, ctx.text("content_type_key"))
    brief = ctx.text("outline")
    extra = ctx.text("extra")
    if extra:
        brief = f"{brief}\n\n补充要求：\n{extra}"

    max_tokens = int(ctx.num("max_tokens", 20000))
    draft: dict[str, Any] | None = None
    err = ""

    async for event, payload in copilot.draft_entry_stream(
        ctx.db,
        ct.id,
        brief,
        created_by=ctx.user_id,
        lang=ctx.p("lang", "zh-CN"),
        max_tokens=max_tokens,
    ):
        if event == "done":
            draft = payload
        elif event == "error":
            err = str(payload.get("detail") or "流式起草失败")

    if draft is None:
        # 流式失败兜底：非流式一次。预算同样给足，撞 60 秒读超时也不至于
        # 把整条流水线卡死 —— 引擎会记失败并重试。
        try:
            draft = await copilot.draft_entry(
                ctx.db,
                ct.id,
                brief,
                created_by=ctx.user_id,
                lang=ctx.p("lang", "zh-CN"),
                max_tokens=max_tokens,
            )
        except Exception as exc:
            raise StepError(f"起草失败：{err or exc}") from exc

    body = _plain(draft.get("content"))
    return {
        "draft": draft,
        "title": draft.get("title") or "",
        "slug": draft.get("slug") or "",
        "word_count": len(body),
        "kb_sources": draft.get("kb_sources") or [],
    }


# ---------------------------------------------------------------------------
# 4. 查重
# ---------------------------------------------------------------------------
@_step(
    StepSpec(
        key="dup.check",
        title="查重",
        group="校验",
        desc="在库内找相似条目，可配置「超阈值直接叫停」",
        inputs=[
            FieldSpec("title", "标题", "text", True, help="可引用上游：{{n3.title}}"),
            FieldSpec("content", "正文", "textarea", True, help="可引用上游：{{n3.draft.content}}"),
            FieldSpec("threshold", "重复阈值", "number", default=0.8),
            FieldSpec("abort", "命中即叫停", "bool", default=True),
        ],
        outputs=["duplicates", "max_score", "blocked"],
    )
)
async def _dup_check(ctx: StepCtx) -> dict[str, Any]:
    threshold = min(0.99, max(0.5, ctx.num("threshold", 0.8)))
    hits = await copilot.detect_duplicates(
        ctx.db,
        ctx.text("title"),
        ctx.params.get("content"),
        threshold=threshold,
        limit=5,
    )
    max_score = max([float(h.get("score") or 0) for h in hits], default=0.0)
    blocked = max_score >= threshold
    out: dict[str, Any] = {
        "duplicates": hits[:5],
        "max_score": round(max_score, 4),
        "blocked": blocked,
    }
    if blocked and str(ctx.p("abort", True)).lower() not in ("false", "0", "none"):
        top = hits[0] if hits else {}
        out["_halt"] = (
            f"查重命中：与《{str(top.get('title') or '已有条目')[:40]}》相似度 "
            f"{max_score:.0%}，超过阈值 {threshold:.0%}"
        )
    return out


# ---------------------------------------------------------------------------
# 5. 质检
# ---------------------------------------------------------------------------
_QUALITY_SYSTEM = """你是内容质量审核员。给一篇待发稿件打分。

只输出一个 JSON 对象：
{"score": 0-100 整数, "verdict": "pass" 或 "revise",
 "dimensions": {"准确性": 0-100, "结构": 0-100, "可读性": 0-100, "信息密度": 0-100},
 "issues": ["具体问题，一条一句"]}

硬性规则：
1. 空洞套话（赋能/闭环/抓手/生态位）、无信息量的段落，直接扣分并在 issues 里点名
2. 出现无法核实的具体数字、客户名、标准号，按「准确性」扣分
3. score >= 75 且没有准确性问题才可 pass
4. issues 最多 6 条，说人话，不要复述原文"""


@_step(
    StepSpec(
        key="quality.check",
        title="质量质检",
        group="校验",
        desc="模型自评打分，可配置「低于分数线直接叫停」",
        inputs=[
            FieldSpec("title", "标题", "text", True),
            FieldSpec("content", "正文", "textarea", True),
            FieldSpec("min_score", "及格分", "number", default=75),
            FieldSpec("abort", "不达标即叫停", "bool", default=False),
            _LANG,
        ],
        outputs=["score", "verdict", "dimensions", "issues"],
    )
)
async def _quality_check(ctx: StepCtx) -> dict[str, Any]:
    body = _plain(ctx.params.get("content"))[:6000]
    if not body:
        raise StepError("正文为空，无法质检")
    raw, _ = await _json_chat(
        _QUALITY_SYSTEM,
        f"标题：{ctx.text('title')}\n语言：{ctx.p('lang', 'zh-CN')}\n\n正文：\n{body}",
        temperature=0.2,
        max_tokens=4000,
    )
    try:
        score = round(float(raw.get("score") or 0))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))
    dims = raw.get("dimensions") if isinstance(raw.get("dimensions"), dict) else {}
    issues = [str(i).strip()[:220] for i in (raw.get("issues") or []) if str(i).strip()][:6]
    min_score = ctx.num("min_score", 75)
    verdict = "pass" if score >= min_score else "revise"
    out: dict[str, Any] = {
        "score": score,
        "verdict": verdict,
        "dimensions": dims,
        "issues": issues,
    }
    if verdict == "revise" and str(ctx.p("abort", False)).lower() in ("true", "1"):
        out["_halt"] = f"质检不达标：{score} 分，低于及格线 {int(min_score)}"
    return out


# ---------------------------------------------------------------------------
# 6. 落库
# ---------------------------------------------------------------------------
@_step(
    StepSpec(
        key="entry.save",
        title="存为草稿",
        group="落库",
        desc="把起草产物写进内容库（强制 draft，AI 不能直接发布）",
        inputs=[
            FieldSpec("draft", "草稿对象", "textarea", True, help="引用上游起草步骤：{{n3.draft}}"),
        ],
        outputs=["entry_id", "title", "status"],
        # 落库有副作用：重试会多建一条重复条目，所以不重试
        retryable=False,
    )
)
async def _entry_save(ctx: StepCtx) -> dict[str, Any]:
    raw = ctx.params.get("draft")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raise StepError("draft 参数不是合法 JSON，请引用起草步骤的输出对象") from None
    if not isinstance(raw, dict) or not raw.get("content_type_id"):
        raise StepError("draft 缺少 content_type_id，无法落库")

    entry = await copilot.create_entry_from_draft(
        ctx.db, raw, created_by=ctx.user_id, ai_origin="draft"
    )
    return {"entry_id": entry.id, "title": entry.title, "status": entry.status}


# ---------------------------------------------------------------------------
# 7. SEO
# ---------------------------------------------------------------------------
@_step(
    StepSpec(
        key="seo.suggest",
        title="SEO 元数据",
        group="增强",
        desc="为已落库条目生成 title/description/keywords 并写回",
        inputs=[
            FieldSpec("entry_id", "条目 ID", "entry", True, help="可引用上游：{{n4.entry_id}}"),
            FieldSpec("apply", "写回条目", "bool", default=True),
            _LANG,
        ],
        outputs=["seo", "applied"],
    )
)
async def _seo_suggest(ctx: StepCtx) -> dict[str, Any]:
    """自己发一次模型请求，不复用 copilot.suggest_seo。

    原因很实际：copilot 那个函数把 max_tokens 写死 1200。当前 chat 模型是
    推理型（MiniMax-M3.1-Flash），1200 预算几乎必然被思考过程吃光，
    表现为「SEO 步骤莫名失败」。这里给 4000。
    """
    entry = await _load_entry(ctx.db, ctx.p("entry_id"))
    body = _plain(entry.content)[:4000]
    raw, _ = await _json_chat(
        _SEO_SYSTEM,
        f"标题：{entry.title}\n正文摘要：\n{body or '（无正文）'}\n语言：{ctx.p('lang', 'zh-CN')}",
        temperature=0.3,
        max_tokens=4000,
    )
    seo = {
        "title": str(raw.get("title") or entry.title)[:120],
        "description": str(raw.get("description") or "")[:300],
        "keywords": [str(k).strip()[:40] for k in (raw.get("keywords") or []) if str(k).strip()][:10],
    }
    applied = False
    if str(ctx.p("apply", True)).lower() not in ("false", "0"):
        entry.seo = {**(entry.seo or {}), **seo}
        await ctx.db.commit()
        applied = True
    return {"seo": seo, "applied": applied}


_SEO_SYSTEM = """你是 SEO 负责人。为一篇内容生成搜索元数据。

只输出一个 JSON 对象：
{"title": "搜索结果标题", "description": "搜索结果摘要", "keywords": ["关键词"]}

硬性规则：
1. title 不超过 30 个汉字，包含核心关键词，不要堆词
2. description 80~120 字，说清这篇内容解决什么问题
3. keywords 3~6 个，是真实会被搜的词
4. 不编造数据、案例名"""


# ---------------------------------------------------------------------------
# 8. 配图
# ---------------------------------------------------------------------------
@_step(
    StepSpec(
        key="illustrate",
        title="生成配图",
        group="增强",
        desc="按正文语义生一张图，落媒体库（默认只出图不自动插正文）",
        inputs=[
            FieldSpec("entry_id", "条目 ID", "entry", True),
            FieldSpec("hint", "风格提示", "text", help="如「车间实景，冷色调」"),
            FieldSpec(
                "style",
                "风格",
                "select",
                default="photo",
                choices=[
                    {"value": "photo", "label": "实景照片"},
                    {"value": "flat", "label": "扁平插画"},
                    {"value": "3d", "label": "3D 渲染"},
                ],
            ),
            FieldSpec(
                "aspect",
                "比例",
                "select",
                default="wide",
                choices=[
                    {"value": "wide", "label": "横图 16:9"},
                    {"value": "square", "label": "方图 1:1"},
                    {"value": "tall", "label": "竖图 3:4"},
                ],
            ),
            FieldSpec(
                "apply",
                "应用到条目",
                "select",
                default="none",
                choices=[
                    {"value": "none", "label": "只出图"},
                    {"value": "cover", "label": "设为封面"},
                    {"value": "insert", "label": "插入正文"},
                ],
            ),
        ],
        outputs=["media_id", "public_url", "applied"],
    )
)
async def _illustrate(ctx: StepCtx) -> dict[str, Any]:
    entry = await _load_entry(ctx.db, ctx.p("entry_id"))
    res = await illustration.generate_for_entry(
        ctx.db,
        entry,
        hint=ctx.text("hint"),
        style=ctx.p("style", "photo"),
        aspect=ctx.p("aspect", "wide"),
        apply=ctx.p("apply", "none"),
        created_by=ctx.user_id,
    )
    return {
        "media_id": res.get("media_id"),
        "public_url": res.get("public_url") or res.get("url"),
        "applied": res.get("applied") or "none",
    }


# ---------------------------------------------------------------------------
# 9. 内链
# ---------------------------------------------------------------------------
@_step(
    StepSpec(
        key="internal_link",
        title="内链建议",
        group="增强",
        desc="检索站内相关条目，给出可以插入的内链",
        inputs=[
            FieldSpec("entry_id", "条目 ID", "entry", True),
            FieldSpec("max_links", "最多几条", "number", default=4),
        ],
        outputs=["links", "candidate_count"],
    )
)
async def _internal_link(ctx: StepCtx) -> dict[str, Any]:
    """同样自己发请求：internal_link.suggest_links 把 max_tokens 写死 900，
    推理模型下必然截断。候选召回复用它的私有函数，提示词自己写。"""
    from cenkor_admin.apps.cms.ai.embedding import entry_to_text
    from cenkor_admin.apps.cms.ai.internal_link import _candidate_entries
    from cenkor_admin.apps.cms.ai.search import similar_entries

    entry = await _load_entry(ctx.db, ctx.p("entry_id"))
    hits = await similar_entries(ctx.db, entry.id, limit=8)
    cands = await _candidate_entries(ctx.db, entry, limit=8)
    if not cands:
        return {"links": [], "candidate_count": 0}

    payload = [
        {
            "entry_id": c.id,
            "title": c.title,
            "slug": c.slug,
            "content_type_key": ct_key,
            "summary": " ".join(entry_to_text(c).split())[:160],
        }
        for c, ct_key in cands
    ]
    raw, _ = await _json_chat(
        _LINK_SYSTEM,
        f"【本文】\n标题：{entry.title}\n正文摘录：\n"
        f"{' '.join(entry_to_text(entry).split())[:1200] or '（无正文）'}\n\n"
        f"【候选】\n{json.dumps(payload, ensure_ascii=False)}",
        temperature=0.3,
        max_tokens=4000,
    )
    links = []
    for it in raw.get("links") or []:
        if not isinstance(it, dict):
            continue
        eid = it.get("entry_id")
        try:
            eid = int(eid)
        except (TypeError, ValueError):
            continue
        links.append(
            {
                "entry_id": eid,
                "title": str(it.get("title") or "")[:200],
                "anchor": str(it.get("anchor") or "")[:60],
                "reason": str(it.get("reason") or "")[:200],
            }
        )
    limit = int(ctx.num("max_links", 4))
    return {"links": links[:limit], "candidate_count": len(hits)}


_LINK_SYSTEM = """你是站内编辑。给一篇正文挑出值得插入的内链。

只输出一个 JSON 对象：
{"links": [{"entry_id": 12, "title": "候选标题", "anchor": "插入的锚文本", "reason": "为什么这里该链"}]}

硬性规则：
1. entry_id 必须来自候选清单，不要编
2. anchor 是要插进正文的那几个字，要跟上下文语义相关，不要用「点击这里」
3. 一篇最多 3 条，宁缺毋滥
4. 不重复链接同一条"""


# ---------------------------------------------------------------------------
# 10. 发布
# ---------------------------------------------------------------------------
@_step(
    StepSpec(
        key="entry.publish",
        title="发布分发",
        group="发布",
        desc="按渠道推送已审核条目（渠道留空 = 所有启用渠道）",
        inputs=[
            FieldSpec("entry_id", "条目 ID", "entry", True),
            FieldSpec("channels", "渠道", "text", help="逗号分隔，留空=全部启用渠道"),
        ],
        outputs=["results", "ok_count", "failed_count"],
        # 发布有副作用：重试会在渠道侧重复投递
        retryable=False,
    )
)
async def _entry_publish(ctx: StepCtx) -> dict[str, Any]:
    from cenkor_admin.apps.cms import publish as publish_mod

    entry = await _load_entry(ctx.db, ctx.p("entry_id"))
    raw_channels = ctx.text("channels")
    keys = [c.strip() for c in re.split(r"[,，\s]+", raw_channels) if c.strip()] or None
    res = await publish_mod.publish_entry(ctx.db, entry.id, keys)
    results = res.get("results") or []
    ok = sum(1 for r in results if r.get("ok"))
    failed = sum(1 for r in results if not r.get("ok") and not r.get("skipped"))
    if failed and not ok:
        raise StepError(f"全部渠道发布失败：{results[0].get('error') if results else '未知原因'}")
    return {"results": results, "ok_count": ok, "failed_count": failed}


logger.debug("cms.workflow.steps loaded count={}", len(_REGISTRY))
