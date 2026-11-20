"""认证防护：登录限流 / 账号锁定 / refresh token 一次性旋转。

为什么要在应用层再做一遍（nginx 已有 limit_req）：
部署形态不止一种（宝塔 / Docker / 裸机），边缘限流规则不一定随代码走；
安全防线不能依赖「运维恰好配了」。本模块只依赖 Redis，任何部署形态都生效。

降级策略：Redis 不可用时**放行**并告警 —— 缓存故障不该把所有人锁在门外，
此时仍有 nginx 边缘限流与验证码兜底。

键位设计（全部带 TTL，无内存泄漏）：
- rl:login:ip:{ip}        登录接口 IP 滑动计数（60s）
- rl:login:fail:{account} 账号连续失败计数（15min），达阈即锁定
- rl:pub:{scope}:{ip}     公开敏感接口（注册/忘记密码）IP 计数（60s）
- auth:rjti:{jti}         refresh token 已消费标记（TTL = token 剩余寿命）
"""
from __future__ import annotations

import structlog
from fastapi import HTTPException

from cenkor_admin.core.redis import redis_client

log = structlog.get_logger()

# ---- 阈值 ----
LOGIN_IP_LIMIT = 30        # 单 IP 每分钟登录尝试（含成功，NAT 出口友好）
LOGIN_FAIL_LIMIT = 10      # 单账号连续失败次数阈值
LOGIN_LOCK_SECONDS = 900   # 触阈后锁定时长（15min）
_WINDOW = 60


async def check_login_rate(ip: str, account: str) -> None:
    """登录前置检查：IP 频率 + 账号锁定。超限抛 429。"""
    account_key = f"rl:login:fail:{account.strip().lower()}"
    try:
        fails = int(await redis_client.get(account_key) or 0)
        if fails >= LOGIN_FAIL_LIMIT:
            ttl = await redis_client.ttl(account_key)
            raise HTTPException(
                status_code=429,
                detail=f"失败次数过多，账号已临时锁定，请 {max(ttl, 1) // 60 + 1} 分钟后重试",
            )
        ip_key = f"rl:login:ip:{ip}"
        n = await redis_client.incr(ip_key)
        if n == 1:
            await redis_client.expire(ip_key, _WINDOW)
        if n > LOGIN_IP_LIMIT:
            raise HTTPException(status_code=429, detail="登录请求过于频繁，请稍后再试")
    except HTTPException:
        raise
    except Exception as e:
        log.warning("auth_guard.redis_unavailable", op="check_login_rate", error=str(e))


async def record_login_failure(ip: str, account: str) -> None:
    """密码错误后累计失败次数（成功登录会清零）。"""
    try:
        key = f"rl:login:fail:{account.strip().lower()}"
        n = await redis_client.incr(key)
        if n == 1:
            await redis_client.expire(key, LOGIN_LOCK_SECONDS)
        if n >= LOGIN_FAIL_LIMIT:
            log.warning("auth_guard.account_locked", account=account, ip=ip, fails=n)
    except Exception as e:
        log.warning("auth_guard.redis_unavailable", op="record_login_failure", error=str(e))


async def record_login_success(ip: str, account: str) -> None:
    try:
        await redis_client.delete(f"rl:login:fail:{account.strip().lower()}")
    except Exception as e:
        log.warning("auth_guard.redis_unavailable", op="record_login_success", error=str(e))


async def check_public_rate(ip: str, scope: str, limit: int = 10) -> None:
    """公开敏感接口（注册 / 忘记密码）的 IP 限流，超限抛 429。"""
    try:
        key = f"rl:pub:{scope}:{ip}"
        n = await redis_client.incr(key)
        if n == 1:
            await redis_client.expire(key, _WINDOW)
        if n > limit:
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
    except HTTPException:
        raise
    except Exception as e:
        log.warning("auth_guard.redis_unavailable", op="check_public_rate", error=str(e))


async def consume_refresh_jti(jti: str, ttl_seconds: int) -> bool:
    """一次性消费 refresh token 的 jti。

    返回 True = 首次使用（放行）；False = 已被消费过（重放，调用方应撤销会话）。
    SET NX 保证并发下也只有一个请求能消费成功。TTL 与 token 剩余寿命对齐，
    token 自然过期后标记同步消失，不留垃圾。
    """
    try:
        ok = await redis_client.set(
            f"auth:rjti:{jti}", "1", nx=True, ex=max(int(ttl_seconds), 1),
        )
        return bool(ok)
    except Exception as e:
        # Redis 故障时放行：旋转降级为「旧式可重用」，不影响登录主链路
        log.warning("auth_guard.redis_unavailable", op="consume_refresh_jti", error=str(e))
        return True


def refresh_ttl_seconds(payload: dict) -> int:
    """从 refresh payload 的 exp 推算剩余寿命（秒），兜底 7 天。"""
    from datetime import UTC, datetime

    exp = payload.get("exp")
    if isinstance(exp, (int, float)):
        return max(int(exp - datetime.now(UTC).timestamp()), 60)
    return 7 * 24 * 3600
