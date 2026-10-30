"""AI Copilot · 对话式建模 + 内容生成 + 翻译 + SEO

四条能力，全部走 OpenAI 兼容协议，全部留溯源：

1. propose_content_type   自然语言 → 内容类型草案（不落库，先给人看）
2. apply_content_type     草案 → 真正建模型（写 cms_content_types + field_definitions）
3. draft_entry            素材/大纲 → 条目草稿（强制 draft，必须人审）
4. translate_entry        原文 → 多语言译文（写 cms_entry_translations）
5. suggest_seo            条目 → SEO 元数据（title/description/keywords/OG）

铁律：
- 模型输出的字段类型必须落在 field_types.FIELD_TYPES 内，越界直接丢弃（不让 LLM 污染 schema）
- AI 生成的条目**强制 draft**，不允许直接 published
- 每次调用写一条 cms_ai_generations，记录 provider/model/token/耗时/prompt 摘要
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import re
from typing import Any

import markdown as md
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.ai import prompt_registry as prompts
from cenkor_admin.apps.cms.ai.models import CmsAiGeneration
from cenkor_admin.apps.cms.ai.search import semantic_search
from cenkor_admin.apps.cms.field_types import ARRAY_VALUE_TYPES, FIELD_TYPES
from cenkor_admin.apps.cms.models import (
    ContentTag,
    ContentType,
    Entry,
    EntryTranslation,
    FieldDefinition,
    Tag,
)
from cenkor_admin.core.db import AsyncSessionLocal
from cenkor_admin.core.llm import LLMError, LLMNotConfiguredError, LLMResult, LLMUsage, get_llm

# ---------------------------------------------------------------------------
# 溯源
# ---------------------------------------------------------------------------
_KIND_CT = "content_type_from_nl"
_KIND_DRAFT = "entry_draft"
_KIND_TAG = "auto_tag"
_KIND_TRANSLATE = "translate"
_KIND_SEO = "seo"
_KIND_REWRITE = "text_rewrite"


def _digest(text_value: str) -> str:
    return hashlib.sha256(text_value.encode("utf-8")).hexdigest()[:32]


def _as_object(raw: Any, what: str) -> dict[str, Any]:
    """把 chat_json 的产物收敛成对象。

    「JSON 合法但不是对象」是模型常见的输出偏差：多包一层数组
    ``[{...}]``、把对象再编码成字符串、或干脆只给一个键值对包装。
    这类情况重试一次也未必能修好（模型认为自己的输出没问题），
    所以先宽容收一次，真收不回来才报错。
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        dicts = [x for x in raw if isinstance(x, dict)]
        if len(dicts) == 1:
            return dicts[0]
    if isinstance(raw, str):
        try:
            return _as_object(json.loads(raw), what)
        except (ValueError, TypeError):
            pass
    raise LLMError(f"{what}输出不是对象结构")


def _md_to_html(text: str) -> str:
    """markdown → HTML，供富文本编辑器回填。

    先转义 ``<``/``>``：模型给的正文如果夹带 ``<script>`` 之类，
    原样交给 markdown 会被当作内联 HTML 直通，落库后就是存储型 XSS。
    markdown 语法本身只用到 ``#``/``*``/``-`` 等字符，转义尖括号不影响排版。
    """
    if not text or not str(text).strip():
        return ""
    return md.markdown(
        html.escape(str(text)),
        extensions=["fenced_code", "tables", "sane_lists"],
        output_format="html",
    )


async def _record(
    session: AsyncSession,
    *,
    kind: str,
    target: str,
    result: LLMResult | None,
    params: dict[str, Any] | None = None,
    status: str = "ok",
    error: str | None = None,
    created_by: int | None = None,
    prompt: str = "",
    latency_ms: int | None = None,
    model: str | None = None,
    provider: str | None = None,
) -> int | None:
    """写一条生成溯源，返回记录 id（失败返回 None）。

    返回 id 是给 create_entry_from_draft 用的 —— 条目要把「我这条是哪次生成
    的产物」写进 ai_generation_id，否则事后查不到用了哪个模型、多少 token、
    哪版提示词。失败不应影响主流程，所以内部吞异常。
    """
    try:
        # 当前站点由中间件写入 contextvar；脚本/CLI 下为空，兜到默认站。
        # 用函数内 import 是为了避免 core -> apps 的循环依赖。
        from cenkor_admin.core.site_scope import current_site_id
        from cenkor_admin.apps.cms.ai import pricing as ai_pricing

        p_provider = provider if provider is not None else (result.provider if result else "")
        p_model = model if model is not None else (result.model if result else "")
        tokens_in = result.usage.tokens_in if result else 0
        tokens_out = result.usage.tokens_out if result else 0
        tokens_cache = result.usage.tokens_cache if result else 0

        # 成本在写记录时就算好存下来（快照）。运营以后调单价，历史账单不该跟着变 ——
        # 否则上月成本今天看一个数、明天改价又变一个数，对账直接废掉。
        # 没配单价时留 NULL，与「配了价且确实 0 元」严格区分。
        cost = None
        currency = "CNY"
        if status == "ok":
            try:
                cost, currency = await ai_pricing.snapshot_cost(
                    session,
                    kind=kind,
                    provider=p_provider,
                    model=p_model,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    tokens_cache=tokens_cache,
                    calls=1,
                )
            except Exception as exc:  # 算钱失败绝不能影响主流程
                logger.warning("cms.ai_cost_snapshot_failed err={}", exc)

        gen = CmsAiGeneration(
            site_id=(current_site_id() or 1),
            kind=kind,
            target=target,
            # 生图返回的不是 LLMResult，provider/model 只能由调用方传
            provider=p_provider,
            model=p_model,
            prompt_digest=_digest(prompt),
            params=params,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            tokens_cache=tokens_cache,
            cost=cost,
            currency=currency,
            # 生图返回的不是 LLMResult，拿不到 result.latency_ms，
            # 必须由调用方传进来 —— 否则最慢的一类操作在用量页反而显示「—」
            latency_ms=(
                latency_ms
                if latency_ms is not None
                else (result.latency_ms if result else 0)
            ),
            status=status,
            error=(error[:2000] if error else None),
            created_by=created_by,
        )
        session.add(gen)
        await session.flush()
        return gen.id
    except Exception as exc:
        # loguru 不认 kwargs，必须用 {} 占位 —— 原写法会让这条日志永远打不出内容
        logger.warning("cms.ai_record_failed err={}", exc)
        return None


# ---------------------------------------------------------------------------
# 站点记忆注入
# ---------------------------------------------------------------------------
async def _with_memory(
    session: AsyncSession,
    system: str,
    *,
    budget: int = 2000,
    entry_id: int | None = None,
) -> str:
    """把站点记忆（+ 该条目的会话记忆）拼到 system prompt **末尾**。

    为什么在末尾：固定部分（角色设定）在前、记忆在后，前缀缓存才能命中。
    把记忆塞最前面会让每次请求的前缀都不一样，缓存全部失效 —— 明明省钱的地方
    反而更贵。

    记忆读失败绝不能连带起草失败：站点的核心业务是产出内容，记忆只是提升质量。
    所以这里吞异常，降级成「没有记忆的起草」。
    """
    try:
        from cenkor_admin.apps.cms.ai import memory as mem

        block, _meta = await mem.render_prompt_block(session, budget=budget)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cms.memory_inject_failed err={}", exc)
        block = ""

    # 会话记忆：围绕这篇内容的历次 AI 动作。没有就跳过，不占预算。
    session_block = ""
    if entry_id:
        try:
            from cenkor_admin.apps.cms.ai import session_memory as sess_mem

            session_block = await sess_mem.render_entry_context(session, entry_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cms.session_inject_failed entry={} err={}", entry_id, exc)

    parts = [p for p in (block, session_block) if p]
    if not parts:
        return system
    return f"{system}\n\n" + "\n\n".join(parts)


async def _remember(
    session: AsyncSession,
    entry_id: int | None,
    *,
    kind: str,
    content: str,
    role: str = "assistant",
    created_by: int | None = None,
    title: str = "",
    commit: bool = True,
) -> None:
    """记一轮会话记忆。失败只打日志，绝不影响主流程。"""
    if not entry_id:
        return
    try:
        from cenkor_admin.apps.cms.ai import session_memory as sess_mem

        await sess_mem.add_turn(
            session, entry_id,
            kind=kind, content=content, role=role,
            created_by=created_by, title=title, commit=commit,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("cms.session_remember_failed entry={} kind={} err={}", entry_id, kind, exc)


# ---------------------------------------------------------------------------
# 模型定义校验（防 LLM 越界）
# ---------------------------------------------------------------------------
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,58}[a-z0-9]$")
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _norm_key(raw: Any, fallback: str = "field") -> str:
    """把任意字符串规整成合法 key（小写、下划线、字母开头）。"""
    s = str(raw or "").strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s or not s[0].isalpha():
        s = f"{fallback}_{s}" if s else fallback
    return s[:60]


def _sanitize_fields(raw_fields: Any) -> list[dict[str, Any]]:
    """清洗 LLM 产出的字段列表。

    强制约束：
    - field_type 必须在 FIELD_TYPES 内，否则丢弃该字段
    - field_key 规整并去重
    - select/multiselect 必须有非空 choices，否则降级为 text
    - 系统字段（id/created_at/...）直接丢弃
    """
    reserved = {
        "id",
        "created_at",
        "updated_at",
        "deleted_at",
        "status",
        "sort",
        "title",
        "slug",
        "content",
        "custom_fields",
        "seo",
        "author_id",
        "published_at",
        "category_id",
        "view_count",
        "entry_id",
    }

    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    if not isinstance(raw_fields, list):
        return out

    for idx, f in enumerate(raw_fields):
        if not isinstance(f, dict):
            continue

        ftype = str(f.get("field_type") or "").strip().lower()
        if ftype not in FIELD_TYPES:
            logger.warning("cms.ai.field_type_rejected", field_type=ftype)
            continue

        fkey = _norm_key(f.get("field_key") or f.get("label"), fallback="field")
        # 系统字段直接丢弃，不参与改名（否则会冒出 id_4 这种垃圾字段）
        if fkey in reserved:
            logger.warning("cms.ai.reserved_field_rejected", field_key=fkey)
            continue
        if fkey in seen:
            fkey = _norm_key(f"{fkey}_{idx}", fallback="field")
        if fkey in seen:
            continue
        seen.add(fkey)

        options = f.get("options") if isinstance(f.get("options"), dict) else None
        if ftype in ("select", "multiselect"):
            choices = (options or {}).get("choices")
            if not isinstance(choices, list) or not [c for c in choices if str(c).strip()]:
                # 选择型没有候选项是废字段，降级为普通文本
                ftype = "text"
                options = None
            else:
                options = {"choices": [str(c).strip() for c in choices if str(c).strip()][:50]}

        validation = f.get("validation") if isinstance(f.get("validation"), dict) else None
        if validation:
            # 只保留安全的白名单键，避免 LLM 塞奇怪规则
            allowed = {"min", "max", "min_length", "max_length", "pattern", "step", "rows"}
            validation = {k: v for k, v in validation.items() if k in allowed} or None

        default_value = f.get("default_value")
        if ftype in ARRAY_VALUE_TYPES:
            # 数组型默认值必须可 JSON 序列化
            try:
                json.dumps(default_value)
            except (TypeError, ValueError):
                default_value = None
        elif isinstance(default_value, (dict, list)):
            default_value = json.dumps(default_value, ensure_ascii=False)

        out.append(
            {
                "field_key": fkey,
                "label": str(f.get("label") or fkey)[:80],
                "field_type": ftype,
                "required": bool(f.get("required", False)),
                "default_value": (str(default_value) if default_value not in (None, "") else None),
                "options": options,
                "validation": validation,
                "group": (str(f.get("group")).strip()[:60] if f.get("group") else None),
                "sort": idx,
            }
        )

    return out[:40]


def sanitize_content_type(raw: Any) -> dict[str, Any]:
    """把 LLM 的内容类型输出整形成可落库的结构。"""
    if not isinstance(raw, dict):
        raise LLMError("模型未返回对象结构")
    # 有些模型会包一层
    for wrapper in ("content_type", "result", "data"):
        if isinstance(raw.get(wrapper), dict):
            raw = raw[wrapper]
            break

    key = _norm_key(raw.get("key") or raw.get("name"), fallback="content")
    name = str(raw.get("name") or key)[:80]
    fields = _sanitize_fields(raw.get("fields"))

    if not fields:
        raise LLMError("模型未产出任何合法字段，请把需求描述得更具体")

    return {
        "key": key[:60],
        "name": name,
        "description": (str(raw.get("description"))[:500] if raw.get("description") else None),
        "icon": (str(raw.get("icon"))[:20] if raw.get("icon") else None),
        "supports_category": bool(raw.get("supports_category", True)),
        "supports_tags": bool(raw.get("supports_tags", True)),
        "translatable": bool(raw.get("translatable", False)),
        "fields": fields,
    }


# ---------------------------------------------------------------------------
# 1) 自然语言 → 内容类型草案
# ---------------------------------------------------------------------------
_CT_SYSTEM = """你是内容建模专家，任务是把用户的业务描述转成一个内容类型（Content Type）定义。

只输出一个 JSON 对象，不要任何解释文字，不要 markdown 代码围栏。

JSON 结构：
{
  "key": "英文小写标识，snake_case，如 customer_case",
  "name": "中文名称，不超过 20 字",
  "description": "一句话说明这个内容类型装什么",
  "icon": "一个 emoji",
  "supports_category": true,
  "supports_tags": true,
  "translatable": false,
  "fields": [
    {
      "field_key": "英文小写 snake_case",
      "label": "中文字段名",
      "field_type": "见下方枚举",
      "required": false,
      "default_value": null,
      "options": {"choices": ["选项1", "选项2"]},
      "validation": {"min": 0, "max": 100},
      "group": "分组名称或 null",
      "sort": 0
    }
  ]
}

field_type 只能从下面这些里选，不得自造：
text, longtext, richtext, markdown, number, boolean, date, datetime,
url, email, phone, image, images, file, files, select, multiselect,
color, json, repeater, relation

硬性规则：
1. field_key 只能是小写字母、数字、下划线，且必须以字母开头
2. select / multiselect 必须在 options.choices 里给出候选值（2~12 个）
3. number 类型尽量给 validation 的 min/max
4. 字段总数 6~15 个；required 只标 2~5 个真正必要的
5. 禁止生成系统字段：id / title / slug / content / status / created_at / updated_at / seo
6. 用户没提到的字段不要瞎编，宁可少几个
7. 分组（group）只在字段超过 8 个时才用"""


async def propose_content_type(
    session: AsyncSession,
    description: str,
    *,
    locale: str = "zh-CN",
    created_by: int | None = None,
    extra_hint: str = "",
) -> dict[str, Any]:
    """把业务描述变成内容类型草案。**不落库**，返回给前端让用户确认/微调。"""
    desc = (description or "").strip()
    if len(desc) < 4:
        raise ValueError("描述太短，请至少说明要管理什么内容、有哪些字段")

    llm = get_llm()
    user_msg = f"内容需求描述：\n{desc}"
    if extra_hint:
        user_msg += f"\n\n补充要求：\n{extra_hint}"
    user_msg += f"\n\n（界面语言：{locale}；name/label 用该语言）"

    messages = [
        {"role": "system", "content": await prompts.get(session, "ct", _CT_SYSTEM)},
        {"role": "user", "content": user_msg},
    ]

    try:
        raw, result = await llm.chat_json(messages, temperature=0.2, max_tokens=3000)
        spec = sanitize_content_type(raw)
    except Exception as exc:
        await _record(
            session,
            kind=_KIND_CT,
            target="content_type:draft",
            result=None,
            params={"description_digest": _digest(desc)},
            status="failed",
            error=str(exc),
            created_by=created_by,
            prompt=user_msg,
        )
        raise

    await _record(
        session,
        kind=_KIND_CT,
        target="content_type:draft",
        result=result,
        params={"description_digest": _digest(desc), "field_count": len(spec["fields"])},
        created_by=created_by,
        prompt=user_msg,
    )

    # 顺带告诉调用方这个 key 有没有被占
    exists = (
        await session.execute(select(ContentType.id).where(ContentType.key == spec["key"]))
    ).scalar_one_or_none()
    spec["key_conflict"] = exists is not None
    spec["_meta"] = result.meta()
    return spec


# ---------------------------------------------------------------------------
# 2) 草案 → 真正建模型
# ---------------------------------------------------------------------------
async def apply_content_type(
    session: AsyncSession,
    spec: dict[str, Any],
    *,
    created_by: int | None = None,
) -> ContentType:
    """把（已人工确认的）草案落库：建 ContentType + FieldDefinition。"""
    clean = sanitize_content_type(spec)

    key = clean["key"]
    clash = (
        await session.execute(select(ContentType).where(ContentType.key == key))
    ).scalar_one_or_none()
    if clash is not None:
        raise ValueError(f"内容类型标识「{key}」已存在，请换一个 key")

    ct = ContentType(
        key=key,
        name=clean["name"],
        description=clean["description"],
        icon=clean["icon"],
        supports_category=clean["supports_category"],
        supports_tags=clean["supports_tags"],
        translatable=clean["translatable"],
    )
    session.add(ct)
    await session.flush()  # 拿到 ct.id

    for f in clean["fields"]:
        session.add(
            FieldDefinition(
                content_type_id=ct.id,
                field_key=f["field_key"],
                label=f["label"],
                field_type=f["field_type"],
                required=f["required"],
                default_value=f["default_value"],
                options=f["options"],
                validation=f["validation"],
                sort=f["sort"],
                status="active",
                created_by=created_by,
            )
        )

    # 标记来源：写一条溯源，target 指向真实 id
    await _record(
        session,
        kind=_KIND_CT,
        target=f"content_type:{ct.id}",
        result=None,
        params={"key": key, "field_count": len(clean["fields"]), "applied": True},
        created_by=created_by,
        prompt=json.dumps(clean, ensure_ascii=False)[:2000],
    )

    await session.commit()
    await session.refresh(ct)
    logger.info("cms.ai.content_type_created", key=key, fields=len(clean["fields"]))
    return ct


# ---------------------------------------------------------------------------
# 3) 素材 → 条目草稿
# ---------------------------------------------------------------------------
_DRAFT_SYSTEM = """你是资深内容编辑。根据用户给的素材和大纲，为指定内容类型写一条结构完整的草稿。

只输出一个 JSON 对象（以 { 开头、以 } 结尾），不要数组、不要任何解释文字：
{
  "title": "标题，不超过 60 字",
  "slug": "英文小写短横线，如 customer-case-baosteel",
  "content": {"summary": "摘要（80~150 字）", "body": "正文 markdown"},
  "custom_fields": {"字段key": 值, ...},
  "seo": {"title": "", "description": ""}
}

硬性规则：
1. custom_fields 的 key 必须是给定字段定义里的 field_key，不得自造
2. 类型对齐：number 用数字（不带单位）、boolean 用 true/false、
   images/files/multiselect/repeater 用数组、select 只能取 choices 里的值
3. **绝不编造具体数字、客户名、日期、证书编号**——素材里没有就留空字符串或 null，
   并在 content.body 里用「（待补充）」标出缺口
4. 正文用 markdown，段落之间空行，不用一级标题（标题在 title 里）
5. 语气专业克制，不用「赋能」「闭环」「抓手」这类空话
6. **正文 600~1200 字**，宁可短而实，不要为凑长度注水
7. **整段输出不要用 ``` 代码围栏包裹**；正文里确实需要代码块时用 4 空格缩进，
   否则围栏会把外层 JSON 截断"""


async def draft_entry(
    session: AsyncSession,
    content_type_id: int,
    brief: str,
    *,
    created_by: int | None = None,
    lang: str = "zh-CN",
    max_tokens: int = 4000,
) -> dict[str, Any]:
    """根据素材/大纲生成条目草稿。**只返回草稿，不落库**。"""
    ct = (
        await session.execute(select(ContentType).where(ContentType.id == content_type_id))
    ).scalar_one_or_none()
    if ct is None:
        raise ValueError(f"内容类型 {content_type_id} 不存在")

    fields = (
        (
            await session.execute(
                select(FieldDefinition)
                .where(
                    FieldDefinition.content_type_id == content_type_id,
                    FieldDefinition.status == "active",
                )
                .order_by(FieldDefinition.sort)
            )
        )
        .scalars()
        .all()
    )

    field_spec = [
        {
            "field_key": f.field_key,
            "label": f.label,
            "field_type": f.field_type,
            "required": f.required,
            "choices": ((f.options or {}).get("choices") if isinstance(f.options, dict) else None),
        }
        for f in fields
    ]

    # 知识库参考：先按 brief 召回相关段落。没有命中时 kb_text 为空，
    # 提示词与接入知识库之前完全一致
    kb_text, kb_sources = await _kb_reference(session, brief)

    user_msg = (
        f"内容类型：{ct.name}（key={ct.key}）\n"
        f"字段定义：\n{json.dumps(field_spec, ensure_ascii=False, indent=2)}\n\n"
        f"{_kb_block(kb_text)}"
        f"素材/大纲：\n{(brief or '').strip()[:6000]}\n\n"
        f"（正文语言：{lang}）"
    )

    llm = get_llm()
    messages = [
        {"role": "system", "content": await _with_memory(
            session, await prompts.get(session, "draft", _DRAFT_SYSTEM)
        )},
        {"role": "user", "content": user_msg},
    ]

    try:
        raw, result = await llm.chat_json(messages, temperature=0.5, max_tokens=max_tokens)
    except Exception as exc:
        await _record(
            session,
            kind=_KIND_DRAFT,
            target=f"content_type:{content_type_id}",
            result=None,
            params={
                "brief_digest": _digest(brief),
                "kb_docs": [x["doc_id"] for x in kb_sources],
            },
            status="failed",
            error=str(exc),
            created_by=created_by,
            prompt=user_msg,
        )
        raise

    raw = _as_object(raw, "草稿")

    # 清洗 custom_fields：只留合法 key，并按字段类型粗校验
    custom, dropped = _clean_custom_fields(raw.get("custom_fields"), fields)

    title = str(raw.get("title") or "").strip()[:200]
    if not title:
        raise LLMError("模型未给出标题")

    slug = str(raw.get("slug") or "").strip().lower()
    slug = re.sub(r"[^a-z0-9-]+", "-", slug).strip("-")
    if slug and not _SLUG_RE.match(slug):
        slug = ""
    if not slug:
        slug = f"ai-{_digest(title)[:8]}"

    content = raw.get("content") if isinstance(raw.get("content"), dict) else {}
    seo = raw.get("seo") if isinstance(raw.get("seo"), dict) else {}

    generation_id = await _record(
        session,
        kind=_KIND_DRAFT,
        target=f"content_type:{content_type_id}",
        result=result,
        params={
            "brief_digest": _digest(brief),
            "dropped_fields": dropped,
            "title": title[:60],
        },
        created_by=created_by,
        prompt=user_msg,
    )

    return {
        "content_type_id": content_type_id,
        "content_type_key": ct.key,
        "title": title,
        "slug": slug,
        "content": content,
        "custom_fields": custom,
        "seo": seo,
        "dropped_fields": dropped,
        # 用了哪些知识库资料。前端据此显示「参考了 N 份资料」并允许点开原文 ——
        # 不告诉用户引用了什么，就没法验证稿子里的数字是从哪来的
        "kb_sources": kb_sources,
        "status": "draft",  # AI 产出永远是草稿
        # 供 create_entry_from_draft 写入条目溯源；不在 API 响应里外露（下划线前缀
        # 的 key 会被路由层过滤），避免前端把它当业务字段回传
        "_generation_id": generation_id,
        "_meta": result.meta(),
    }


# 3b) 素材 → 条目草稿（流式）
# ---------------------------------------------------------------------------
_DRAFT_STREAM_SYSTEM = """你是资深内容编辑。根据用户给的素材和大纲，为指定内容类型写一条草稿正文。

**输出格式（严格遵守，第一行就是 TITLE:，不要任何前言、解释或 markdown 代码围栏）：**
TITLE: 标题（不超过 60 字）
SLUG: 英文小写短横线（如 customer-case-baosteel）
（空一行）
正文 markdown（600~1200 字）

硬性规则：
1. 第一行以 TITLE: 开头，第二行以 SLUG: 开头，前缀一字不差，各只占一行
2. 绝不编造具体数字、客户名、日期、证书编号——素材里没有就在正文用「（待补充）」标出
3. 正文用 markdown，段落之间空行，不用一级标题（标题已在 TITLE 里）
4. 语气专业克制，不用「赋能」「闭环」「抓手」这类空话
5. 宁可短而实，不要为凑长度注水
6. TITLE 和 SLUG 之后除正文外不要再输出任何别的内容"""

# 第二阶段：正文完成后补充摘要/字段/SEO（输出少，几秒）
_DRAFT_EXTRA_SYSTEM = """你是内容编辑助理。给你字段定义与一篇已写好的草稿，产出补充元数据。

只输出一个 JSON 对象（不要数组、不要解释、不要代码围栏）：
{"summary": "摘要（80~150 字）", "custom_fields": {"字段key": 值}, "seo": {"title": "", "description": ""}}

硬性规则：
1. custom_fields 的 key 必须是字段定义里的 field_key，不得自造；没有合适值的字段不要硬填
2. 类型对齐：number 用数字、boolean 用 true/false、数组类型用数组、select 只能取 choices 里的值
3. 绝不编造——正文里没有的信息留空字符串或 null"""

_DRAFT_TITLE_RE = re.compile(r"^[ \t]*TITLE[:：][ \t]*(.+?)[ \t]*\r?\n", re.MULTILINE)
_DRAFT_STREAM_SLUG_RE = re.compile(r"^[ \t]*SLUG[:：][ \t]*(\S+)[ \t]*\r?\n", re.MULTILINE)


async def draft_entry_stream(
    session: AsyncSession,
    content_type_id: int,
    brief: str,
    *,
    created_by: int | None = None,
    lang: str = "zh-CN",
    max_tokens: int = 4000,
):
    """流式起草：async generator，yield (event, payload) 事件序列。

    事件：meta(标题/别名) → delta(正文片段，多次) → extra(摘要/字段/SEO) →
    done(与 draft_entry 返回值同构的完整草稿对象)；任何一步失败 yield
    ("error", {"detail", "preview"}) 后结束。

    两阶段设计：阶段一只让模型写 TITLE/SLUG/正文（正文 token 流式透出，
    用户边等边读）；阶段二拿完整正文小请求补 summary/custom_fields/seo。
    """
    ct = (
        await session.execute(select(ContentType).where(ContentType.id == content_type_id))
    ).scalar_one_or_none()
    if ct is None:
        yield ("error", {"detail": f"内容类型 {content_type_id} 不存在"})
        return

    fields = (
        (
            await session.execute(
                select(FieldDefinition)
                .where(
                    FieldDefinition.content_type_id == content_type_id,
                    FieldDefinition.status == "active",
                )
                .order_by(FieldDefinition.sort)
            )
        )
        .scalars()
        .all()
    )
    field_spec = [
        {
            "field_key": f.field_key,
            "label": f.label,
            "field_type": f.field_type,
            "required": f.required,
            "choices": ((f.options or {}).get("choices") if isinstance(f.options, dict) else None),
        }
        for f in fields
    ]

    # 阶段一不带字段定义：正文用不上，省 prompt 也快出第一句
    kb_text, kb_sources = await _kb_reference(session, brief)
    user_msg = (
        f"内容类型：{ct.name}（key={ct.key}）\n"
        f"{_kb_block(kb_text)}"
        f"素材/大纲：\n{(brief or '').strip()[:6000]}\n\n"
        f"（正文语言：{lang}）"
    )
    llm = get_llm()
    messages = [
        {"role": "system", "content": await _with_memory(
            session, await prompts.get(session, "draft_stream", _DRAFT_STREAM_SYSTEM)
        )},
        {"role": "user", "content": user_msg},
    ]

    meta: dict[str, Any] = {}
    acc: list[str] = []
    header_done = False
    body_start = 0  # 正文起点（SLUG 行换行之后，固定不变）
    sent = 0  # 已作为 delta 透出的字符数（随 delta 推进）
    emitted_body = False
    title = ""
    slug = ""
    try:
        async for delta in llm.chat_stream(messages, temperature=0.5, max_tokens=max_tokens, meta_out=meta):
            acc.append(delta)
            text = "".join(acc)
            if not header_done:
                mt = _DRAFT_TITLE_RE.search(text)
                if mt is None:
                    if len(text) > 300:
                        raise LLMError("模型未按 TITLE:/SLUG: 格式输出")
                    continue
                ms = _DRAFT_STREAM_SLUG_RE.search(text, mt.end())
                if ms is None:
                    if len(text) > 400:
                        raise LLMError("模型未按 TITLE:/SLUG: 格式输出（缺 SLUG）")
                    continue
                # 正则要求行尾换行符，行没到齐不会提前匹配（分号边界安全）
                title = mt.group(1).strip()[:200]
                slug = ms.group(1).strip()
                body_start = sent = ms.end()
                header_done = True
                yield ("meta", {"title": title, "slug": slug, "kb_sources": kb_sources})
            if header_done and len(text) > sent:
                seg = text[sent:]
                if not emitted_body:
                    # 头部与正文之间的空行不透出，保证 done.body 与 delta 拼接一致
                    seg = seg.lstrip()
                    if not seg:
                        sent = len(text)
                        continue
                    emitted_body = True
                yield ("delta", {"t": seg})
                sent = len(text)

        if not header_done:
            raise LLMError("模型未按 TITLE:/SLUG: 格式输出")
        body_md = "".join(acc)[body_start:].strip()
        if not body_md:
            raise LLMError("模型未输出正文")

        # slug 清洗与兜底（与 draft_entry 同规则）
        slug_clean = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")
        if slug_clean and not _SLUG_RE.match(slug_clean):
            slug_clean = ""
        if not slug_clean:
            slug_clean = f"ai-{_digest(title)[:8]}"

        # 阶段二：补充元数据。失败不阻断 —— 草稿仍可保存，缺的字段用户手填
        extra_error = ""
        extra_obj: dict[str, Any] = {}
        extra_result = None
        try:
            extra_raw, extra_result = await llm.chat_json(
                [
                    {"role": "system", "content": await prompts.get(session, "draft_extra", _DRAFT_EXTRA_SYSTEM)},
                    {
                        "role": "user",
                        "content": (
                            f"字段定义：\n{json.dumps(field_spec, ensure_ascii=False, indent=2)}\n\n"
                            f"标题：{title}\n\n正文：\n{body_md[:8000]}"
                        ),
                    },
                ],
                temperature=0.3,
                max_tokens=1200,
            )
            extra_obj = _as_object(extra_raw, "补充元数据")
        except Exception as exc:  # noqa: BLE001
            extra_error = str(exc)[:300]

        custom, dropped = _clean_custom_fields(extra_obj.get("custom_fields"), fields)
        content = {
            "summary": str(extra_obj.get("summary") or "").strip(),
            "body": body_md,
        }
        seo = extra_obj.get("seo") if isinstance(extra_obj.get("seo"), dict) else {}

        # 两次调用合并为一条溯源记录（kind 与非流式一致，驾驶舱统计不断档）
        su = meta.get("usage") or {}
        eu = extra_result.usage if extra_result else LLMUsage()
        gen_result = LLMResult(
            text="",
            model=str(meta.get("model") or ""),
            provider=str(meta.get("provider") or ""),
            usage=LLMUsage(
                tokens_in=int(su.get("tokens_in") or 0) + eu.tokens_in,
                tokens_out=int(su.get("tokens_out") or 0) + eu.tokens_out,
                total_tokens=int(su.get("total_tokens") or 0) + eu.total_tokens,
            ),
            latency_ms=int(meta.get("latency_ms") or 0) + (extra_result.latency_ms if extra_result else 0),
            finish_reason=str(meta.get("finish_reason") or ""),
        )
        generation_id = await _record(
            session,
            kind=_KIND_DRAFT,
            target=f"content_type:{content_type_id}",
            result=gen_result,
            params={
                "brief_digest": _digest(brief),
                "dropped_fields": dropped,
                "title": title[:60],
                "stream": True,
                "kb_docs": [x["doc_id"] for x in kb_sources],
                **({"extra_error": extra_error} if extra_error else {}),
            },
            created_by=created_by,
            prompt=user_msg,
        )
        await session.commit()

        draft = {
            "content_type_id": content_type_id,
            "content_type_key": ct.key,
            "title": title,
            "slug": slug_clean,
            "content": content,
            "custom_fields": custom,
            "seo": seo,
            "dropped_fields": dropped,
            "kb_sources": kb_sources,
            "status": "draft",
            "_generation_id": generation_id,
            "_meta": gen_result.meta(),
        }
        yield (
            "extra",
            {
                "summary": content["summary"],
                "custom_fields": custom,
                "seo": seo,
                "dropped_fields": dropped,
                "extra_error": extra_error,
            },
        )
        yield ("done", draft)
    except Exception as exc:  # noqa: BLE001
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            pass
        await _record(
            session,
            kind=_KIND_DRAFT,
            target=f"content_type:{content_type_id}",
            result=None,
            params={"brief_digest": _digest(brief), "stream": True},
            status="failed",
            error=str(exc),
            created_by=created_by,
            prompt=user_msg,
        )
        await session.commit()
        yield (
            "error",
            {"detail": str(exc)[:300] or "生成失败", "preview": "".join(acc)[:300]},
        )


def _clean_custom_fields(
    raw_custom: Any, fields: list[Any]
) -> tuple[dict[str, Any], list[str]]:
    """清洗模型给的 custom_fields：只留合法 key，按字段类型粗校验。

    draft_entry 与 draft_entry_stream 共用；返回 (custom, dropped)。
    """
    valid_keys = {f.field_key: f.field_type for f in fields}
    custom: dict[str, Any] = {}
    dropped: list[str] = []
    for k, v in (raw_custom or {}).items() if isinstance(raw_custom, dict) else []:
        fk = _norm_key(k)
        if fk not in valid_keys:
            dropped.append(str(k))
            continue
        ftype = valid_keys[fk]
        if ftype in ("number",) and not isinstance(v, (int, float)):
            try:
                v = float(str(v).strip() or 0)
            except (TypeError, ValueError):
                v = None
        if ftype in ARRAY_VALUE_TYPES and not isinstance(v, list):
            v = [v] if v not in (None, "") else []
        custom[fk] = v
    return custom, dropped


async def create_entry_from_draft(
    session: AsyncSession,
    draft: dict[str, Any],
    *,
    created_by: int | None = None,
    ai_origin: str = "draft",
) -> Entry:
    """把 draft_entry 的产物真正落库为草稿条目。

    ai_origin 同时承担两个作用：写入条目的来源标记，以及决定是否关联生成记录。
    显式传 None 表示「这次落库不算 AI 产出」（比如人工确认后重放草稿）。
    """
    content = dict(draft.get("content") or {})

    # 起草给的是 markdown（content.body），编辑页读的是富文本（content.text）。
    # 不转这一步，AI 写完点进编辑页正文是空的 —— 数据在库里，但界面读不到。
    if not str(content.get("text") or "").strip():
        body = content.get("body") or content.get("markdown") or content.get("md")
        if body:
            content["text"] = _md_to_html(str(body))
        content.pop("body", None)  # 只留 text，避免两份正文日后各改一半而漂移
        content.pop("markdown", None)
        content.pop("md", None)

    entry = Entry(
        content_type_id=draft["content_type_id"],
        title=draft["title"],
        slug=draft.get("slug"),
        content=content,
        custom_fields=draft.get("custom_fields") or {},
        seo=draft.get("seo") or {},
        status="draft",  # 强制草稿，AI 不能直接发布
        author_id=created_by,
        ai_origin=ai_origin,
        ai_generation_id=(draft.get("_generation_id") if ai_origin else None),
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    # 顺手把来源和溯源 id 记进日志：用户报「这篇是 AI 写的吗」时能直接查
    logger.info(
        "cms.ai.entry_created id={} origin={} gen={} title={}",
        entry.id, ai_origin, entry.ai_generation_id, entry.title[:40],
    )
    # 自动打标签：后台任务补打，不拖慢保存/批量响应
    _spawn_bg_task(_auto_tag_later(entry.id, created_by))

    # 开一条会话：把这次起草的由头记下来，后面改写 / SEO / 翻译都跟它对齐
    if ai_origin:
        brief = str(draft.get("_brief") or draft.get("brief") or "").strip()
        body_text = _draft_to_text(entry.title, entry.content)
        await _remember(
            session, entry.id,
            kind="draft",
            content=(
                (f"起草由头：{brief[:300]}；" if brief else "起草由头：未记录；")
                + f"成稿标题「{entry.title}」，正文约 {len(body_text)} 字"
            ),
            created_by=created_by,
            title=entry.title,
        )
    return entry


# ---------------------------------------------------------------------------
# 3b) 内容去重检测
# ---------------------------------------------------------------------------
def _collect_simple(obj: Any, out: list[str], depth: int = 0) -> None:
    """递归收集 JSON 里的字符串值（查重辅助：自定义字段文本也纳入比对）。"""
    if depth > 5:
        return
    if isinstance(obj, str):
        s = obj.strip()
        if len(s) >= 2 and not s.startswith(("http://", "https://", "#")):
            out.append(s)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_simple(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            _collect_simple(v, out, depth + 1)


def _draft_to_text(title: str, content: Any) -> str:
    """把 draft 的标题+正文压成可检索纯文本（查重用，覆盖标题/正文/自定义/SEO）。

    content 可能是 str（纯文本）或 dict（entry.content：text/body/markdown/custom_fields/seo）。
    顺序即重要度：标题 → 正文 → 自定义字段 → SEO。
    """
    parts: list[str] = []
    if title:
        parts.append(str(title).strip())

    if isinstance(content, str):
        parts.append(re.sub(r"<[^>]+>", " ", content))
    elif isinstance(content, dict):
        for key in ("text", "body", "markdown", "md", "summary"):
            v = content.get(key)
            if isinstance(v, str) and v.strip():
                parts.append(re.sub(r"<[^>]+>", " ", v))
        custom = content.get("custom_fields")
        if isinstance(custom, dict):
            extra: list[str] = []
            _collect_simple(custom, extra)
            parts.extend(extra)
        seo = content.get("seo")
        if isinstance(seo, dict):
            for key in ("title", "description", "keywords"):
                v = seo.get(key)
                if isinstance(v, str) and v.strip():
                    parts.append(v)

    text = "\n".join(p for p in parts if p)
    return text[:6000]


async def detect_duplicates(
    session: AsyncSession,
    title: str,
    content: Any,
    *,
    content_type_id: int | None = None,
    content_type_key: str | None = None,
    threshold: float = 0.8,
    limit: int = 5,
    recall_min: float = 0.4,
) -> list[dict[str, Any]]:
    """查重：把给定标题+正文当作查询，返回库内相似条目。

    threshold 是「判定重复」的硬阈值（默认 0.8，即 >80% 相似）；recall_min 是
    「召回下限」——只展示 >= recall_min 的命中，把弱相关噪声挡在外面。
    每条命中带 is_duplicate = score >= threshold，前端据此决定「预警」还是「仅参考」。

    复用 semantic_search(include_drafts=True)：查当前站点内所有非删除条目
    （含已发布 + 草稿），避免和任何已有内容撞车。embedding 未配置时静默返回空。
    """
    text = _draft_to_text(title, content)
    if not text.strip():
        return []
    try:
        hits = await semantic_search(
            session,
            text,
            content_type_id=content_type_id,
            content_type_key=content_type_key,
            include_drafts=True,
            min_score=recall_min,
            limit=limit,
            lang="base",
        )
    except LLMNotConfiguredError:
        logger.warning("cms.dedup.skip_embed_not_configured")
        return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("cms.dedup.search_failed err={}", str(exc))
        return []

    out: list[dict[str, Any]] = []
    for h in hits:
        d = h.as_dict()
        d["is_duplicate"] = h.score >= threshold
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# 3c) 自动打标签
# ---------------------------------------------------------------------------
_AUTO_TAG_SYSTEM = """你是内容标签员。给你一篇内容的标题与正文摘录，以及站点的已有标签池。

只输出一个 JSON 对象（不要数组、不要解释、不要代码围栏）：
{"tags": [{"name": "标签名", "slug": "english-slug"}]}

硬性规则：
1. 最多 5 个标签，按相关性排序；宁缺毋滥，没有贴切的就少给
2. 优先复用已有标签池里的标签（名字一致或明显同义）；池里确实没有贴切的新标签才新建
3. 新标签 name 用简短中文（2~8 字），slug 用小写英文短横线
4. 不要输出与内容无关的泛化标签（如「新闻」「其他」「文章」）
5. 绝不编造正文里没有的属性（客户名、型号、地域）"""

# 后台任务引用集：防 create_task 后被 GC
_bg_tasks: set[asyncio.Task] = set()


def _spawn_bg_task(coro) -> None:
    t = asyncio.create_task(coro)
    _bg_tasks.add(t)
    t.add_done_callback(_bg_tasks.discard)


async def _kb_reference(
    session: AsyncSession,
    query: str,
    *,
    limit: int = 4,
    max_chars: int = 4000,
) -> tuple[str, list[dict[str, Any]]]:
    """从知识库捞参考资料，返回 (拼好的文本块, 出处列表)。

    函数内 import 是必需的，不是洁癖：knowledge → ingest → copilot 是一条回边，
    顶层 import 会在模块初始化阶段撞上循环导入。

    没有命中时返回 ("", [])，调用方据此保持原提示词 —— 知识库为空
    不该让起草变差，也不该让 prompt 里多出一段空标题。
    """
    text = (query or "").strip()
    if not text:
        return "", []

    from cenkor_admin.apps.cms import knowledge
    from cenkor_admin.core.site_scope import current_site_id

    try:
        return await knowledge.context_for_prompt(
            session,
            text[:500],
            site_id=current_site_id() or 1,
            limit=limit,
            max_chars=max_chars,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("cms.draft.kb_failed", error=str(exc))
        return "", []


def _kb_block(block: str) -> str:
    """包成提示词片段。

    措辞刻意保守：「资料里没有的不许编造」而不是「请充分利用资料」。
    后一种说法会让模型把不相干的段落硬接上去凑出因果关系 ——
    有了 RAG 之后最常见的质量问题就是这个。
    """
    if not block.strip():
        return ""
    return (
        "【企业内部资料】\n"
        "以下是该企业自己的资料摘录。涉及事实、参数、流程、数字、名称时"
        "优先采用这里的内容；资料里没有的不许编造，写不出就留空或标「（待补充）」。\n\n"
        f"{block}\n\n"
    )


def _content_excerpt(content: dict[str, Any] | None, limit: int = 1200) -> str:
    """从条目 content 里抽纯文本摘录（标签/摘要/翻译共用的小工具）。"""
    for k in ("text", "body", "markdown", "summary"):
        v = (content or {}).get(k)
        if isinstance(v, str) and v.strip():
            return re.sub(r"<[^>]+>", " ", v)[:limit].strip()
    return ""


async def auto_tag_entry(
    session: AsyncSession,
    entry: Entry,
    *,
    created_by: int | None = None,
    max_tags: int = 5,
    max_new: int = 3,
) -> dict[str, Any]:
    """给条目自动打标签：LLM 优先从已有标签池挑，必要时新建少量标签。

    加法式：只新增关联，不动已有标签；LLM 失败抛异常由调用方兜底。
    返回 {"attached": 新增关联的标签名, "created": 新建的标签名, "already": 本来就有的}。
    """
    existing = (
        await session.execute(
            select(Tag).where(
                Tag.site_id == entry.site_id,
                Tag.content_type_id == entry.content_type_id,
            )
        )
    ).scalars()
    existing = list(existing)
    pool = [{"name": t.name, "slug": t.slug} for t in existing]

    user_msg = (
        f"标题：{entry.title}\n\n"
        f"已有标签池（优先从中选）：{json.dumps(pool, ensure_ascii=False)}\n\n"
        f"正文摘录：\n{_content_excerpt(entry.content) or '（无正文，仅按标题判断）'}"
    )
    llm = get_llm()
    raw, result = await llm.chat_json(
        [
            {"role": "system", "content": await prompts.get(session, "auto_tag", _AUTO_TAG_SYSTEM)},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
        max_tokens=600,
    )
    obj = _as_object(raw, "标签建议")
    items = obj.get("tags") if isinstance(obj.get("tags"), list) else []

    picks: list[dict[str, str]] = []
    seen: set[str] = set()
    for it in items[:max_tags]:
        if isinstance(it, dict):
            name = str(it.get("name") or "").strip()[:80]
            slug = str(it.get("slug") or "").strip()[:80]
        else:
            name, slug = str(it).strip()[:80], ""
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        picks.append({"name": name, "slug": slug})

    attached: list[str] = []
    created: list[str] = []
    already: list[str] = []
    if picks:
        by_name = {t.name.strip().lower(): t for t in existing}
        have = set(
            (
                await session.execute(
                    select(ContentTag.tag_id).where(
                        ContentTag.content_type_id == entry.content_type_id,
                        ContentTag.content_id == entry.id,
                    )
                )
            ).scalars()
        )
        taken_slugs = {t.slug for t in existing}
        for p in picks:
            tag = by_name.get(p["name"].lower())
            if tag is None and len(created) < max_new:
                slug_clean = re.sub(r"[^a-z0-9-]+", "-", p["slug"].lower()).strip("-")
                if not slug_clean:
                    slug_clean = f"tag-{_digest(p['name'])[:8]}"
                base = slug_clean
                while slug_clean in taken_slugs:  # 唯一约束兜底：撞了就拼摘要后缀
                    slug_clean = f"{base}-{_digest(p['name'] + slug_clean)[:4]}"
                taken_slugs.add(slug_clean)
                tag = Tag(
                    site_id=entry.site_id,
                    content_type_id=entry.content_type_id,
                    slug=slug_clean,
                    name=p["name"],
                )
                session.add(tag)
                await session.flush()
                existing.append(tag)
                by_name[p["name"].lower()] = tag
                created.append(p["name"])
            if tag is None:  # 超出 max_new 的新标签：复用失败就跳过
                continue
            if tag.id in have:
                already.append(tag.name)
                continue
            session.add(ContentTag(
                content_type_id=entry.content_type_id,
                content_id=entry.id,
                tag_id=tag.id,
            ))
            have.add(tag.id)
            attached.append(tag.name)
        await session.commit()

    await _record(
        session,
        kind=_KIND_TAG,
        target=f"entry:{entry.id}",
        result=result,
        params={"attached": attached, "created": created},
        created_by=created_by,
        prompt=user_msg,
    )
    await session.commit()
    if attached or created:
        logger.info(
            "cms.ai.auto_tag entry={} attached={} created={}",
            entry.id, attached, created,
        )
    return {"attached": attached, "created": created, "already": already}


async def _auto_tag_later(entry_id: int, created_by: int | None = None) -> None:
    """落库后异步补标签：自开 session，不占调用方的连接。"""
    try:
        async with AsyncSessionLocal() as s:
            entry = await s.get(Entry, entry_id)
            if entry is None or getattr(entry, "deleted_at", None) is not None:
                return
            await auto_tag_entry(s, entry, created_by=created_by)
    except Exception as exc:  # noqa: BLE001
        # 标签是增强不是门槛：失败只记日志，绝不影响条目
        logger.warning("cms.ai.auto_tag_failed entry={} err={}", entry_id, str(exc)[:200])


# ---------------------------------------------------------------------------
# 4) 翻译
# ---------------------------------------------------------------------------
_TRANSLATE_SYSTEM = """你是专业本地化译者。把给定内容翻译成目标语言。

只输出一个 JSON 对象：
{"title": "译后标题", "content": {原结构，值译成目标语言}, "custom_fields": {原结构，值译成目标语言}}

硬性规则：
1. **保持 JSON 结构和所有 key 完全不变**，只翻译值
2. markdown 标记、URL、图片地址、代码块、专有型号原样保留
3. 数字、单位、日期格式按目标语言习惯，但数值不变
4. 品牌名、产品名不翻译（除非该语言有官方译名）
5. 不要添加、删除、合并任何字段"""


async def translate_entry(
    session: AsyncSession,
    entry: Entry,
    target_langs: list[str],
    *,
    created_by: int | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """把条目翻译成多语言，写 cms_entry_translations（状态 draft）。

    返回 {lang: {"ok": bool, "status": ..., "error": ...}}
    """
    if not target_langs:
        return {}

    langs = [lg.strip() for lg in target_langs if lg and lg.strip()][:10]
    llm = get_llm()

    # 已存在的译文
    existing = {
        t.lang: t
        for t in (
            await session.execute(
                select(EntryTranslation).where(
                    EntryTranslation.entry_id == entry.id,
                    EntryTranslation.lang.in_(langs),
                )
            )
        )
        .scalars()
        .all()
    }

    results: dict[str, Any] = {}
    source = {
        "title": entry.title,
        "content": entry.content or {},
        "custom_fields": entry.custom_fields or {},
    }
    payload = json.dumps(source, ensure_ascii=False)[:12000]

    for lang in langs:
        if lang in existing and not overwrite:
            results[lang] = {"ok": True, "status": "skipped", "reason": "已有译文，未覆盖"}
            continue

        user_msg = f"目标语言：{lang}\n\n原文 JSON：\n{payload}"
        messages = [
            {"role": "system", "content": await _with_memory(
                session,
                await prompts.get(session, "translate", _TRANSLATE_SYSTEM),
                entry_id=entry.id,
            )},
            {"role": "user", "content": user_msg},
        ]

        try:
            raw, result = await llm.chat_json(messages, temperature=0.2, max_tokens=6000)
            raw = _as_object(raw, "翻译")

            field_values = {
                "title": str(raw.get("title") or entry.title)[:200],
                "content": raw.get("content") if isinstance(raw.get("content"), dict) else {},
                "custom_fields": (
                    raw.get("custom_fields") if isinstance(raw.get("custom_fields"), dict) else {}
                ),
            }

            tr = existing.get(lang)
            if tr is None:
                tr = EntryTranslation(
                    entry_id=entry.id,
                    lang=lang,
                    field_values=field_values,
                    status="draft",
                    created_by=created_by,
                )
                session.add(tr)
            else:
                tr.field_values = field_values
                tr.status = "draft"

            await _record(
                session,
                kind=_KIND_TRANSLATE,
                target=f"entry:{entry.id}",
                result=result,
                params={"lang": lang},
                created_by=created_by,
                prompt=user_msg,
            )
            results[lang] = {"ok": True, "status": "draft", "_meta": result.meta()}
        except Exception as exc:
            await _record(
                session,
                kind=_KIND_TRANSLATE,
                target=f"entry:{entry.id}",
                result=None,
                params={"lang": lang},
                status="failed",
                error=str(exc),
                created_by=created_by,
                prompt=user_msg,
            )
            results[lang] = {"ok": False, "error": str(exc)[:300]}

    await session.commit()

    if any(v.get("ok") for v in results.values()):
        ok_langs = [k for k, v in results.items() if v.get("ok")]
        await _remember(
            session, entry.id,
            kind="translate",
            content=f"译文已生成：{'、'.join(ok_langs)}（标题与字段按中文原稿对齐）",
            created_by=created_by,
            title=entry.title,
        )

    return results


# ---------------------------------------------------------------------------
# 5) SEO
# ---------------------------------------------------------------------------
_SEO_SYSTEM = """你是 SEO 与 GEO（生成式引擎优化）专家。为给定内容生成元数据。

只输出一个 JSON 对象（以 { 开头、以 } 结尾），不要数组、不要任何解释文字：
{
  "title": "SEO 标题，不超过 60 字符",
  "description": "meta description，60~155 字符，包含核心关键词，像人话不像堆词",
  "keywords": ["5~8 个关键词"],
  "og_title": "社交分享标题，不超过 50 字符",
  "og_description": "社交分享描述，不超过 100 字符",
  "json_ld_type": "最贴切的 schema.org 类型，如 Article / Product / FAQPage / Organization"
}

规则：
1. 不要编造原文没有的信息
2. 关键词覆盖用户可能的搜索问法（含长尾）
3. 描述里不要出现「本文」「这篇文章」这类自指"""


async def suggest_seo(
    session: AsyncSession,
    entry: Entry,
    *,
    created_by: int | None = None,
    lang: str = "zh-CN",
) -> dict[str, Any]:
    """生成 SEO 元数据。**只返回建议，不写库**（由调用方决定是否合并）。"""
    llm = get_llm()

    body = entry.content or {}
    body_text = json.dumps(body, ensure_ascii=False)[:4000]
    user_msg = (
        f"标题：{entry.title}\n"
        f"正文摘要：{body_text}\n"
        f"自定义字段：{json.dumps(entry.custom_fields or {}, ensure_ascii=False)[:1500]}\n"
        f"（输出语言：{lang}）"
    )
    messages = [
        {"role": "system", "content": await _with_memory(
            session, await prompts.get(session, "seo", _SEO_SYSTEM), entry_id=entry.id
        )},
        {"role": "user", "content": user_msg},
    ]

    try:
        raw, result = await llm.chat_json(messages, temperature=0.4, max_tokens=1200)
    except Exception as exc:
        await _record(
            session,
            kind=_KIND_SEO,
            target=f"entry:{entry.id}",
            result=None,
            status="failed",
            error=str(exc),
            created_by=created_by,
            prompt=user_msg,
        )
        raise

    raw = _as_object(raw, "SEO")

    seo = {
        "title": str(raw.get("title") or "")[:120],
        "description": str(raw.get("description") or "")[:300],
        "keywords": [str(k)[:40] for k in (raw.get("keywords") or []) if str(k).strip()][:10],
        "og_title": str(raw.get("og_title") or "")[:120],
        "og_description": str(raw.get("og_description") or "")[:200],
        "json_ld_type": str(raw.get("json_ld_type") or "Article")[:40],
    }

    await _record(
        session,
        kind=_KIND_SEO,
        target=f"entry:{entry.id}",
        result=result,
        params={"title": seo["title"][:60]},
        created_by=created_by,
        prompt=user_msg,
    )

    # 会话记忆：记下这次 SEO 的口径，后续翻译/再分发要跟它对齐
    await _remember(
        session, entry.id,
        kind="seo",
        content=f"SEO 标题「{seo['title']}」；描述「{seo['description'][:80]}」；"
                f"关键词 {', '.join(seo['keywords'][:6])}",
        created_by=created_by,
        title=entry.title,
    )

    return {"seo": seo, "_meta": result.meta()}


# ---------------------------------------------------------------------------
# 6) 字段级改写（编辑页内嵌用）
# ---------------------------------------------------------------------------
# 与「AI 起草」的区别：起草是生成新内容，这里改的是**用户已经写下的东西**。
# 所以铁律是三不：不落库、不新增事实、不动结构。
# 正文是 HTML，但模型**永远不产出 HTML** —— 前端把 HTML 拆成纯文本块送过来，
# 模型只回文本块，前端按序回填。这样标签结构由浏览器 DOM 保证，
# 既不会出现半截标签，也没有 XSS 面。

REWRITE_ACTIONS: dict[str, str] = {
    "polish": "润色：修正语病、调整用词，保持原意，长度与原文相近",
    "expand": "扩写：补充细节与论证，长度为原文的 1.5~2 倍",
    "shorten": "精简：删掉冗余与重复，长度约为原文的一半",
    "formal": "改写为正式书面语，适合官网、白皮书、商务函件",
    "plain": "改写为通俗口语，让不懂行的人也能看懂",
    "title": "另拟一个新标题：不超过 30 字，不堆关键词，不加引号与句号，不要「浅谈」「解析」这类空话；新标题必须与输入的现有标题不同",
    "summary": "概括为一段摘要：80~120 字，只陈述原文意思，不添加新信息，不要「本文」「这篇文章」",
    "custom": "按用户给出的具体要求改写",
}

_REWRITE_SYSTEM = """你是资深文字编辑。按用户指定的动作改写给定文本。

输出规则：
- 单块模式只输出：{"text": "改写后的文本"}
- 多块模式只输出：{"blocks": ["第一块改写", "第二块改写", ...]}

硬性规则：
1. **块数与顺序必须与输入完全一致**，不得合并、拆分或增删
2. 只改文字表达，**不得新增原文没有的事实、数字、人名、日期、结论**
3. 输入里的 HTML 标签、Markdown 标记、URL、图片地址、型号原样保留，不要改写它们
4. 输入中的「（待补充）」占位符原样保留，不要编造内容去填充
5. 空输入块返回空字符串
6. 只输出 JSON，不要任何解释性文字、前言或收尾"""

# 单次改写的上限：模型不是用来改整篇长文的，超了说明用错了地方
_MAX_TEXT_CHARS = 8000
_MAX_BLOCKS = 80
_MAX_BLOCK_CHARS = 4000
_MAX_TOTAL_BLOCK_CHARS = 12000


def _rewrite_user_msg(
    action: str,
    lang: str,
    text: str | None,
    blocks: list[str] | None,
    context: str | None,
    instruction: str | None,
) -> str:
    parts = [f"动作：{REWRITE_ACTIONS[action]}（{action}）", f"输出语言：{lang}"]
    if context:
        parts.append(f"上下文（仅供理解，不要改写）：{context[:1000]}")
    if action == "title":
        # 模型看到输入就是一句像模像样的标题时，很容易原样返回。
        # 这里把「输入是旧标题、要依据正文重拟」说死，并给出信息不足时的退路。
        parts.append(
            "注意：下面的输入是**现有标题**，不是要概括的正文。"
            "请依据上下文里的正文另拟一个新标题，且必须与现有标题不同。"
            "若正文信息不足以支撑新标题，就换一个更具体的角度改写（补上主题词），"
            "但绝不要原样返回现有标题。"
        )
    if instruction:
        parts.append(f"用户具体要求：{instruction[:1000]}")
    if blocks is not None:
        payload = json.dumps(blocks, ensure_ascii=False)
        parts.append(f"多块模式，共 {len(blocks)} 块，输入 JSON 数组：\n{payload}")
    else:
        parts.append(f"单块模式，输入：\n{text}")
    return "\n\n".join(parts)


async def rewrite_text(
    session: AsyncSession,
    *,
    action: str = "polish",
    text: str | None = None,
    blocks: list[str] | None = None,
    instruction: str | None = None,
    lang: str = "zh-CN",
    context: str | None = None,
    created_by: int | None = None,
) -> dict[str, Any]:
    """改写一段文本（text）或多块文本（blocks）。**不写业务表，只留一条溯源。**

    返回 {"text": ...} 或 {"blocks": [...]}，附 _meta。
    模型漏掉的块用原文补，绝不返回空串覆盖用户内容。
    """
    if action not in REWRITE_ACTIONS:
        raise ValueError(f"不支持的改写动作：{action}")

    if blocks is not None:
        if not blocks:
            raise ValueError("blocks 不能为空")
        if len(blocks) > _MAX_BLOCKS:
            raise ValueError(f"最多 {_MAX_BLOCKS} 个文本块，当前 {len(blocks)}")
        blocks = [str(b) for b in blocks]
        if any(len(b) > _MAX_BLOCK_CHARS for b in blocks):
            raise ValueError(f"单个文本块不能超过 {_MAX_BLOCK_CHARS} 字")
        if sum(len(b) for b in blocks) > _MAX_TOTAL_BLOCK_CHARS:
            raise ValueError(f"文本总量超出 {_MAX_TOTAL_BLOCK_CHARS} 字，请分次改写")
    else:
        text = (text or "").strip()
        if not text:
            raise ValueError("text 不能为空")
        if len(text) > _MAX_TEXT_CHARS:
            raise ValueError(f"文本不能超过 {_MAX_TEXT_CHARS} 字，请分次改写")

    llm = get_llm()
    user_msg = _rewrite_user_msg(action, lang, text, blocks, context, instruction)
    messages = [
        {"role": "system", "content": await _with_memory(
            session, await prompts.get(session, "rewrite", _REWRITE_SYSTEM)
        )},
        {"role": "user", "content": user_msg},
    ]
    target = f"action:{action}"

    try:
        raw, result = await llm.chat_json(messages, temperature=0.5, max_tokens=4000)
    except Exception as exc:
        await _record(
            session,
            kind=_KIND_REWRITE,
            target=target,
            result=None,
            params={"action": action, "mode": "blocks" if blocks is not None else "text"},
            status="failed",
            error=str(exc),
            created_by=created_by,
            prompt=user_msg,
        )
        raise

    raw = _as_object(raw, "改写")

    # 拟标题时模型若把现有标题原样吐回来，等于什么也没做。
    # 给一次带明确指正的重试；仍不行就如实返回，由前端提示「未改动」。
    if action == "title" and blocks is None and text:
        first = str(raw.get("text") or "").strip()
        if first == text.strip():
            retry_messages = [
                *messages,
                {"role": "assistant", "content": result.text[:2000]},
                {
                    "role": "user",
                    "content": (
                        "你刚才把现有标题原样返回了，没有完成任务。"
                        "请依据上下文里的正文另拟一个与现有标题不同的标题，"
                        '仍然只输出 {"text": "新标题"}。'
                    ),
                },
            ]
            try:
                retried, retry_result = await llm.chat_json(
                    retry_messages, temperature=0.8, max_tokens=200
                )
                alt = str((retried or {}).get("text") or "").strip() if isinstance(retried, dict) else ""
                if alt and alt != text.strip():
                    raw = retried
                    result = retry_result
                    logger.info("cms.ai.title_retried", entry_title=text[:40])
            except Exception as exc:  # noqa: BLE001
                # 重试是锦上添花，失败就用第一次的结果，不能把主流程带崩
                logger.warning("cms.ai.title_retry_failed", error=str(exc))

    out: dict[str, Any] = {"action": action}
    if blocks is not None:
        got = raw.get("blocks")
        if isinstance(got, dict):
            # 有些模型会回 {"0": "...", "1": "..."}
            got = [got.get(str(i)) for i in range(len(blocks))]
        if not isinstance(got, list):
            raise LLMError("多块改写缺少 blocks 数组")
        merged: list[str] = []
        for idx, original in enumerate(blocks):
            val = got[idx] if idx < len(got) else None
            merged.append(str(val) if isinstance(val, str) and val.strip() else original)
        out["blocks"] = merged
        # 模型漏块是可诊断的信号：记下来，别静默
        missed = sum(
            1
            for i, o in enumerate(blocks)
            if o.strip() and not (i < len(got) and str(got[i] or "").strip())
        )
    else:
        val = raw.get("text")
        if not isinstance(val, str) or not val.strip():
            raise LLMError("改写结果为空")
        out["text"] = val.strip()
        missed = 0

    await _record(
        session,
        kind=_KIND_REWRITE,
        target=target,
        result=result,
        params={
            "action": action,
            "mode": "blocks" if blocks is not None else "text",
            "blocks": len(blocks) if blocks is not None else None,
            "missed": missed,
        },
        created_by=created_by,
        prompt=user_msg,
    )
    out["_meta"] = result.meta()
    return out


# ---------------------------------------------------------------------------
# 用量统计（给后台看成本）
# ---------------------------------------------------------------------------
async def usage_summary(session: AsyncSession, *, days: int = 30) -> list[dict[str, Any]]:
    """按 kind 汇总最近 N 天的 AI 用量（旧接口，只给用量，不含金额）。

    新代码请用 `ai.pricing.usage_summary`：它会细到模型维度并折算金额。
    这里保留只是为了不破坏已有调用方。
    """
    from cenkor_admin.apps.cms.ai import pricing

    data = await pricing.usage_summary(session, days=days)
    return [
        {
            "kind": i["kind"],
            "calls": i["calls"],
            "tokens_in": i["tokens_in"],
            "tokens_out": i["tokens_out"],
            "avg_latency_ms": i["avg_latency_ms"],
        }
        for i in data["items"]
    ]
