"""模型变更影响分析。

## 为什么需要

内容类型的字段定义（`cms_field_definitions`）是「模型 schema」。
运营想改个字段类型（比如 price 从 text 改成 number）、或删掉一个不再用的字段时，
**没有人告诉他会炸掉多少条已经上线的内容** —— 改完前端一渲染，
线上立刻报类型错误，而那时候数据已经写坏了。

所以：改之前先算清楚。

## 产出三件事

1. **影响面**：多少条条目带这个字段（已发布 / 草稿分列）—— 决定要不要发公告
2. **兼容性**：把旧值按新类型逐条跑 `validate_field_value`，
   有多少条**真的会坏**（不是「可能会坏」）—— 决定要不要先跑数据迁移
3. **残留数据**：删字段后有多少值会变成孤儿（躺在 custom_fields 里没人认领）

## 为什么不猜

判定用的是项目自己的 `validate_field_value`（`field_types.py`），
不是另写一套规则 —— 规则改了，这里自动跟着改，不会出现「分析说没事、运行时报错」。
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.field_types import (
    ARRAY_VALUE_TYPES,
    FIELD_DEFAULTS,
    FIELD_TYPES,
    SINGLE_VALUE_TYPES,
    validate_field_value,
)
from cenkor_admin.apps.cms.models import Entry, FieldDefinition

# 单条内容里 custom_fields 的最大遍历深度（与 embedding._collect_strings 同量级）
_MAX_VALUE_DEPTH = 6


def _values_of(raw: Any, key: str, depth: int = 0) -> list[Any]:
    """取出某条目里指定 key 的所有值。

    custom_fields 是自由 JSON，同一个 key 可能出现在嵌套结构里
    （repeater 的每行、json 里再套一层），所以要递归找而不是只取顶层。
    """
    out: list[Any] = []
    if depth > _MAX_VALUE_DEPTH:
        return out
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k == key:
                out.append(v)
            else:
                out.extend(_values_of(v, key, depth + 1))
    elif isinstance(raw, list):
        for v in raw:
            out.extend(_values_of(v, key, depth + 1))
    return out


def _is_empty(v: Any) -> bool:
    """空值不算「有数据」：'' / None / [] / {} 都算空。"""
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return bool(isinstance(v, (list, dict, tuple, set)) and len(v) == 0)


def _type_family(field_type: str) -> str:
    """把 22 种字段类型归成几个「数据形状」族，用于判断改造是否破坏数据形状。"""
    if field_type in SINGLE_VALUE_TYPES:
        return "single"
    if field_type in ARRAY_VALUE_TYPES:
        return "array"
    return "single"


def _compatibility_note(old_type: str, new_type: str) -> str:
    """给人看的一句话结论。"""
    if old_type == new_type:
        return "类型未变，无影响"
    if _type_family(old_type) == _type_family(new_type):
        return "数据形状兼容（单值↔单值 / 数组↔数组），仅取值校验可能受影响"
    return "数据形状不兼容（单值↔数组），旧数据需先迁移"


async def field_impact(
    session: AsyncSession,
    content_type_id: int,
    field_key: str,
    *,
    target_field_type: str | None = None,
    sample_limit: int = 5,
) -> dict[str, Any]:
    """分析某个字段定义被改/删时的影响面。

    target_field_type=None 表示「删除该字段」；
    给出目标类型则分析「改成该类型」的兼容性。
    """
    fd = (
        await session.execute(
            select(FieldDefinition).where(
                FieldDefinition.content_type_id == content_type_id,
                FieldDefinition.field_key == field_key,
            )
        )
    ).scalar_one_or_none()
    if fd is None:
        return {"found": False, "field_key": field_key, "reason": "字段定义不存在"}

    old_type = fd.field_type
    new_type = target_field_type or old_type

    # 1) 影响面：该内容类型下带这个 key 的条目
    rows = (
        await session.execute(
            select(
                Entry.id,
                Entry.status,
                Entry.title,
                Entry.custom_fields,
            ).where(
                Entry.content_type_id == content_type_id,
                Entry.deleted_at.is_(None),
            )
        )
    ).all()

    published_with = 0
    draft_with = 0
    published_total = 0
    broken: list[dict[str, Any]] = []
    with_value = 0
    empty_value = 0

    for eid, status, title, cf in rows:
        if status == "published":
            published_total += 1
        values = _values_of(cf or {}, field_key)
        real = [v for v in values if not _is_empty(v)]
        if not real:
            if values:
                empty_value += 1
            continue

        with_value += 1
        if status == "published":
            published_with += 1
        else:
            draft_with += 1

        # 2) 兼容性：把旧值按新类型逐条校验
        if old_type != new_type:
            for v in real:
                errs = validate_field_value(new_type, v, fd.validation)
                if errs:
                    broken.append(
                        {
                            "entry_id": eid,
                            "title": title or "",
                            "status": status,
                            "sample_value": str(v)[:120],
                            "errors": errs[:3],
                        }
                    )
                    break  # 一条条目只记一次

    severity = "none"
    if old_type != new_type and broken:
        severity = "breaking"
    elif published_with:
        severity = "notice"
    elif draft_with:
        severity = "draft_only"

    out: dict[str, Any] = {
        "found": True,
        "content_type_id": content_type_id,
        "field_key": field_key,
        "field_label": fd.label,
        "old_field_type": old_type,
        "new_field_type": new_type,
        "action": "update" if target_field_type else "delete",
        "severity": severity,
        "compatibility": _compatibility_note(old_type, new_type),
        "impact": {
            "entries_total": len(rows),
            "entries_published_total": published_total,
            "entries_with_value": with_value,
            "published_with_value": published_with,
            "draft_with_value": draft_with,
            "empty_value_entries": empty_value,
        },
        "broken_count": len(broken),
        "broken_samples": broken[:sample_limit],
        "message": _build_message(
            action="delete" if not target_field_type else "update",
            old_type=old_type,
            new_type=new_type,
            published_with=published_with,
            broken=len(broken),
        ),
    }
    logger.info(
        "cms.schema_impact field={} old={} new={} published={} broken={}",
        field_key, old_type, new_type, published_with, len(broken),
    )
    return out


def _build_message(
    *, action: str, old_type: str, new_type: str, published_with: int, broken: int
) -> str:
    if action == "delete":
        if published_with == 0:
            return f"删除该字段不影响任何已发布内容（{published_with} 条已发布内容使用该字段）"
        return (
            f"删除该字段将影响 {published_with} 条已发布内容，"
            f"这些内容的 {old_type} 值会变成无人认领的残留数据"
        )
    if broken:
        return (
            f"把字段类型从 {old_type} 改成 {new_type} 会破坏 {broken} 条已有数据，"
            f"其中 {published_with} 条已发布内容用到该字段 —— 建议先跑数据迁移"
        )
    if published_with:
        return (
            f"把字段类型从 {old_type} 改成 {new_type} 不会破坏现有数据"
            f"（{published_with} 条已发布内容使用该字段）"
        )
    return f"把字段类型从 {old_type} 改成 {new_type} 没有已发布内容受影响"


async def content_type_impact(
    session: AsyncSession,
    content_type_id: int,
    *,
    target_field_type: str | None = None,
) -> dict[str, Any]:
    """整个内容类型的字段全景：逐字段列出影响面（改 schema 前的总览）。"""
    fds = (
        await session.execute(
            select(FieldDefinition).where(
                FieldDefinition.content_type_id == content_type_id,
                FieldDefinition.status == "active",
            )
        )
    ).scalars().all()

    entries_total = (
        await session.execute(
            select(func.count())
            .select_from(Entry)
            .where(
                Entry.content_type_id == content_type_id,
                Entry.deleted_at.is_(None),
            )
        )
    ).scalar() or 0
    published_total = (
        await session.execute(
            select(func.count())
            .select_from(Entry)
            .where(
                Entry.content_type_id == content_type_id,
                Entry.deleted_at.is_(None),
                Entry.status == "published",
            )
        )
    ).scalar() or 0

    fields: list[dict[str, Any]] = []
    for fd in fds:
        r = await field_impact(
            session,
            content_type_id,
            fd.field_key,
            target_field_type=target_field_type,
            sample_limit=3,
        )
        if r.get("found"):
            fields.append(
                {
                    "field_key": r["field_key"],
                    "field_label": r["field_label"],
                    "field_type": r["old_field_type"],
                    "published_with_value": r["impact"]["published_with_value"],
                    "draft_with_value": r["impact"]["draft_with_value"],
                    "broken_count": r["broken_count"],
                }
            )

    return {
        "content_type_id": content_type_id,
        "entries_total": entries_total,
        "entries_published": published_total,
        "field_count": len(fields),
        "fields": fields,
    }


__all__ = [
    "FIELD_DEFAULTS",
    "FIELD_TYPES",
    "content_type_impact",
    "field_impact",
]
