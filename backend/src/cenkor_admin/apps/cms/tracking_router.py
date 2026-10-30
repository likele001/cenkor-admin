"""埋点采集接口（公开、免鉴权）。

两个接口：

- ``POST /api/v1/public/track`` 收事件。永远返回 204 —— 埋点失败绝不能
  影响访客浏览页面，所以这里把所有异常都咽掉，只留日志。
- ``GET /api/v1/public/track.js`` 出自托管脚本。域名从请求本身推断，
  站点从哪取脚本就往哪上报，不用配一堆环境变量。
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms import tracking
from cenkor_admin.core.db import get_db

log = structlog.get_logger()
router = APIRouter()

# 单次请求体上限。正常一批 50 条事件不到 20KB，256KB 已经非常宽松，
# 超过这个量基本可以确定不是正常浏览器发来的。
_MAX_BODY = 256 * 1024


def _client_ip(request: Request) -> str | None:
    """取真实客户端 IP。

    反向代理后面 ``request.client.host`` 拿到的是网关地址，所有访客会共用
    同一个 ip_hash，日配额会被瞬间打满。所以优先看代理头。
    """
    for header in ("x-forwarded-for", "x-real-ip", "cf-connecting-ip"):
        raw = request.headers.get(header)
        if raw:
            first = raw.split(",")[0].strip()
            if first:
                return first
    return request.client.host if request.client else None


@router.post("/track", include_in_schema=False)
async def collect(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    """接收一批埋点事件。

    Content-Type 是 ``text/plain``（CORS safelisted，不触发预检），
    所以这里手动读 body 再解析 JSON，不走 Pydantic 的自动反序列化。
    """
    try:
        raw = await request.body()
        if not raw or len(raw) > _MAX_BODY:
            return Response(status_code=204)

        payload: Any = json.loads(raw.decode("utf-8", "replace"))
        if not isinstance(payload, dict):
            return Response(status_code=204)

        events = payload.get("events")
        if not isinstance(events, list) or not events:
            return Response(status_code=204)

        result = await tracking.record_batch(
            db,
            site_id=int(payload.get("site_id") or 1),
            visitor_id=str(payload.get("visitor_id") or ""),
            session_id=str(payload.get("session_id") or ""),
            events=events,
            ip=_client_ip(request),
            ua=request.headers.get("user-agent"),
            utm_source=payload.get("utm_source"),
            utm_medium=payload.get("utm_medium"),
            utm_campaign=payload.get("utm_campaign"),
        )
        if result.get("dropped"):
            log.debug("cms.track.partial", **result)
    except Exception as exc:  # noqa: BLE001
        # 埋点是旁路，任何情况都不能把错误抛给访客的浏览器
        log.warning("cms.track.failed", error=str(exc))
    return Response(status_code=204)


@router.get("/track.js", include_in_schema=False)
async def client_script(request: Request) -> Response:
    """自托管埋点脚本。

    域名取请求来源本身：官网从哪个域取脚本，脚本就往哪个域上报。这样同一份
    代码可以在 admin / api / 各个站点域名下通用，不用为每个站配环境变量。
    """
    api_base = str(request.base_url).rstrip("/")
    return Response(
        content=tracking.render_client_script(api_base),
        media_type="application/javascript; charset=utf-8",
        headers={
            "Cache-Control": "public, max-age=1800",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.options("/track")
async def track_preflight() -> Response:
    """预检兜底。

    正常路径走 text/plain 不会触发预检，但万一有人用 application/json 的
    fetch，这里得能应答，否则浏览器直接拦掉请求、服务端连日志都看不到。
    """
    return Response(
        status_code=204,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "86400",
        },
    )
