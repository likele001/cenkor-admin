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
from cenkor_admin.apps.cms.ai.router import router as cms_ai_router
from cenkor_admin.apps.cms.content_engine_router import router as content_engine_router
from cenkor_admin.apps.cms.mcp.router import router as cms_mcp_router
from cenkor_admin.apps.cms.public_router import router as cms_public_router
from cenkor_admin.apps.cms.rbac_guard import cms_permission_guard
from cenkor_admin.apps.cms.router import router as cms_router
from cenkor_admin.apps.cms.site_router import router as cms_site_router
from cenkor_admin.apps.cms.template_router import router as template_router
from cenkor_admin.apps.cms.url_rules_router import router as cms_url_rules_router
from cenkor_admin.apps.notification.router import router as notification_router
from cenkor_admin.apps.portal.admin_router import router as portal_admin_router
from cenkor_admin.apps.portal.router import router as portal_router
from cenkor_admin.apps.rbac.router import router as rbac_router
from cenkor_admin.apps.system.router import public_router as system_public_router
from cenkor_admin.apps.system.router import router as system_router
from cenkor_admin.apps.system.webhook_router import router as webhook_router
from cenkor_admin.core.hooks_router import router as hooks_router

log = get_logger(__name__)

api_v1_router = APIRouter()

# ============================================================
# 公开接口
# ============================================================
api_v1_router.include_router(cms_public_router, prefix="/public", tags=["public"])
api_v1_router.include_router(portal_router, prefix="/public/portal", tags=["portal"])
# SSO 授权跳转与回调必须匿名（理由见 apps/sso/router.py 顶部注释）
from cenkor_admin.apps.sso.router import public_router as sso_public_router

api_v1_router.include_router(sso_public_router, prefix="/public/sso", tags=["sso"])
# M4·P3：评论 & 表单 公共接口
from cenkor_admin.apps.comments.public_router import router as comments_public_router
from cenkor_admin.apps.forms.public_router import router as forms_public_router

api_v1_router.include_router(comments_public_router, prefix="/public", tags=["comments"])
api_v1_router.include_router(forms_public_router, prefix="/public", tags=["forms"])
# M3·P2：Builder 页面公共接口
from cenkor_admin.apps.builder.public_router import router as builder_public_router

api_v1_router.include_router(builder_public_router, prefix="/public", tags=["builder"])
# 埋点采集：公开接口，勿加鉴权依赖（访客浏览器直接上报）
from cenkor_admin.apps.cms.tracking_router import router as cms_tracking_router

api_v1_router.include_router(cms_tracking_router, prefix="/public", tags=["tracking"])

# CMS 兜底路由（按后台配置的 URL 规则反解地址）
# ⚠️ 必须放在所有 public 子路由**之后**：/{full_path:path} 是通配路由，
# 排在前面会把 /public/comments、/public/forms、/public/track、/public/lp/*
# 全吃掉（表现为接口返回 CMS 的 HTML 404，且日志里一条 ERROR 都没有）。
from cenkor_admin.apps.cms.cms_fallback_router import router as cms_fallback_router

api_v1_router.include_router(cms_fallback_router, prefix="/public", tags=["public"])

# ============================================================
# 页面渲染前缀 /page
# ============================================================
# 为什么要有这个独立前缀：
#
# nginx 把站点上「静态文件没命中」的任意路径转发回后端，让后端按后台配置的
# URL 规则反解。以前它转发到 /api/v1/public$uri —— 那是 JSON 接口的地盘，
# 一旦用户把某条内容的地址配成 /site、/news、/products、/search 这类名字，
# 转发过去就会撞上同名 JSON 接口：浏览器拿到一段 JSON，状态码 200，
# 页面渲染彻底错乱，而且日志里一条错都看不到（那本来就是合法接口）。
#
# 所以页面渲染单独占一个前缀 /api/v1/page —— 里面只有页面路由和兜底反解，
# 不跟任何 JSON 接口抢名字。官网静态站读 JSON 仍然走 /api/v1/public。
from cenkor_admin.apps.cms.cms_page_router import router as cms_page_router

api_v1_router.include_router(cms_page_router, prefix="/page", tags=["page"])


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
    dependencies=[Depends(get_current_user), Depends(cms_permission_guard)],
)
# CMS AI 能力（对话式建模 / AI 起草 / 翻译 / SEO / 语义检索）
api_v1_router.include_router(
    cms_ai_router, prefix="/cms", tags=["cms-ai"],
    dependencies=[Depends(get_current_user), Depends(cms_permission_guard)],
)
# 站点管理（多站点 / 站群）：本 router 内部 bypass 站点过滤，自身要跨站
api_v1_router.include_router(
    cms_site_router, prefix="/cms", tags=["cms-sites"],
    dependencies=[Depends(get_current_user), Depends(cms_permission_guard)],
)
# CMS MCP（Agent 接入）：鉴权走 MCP_API_KEY，绝不能套登录依赖，否则 Agent 进不来
api_v1_router.include_router(cms_mcp_router, prefix="/cms", tags=["cms-mcp"])
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

# CRM 对外 Open API（API Key 鉴权，无需 JWT）— 供外部 ES/ERP 系统对接
try:
    from cenkor_admin.apps.crm.routers.openapi_router import router as crm_openapi_router
    api_v1_router.include_router(crm_openapi_router, prefix="/crm-open", tags=["crm-open"])
except Exception as e:
    log.warning("crm.openapi_mount_failed", error=str(e))

# 插件框架：已注册钩子内省（受保护）
api_v1_router.include_router(
    hooks_router, prefix="/system", tags=["hooks"],
    dependencies=[Depends(get_current_user)],
)

# M3·P2：Webhook 订阅 & URL 重定向管理（受保护）
api_v1_router.include_router(
    webhook_router, prefix="/system", tags=["webhooks-redirects"],
    dependencies=[Depends(get_current_user)],
)

# V2 内容引擎
api_v1_router.include_router(
    content_engine_router, prefix="/cms", tags=["content-engine"],
    dependencies=[Depends(get_current_user)],
)
# URL 伪静态规则管理（站点默认规则 / 预览 / 冲突检测 / 存档）
api_v1_router.include_router(
    cms_url_rules_router, prefix="/cms", tags=["cms-url-rules"],
    dependencies=[Depends(get_current_user)],
)
# GraphQL（M2·P1 2.1，受保护；REST 并存）
try:
    from cenkor_admin.apps.cms.graphql import graphql_router
    api_v1_router.include_router(
        graphql_router, prefix="/cms", tags=["graphql"],
        dependencies=[Depends(get_current_user), Depends(cms_permission_guard)],
    )
except Exception as e:
    import structlog
    structlog.get_logger().warning("graphql.mount_failed", error=str(e))
api_v1_router.include_router(
    template_router, prefix="/cms", tags=["templates"],
    dependencies=[Depends(get_current_user), Depends(cms_permission_guard)],
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
    # 必须先登记 sys.modules 再 exec：pydantic 2.11+ 按 cls.__module__ 反查命名空间，
    # 外置 App 的 router 普遍写 `from __future__ import annotations`，不登记则模型停在
    # 「待补全」，直到 /api/docs 或首次请求体校验才炸 class not fully defined。
    # _clear_app_module_cache 与本函数共用键名，卸载/更新时成对回收。
    name = f"app_routers.{app_key}.router"
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)  # 半个模块留在 sys.modules 更糟
        raise
    return module


def app_enabled_dependency(app_key: str):
    """构造「App 必须处于启用状态」的 FastAPI 依赖。

    停用应用后其下所有 API 一律 403，启用即时恢复。启用状态带 TTL 缓存
    （见 ``app_registry.is_app_enabled``），不会造成每请求查库。
    用独立 session，避免依赖与 endpoint 共用会话引发并发冲突。
    """

    async def _require_enabled() -> None:
        from fastapi import HTTPException

        from cenkor_admin.apps.system.app_registry import is_app_enabled
        from cenkor_admin.core.db import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            if not await is_app_enabled(session, app_key):
                raise HTTPException(status_code=403, detail=f"应用已停用：{app_key}")

    return _require_enabled


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
            dependencies=[
                Depends(get_current_user),
                Depends(app_enabled_dependency(app_key)),
                # cms 在上方已手动注册过一份（保留是为了让旧路由优先于 V2 匹配），
                # 自动发现这里会 getattr 到同名模块并再 import 一次，形成同路径两份。
                # 两份都必须挂守卫，否则「谁先注册谁生效」就成了隐式安全边界。
                *([Depends(cms_permission_guard)] if app_key == "cms" else []),
            ],
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


def register_app_template_tags(
    app_key: str, *, path: Path | None = None
) -> bool:
    """发现并注册 App 的模板标签：``apps/<key>/template_tags.py``。

    文件里声明两个 dict 即可，其余交给框架：

        FUNCTIONS = {"my_widget": fn}   # fn(ctx, *args, **kwargs)
        FILTERS   = {"my_price": fn}    # fn(value, *args)

    与路由的差别：模板标签没有「一次请求」可以挂依赖守卫，所以注册进来就全局可用。
    停用 App **不会**自动摘掉标签，卸载时由调用方显式
    ``unregister_template_api(app_key)``。模块不存在 / 加载失败一律返回 False，
    不抛异常 —— 闭源 App 在核心包里缺失属于正常情况，不该拖垮启动。
    """
    from cenkor_admin.core.jinja_env import register_template_api

    if path is None:
        found = _resolve_app_file(app_key, "template_tags.py")
        if found is None:
            return False
        path = found
    if not path.exists():
        return False

    name = f"app_template_tags.{app_key}"
    sys.modules.pop(name, None)
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            log.warning("app.template_tags_no_spec", key=app_key)
            return False
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)  # 半个模块留在 sys.modules 更糟
            raise
    except Exception as exc:
        log.warning("app.template_tags_failed", key=app_key, error=str(exc))
        return False

    functions = getattr(module, "FUNCTIONS", None) or {}
    filters = getattr(module, "FILTERS", None) or {}
    if not isinstance(functions, dict) or not isinstance(filters, dict):
        log.warning(
            "app.template_tags_bad_shape",
            key=app_key,
            hint="FUNCTIONS / FILTERS 必须是 dict（name -> callable）",
        )
        return False

    result = register_template_api(app_key, functions=functions, filters=filters)
    return bool(result["functions"] or result["filters"])


def _resolve_app_file(app_key: str, filename: str) -> Path | None:
    """在核心 apps/ 与外置 src/apps/ 里找 App 内的文件。"""
    from cenkor_admin import apps as apps_pkg

    apps_dir = Path(apps_pkg.__path__[0])
    for base in (apps_dir, apps_dir.parent.parent / "apps"):
        candidate = base / app_key / filename
        if candidate.exists():
            return candidate
    return None


def _discover_and_register(apps_dir: Path) -> None:
    """扫描单个 App 目录，注册路由与模板标签。"""
    for item in sorted(apps_dir.iterdir()):
        if item.name.startswith("_") or not item.is_dir():
            continue
        has_router = (item / "router.py").exists()
        has_tags = (item / "template_tags.py").exists()
        if not (has_router or has_tags):
            continue
        if has_router:
            register_app_router(item.name)
        if has_tags:
            register_app_template_tags(item.name, path=item / "template_tags.py")


_auto_register_app_routers()


# ============================================================
# 应用商店路由（不受 /system 的 admin-only 限制）
# ============================================================
from cenkor_admin.apps.system.store_router import router as store_router

api_v1_router.include_router(store_router, prefix="/store", tags=["app-store"])

# 核心平台版本 / 升级检查（latest 公开，check 需登录）
from cenkor_admin.apps.system.release_router import router as release_router

api_v1_router.include_router(release_router, prefix="/release", tags=["release"])

# 生态交易层（定价 / 订单 / 授权 / 云端安装）—— 随仓开源（MIT）。
# 源码在 cenkor_admin/apps/commerce/。仍保留 ImportError 兜底：
# 裁剪部署（只要平台、不要交易层）时照样能正常启动。
try:
    from cenkor_admin.apps.commerce.commerce_router import router as commerce_router
    api_v1_router.include_router(commerce_router, prefix="/store", tags=["app-commerce"])
except Exception as e:
    log.warning("commerce.mount_skipped", error=str(e))

# 应用市场云端绑定（实例 ↔ 官方账号）：与 commerce 同目录，随仓开源。
# 客户实例用它「连接 Cenkor 账号 / 浏览官方市场 / 拉取已购并安装」。
try:
    from cenkor_admin.apps.commerce.cloud_router import router as cloud_router
    api_v1_router.include_router(cloud_router, prefix="/store", tags=["app-cloud"])
except Exception as e:
    log.warning("cloud.mount_skipped", error=str(e))

# 支付中心公开路由（第三方回调 / 收银台 / 状态轮询，免鉴权）
# 随仓开源（MIT），源码在 cenkor_admin/apps/payment/。
# 保留 ImportError 兜底：裁剪部署（不要支付能力）时照样能正常启动。
try:
    from cenkor_admin.apps.payment.public_router import router as payment_public_router
    api_v1_router.include_router(
        payment_public_router, prefix="/public/payment", tags=["payment-public"],
    )
except Exception as e:
    log.warning("payment.mount_skipped", error=str(e))

# ============================================================
# /me
# ============================================================
@api_v1_router.get("/auth/me", response_model=UserBrief, tags=["auth"])
async def me(user: auth_models.User = Depends(get_current_user)):
    """当前用户信息（含权限 + 菜单）"""
    from cenkor_admin.apps.auth.router import _build_user_brief
    return _build_user_brief(user)
