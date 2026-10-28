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

import hashlib
import html
import json
import re
from typing import Any

import markdown as md
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.ai.models import CmsAiGeneration
from cenkor_admin.apps.cms.field_types import ARRAY_VALUE_TYPES, FIELD_TYPES
from cenkor_admin.apps.cms.models import (
    ContentType,
    Entry,
    EntryTranslation,
    FieldDefinition,
)
from cenkor_admin.core.llm import LLMError, LLMResult, get_llm

# ---------------------------------------------------------------------------
# 溯源
# ---------------------------------------------------------------------------
_KIND_CT = "content_type_from_nl"
_KIND_DRAFT = "entry_draft"
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
) -> None:
    """写一条生成溯源。失败不应影响主流程，所以内部吞异常。"""
    try:
        gen = CmsAiGeneration(
            kind=kind,
            target=target,
            provider=(result.provider if result else ""),
            model=(result.model if result else ""),
            prompt_digest=_digest(prompt),
            params=params,
            tokens_in=(result.usage.tokens_in if result else 0),
            tokens_out=(result.usage.tokens_out if result else 0),
            latency_ms=(result.latency_ms if result else 0),
            status=status,
            error=(error[:2000] if error else None),
            created_by=created_by,
        )
        session.add(gen)
        await session.flush()
    except Exception as exc:
        logger.warning("cms.ai_record_failed", error=str(exc))


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
        {"role": "system", "content": _CT_SYSTEM},
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

    user_msg = (
        f"内容类型：{ct.name}（key={ct.key}）\n"
        f"字段定义：\n{json.dumps(field_spec, ensure_ascii=False, indent=2)}\n\n"
        f"素材/大纲：\n{(brief or '').strip()[:6000]}\n\n"
        f"（正文语言：{lang}）"
    )

    llm = get_llm()
    messages = [
        {"role": "system", "content": _DRAFT_SYSTEM},
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
            params={"brief_digest": _digest(brief)},
            status="failed",
            error=str(exc),
            created_by=created_by,
            prompt=user_msg,
        )
        raise

    raw = _as_object(raw, "草稿")

    # 清洗 custom_fields：只留合法 key，并按字段类型粗校验
    valid_keys = {f.field_key: f.field_type for f in fields}
    raw_custom = raw.get("custom_fields") if isinstance(raw.get("custom_fields"), dict) else {}
    custom: dict[str, Any] = {}
    dropped: list[str] = []
    for k, v in raw_custom.items():
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

    await _record(
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
        "status": "draft",  # AI 产出永远是草稿
        "_meta": result.meta(),
    }


async def create_entry_from_draft(
    session: AsyncSession,
    draft: dict[str, Any],
    *,
    created_by: int | None = None,
) -> Entry:
    """把 draft_entry 的产物真正落库为草稿条目。"""
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
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    logger.info("cms.ai.entry_created", entry_id=entry.id, title=entry.title[:40])
    return entry


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
            {"role": "system", "content": _TRANSLATE_SYSTEM},
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
        {"role": "system", "content": _SEO_SYSTEM},
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
        {"role": "system", "content": _REWRITE_SYSTEM},
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
    """按 kind 汇总最近 N 天的 AI 用量。"""
    rows = (
        await session.execute(
            select(
                CmsAiGeneration.kind,
                func.count(CmsAiGeneration.id),
                func.coalesce(func.sum(CmsAiGeneration.tokens_in), 0),
                func.coalesce(func.sum(CmsAiGeneration.tokens_out), 0),
                func.coalesce(func.avg(CmsAiGeneration.latency_ms), 0),
            )
            .where(
                CmsAiGeneration.created_at >= func.now() - func.make_interval(0, 0, 0, days),
                CmsAiGeneration.status == "ok",
            )
            .group_by(CmsAiGeneration.kind)
        )
    ).all()

    return [
        {
            "kind": r[0],
            "calls": int(r[1]),
            "tokens_in": int(r[2]),
            "tokens_out": int(r[3]),
            "avg_latency_ms": int(r[4] or 0),
        }
        for r in rows
    ]
