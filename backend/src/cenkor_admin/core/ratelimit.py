"""轻量 API 限流（M4·P3 4.4 打磨项）。

- 内存滑动窗口（单进程场景够用），按路径前缀分档
- 仅作用于公开写接口，超限返回 429 + X-RateLimit-* 响应头

为什么埋点要单独一档：一个访客打开文章页会产生 1 次 PV + 每 15 秒一次
心跳 + 离开时一次滚动上报，3 分钟看一篇文章就是十几次请求。用默认的
60 次/分钟，公司 NAT 后面几十个人共用一个出口 IP，正常浏览就会被判成
攻击，数据直接丢光。埋点给 600，其余接口保持 60。
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse

log = structlog.get_logger()

_LIMIT = 60            # 每分钟（默认）
_WINDOW = 60.0         # 秒

# 按路径前缀覆盖限额，长的前缀优先匹配
_PATH_RULES: tuple[tuple[str, int], ...] = (
    ("/api/v1/public/track", 600),
)

# 桶数量超过这个值时清理空桶，防止长期运行内存缓慢增长
_SWEEP_AT = 5000

_buckets: dict[str, deque[float]] = defaultdict(deque)


def _limit_for(path: str) -> int:
    for prefix, limit in _PATH_RULES:
        if path.startswith(prefix):
            return limit
    return _LIMIT


def _sweep(now: float) -> None:
    """清掉空的和过期的桶。

    原实现从不清理，访问过的每个 IP 都会留下一个空 deque。单进程跑几个月，
    这是稳定的内存泄漏。桶数不多时不做，避免每次请求都遍历。
    """
    if len(_buckets) < _SWEEP_AT:
        return
    dead = [k for k, dq in _buckets.items() if not dq or now - dq[-1] > _WINDOW]
    for k in dead:
        _buckets.pop(k, None)


async def rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and path.startswith("/api/v1/public/"):
        limit = _limit_for(path)
        key = f"{request.client.host if request.client else 'unknown'}:{limit}"
        now = time.monotonic()
        dq = _buckets[key]
        while dq and now - dq[0] > _WINDOW:
            dq.popleft()
        if len(dq) >= limit:
            # 埋点接口即使被限流也返回 204：让刷量的人看不出被挡，
            # 同时访客侧不产生任何报错。
            if path.startswith("/api/v1/public/track"):
                log.warning("cms.track.rate_limited", ip=key.split(":")[0])
                return JSONResponse(status_code=204, content=None)
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后再试"},
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )
        dq.append(now)
        _sweep(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - len(dq)))
        return response
    return await call_next(request)
