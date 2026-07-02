"""API 路由聚合 — 核心路由手动注册 + App 路由自动发现"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

from fastapi import APIRouter, Depends
from structlog import get_logger

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
from cenkor_admin.apps.portal.admin_router import router as portal_admin_router
from cenkor_admin.apps.rbac.router import router as rbac_router
from cenkor_admin.apps.system.router import router as system_router, public_router as system_public_router

log = get_logger(__name__)

api_v1_router = APIRouter()

# ============================================================
# 公开接口
# ============================================================
api_v1_router.include_router(cms_public_router, prefix="/public", tags=["public"])
api_v1_router.include_router(portal_router, prefix="/public/portal", tags=["portal"])

# ============================================================
# 鉴权
# ============================================================
api_v1_router.include_router(auth_router, prefix="/auth", tags=["auth"])

# ============================================================
# 核心平台路由（受保护）
# ============================================================
api_v1_router.include_router(
    dashboard_module.router, prefix="/dashboard", tags=["dashboard"],
    dependencies=[Depends(get_current_user)],
)
api_v1_router.include_router(
    notification_router, prefix="/notifications", tags=["notifications"],
    dependencies=[Depends(get_current_user)],
)
api_v1_router.include_router(
    api_key_router, prefix="/api-keys", tags=["api-keys"],
    dependencies=[Depends(get_current_user)],
)

# 旧 CMS 路由（优先注册，避免被 V2 覆盖）
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

# 系统公开路由（无需鉴权）— 供前端 PluginManager 在未登录时也能加载插件列表
api_v1_router.include_router(
    system_public_router, prefix="/system", tags=["system-public"],
)

# V2 内容引擎
api_v1_router.include_router(
    content_engine_router, prefix="/cms", tags=["content-engine"],
    dependencies=[Depends(get_current_user)],
)
api_v1_router.include_router(
    template_router, prefix="/cms", tags=["templates"],
    dependencies=[Depends(get_current_user)],
)

# Portal 后台管理
api_v1_router.include_router(
    portal_admin_router, prefix="/portal-admin", tags=["portal-admin"],
    dependencies=[Depends(get_current_user)],
)


# ============================================================
# App 路由自动发现
# ============================================================
# 扫描所有已安装 App 的 router.py，自动挂载到 /{app_key}/
# 开发者只需在 manifest 中声明 api_prefix（默认取 app key）

def _app_router_is_registered(app_key: str) -> bool:
    prefix = f"/{app_key}"
    return any(getattr(r, 'path', '') == prefix for r in api_v1_router.routes)


def _clear_app_module_cache(app_key: str) -> None:
    """安装/更新 App 后仅清除 router 模块缓存，避免 models 重复注册。"""
    for name in (
        f"cenkor_admin.apps.{app_key}.router",
        f"app_routers.{app_key}.router",
    ):
        sys.modules.pop(name, None)


def _load_app_router_module(app_key: str, router_file: Path, *, external: bool = False):
    """加载 App 的 router 模块。"""
    if not external:
        try:
            return importlib.import_module(f"cenkor_admin.apps.{app_key}.router")
        except (ImportError, ModuleNotFoundError):
            pass

    spec = importlib.util.spec_from_file_location(
        f"app_routers.{app_key}.router", router_file
    )
    if not spec or not spec.loader:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def register_app_router(app_key: str) -> bool:
    """动态注册单个 App 路由（商店安装后无需重启）。"""
    from cenkor_admin import apps as apps_pkg

    apps_dir = Path(apps_pkg.__path__[0])
    router_file = apps_dir / app_key / "router.py"
    external = False
    if not router_file.exists():
        external_dir = apps_dir.parent.parent / "apps"
        router_file = external_dir / app_key / "router.py"
        if not router_file.exists():
            return False
        external = True

    if _app_router_is_registered(app_key):
        return True

    _clear_app_module_cache(app_key)
    try:
        module = _load_app_router_module(app_key, router_file, external=external)
        if module is None or not hasattr(module, "router"):
            log.warning("app.route_register_no_router", key=app_key)
            return False

        prefix = f"/{app_key}"
        api_v1_router.include_router(
            module.router,
            prefix=prefix,
            tags=[app_key],
            dependencies=[Depends(get_current_user)],
        )
        log.info("app.route_registered", key=app_key, prefix=prefix)
        return True
    except Exception as exc:
        log.warning("app.route_register_failed", key=app_key, error=str(exc))
        return False


def _auto_register_app_routers() -> None:
    """扫描 App 目录下所有 router.py，自动注册到 API 路由。"""
    from cenkor_admin import apps as apps_pkg
    apps_dir = Path(apps_pkg.__path__[0])
    _discover_and_register(apps_dir)

    external_dir = apps_dir.parent.parent / "apps"
    if external_dir.exists():
        _discover_and_register(external_dir)


def _discover_and_register(apps_dir: Path) -> None:
    """扫描单个 App 目录并注册路由。"""
    for item in sorted(apps_dir.iterdir()):
        if item.name.startswith("_") or not item.is_dir():
            continue
        if not (item / "router.py").exists():
            continue
        register_app_router(item.name)


_auto_register_app_routers()


# ============================================================
# 应用商店路由（不受 /system 的 admin-only 限制）
# ============================================================
from cenkor_admin.apps.system.store_router import router as store_router  # noqa: E402
api_v1_router.include_router(store_router, prefix="/store", tags=["app-store"])

# ============================================================
# /me
# ============================================================
@api_v1_router.get("/auth/me", response_model=UserBrief, tags=["auth"])
async def me(user: auth_models.User = Depends(get_current_user)):
    """当前用户信息（含权限 + 菜单）"""
    from cenkor_admin.apps.auth.router import _build_user_brief
    return _build_user_brief(user)
