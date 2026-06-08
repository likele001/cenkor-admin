"""第三方登录（飞书 / 企微 / GitHub）MVP"""
from __future__ import annotations

import secrets
import structlog
from urllib.parse import urlencode

import httpx

from cenkor_admin.core.config import get_settings
from cenkor_admin.core.redis import redis_client

settings = get_settings()
log = structlog.get_logger()

FEISHU_OAUTH_STATE_PREFIX = "oauth:feishu:state:"
FEISHU_OAUTH_STATE_TTL = 300  # 5 分钟


# ---- 飞书 OAuth ----
class FeishuOAuth:
    """飞书 OAuth 2.0 标准授权码模式

    流程：
    1. 前端跳转到 /api/v1/auth/feishu/authorize
    2. 后端 302 重定向到飞书授权页
    3. 用户授权后飞书 302 到 REDIRECT_URI（带 code）
    4. 后端拿 code 换 access_token + user info
    5. 查找/创建本地用户，返回内部 JWT
    """

    AUTHORIZE_URL = "https://open.feishu.cn/open-apis/authen/v1/index"
    TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
    USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"

    def __init__(self) -> None:
        self.app_id = settings.FEISHU_APP_ID
        self.app_secret = settings.FEISHU_APP_SECRET
        self.redirect_uri = settings.FEISHU_REDIRECT_URI

    @property
    def enabled(self) -> bool:
        return bool(self.app_id and self.app_secret)

    def build_authorize_url(self, state: str) -> str:
        """构造飞书授权页 URL（前端跳转）"""
        params = {
            "app_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "state": state,
            "scope": "contact:user.id:readonly contact:user.base:readonly",
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        """用 code 换 access_token（同时拿到 user info）"""
        async with httpx.AsyncClient(timeout=15) as client:
            # 1. 换 access_token
            r = await client.post(self.TOKEN_URL, json={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.app_id,
                "client_secret": self.app_secret,
            })
            r.raise_for_status()
            data = r.json()
            if data.get("code") != 0:
                raise RuntimeError(f"Feishu token error: {data}")

            access_token = data["access_token"]

            # 2. 拿用户信息
            r2 = await client.get(self.USER_INFO_URL, headers={
                "Authorization": f"Bearer {access_token}",
            })
            r2.raise_for_status()
            user_info = r2.json()
            if user_info.get("code") != 0:
                raise RuntimeError(f"Feishu user_info error: {user_info}")

            return {
                "access_token": access_token,
                "refresh_token": data.get("refresh_token"),
                "expires_in": data.get("expires_in", 7200),
                "open_id": user_info["data"]["open_id"],
                "union_id": user_info["data"].get("union_id"),
                "name": user_info["data"].get("name", ""),
                "email": user_info["data"].get("email", ""),
                "avatar_url": user_info["data"].get("avatar_url", ""),
            }

    def new_state(self) -> str:
        return secrets.token_urlsafe(32)

    async def store_state(self, state: str) -> None:
        """写入 Redis，防 CSRF（一次性，TTL 5 分钟）"""
        await redis_client.setex(f"{FEISHU_OAUTH_STATE_PREFIX}{state}", FEISHU_OAUTH_STATE_TTL, "1")

    async def consume_state(self, state: str) -> bool:
        """校验并消费 state（防重放）"""
        key = f"{FEISHU_OAUTH_STATE_PREFIX}{state}"
        if not await redis_client.get(key):
            return False
        await redis_client.delete(key)
        return True


feishu = FeishuOAuth()
