"""页面级 A/B 实验管理。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms import models
from cenkor_admin.apps.cms.ab_models import AbTest
from cenkor_admin.core.db import get_db
from cenkor_admin.core.site_scope import require_site_id

router = APIRouter(prefix="/ab", tags=["cms-ab"])


class CreateIn(BaseModel):
    entry_id: int
    name: str = Field(default="", max_length=120)
    weight: int = Field(default=50, ge=0, le=100)
    variant_b: dict[str, Any] = Field(default_factory=dict)


def _row(t: AbTest) -> dict[str, Any]:
    total = (t.views_a or 0) + (t.views_b or 0)
    return {
        "id": t.id,
        "entry_id": t.entry_id,
        "name": t.name,
        "weight": t.weight,
        "status": t.status,
        "views_a": t.views_a,
        "views_b": t.views_b,
        "total": total,
        "share_b": round((t.views_b or 0) / total * 100, 2) if total else 0.0,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "stopped_at": t.stopped_at.isoformat() if t.stopped_at else None,
    }


@router.get("", summary="A/B 实验列表")
async def list_tests(
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    rows = (
        await db.execute(select(AbTest).order_by(AbTest.id.desc()).limit(200))
    ).scalars().all()
    return {"items": [_row(t) for t in rows], "running": sum(1 for t in rows if t.status == "running")}


@router.post("", summary="新建实验（同一页只能有一个 running）")
async def create_test(
    body: CreateIn,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    site_id = require_site_id()
    entry = (
        await db.execute(
            select(models.Entry).where(
                models.Entry.id == body.entry_id, models.Entry.deleted_at.is_(None)
            )
        )
    ).scalars().first()
    if entry is None:
        raise HTTPException(404, "条目不存在")
    running = (
        await db.execute(
            select(AbTest).where(AbTest.entry_id == body.entry_id, AbTest.status == "running")
        )
    ).scalars().first()
    if running is not None:
        raise HTTPException(409, f"该页已有运行中的实验 #{running.id}，先停掉")
    if not body.variant_b:
        raise HTTPException(422, "variant_b 不能为空，至少给一份替换内容")
    test = AbTest(
        site_id=site_id,
        entry_id=body.entry_id,
        name=body.name or f"entry-{body.entry_id}",
        variant_b=body.variant_b,
        weight=body.weight,
    )
    db.add(test)
    await db.commit()
    await db.refresh(test)
    return _row(test)


@router.post("/{test_id}/stop", summary="停止实验")
async def stop_test(
    test_id: int,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    test = (await db.execute(select(AbTest).where(AbTest.id == test_id))).scalars().first()
    if test is None:
        raise HTTPException(404, "实验不存在")
    test.status = "stopped"
    test.stopped_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(test)
    return _row(test)


@router.delete("/{test_id}", summary="删除实验（历史曝光一并清掉）")
async def delete_test(
    test_id: int,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    test = (await db.execute(select(AbTest).where(AbTest.id == test_id))).scalars().first()
    if test is None:
        raise HTTPException(404, "实验不存在")
    await db.delete(test)
    await db.commit()
    return {"deleted": test_id}
