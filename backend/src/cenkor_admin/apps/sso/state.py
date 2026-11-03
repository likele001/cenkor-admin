"""OAuth 一次性凭证：state、PKCE、ticket。

三个东西解决三个不同的问题，别混在一起：

- **state**：防 CSRF。攻击者诱导你点一个带他自己 code 的回调链接，让你登进
  他的账号（之后你在他账号里操作的所有东西他都看得到）。state 存 Redis，
  回调时校验存在性并立即删除，用过就作废。
- **PKCE**（code_verifier / code_challenge）：防 code 被截获。授权码在浏览器
  地址栏里明文可见，会进历史记录、Referer、Nginx access log。PKCE 让「拿到
  code 但没拿到 verifier」的人换不出 token。微信和抖音不支持，其余三个开。
- **ticket**：防 JWT 泄露。回调成功后**不能**把 access_token 放重定向 URL 里，
  同样会进日志和浏览器历史。改为发一个 60 秒一次性票据，前端拿它换 token。

全部放 Redis 不用数据库：这些数据的生命周期是秒级，写库纯属浪费，而且 Redis
的 TTL 天然实现了「过期自动清理」。
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from typing import Any

from cenkor_admin.core.redis import redis_client

STATE_PREFIX = "sso:state:"
STATE_TTL = 600  # 10 分钟：够用户慢吞吞扫码，又不至于开个窗口放一整天

TICKET_PREFIX = "sso:ticket:"
TICKET_TTL = 120  # 2 分钟：够前端从回调页跳一次并换 token

# state 里带一个 nonce，回调后拼进前端地址，防止「回调页被缓存后重放」
MAX_REDIRECT_LEN = 512


def new_state() -> str:
    return secrets.token_urlsafe(32)


def new_pkce_pair() -> tuple[str, str]:
    """生成 (code_verifier, code_challenge)。S256，RFC 7636 标准做法。

    verifier 必须 43~128 字符且只含 unreserved 字符，token_urlsafe(64) 正好。
    """
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def _safe_redirect(url: str | None) -> str:
    """只接受站内相对路径，拒绝 http://evil.com 这类外跳。

    这是开放重定向防护：如果允许任意 URL，攻击者可以构造
    ``?redirect=https://phishing.com`` 让你的域名变成钓鱼跳板。
    """
    if not url or len(url) > MAX_REDIRECT_LEN:
        return ""
    if not url.startswith("/") or url.startswith("//"):
        return ""
    return url


async def put_state(
    state: str,
    *,
    provider: str,
    realm: str,
    code_verifier: str | None = None,
    redirect_after: str | None = None,
    link_user_id: int | None = None,
) -> None:
    payload = {
        "provider": provider,
        "realm": realm,
        "code_verifier": code_verifier,
        "redirect_after": _safe_redirect(redirect_after),
        # 已登录用户主动来「绑定新渠道」时带 user_id，回调后绑到该账号而不是登录
        "link_user_id": link_user_id,
    }
    await redis_client.setex(STATE_PREFIX + state, STATE_TTL, json.dumps(payload))


async def take_state(state: str) -> dict[str, Any] | None:
    """取出并立即删除。不存在（过期/伪造/已用过）返回 None。"""
    key = STATE_PREFIX + state
    raw = await redis_client.get(key)
    if not raw:
        return None
    await redis_client.delete(key)
    try:
        return json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
    except (ValueError, AttributeError):
        return None


def new_ticket() -> str:
    return secrets.token_urlsafe(32)


async def put_ticket(
    ticket: str,
    *,
    realm: str,
    user_id: int,
    provider: str,
    is_new_user: bool = False,
) -> None:
    payload = {
        "realm": realm,
        "user_id": user_id,
        "provider": provider,
        "is_new_user": is_new_user,
    }
    await redis_client.setex(TICKET_PREFIX + ticket, TICKET_TTL, json.dumps(payload))


async def take_ticket(ticket: str) -> dict[str, Any] | None:
    key = TICKET_PREFIX + ticket
    raw = await redis_client.get(key)
    if not raw:
        return None
    await redis_client.delete(key)
    try:
        return json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
    except (ValueError, AttributeError):
        return None


__all__ = [
    "new_pkce_pair",
    "new_state",
    "new_ticket",
    "put_state",
    "put_ticket",
    "take_state",
    "take_ticket",
]
