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

    try:
        await redis_client.ping()
        log.info("redis.ok")
    except Exception as e:
        log.error("redis.fail", error=str(e))

    # 启动时创建默认 bucket
    try:
        await s3.ensure_bucket(settings.S3_BUCKET_PUBLIC)
        await s3.ensure_bucket(settings.S3_BUCKET_PRIVATE)
        log.info("s3.buckets.ready", public=settings.S3_BUCKET_PUBLIC, private=settings.S3_BUCKET_PRIVATE)
    except Exception as e:
        log.warning("s3.buckets.fail", error=str(e))

    yield

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

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 审计（写操作 + 鉴权请求）
app.add_middleware(AuditMiddleware)


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
