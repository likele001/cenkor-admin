"""URL 重定向（M3·P2 3.3）：from_path → to_path（301/302）。

- 内存缓存 60s，写操作后调用 clear_redirect_cache() 立即刷新。
- 仅对 GET/HEAD 生效。
"""
from __future__ import annotations

import time

import structlog
from fastapi import Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from cenkor_admin.core.db import AsyncSessionLocal

log = structlog.get_logger()

CACHE_TTL = 60.0
_cache: dict = {"at": 0.0, "map": {}}


def clear_redirect_cache() -> None:
    _cache["at"] = 0.0


async def _load_redirects() -> dict[str, tuple[str, int]]:
    now = time.monotonic()
    if now - _cache["at"] < CACHE_TTL:
        return _cache["map"]
    try:
        from cenkor_admin.apps.system.models import Redirect
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(Redirect).where(Redirect.enabled.is_(True))
            )).scalars().all()
        _cache["map"] = {r.from_path: (r.to_path, r.code) for r in rows}
        _cache["at"] = now
    except Exception as e:  # noqa: BLE001
        log.warning("redirects.load_failed", error=str(e))
    return _cache["map"]


async def redirect_middleware(request: Request, call_next):
    """FastAPI http 中间件：命中 from_path 则 301/302 跳转。"""
    if request.method in ("GET", "HEAD"):
        try:
            m = await _load_redirects()
            hit = m.get(request.url.path)
            if hit:
                to_path, code = hit
                return RedirectResponse(to_path, status_code=code)
        except Exception as e:  # noqa: BLE001 - 中间件绝不可 500
            log.warning("redirects.middleware_failed", error=str(e))
    return await call_next(request)
