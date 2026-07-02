"""API 路由聚合"""
from fastapi import APIRouter, Depends

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.api.v1 import dashboard as dashboard_module
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.auth.api_key_router import router as api_key_router
from cenkor_admin.apps.auth.router import router as auth_router
from cenkor_admin.apps.auth.schemas import UserBrief
from cenkor_admin.apps.cms.router import router as cms_router
from cenkor_admin.apps.cms.content_engine_router import router as content_engine_router
from cenkor_admin.apps.cms.public_router import router as cms_public_router
from cenkor_admin.apps.cms.template_router import router as template_router
from cenkor_admin.apps.notification.router import router as notification_router
from cenkor_admin.apps.portal.router import router as portal_router
from cenkor_admin.apps.rbac.router import router as rbac_router
from cenkor_admin.apps.system.router import router as system_router

api_v1_router = APIRouter()

# 公开接口（公网站点）
api_v1_router.include_router(cms_public_router, prefix="/public", tags=["public"])
api_v1_router.include_router(portal_router, prefix="/public/portal", tags=["portal"])

# 鉴权
api_v1_router.include_router(auth_router, prefix="/auth", tags=["auth"])

# Dashboard（受保护）
api_v1_router.include_router(
    dashboard_module.router, prefix="/dashboard", tags=["dashboard"],
    dependencies=[Depends(get_current_user)],
)

# 通知（受保护）
api_v1_router.include_router(
    notification_router, prefix="/notifications", tags=["notifications"],
    dependencies=[Depends(get_current_user)],
)

# API Key（受保护）
api_v1_router.include_router(
    api_key_router, prefix="/api-keys", tags=["api-keys"],
    dependencies=[Depends(get_current_user)],
)

# 业务 App 路由（受保护）— 旧路由优先，避免被 V2 兼容路由覆盖
api_v1_router.include_router(
    cms_router, prefix="/cms", tags=["cms"],
    dependencies=[Depends(get_current_user)],
)
api_v1_router.include_router(
    rbac_router, prefix="/rbac", tags=["rbac"],
    dependencies=[Depends(get_current_user)],
)
api_v1_router.include_router(
    system_router, prefix="/system", tags=["system"],
    dependencies=[Depends(get_current_user)],
)

# V2 内容引擎（受保护）— 后注册，不覆盖旧 API
api_v1_router.include_router(
    content_engine_router, prefix="/cms", tags=["content-engine"],
    dependencies=[Depends(get_current_user)],
)
api_v1_router.include_router(
    template_router, prefix="/cms", tags=["templates"],
    dependencies=[Depends(get_current_user)],
)


# /me 放在这里（避免循环）
@api_v1_router.get("/auth/me", response_model=UserBrief, tags=["auth"])
async def me(user: auth_models.User = Depends(get_current_user)):
    """当前用户信息（含权限 + 菜单）"""
    from cenkor_admin.apps.auth.router import _build_user_brief
    return _build_user_brief(user)
