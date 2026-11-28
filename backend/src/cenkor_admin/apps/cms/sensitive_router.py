"""敏感词库 API：维护词表 + 文本预检。"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms import sensitive_service as svc
from cenkor_admin.apps.cms.sensitive_models import SensitiveWord
from cenkor_admin.core.db import get_db
from cenkor_admin.core.site_scope import require_site_id

router = APIRouter(prefix="/sensitive-words", tags=["cms-sensitive"])


class WordIn(BaseModel):
    word: str = Field(min_length=1, max_length=120)
    level: Literal["block", "warn"] = "warn"
    scope: Literal["site", "global"] = "site"


class CheckIn(BaseModel):
    text: str = Field(max_length=20000)


def _out(w: SensitiveWord) -> dict[str, Any]:
    return {
        "id": w.id,
        "word": w.word,
        "level": w.level,
        "scope": w.scope,
        "site_id": w.site_id,
    }


@router.get("", summary="当前站点可见的敏感词（含全站词）")
async def list_words(
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    site_id = require_site_id()
    return [_out(w) for w in await svc.list_words(db, site_id)]


@router.post("", status_code=201, summary="新增敏感词")
async def add_word(
    body: WordIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    scope_site = require_site_id() if body.scope == "site" else None
    word = body.word.strip()
    if not word:
        raise HTTPException(422, "词不能为空")

    dup = (
        await db.execute(
            select(SensitiveWord.id).where(
                SensitiveWord.scope == body.scope,
                SensitiveWord.site_id == scope_site,
                func.lower(SensitiveWord.word) == word.lower(),
            )
        )
    ).scalar()
    if dup:
        raise HTTPException(409, "该词已存在")

    row = SensitiveWord(
        site_id=scope_site, scope=body.scope, word=word, level=body.level,
        created_by=getattr(user, "id", None),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _out(row)


@router.delete("/{word_id}", summary="删除敏感词")
async def delete_word(
    word_id: int,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    row = await db.get(SensitiveWord, word_id)
    if row is None:
        raise HTTPException(404, "词不存在")
    await db.delete(row)
    await db.commit()
    return {"deleted": word_id}


@router.post("/check", summary="文本预检（不落库）")
async def check(
    body: CheckIn,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    site_id = require_site_id()
    return await svc.check_text(db, site_id, body.text)
