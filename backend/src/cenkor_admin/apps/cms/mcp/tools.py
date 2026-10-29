"""MCP 工具集 · 定义与实现

每个工具 = 一段 JSON Schema（给模型看）+ 一个 async 实现。
所有工具都拿同一个 AsyncSession，事务由调用方（server 层）控制。

写权限：MCP_ALLOW_WRITE 打开才允许 create/update/publish。
默认允许（因为访问本身已经需要 MCP_API_KEY），但可以在 .env 里一键锁成只读。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.ai import copilot
from cenkor_admin.apps.cms.ai.search import semantic_search
from cenkor_admin.apps.cms.models import ContentType, Entry, FieldDefinition
from cenkor_admin.core.config import get_settings
from cenkor_admin.core.llm import LLMNotConfiguredError

# ---------------------------------------------------------------------------
# 工具实现
# ---------------------------------------------------------------------------


async def _list_content_types(session: AsyncSession, args: dict[str, Any]) -> Any:
    rows = (await session.execute(select(ContentType).order_by(ContentType.key))).scalars().all()
    counts = {}
    for ct_id, cnt in (
        await session.execute(
            select(FieldDefinition.content_type_id, func.count())
            .where(FieldDefinition.status == "active")
            .group_by(FieldDefinition.content_type_id)
        )
    ).all():
        counts[ct_id] = int(cnt)

    return [
        {
            "key": ct.key,
            "name": ct.name,
            "description": ct.description,
            "translatable": ct.translatable,
            "field_count": counts.get(ct.id, 0),
        }
        for ct in rows
    ]


async def _describe_content_type(session: AsyncSession, args: dict[str, Any]) -> Any:
    key = str(args.get("key") or "").strip()
    if not key:
        raise ValueError("缺少参数 key")
    ct = (
        await session.execute(select(ContentType).where(ContentType.key == key))
    ).scalar_one_or_none()
    if ct is None:
        raise ValueError(f"内容类型 {key} 不存在")

    fields = (
        (
            await session.execute(
                select(FieldDefinition)
                .where(FieldDefinition.content_type_id == ct.id, FieldDefinition.status == "active")
                .order_by(FieldDefinition.sort)
            )
        )
        .scalars()
        .all()
    )

    return {
        "key": ct.key,
        "name": ct.name,
        "description": ct.description,
        "supports_category": ct.supports_category,
        "supports_tags": ct.supports_tags,
        "translatable": ct.translatable,
        "fields": [
            {
                "field_key": f.field_key,
                "label": f.label,
                "field_type": f.field_type,
                "required": f.required,
                "choices": (
                    (f.options or {}).get("choices") if isinstance(f.options, dict) else None
                ),
                "validation": f.validation,
            }
            for f in fields
        ],
    }


async def _search_content(session: AsyncSession, args: dict[str, Any]) -> Any:
    query = str(args.get("query") or "").strip()
    if not query:
        raise ValueError("缺少参数 query")

    hits = await semantic_search(
        session,
        query,
        content_type_key=args.get("content_type_key"),
        lang=str(args.get("lang") or "base"),
        limit=int(args.get("limit") or 10),
        include_drafts=bool(args.get("include_drafts", False)),
    )
    return {"query": query, "count": len(hits), "results": [h.as_dict() for h in hits]}


async def _get_entry(session: AsyncSession, args: dict[str, Any]) -> Any:
    entry: Entry | None = None
    if args.get("entry_id"):
        entry = (
            await session.execute(
                select(Entry).where(Entry.id == int(args["entry_id"]), Entry.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
    elif args.get("slug"):
        stmt = select(Entry).where(Entry.slug == str(args["slug"]), Entry.deleted_at.is_(None))
        if args.get("content_type_key"):
            ct = (
                await session.execute(
                    select(ContentType).where(ContentType.key == str(args["content_type_key"]))
                )
            ).scalar_one_or_none()
            if ct is None:
                raise ValueError(f"内容类型 {args['content_type_key']} 不存在")
            stmt = stmt.where(Entry.content_type_id == ct.id)
        entry = (await session.execute(stmt)).scalars().first()
    else:
        raise ValueError("需要 entry_id 或 slug 之一")

    if entry is None:
        raise ValueError("条目不存在")

    ct = (
        await session.execute(select(ContentType).where(ContentType.id == entry.content_type_id))
    ).scalar_one_or_none()

    return {
        "entry_id": entry.id,
        "content_type_key": ct.key if ct else "",
        "title": entry.title,
        "slug": entry.slug,
        "status": entry.status,
        "content": entry.content,
        "custom_fields": entry.custom_fields,
        "seo": entry.seo,
        "published_at": entry.published_at.isoformat() if entry.published_at else None,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }


async def _create_entry(session: AsyncSession, args: dict[str, Any]) -> Any:
    _require_write()
    ct_key = str(args.get("content_type_key") or "").strip()
    title = str(args.get("title") or "").strip()
    if not ct_key or not title:
        raise ValueError("需要 content_type_key 与 title")

    ct = (
        await session.execute(select(ContentType).where(ContentType.key == ct_key))
    ).scalar_one_or_none()
    if ct is None:
        raise ValueError(f"内容类型 {ct_key} 不存在")

    entry = Entry(
        content_type_id=ct.id,
        title=title[:200],
        slug=(str(args.get("slug")).strip()[:120] if args.get("slug") else None),
        content=args.get("content") if isinstance(args.get("content"), dict) else {},
        custom_fields=(
            args.get("custom_fields") if isinstance(args.get("custom_fields"), dict) else {}
        ),
        seo=args.get("seo") if isinstance(args.get("seo"), dict) else {},
        status="draft",  # Agent 只能建草稿，发布必须走 publish 且有权限
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)

    logger.info("mcp.entry_created", entry_id=entry.id, ct=ct_key)
    return {"entry_id": entry.id, "status": entry.status, "title": entry.title}


async def _update_entry(session: AsyncSession, args: dict[str, Any]) -> Any:
    _require_write()
    entry_id = args.get("entry_id")
    if not entry_id:
        raise ValueError("缺少参数 entry_id")

    entry = (
        await session.execute(
            select(Entry).where(Entry.id == int(entry_id), Entry.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if entry is None:
        raise ValueError(f"条目 {entry_id} 不存在")

    changed: list[str] = []
    if isinstance(args.get("title"), str) and args["title"].strip():
        entry.title = args["title"].strip()[:200]
        changed.append("title")
    if isinstance(args.get("content"), dict):
        entry.content = {**(entry.content or {}), **args["content"]}
        changed.append("content")
    if isinstance(args.get("custom_fields"), dict):
        entry.custom_fields = {**(entry.custom_fields or {}), **args["custom_fields"]}
        changed.append("custom_fields")
    if isinstance(args.get("seo"), dict):
        entry.seo = {**(entry.seo or {}), **args["seo"]}
        changed.append("seo")
    if isinstance(args.get("slug"), str) and args["slug"].strip():
        entry.slug = args["slug"].strip()[:120]
        changed.append("slug")

    if not changed:
        raise ValueError("没有可更新的字段")

    await session.commit()
    logger.info("mcp.entry_updated", entry_id=entry.id, fields=changed)
    return {"entry_id": entry.id, "updated_fields": changed, "status": entry.status}


async def _publish_entry(session: AsyncSession, args: dict[str, Any]) -> Any:
    _require_write()
    entry_id = args.get("entry_id")
    if not entry_id:
        raise ValueError("缺少参数 entry_id")

    entry = (
        await session.execute(
            select(Entry).where(Entry.id == int(entry_id), Entry.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if entry is None:
        raise ValueError(f"条目 {entry_id} 不存在")

    from datetime import UTC, datetime

    entry.status = "published"
    entry.published_at = entry.published_at or datetime.now(UTC)
    await session.commit()
    logger.info("mcp.entry_published", entry_id=entry.id)
    # [P2C] Agent 自己调用的发布会走另一条路径，事件必须补上
    try:
        from cenkor_admin.core.hooks import dispatch as _dispatch

        await _dispatch("entry.published", entry=entry, db=session, user=None)
    except Exception as _de:  # noqa: BLE001
        logger.warning("mcp.publish_dispatch_failed", error=str(_de))
    return {"entry_id": entry.id, "status": "published"}


async def _create_content_type(session: AsyncSession, args: dict[str, Any]) -> Any:
    _require_write()
    description = str(args.get("description") or "").strip()
    if len(description) < 4:
        raise ValueError("请描述要管理什么内容、有哪些字段")

    spec = await copilot.propose_content_type(
        session,
        description,
        locale=str(args.get("locale") or "zh-CN"),
    )

    # 默认只返回草案。confirm=true 才真的建，避免 Agent 自作主张改 schema
    if not bool(args.get("confirm", False)):
        spec["_note"] = "这是草案，未落库。确认无误后带 confirm=true 再调一次即可创建。"
        return spec

    ct = await copilot.apply_content_type(session, spec)
    return {"created": True, "id": ct.id, "key": ct.key, "name": ct.name}


async def _translate_entry(session: AsyncSession, args: dict[str, Any]) -> Any:
    _require_write()
    entry_id = args.get("entry_id")
    langs = args.get("langs")
    if not entry_id or not isinstance(langs, list) or not langs:
        raise ValueError("需要 entry_id 与 langs（语言代码数组）")

    entry = (
        await session.execute(
            select(Entry).where(Entry.id == int(entry_id), Entry.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if entry is None:
        raise ValueError(f"条目 {entry_id} 不存在")

    return await copilot.translate_entry(
        session, entry, [str(lg) for lg in langs], overwrite=bool(args.get("overwrite", False))
    )


async def _ai_draft_entry(session: AsyncSession, args: dict[str, Any]) -> Any:
    """AI 起草：只返回草稿内容，不落库（落库请用 cms_create_entry）。"""
    ct_key = str(args.get("content_type_key") or "").strip()
    brief = str(args.get("brief") or "").strip()
    if not ct_key or not brief:
        raise ValueError("需要 content_type_key 与 brief（素材/大纲）")

    ct = (
        await session.execute(select(ContentType).where(ContentType.key == ct_key))
    ).scalar_one_or_none()
    if ct is None:
        raise ValueError(f"内容类型 {ct_key} 不存在")

    draft = await copilot.draft_entry(session, ct.id, brief, lang=str(args.get("lang") or "zh-CN"))
    await session.commit()
    return draft


def _require_write() -> None:
    if not getattr(get_settings(), "MCP_ALLOW_WRITE", True):
        raise PermissionError("MCP 写操作已被禁用（MCP_ALLOW_WRITE=false），当前为只读模式")


# ---------------------------------------------------------------------------
# 工具注册表
# ---------------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
        "name": "cms_list_content_types",
        "description": "列出这个 CMS 里所有内容类型（内容模型），返回 key、名称、字段数量。"
        "不确定有哪些内容时先调这个。",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "handler": _list_content_types,
        "readonly": True,
    },
    {
        "name": "cms_describe_content_type",
        "description": "查看某个内容类型的完整字段定义（字段名、类型、是否必填、可选值）。"
        "创建条目之前必须先调它确认字段。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "内容类型 key，如 customer_case"}
            },
            "required": ["key"],
        },
        "handler": _describe_content_type,
        "readonly": True,
    },
    {
        "name": "cms_search_content",
        "description": "按语义搜索内容。不需要精确关键词，用自然语言描述想找什么即可"
        "（例：'帮客户省电的制造业案例'）。返回按相关度排序的条目列表和摘要片段。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "自然语言查询"},
                "content_type_key": {"type": "string", "description": "限定内容类型（可选）"},
                "limit": {"type": "integer", "description": "返回条数，默认 10", "default": 10},
                "lang": {
                    "type": "string",
                    "description": "检索语言，base 为原文，或 zh-CN / en-US 等",
                    "default": "base",
                },
                "include_drafts": {
                    "type": "boolean",
                    "description": "是否包含草稿，默认 false（只看已发布）",
                    "default": False,
                },
            },
            "required": ["query"],
        },
        "handler": _search_content,
        "readonly": True,
    },
    {
        "name": "cms_get_entry",
        "description": "按 entry_id 或 slug 取单条内容的完整正文与自定义字段。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entry_id": {"type": "integer"},
                "slug": {"type": "string"},
                "content_type_key": {"type": "string", "description": "配合 slug 使用时消歧"},
            },
            "required": [],
        },
        "handler": _get_entry,
        "readonly": True,
    },
    {
        "name": "cms_create_content_type",
        "description": "用一句自然语言描述，创建新的内容类型（内容模型）。"
        "默认只返回草案不落库；确认后带 confirm=true 再调一次才会真正创建。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "业务描述，说明要管什么内容、有哪些字段",
                },
                "locale": {"type": "string", "default": "zh-CN"},
                "confirm": {
                    "type": "boolean",
                    "default": False,
                    "description": "为 true 才真正创建",
                },
            },
            "required": ["description"],
        },
        "handler": _create_content_type,
        "readonly": False,
    },
    {
        "name": "cms_ai_draft_entry",
        "description": "让 AI 根据素材/大纲起草一条内容（不落库，返回草稿 JSON）。"
        "拿到草稿后可用 cms_create_entry 落库。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content_type_key": {"type": "string"},
                "brief": {"type": "string", "description": "素材或大纲"},
                "lang": {"type": "string", "default": "zh-CN"},
            },
            "required": ["content_type_key", "brief"],
        },
        "handler": _ai_draft_entry,
        "readonly": False,
    },
    {
        "name": "cms_create_entry",
        "description": "新建一条内容草稿。注意：只能创建草稿（draft），发布需调 cms_publish_entry。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content_type_key": {"type": "string"},
                "title": {"type": "string"},
                "slug": {"type": "string"},
                "content": {"type": "object", "description": "正文结构，如 {summary, body}"},
                "custom_fields": {"type": "object", "description": "自定义字段键值对"},
                "seo": {"type": "object"},
            },
            "required": ["content_type_key", "title"],
        },
        "handler": _create_entry,
        "readonly": False,
    },
    {
        "name": "cms_update_entry",
        "description": "更新已有内容的字段。传入的 content/custom_fields/seo 会与现有值合并，不是整体替换。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entry_id": {"type": "integer"},
                "title": {"type": "string"},
                "slug": {"type": "string"},
                "content": {"type": "object"},
                "custom_fields": {"type": "object"},
                "seo": {"type": "object"},
            },
            "required": ["entry_id"],
        },
        "handler": _update_entry,
        "readonly": False,
    },
    {
        "name": "cms_translate_entry",
        "description": "把一条内容翻译成指定语言（AI 翻译，保留结构和 markdown），译文以草稿存入。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entry_id": {"type": "integer"},
                "langs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": '如 ["en-US","ja-JP"]',
                },
                "overwrite": {"type": "boolean", "default": False},
            },
            "required": ["entry_id", "langs"],
        },
        "handler": _translate_entry,
        "readonly": False,
    },
    {
        "name": "cms_publish_entry",
        "description": "发布一条草稿内容，使其对公众可见。",
        "inputSchema": {
            "type": "object",
            "properties": {"entry_id": {"type": "integer"}},
            "required": ["entry_id"],
        },
        "handler": _publish_entry,
        "readonly": False,
    },
]

TOOL_MAP: dict[str, dict[str, Any]] = {t["name"]: t for t in TOOLS}


def tool_catalog() -> list[dict[str, Any]]:
    """给 tools/list 用的纯净版（去掉 handler 这种不可序列化字段）。"""
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "inputSchema": t["inputSchema"],
            "annotations": {"readOnlyHint": t["readonly"]},
        }
        for t in TOOLS
    ]


async def call_tool(session: AsyncSession, name: str, arguments: dict[str, Any]) -> str:
    """执行工具，返回给模型看的文本。异常向上抛，由 server 层包成 isError。"""
    tool = TOOL_MAP.get(name)
    if tool is None:
        raise ValueError(f"未知工具：{name}")

    handler: Callable[..., Any] = tool["handler"]
    result = await handler(session, arguments or {})
    try:
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        return str(result)


__all__ = ["TOOLS", "TOOL_MAP", "LLMNotConfiguredError", "call_tool", "tool_catalog"]
