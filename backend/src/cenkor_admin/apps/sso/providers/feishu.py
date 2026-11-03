"""飞书 OAuth 2.0。

这份实现是对原有硬编码版本的重写，行为保持兼容（同样是 open_id 作锚点、
同样是 v1 user_info 接口），但修掉了原版的两个问题：

1. **token 明文入库**：原版直接把 access_token 塞进 ``*_enc`` 字段却没有任何
   加密，字段名骗人。这里由 router 层统一走 ``core.secrets.encrypt_secret``。
2. **邮箱占位符造垃圾数据**：原版给没邮箱的用户填 ``{username}@feishu.local``，
   而 ``portal_users.email`` 是 UNIQUE，两个人撞同一个占位符就 500。
   现在没邮箱就存 NULL（PG 的 UNIQUE 允许多个 NULL）。

飞书是唯一「后台也可以开」的渠道：它有企业管理员体系，
属于组织内身份，不像微信/抖音那样是 C 端账号。
"""

from __future__ import annotations

import httpx

from .base import OAuthError, OAuthProvider, OAuthUser, ProviderConfig

AUTHORIZE_URL = "https://open.feishu.cn/open-apis/authen/v1/index"
TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
USERINFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"


class FeishuProvider(OAuthProvider):
    key = "feishu"
    name = "飞书"
    icon = "🪶"
    scopes = ("contact:user.id:readonly", "contact:user.base:readonly")
    supports_pkce = True
    order = 30
    note = "企业内部渠道，后台可开；需在飞书开放平台建企业自建应用"

    def authorize_url(
        self,
        cfg: ProviderConfig,
        redirect_uri: str,
        state: str,
        code_challenge: str | None = None,
    ) -> str:
        params = {
            "app_id": cfg.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": " ".join(self.scopes),
        }
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        return self._q(AUTHORIZE_URL, params)

    async def exchange(
        self,
        cfg: ProviderConfig,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> OAuthUser:
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
            "redirect_uri": redirect_uri,
        }
        if code_verifier:
            body["code_verifier"] = code_verifier

        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(TOKEN_URL, json=body)
            try:
                data = r.json()
            except ValueError as exc:
                raise OAuthError("飞书换取 token 返回了无法解析的内容") from exc

            # v2 接口成功时 code=0；v1 用 code 但语义一致
            if data.get("code") not in (None, 0):
                raise OAuthError(
                    f"飞书换取 token 失败：{data.get('error_description') or data.get('msg') or data.get('code')}"
                )
            token = data.get("access_token")
            if not token:
                raise OAuthError("飞书未返回 access_token")

            ru = await client.get(
                USERINFO_URL, headers={"Authorization": f"Bearer {token}"}
            )
            try:
                info = ru.json()
            except ValueError as exc:
                raise OAuthError("飞书读取用户信息返回了无法解析的内容") from exc
            if info.get("code") not in (None, 0):
                raise OAuthError(
                    f"飞书读取用户信息失败：{info.get('msg') or info.get('code')}"
                )
            user = info.get("data") or {}

        subject = user.get("open_id") or ""
        if not subject:
            raise OAuthError("飞书未返回 open_id")

        return OAuthUser(
            subject=subject,
            nickname=user.get("name") or user.get("en_name") or "飞书用户",
            avatar=user.get("avatar_url") or user.get("avatar_big"),
            email=user.get("email") or user.get("enterprise_email") or None,
            union_id=user.get("union_id"),
            raw=user,
            access_token=token,
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
        )
