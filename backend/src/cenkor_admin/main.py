"""FastAPI 主入口"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

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
    # 用 "heads" 而非 "head"：公开链与商业应用闭源链靠挂载点串成单 head，
    # 万一挂载点漏顺延出现双 head，heads 仍能各升各的；"head" 会抛 MultipleHeads 整条失败。
    #
    # 但直接 upgrade 有个坑：库里结构可能已经比版本号新（历史上手工补过 DDL，
    # 见 core/migration_drift.py 的背景）。此时 upgrade 会重跑那一整串迁移，
    # 撞 DuplicateColumn/DuplicateTable，启动日志被刷满 error。
    # 所以先做一次全量图漂移检测：期望对象全在库里 → stamp（版本号落后），
    # 有缺失 → 正常 upgrade（结构真落后）。
    try:
        from cenkor_admin.core.migration_runner import run_migrations_with_drift_guard

        _mig_result = run_migrations_with_drift_guard()
        log.info("migration.ok", result=_mig_result)
    except Exception as e:
        # 迁移失败意味着数据表可能缺失：服务虽能起来，但接口会大面积报错，
        # 必须显式告警（error 级，而非静默的 warning），以便日志告警规则能捕获。
        log.error("migration.fail", error=str(e), hint="数据表可能未创建，接口可能大面积失败")

    # 应用自带的 schema.sql（方案 D / 2026-10-27）
    # crm / erp / mes 的表已从 alembic 主链剥离，改由各应用目录下的 schema.sql 创建。
    # 幂等执行：checksum 没变就跳过；CENKOR_APPS 控制装哪些
    # （未设置=全部内置，空字符串=只有核心表，逗号分隔=指定）。
    # 必须在迁移之后、install_app 之前 —— install_app 要注册 content_types，依赖表存在。
    try:
        from cenkor_admin.apps.system.app_registry import scan_app_manifests as _scan_apps
        from cenkor_admin.core.app_schema import summarize, sync_builtin_apps

        _apps_dir = Path(__file__).resolve().parent / "apps"
        _results = sync_builtin_apps(_apps_dir, _scan_apps())
        log.info("app.schema.sync", detail=summarize(_results))
        _failed = [r.key for r in _results if r.status == "failed"]
        if _failed:
            # 单个应用建表失败不该拖垮整个平台，但必须显式告警，
            # 否则接口大面积 500 时无从查起。
            log.error("app.schema.partial_fail", keys=_failed)
    except Exception as e:
        log.error("app.schema.sync_fail", error=str(e), hint="应用表可能缺失")

    # CMS AI 层表（条目向量 / AI 生成溯源）
    # 2026-10-31 起建表由 alembic 负责（core/20261031_1310_cms_ai_tables.py），
    # 这里只校验表在不在；失败只告警：AI 是可选增强，不能拖垮主链路
    try:
        from cenkor_admin.apps.cms.ai.bootstrap import ensure_cms_ai_schema

        if not ensure_cms_ai_schema():
            log.warning(
                "cms_ai.schema.not_ready",
                hint="语义检索与 AI 溯源不可用，CMS 其他功能不受影响",
            )
    except Exception as e:
        log.warning("cms_ai.schema.bootstrap_failed", error=str(e))

    # AI 配置缓存预热：后台配置（服务商 / 能力绑定）读进内存，
    # 让 get_llm_for() 这种同步调用点无需查库。预热失败不阻塞启动，
    # registry 会在首次异步调用点自行补刷。
    try:
        from cenkor_admin.apps.cms.ai import registry as ai_registry
        from cenkor_admin.core.db import AsyncSessionLocal

        async with AsyncSessionLocal() as _ai_session:
            reg = await ai_registry.load(_ai_session, force=True)
        log.info(
            "ai.registry.ready",
            providers=len(reg.providers),
            capabilities=sorted(reg.endpoints),
        )
    except Exception as e:
        log.warning("ai.registry.warm_failed", error=str(e))

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
        from sqlalchemy import select

        from cenkor_admin.apps.system.app_registry import (
            install_app,
            scan_app_manifests,
        )
        from cenkor_admin.apps.system.models import InstalledApp
        from cenkor_admin.core.db import AsyncSessionLocal

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
                        # 多 worker（uvicorn --workers N）同时启动时，同一个 App 会被并发安装：
                        # 抢先的 worker 插入成功，其余撞 platform_apps 主键（UniqueViolation）。
                        # 这属于幂等预期内 —— 回滚后确认记录已存在即可，不要当故障刷 warning；
                        # 更关键的是必须 rollback，否则事务被污染，同进程后续 App 全部安装失败。
                        await db.rollback()
                        try:
                            raced = (
                                await db.execute(
                                    select(InstalledApp).where(InstalledApp.key == key)
                                )
                            ).scalar_one_or_none() is not None
                        except Exception:
                            raced = False
                        if raced:
                            log.debug("app.auto_install.raced", key=key)
                        else:
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
                except Exception as _he:
                    log.warning("app.hooks_register_failed", key=key, error=str(_he))
            if drifted:
                await db.commit()
                log.info("app.version_reconciled", count=len(drifted), detail=",".join(drifted))
    except Exception as e:
        log.warning("app.auto_install.check_fail", error=str(e))

    # 注册内置钩子处理器（插件框架 M1·P0）：导入模块即触发 @hook 装饰器注册
    try:
        from cenkor_admin.apps.system import hooks as _builtin_hooks

        # [P2C] webhook 投递器此前无人 import，@hook 处理器全未注册
        from cenkor_admin.apps.system import webhooks as _webhook_hooks  # noqa: F401

        # 已退役 cenkormes-center 桥接：付款后发卡改由本仓 commerce 层自行签发，不再向外部仓库 auto-issue。
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
        import asyncio as _asyncio

        from cenkor_admin.core.scheduler import scheduler_loop

        scheduler_task = _asyncio.create_task(scheduler_loop())
        log.info("scheduler.started")
    except Exception as e:
        log.warning("scheduler.start_failed", error=str(e))

    # [P2C] Webhook 失败重试 worker（进程重启后未投完的记录会续上）
    webhook_task = None
    try:
        import asyncio as _asyncio

        from cenkor_admin.apps.system.webhooks import retry_loop as _wh_retry_loop

        webhook_task = _asyncio.create_task(_wh_retry_loop())
        log.info("webhook.retry_loop.spawned")
    except Exception as e:
        log.warning("webhook.retry_loop.spawn_failed", error=str(e))

    # 核心版本检查预热（升级提示）：spoke 向官方云查一次，发现新版记日志，不阻塞启动
    try:
        import asyncio as _asyncio

        from cenkor_admin.apps.system import release_service

        _asyncio.create_task(release_service.warm_cache())
    except Exception as e:
        log.warning("release.warm_spawn_failed", error=str(e))

    # AI 批量生产：进程上次被杀时可能停在 running，启动时把僵死项回退成 pending。
    # 故意不自动续跑 —— 重启瞬间就冲 LLM 配额很难排查；用户点「继续」即可，
    # 已生成的篇目不会重复。
    async def _recover_batch_jobs() -> None:
        try:
            from cenkor_admin.apps.cms.ai import batch_runner

            n = await batch_runner.resume_on_boot()
            if n:
                log.warning("cms.ai.batch.recovered_jobs", count=n)
        except Exception as e:
            log.warning("cms.ai.batch.recover_failed", error=str(e))

    try:
        import asyncio as _asyncio

        _asyncio.create_task(_recover_batch_jobs())
    except Exception as e:
        log.warning("cms.ai.batch.recover_spawn_failed", error=str(e))

    try:
        yield
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            log.info("scheduler.stopped")
        if webhook_task is not None:
            webhook_task.cancel()
            log.info("webhook.retry_loop.stopped")

    log.info("app.stopping")
    await async_engine.dispose()
    await redis_client.close()


# ---- P0-4：生产环境不暴露 traceback 页与 API 目录（2026-10-12）----
# 为什么不能直接用 settings.DEBUG：
#   config.py 里 DEBUG 默认 True，而宝塔 Python 项目的环境文件只设了 APP_ENV=production，
#   于是线上曾经以 debug=True 运行——任何未捕获异常都会把「源码片段 + 每帧局部变量」的
#   HTML traceback 直接返回给访客（10-08 那三次 checkout 500 的响应体就是 17KB 的 debug 页）。
# 为什么这里不顺手把 settings.DEBUG 改成 False：
#   core/mail.py:65 用 settings.DEBUG 决定邮件走同步还是 Celery，而本服务没有自己的
#   celery worker（机器上跑着的 worker 属于另一个项目）。改了会让邮件静默不发送。
# 所以只在「构造 app」这一层收口，不动全局配置。
_debug_enabled = settings.DEBUG and settings.APP_ENV != "production"

app = FastAPI(
    title=settings.APP_NAME,
    version=__version__,
    debug=_debug_enabled,
    lifespan=lifespan,
    # 生产关文档：openapi.json 会把闭源 /api/v1/store/* 全部端点明文列出来（808KB）。
    # 本地开发仍可用 APP_ENV=development 打开。
    docs_url="/api/docs" if _debug_enabled else None,
    redoc_url="/api/redoc" if _debug_enabled else None,
    openapi_url="/api/openapi.json" if _debug_enabled else None,
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

# 多站点隔离：把当前站点写进 contextvar，ORM 层据此自动加 site_id 条件
from cenkor_admin.core.site_scope import site_scope_middleware

app.middleware("http")(site_scope_middleware)


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
