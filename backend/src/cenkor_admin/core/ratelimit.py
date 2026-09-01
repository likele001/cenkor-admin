"""轻量 API 限流（M4·P3 4.4 打磨项）。

- 内存滑动窗口（单进程场景够用），默认 60 次/分钟/IP
- 仅作用于公开写接口（/api/v1/public/ 的 POST/PUT/PATCH/DELETE）
- 超限返回 429 + X-RateLimit-* 响应头
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse

log = structlog.get_logger()

_LIMIT = 60            # 每分钟
_WINDOW = 60.0         # 秒
_buckets: dict[str, deque[float]] = defaultdict(deque)


async def rate_limit_middleware(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/v1/public/"):
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        dq = _buckets[key]
        while dq and now - dq[0] > _WINDOW:
            dq.popleft()
        if len(dq) >= _LIMIT:
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后再试"},
                headers={
                    "X-RateLimit-Limit": str(_LIMIT),
                    "X-RateLimit-Remaining": "0",
                },
            )
        dq.append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(_LIMIT)
        response.headers["X-RateLimit-Remaining"] = str(max(0, _LIMIT - len(dq)))
        return response
    return await call_next(request)
