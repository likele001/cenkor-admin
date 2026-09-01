"""钩子内省接口：后台可视化已注册的插件处理器。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.core.hooks import registry

router = APIRouter()


@router.get("/hooks", tags=["hooks"])
async def list_registered_hooks(
    current: auth_models.User = Depends(get_current_user),
) -> dict:
    """列出当前进程内所有已注册的钩子及其处理器（按 App 分组）。"""
    return {"hooks": registry.all_hooks()}
