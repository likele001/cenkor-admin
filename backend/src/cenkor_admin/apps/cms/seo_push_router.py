"""收录推送 API。"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms import seo_push_service as svc
from cenkor_admin.core.db import get_db
from cenkor_admin.core.site_scope import require_site_id

router = APIRouter(prefix="/seo", tags=["cms-seo-push"])


class PushIn(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=200)
    engine: Literal["indexnow", "baidu"] = "indexnow"
    # 手动补推默认立即跑一轮，否则用户点了看不到任何变化
    run_now: bool = True


@router.post("/push", summary="把 URL 加入收录推送队列")
async def push(
    body: PushIn,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    site_id = require_site_id()
    added = await svc.enqueue(db, site_id, body.urls, body.engine)
    ran = await svc.process_pending(db, limit=20) if body.run_now else {}
    return {"queued": added, "skipped_duplicate": len(body.urls) - added, "run": ran}


@router.get("/push/stats", summary="推送队列状态")
async def push_stats(
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    site_id = require_site_id()
    return await svc.stats(db, site_id)
