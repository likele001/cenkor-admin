"""AI 提示词管理 · 版本化 / 对比 / 回滚

端点：
    GET    /ai/prompts                     各 key 的生效版本概览（含是否偏离出厂默认）
    GET    /ai/prompts/{key}               该 key 的全部历史版本
    POST   /ai/prompts/{key}               新建版本（可立即激活）
    POST   /ai/prompts/{key}/{ver}/activate 激活指定版本
    GET    /ai/prompts/{key}/diff          两版对比（unified diff）
    POST   /ai/prompts/{key}/reset         恢复出厂默认（把代码常量存为新版本）

权限：读 cms:ai:read，写 cms:ai:manage —— 与「AI 服务商/能力」同档，
因为改提示词和改模型一样会改变全站产出。

写入后调 prompt_registry.invalidate()，下一请求即生效（单进程）。
"""

from __future__ import annotations

import difflib
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms.ai import prompt_registry
from cenkor_admin.apps.cms.ai import copilot
from cenkor_admin.apps.cms.ai.models import CmsAiPrompt
from cenkor_admin.core.db import get_db

router = APIRouter(tags=["cms-ai-prompt"])


# ---------------------------------------------------------------- 出厂默认


def _factory_default(key: str) -> str | None:
    """代码里的常量。这是「恢复出厂」的来源。"""
    return {
        "ct": copilot._CT_SYSTEM,
        "draft": copilot._DRAFT_SYSTEM,
        "draft_stream": copilot._DRAFT_STREAM_SYSTEM,
        "draft_extra": copilot._DRAFT_EXTRA_SYSTEM,
        "translate": copilot._TRANSLATE_SYSTEM,
        "seo": copilot._SEO_SYSTEM,
        "rewrite": copilot._REWRITE_SYSTEM,
        "auto_tag": copilot._AUTO_TAG_SYSTEM,
        "internal_link": _internal_link_system(),
        "redistribute": _redistribute_system(),
        "qa_ask": _qa_ask_system(),
        "topic_gap": _topic_gap_system(),
        "ab_run": _ab_run_system(),
        "illustration": _illustration_system(),
    }.get(key)


def _internal_link_system() -> str:
    """内链建议的出厂提示词（在独立模块里，避免 copilot.py 继续膨胀）。"""
    from cenkor_admin.apps.cms.ai.internal_link import _INTERNAL_LINK_SYSTEM

    return _INTERNAL_LINK_SYSTEM


def _redistribute_system() -> str:
    """多渠道再分发的出厂提示词。"""
    from cenkor_admin.apps.cms.ai.redistribute import _REDISTRIBUTE_SYSTEM

    return _REDISTRIBUTE_SYSTEM


def _qa_ask_system() -> str:
    """问答式站内搜索的出厂提示词。"""
    from cenkor_admin.apps.cms.ai.qa_search import _ASK_SYSTEM

    return _ASK_SYSTEM


def _topic_gap_system() -> str:
    """选题 Gap 分析的出厂提示词。"""
    from cenkor_admin.apps.cms.ai.topic_gap import _GAP_SYSTEM

    return _GAP_SYSTEM


def _ab_run_system() -> str:
    """模型 A/B 起草的出厂提示词。"""
    from cenkor_admin.apps.cms.ai.quality import _AB_SYSTEM

    return _AB_SYSTEM


def _illustration_system() -> str:
    """AI 配图的出厂提示词（正文 → 画面描述）。"""
    from cenkor_admin.apps.cms.ai.illustration import _ILLUSTRATION_SYSTEM

    return _ILLUSTRATION_SYSTEM


def _known_keys() -> list[str]:
    return list(prompt_registry.PROMPT_LABELS)


# ---------------------------------------------------------------- schemas


class PromptOverview(BaseModel):
    key: str
    label: str
    active_version: int | None = None
    note: str | None = None
    updated_at: Any = None
    # 生效内容与出厂默认是否一致 —— 概览页用来提示「这个被改过」
    differs_from_default: bool = False
    has_versions: bool = False


class PromptVersion(BaseModel):
    id: int
    version: int
    content: str
    note: str | None
    is_active: bool
    created_by: int | None
    created_at: Any = None


class PromptDetail(BaseModel):
    key: str
    label: str
    factory_default: str
    active_content: str
    versions: list[PromptVersion]


class NewVersionBody(BaseModel):
    content: str = Field(min_length=1, description="提示词正文")
    note: str | None = Field(default=None, max_length=255, description="本次改动说明")
    activate: bool = True


class DiffOut(BaseModel):
    key: str
    from_version: int
    to_version: int
    diff: str


# ---------------------------------------------------------------- helpers


async def _get_or_404(db: AsyncSession, key: str) -> None:
    if key not in prompt_registry.PROMPT_LABELS:
        raise HTTPException(
            status_code=404,
            detail=f"未知提示词 {key!r}，可用：{', '.join(_known_keys())}",
        )


async def _activate(db: AsyncSession, key: str, version: int) -> CmsAiPrompt:
    row = (
        await db.execute(
            select(CmsAiPrompt).where(
                CmsAiPrompt.prompt_key == key, CmsAiPrompt.version == version
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{key} v{version} 不存在")

    # 先全部置否再置是：部分唯一索引不允许两个 active 同时存在
    await db.execute(
        update(CmsAiPrompt)
        .where(CmsAiPrompt.prompt_key == key, CmsAiPrompt.is_active.is_(True))
        .values(is_active=False)
    )
    await db.flush()
    row.is_active = True
    await db.flush()
    return row


async def _next_version(db: AsyncSession, key: str) -> int:
    cur = (
        await db.execute(
            select(func.max(CmsAiPrompt.version)).where(CmsAiPrompt.prompt_key == key)
        )
    ).scalar()
    return int(cur or 0) + 1


# ---------------------------------------------------------------- 端点


@router.get("/prompts", response_model=list[PromptOverview])
async def list_prompts(
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> list[PromptOverview]:
    actives = await prompt_registry.active_versions(db)
    contents = dict(
        (
            await db.execute(
                select(CmsAiPrompt.prompt_key, CmsAiPrompt.content).where(
                    CmsAiPrompt.is_active.is_(True)
                )
            )
        ).all()
    )
    counts = dict(
        (
            await db.execute(
                select(CmsAiPrompt.prompt_key, func.count()).group_by(CmsAiPrompt.prompt_key)
            )
        ).all()
    )

    out: list[PromptOverview] = []
    for key, label in prompt_registry.PROMPT_LABELS.items():
        a = actives.get(key) or {}
        active_content = contents.get(key)
        default = _factory_default(key) or ""
        out.append(
            PromptOverview(
                key=key,
                label=label,
                active_version=a.get("version"),
                note=a.get("note"),
                updated_at=a.get("created_at"),
                has_versions=int(counts.get(key, 0)) > 0,
                differs_from_default=(
                    active_content is not None
                    and (active_content or "").strip() != (default or "").strip()
                ),
            )
        )
    return out


@router.get("/prompts/{key}", response_model=PromptDetail)
async def get_prompt(
    key: str,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> PromptDetail:
    await _get_or_404(db, key)
    rows = (
        (
            await db.execute(
                select(CmsAiPrompt)
                .where(CmsAiPrompt.prompt_key == key)
                .order_by(CmsAiPrompt.version.desc())
            )
        )
        .scalars()
        .all()
    )
    default = _factory_default(key) or ""
    active = next((r for r in rows if r.is_active), None)
    return PromptDetail(
        key=key,
        label=prompt_registry.PROMPT_LABELS[key],
        factory_default=default,
        active_content=active.content if active else default,
        versions=[
            PromptVersion(
                id=r.id,
                version=r.version,
                content=r.content,
                note=r.note,
                is_active=r.is_active,
                created_by=r.created_by,
                created_at=r.created_at,
            )
            for r in rows
        ],
    )


@router.post("/prompts/{key}", response_model=PromptVersion, status_code=status.HTTP_201_CREATED)
async def create_version(
    key: str,
    body: NewVersionBody,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> PromptVersion:
    await _get_or_404(db, key)
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="提示词不能为空")

    row = CmsAiPrompt(
        prompt_key=key,
        version=await _next_version(db, key),
        content=content,
        note=body.note,
        is_active=False,
        created_by=getattr(user, "id", None),
    )
    db.add(row)
    await db.flush()

    if body.activate:
        await _activate(db, key, row.version)

    await db.commit()
    await db.refresh(row)
    prompt_registry.invalidate(key)
    return PromptVersion(
        id=row.id,
        version=row.version,
        content=row.content,
        note=row.note,
        is_active=row.is_active,
        created_by=row.created_by,
        created_at=row.created_at,
    )


@router.post("/prompts/{key}/{version}/activate", response_model=PromptVersion)
async def activate_version(
    key: str,
    version: int,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> PromptVersion:
    await _get_or_404(db, key)
    row = await _activate(db, key, version)
    await db.commit()
    await db.refresh(row)
    prompt_registry.invalidate(key)
    return PromptVersion(
        id=row.id,
        version=row.version,
        content=row.content,
        note=row.note,
        is_active=row.is_active,
        created_by=row.created_by,
        created_at=row.created_at,
    )


@router.get("/prompts/{key}/diff", response_model=DiffOut)
async def diff_versions(
    key: str,
    from_version: int = Query(..., alias="from"),
    to_version: int = Query(..., alias="to"),
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> DiffOut:
    await _get_or_404(db, key)
    rows = (
        (
            await db.execute(
                select(CmsAiPrompt).where(
                    CmsAiPrompt.prompt_key == key,
                    CmsAiPrompt.version.in_([from_version, to_version]),
                )
            )
        )
        .scalars()
        .all()
    )
    by_ver = {r.version: r.content for r in rows}
    if from_version not in by_ver or to_version not in by_ver:
        missing = [v for v in (from_version, to_version) if v not in by_ver]
        raise HTTPException(status_code=404, detail=f"版本不存在：{missing}")

    text = "\n".join(
        difflib.unified_diff(
            by_ver[from_version].splitlines(),
            by_ver[to_version].splitlines(),
            fromfile=f"{key} v{from_version}",
            tofile=f"{key} v{to_version}",
            lineterm="",
        )
    )
    return DiffOut(
        key=key, from_version=from_version, to_version=to_version, diff=text
    )


@router.post("/prompts/{key}/reset", response_model=PromptVersion)
async def reset_to_default(
    key: str,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> PromptVersion:
    """恢复出厂默认：把代码里的常量存成一个新版本并激活。

    不删历史 —— 运营可能「手滑点了恢复」还想回滚到自己那版。
    """
    await _get_or_404(db, key)
    default = _factory_default(key)
    if not default:
        raise HTTPException(status_code=500, detail=f"{key} 没有出厂默认值")

    row = CmsAiPrompt(
        prompt_key=key,
        version=await _next_version(db, key),
        content=default,
        note="恢复出厂默认",
        is_active=False,
        created_by=getattr(user, "id", None),
    )
    db.add(row)
    await db.flush()
    await _activate(db, key, row.version)
    await db.commit()
    await db.refresh(row)
    prompt_registry.invalidate(key)
    return PromptVersion(
        id=row.id,
        version=row.version,
        content=row.content,
        note=row.note,
        is_active=row.is_active,
        created_by=row.created_by,
        created_at=row.created_at,
    )
