"""Cenkor Admin · 审计日志模型 + 中间件"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from typing import Any

import structlog
from fastapi import Request
from sqlalchemy import String, Integer, DateTime, func, Text
from sqlalchemy.orm import Mapped, mapped_column
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from cenkor_admin.core.compat import json_column
from cenkor_admin.core.db import AsyncSessionLocal, Base

log = structlog.get_logger()


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        # 月分区（PG 原生 partitioning；MVP 先不分）
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, default=1, index=True)
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(500), index=True)
    status_code: Mapped[int] = mapped_column(Integer, index=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    diff: Mapped[Any] = mapped_column(json_column(), nullable=True)  # 变更前后
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class AuditMiddleware(BaseHTTPMiddleware):
    """记录所有写操作（POST/PATCH/PUT/DELETE）+ 鉴权请求的审计日志"""

    WRITE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}

    async def dispatch(self, request: Request, call_next):
        # 跳过健康检查 / 文档
        if request.url.path in ("/api/health", "/api/openapi.json") or \
           request.url.path.startswith("/api/docs") or \
           request.url.path.startswith("/api/redoc"):
            return await call_next(request)

        # 写操作或鉴权路径才审计
        should_audit = request.method in self.WRITE_METHODS
        if not should_audit:
            return await call_next(request)

        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        start = time.time()
        response: Response | None = None
        error: str | None = None
        user_id: int | None = None

        try:
            # 鉴权：尝试从 token 拿 user_id（不强制）
            from cenkor_admin.core.security import decode_token
            from jose import JWTError
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                try:
                    payload = decode_token(auth[7:])
                    if payload.get("type") == "access":
                        user_id = int(payload["sub"])
                except JWTError:
                    pass

            response = await call_next(request)
            # 把 request_id 注入响应头（方便排错）
            response.headers["X-Request-Id"] = request_id
            return response
        except Exception as e:
            error = repr(e)[:500]
            raise
        finally:
            duration_ms = int((time.time() - start) * 1000)
            # 异步写审计（不阻塞响应）
            import asyncio
            asyncio.create_task(
                _write_audit(
                    request_id=request_id,
                    user_id=user_id,
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code if response else 500,
                    duration_ms=duration_ms,
                    ip=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent", "")[:500],
                    error=error,
                )
            )


async def _write_audit(**kwargs: Any) -> None:
    """异步写审计日志（独立 session）"""
    try:
        async with AsyncSessionLocal() as db:
            db.add(AuditLog(**kwargs))
            await db.commit()
    except Exception as e:
        log.warning("audit.write.failed", error=str(e))
