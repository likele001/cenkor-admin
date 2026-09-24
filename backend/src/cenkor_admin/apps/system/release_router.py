"""核心平台版本 / 升级检查路由。

- ``GET /release/latest``  公开：中心端对外声明的最新核心版本（读 release.json）。
- ``GET /release/check``   需登录：本实例检查是否有新版本（供工作台升级横幅调用）。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.system import release_service

router = APIRouter()


@router.get("/latest", response_model=dict[str, Any])
async def release_latest():
    """最新核心版本清单（公开只读，供客户实例联网检查）。"""
    return release_service.load_local_release()


@router.get("/check", response_model=dict[str, Any])
async def release_check(
    force: bool = False,
    _: auth_models.User = Depends(get_current_user),
):
    """本实例的版本检查结果。force=true 跳过缓存实时查中心。"""
    return await release_service.check_latest(force=force)
