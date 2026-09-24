"""FastAPI 主入口"""
from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from cenkor_admin import __version__
from cenkor_admin.api.v1 import api_v1_router
from cenkor_admin.api.v1 import ws as ws_module
from cenkor_admin.core.audit import AuditMiddleware
from cenkor_admin.core.config import get_settings
from cenkor_admin.core.db import async_engine
from cenkor_admin.core.i18n import SUPPORTED_LOCALES, detect_locale
from cenkor_admin.core.redis import redis_client
from cenkor_admin.core.storage import s3
from pathlib import Path

settings = get_settings()
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动 / 关闭钩子。"""
    log.info("app.starting", env=settings.APP_ENV, version=__version__)
    # 启动时 ping 一下依赖
    try:
        async with async_engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
        log.info("db.ok", dialect=settings.db_dialect)
    except Exception as e:
        log.error("db.fail", error=str(e))

    # 启动时自动应用所有待执行的数据库迁移
    # 安装 App 时拷贝的迁移文件会在下次重启时自动生效
    try:
        from alembic.config import Config
        from alembic import command
        _alembic_cfg = Config(Path(__file__).resolve().parent.parent.parent / "alembic.ini")
        command.upgrade(_alembic_cfg, "head")
        log.info("migration.ok")
    except Exception as e:
        log.warning("migration.fail", error=str(e))

    try:
        await redis_client.ping()
        log.info("redis.ok")
    except Exception as e:
        log.error("redis.fail", error=str(e))

    # 启动时校验默认 bucket（cloud_storage 激活时用凭据中的 bucket）
    try:
        public_bucket = await s3.public_bucket()
        await s3.ensure_bucket(public_bucket)
        log.info("s3.buckets.ready", public=public_bucket)
    except Exception as e:
        log.warning("s3.buckets.fail", error=str(e))

    # 启动时自动安装 + 版本对齐：
    # - platform_apps 里**完全没有记录**的 App → 自动安装
    # - 已 installed 的 App → 同步 name/version（源码 bump 后对齐，避免商店"有更新"误报）
    # - 已 uninstall 的 App → 不动，必须由管理员显式安装
    try:
        from cenkor_admin.core.db import AsyncSessionLocal
        from cenkor_admin.apps.system.app_registry import (
            install_app, scan_app_manifests, list_apps_with_status,
        )
        from sqlalchemy import select
        from cenkor_admin.apps.system.models import InstalledApp
        async with AsyncSessionLocal() as db:
            manifests = scan_app_manifests()
            all_rows = (await db.execute(select(InstalledApp))).scalars().all()
            known_keys = {a.key for a in all_rows}  # 包括 uninstalled 的
            by_key = {a.key: a for a in all_rows}
            drifted = []
            for key, manifest in manifests.items():
                if key not in known_keys:
                    try:
                        await install_app(db, key)
                        log.info("app.auto_installed", key=key, version=manifest.version)
                    except Exception as e:
                        log.warning("app.auto_install_failed", key=key, error=str(e))
                    continue
                row = by_key.get(key)
                if row is None or row.status != "installed":
                    continue  # uninstalled 的 App 不自动重装
                if row.version != manifest.version or row.name != manifest.name:
                    drifted.append(key + ":" + str(row.version) + "->" + manifest.version)
                    row.version = manifest.version
                    row.name = manifest.name

                # 内存钩子注册表随进程重启清空，而 register_app_hooks 只在 install_app
                # 里调用过一次 —— 已装应用重启后会静默失去全部 @hook 处理器。这里补注册。
                try:
                    from cenkor_admin.core.hooks import register_app_hooks as _reg_hooks
                    _reg_hooks(key, list(manifest.hooks or []))
                except Exception as _he:  # noqa: BLE001
                    log.warning("app.hooks_register_failed", key=key, error=str(_he))
            if drifted:
                await db.commit()
                log.info("app.version_reconciled", count=len(drifted), detail=",".join(drifted))
    except Exception as e:
        log.warning("app.auto_install.check_fail", error=str(e))

    # 注册内置钩子处理器（插件框架 M1·P0）：导入模块即触发 @hook 装饰器注册
    try:
        from cenkor_admin.apps.system import hooks as _builtin_hooks  # noqa: F401
        from cenkor_admin.apps.system import webhooks as _webhook_hooks  # noqa: F401  (M3·P2)
        # 闭源商业模块（无 manifest，由 api/v1/__init__.py 直接挂载 /api/v1/store）
        try:
            from cenkor_admin.apps.commerce import hooks as _commerce_hooks  # noqa: F401
        except ImportError:
            pass
        log.info("hooks.builtin_loaded", handlers=len(_builtin_hooks.__dict__))
    except Exception as e:
        log.warning("hooks.builtin_failed", error=str(e))

    # 定时发布调度器（M2·P1 2.5）
    scheduler_task = None
    try:
        from cenkor_admin.core.scheduler import scheduler_loop
        import asyncio as _asyncio
        scheduler_task = _asyncio.create_task(scheduler_loop())
        log.info("scheduler.started")
    except Exception as e:
        log.warning("scheduler.start_failed", error=str(e))

    # 核心版本检查预热（升级提示）：spoke 向官方云查一次，发现新版记日志，不阻塞启动
    try:
        import asyncio as _asyncio
        from cenkor_admin.apps.system import release_service
        _asyncio.create_task(release_service.warm_cache())
    except Exception as e:
        log.warning("release.warm_spawn_failed", error=str(e))

    try:
        yield
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            log.info("scheduler.stopped")

    log.info("app.stopping")
    await async_engine.dispose()
    await redis_client.close()


app = FastAPI(
    title=settings.APP_NAME,
    version=__version__,
    debug=settings.DEBUG,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS（按环境收紧：生产禁用 allow_origins=["*"]）
cors_kwargs = {
    "allow_origins": settings.cors_origins_list,
    "allow_credentials": True,
    "allow_methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    "allow_headers": [
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "X-Request-Id",
    ],
    "expose_headers": ["X-Request-Id", "Content-Language"],
    "max_age": 600,  # 10 min
}
if settings.APP_ENV == "production":
    # 生产环境不允许 allow_origins=["*"]（已通过 cors_origins_list 控制）
    pass
app.add_middleware(CORSMiddleware, **cors_kwargs)

# 审计（写操作 + 鉴权请求）
app.add_middleware(AuditMiddleware)

# 挂载 App 前端静态资源（安装时从 ZIP 解压出来的前端 bundle）
from fastapi.staticfiles import StaticFiles
_app_static_dir = Path(__file__).resolve().parent / "static" / "apps"
_app_static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/.app-assets", StaticFiles(directory=str(_app_static_dir)), name="app_assets")

# 健康检查
@app.get("/api/health", tags=["meta"])
async def health() -> dict:
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": __version__,
        "env": settings.APP_ENV,
        "db": settings.db_dialect,
        "supported_locales": SUPPORTED_LOCALES,
    }


# i18n 中间件：把 Accept-Language 解析结果存到 request.state.locale
@app.middleware("http")
async def locale_middleware(request: Request, call_next):
    request.state.locale = detect_locale(request.headers.get("accept-language", ""))
    response = await call_next(request)
    response.headers["Content-Language"] = request.state.locale
    return response


# 重定向中间件（M3·P2 3.3）：GET/HEAD 命中 from_path 时 301/302
from cenkor_admin.core.redirects import redirect_middleware
app.middleware("http")(redirect_middleware)

# 限流中间件（M4·P3 4.4）：公开写接口 60次/分钟/IP
from cenkor_admin.core.ratelimit import rate_limit_middleware
app.middleware("http")(rate_limit_middleware)


# 路由
app.include_router(api_v1_router, prefix="/api/v1")
app.include_router(ws_module.router, prefix="/api/v1")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    log.exception("unhandled", path=str(request.url), error=str(exc))
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "服务内部错误",
            "request_id": request.headers.get("X-Request-Id", ""),
        },
    )
