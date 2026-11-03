"""Google OAuth 2.0 / OpenID Connect。

走标准 OIDC：authorize 端点 + token 端点 + userinfo 端点。
必须开 PKCE（Google 对"公开客户端"强制要求，机密客户端虽可选但开了更安全）。

两个 Google 特有的注意点：
1. ``access_type=offline`` + ``prompt=consent`` 才会返回 refresh_token。
   不加的话拿不到 refresh_token，后续想读用户 Google Drive/Calendar 就废了。
   代价是用户每次都要看到授权确认页，体验略差 —— 但登录场景其实不需要
   refresh_token，所以默认**不开** offline，只在需要长期访问时由后台勾选。
2. ``sub`` 是稳定唯一标识，**不要用 email 当 subject**：用户可以在 Google
   账号里改邮箱，改完就是另一个人了。
"""

from __future__ import annotations

import httpx

from .base import OAuthError, OAuthProvider, OAuthUser, ProviderConfig

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


class GoogleProvider(OAuthProvider):
    key = "google"
    name = "Google"
    icon = "🔍"
    scopes = ("openid", "email", "profile")
    supports_pkce = True
    order = 40
    note = "海外用户主流渠道，需在 Google Cloud Console 建 OAuth 客户端"

    def authorize_url(
        self,
        cfg: ProviderConfig,
        redirect_uri: str,
        state: str,
        code_challenge: str | None = None,
    ) -> str:
        params: dict[str, str] = {
            "client_id": cfg.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
        }
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        if cfg.extra.get("offline"):
            params["access_type"] = "offline"
            params["prompt"] = "consent"
        return self._q(AUTHORIZE_URL, params)

    async def exchange(
        self,
        cfg: ProviderConfig,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> OAuthUser:
        # Google 的 token 端点只认 application/x-www-form-urlencoded，
        # 发 JSON 会返回 400 unsupported_content_type
        form = {
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        if code_verifier:
            form["code_verifier"] = code_verifier

        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(TOKEN_URL, data=form)
            if r.status_code >= 400:
                detail = "凭证无效或回调地址不匹配"
                try:
                    err = r.json()
                    detail = err.get("error_description") or err.get("error") or detail
                except ValueError:
                    pass
                raise OAuthError(f"Google 换取 token 失败：{detail}")
            data = r.json()
            token = data.get("access_token")
            if not token:
                raise OAuthError("Google 未返回 access_token")

            ru = await client.get(
                USERINFO_URL, headers={"Authorization": f"Bearer {token}"}
            )
            if ru.status_code >= 400:
                raise OAuthError(f"Google 读取用户信息失败（HTTP {ru.status_code}）")
            info = ru.json()

        subject = info.get("sub") or ""
        if not subject:
            raise OAuthError("Google 未返回 sub")

        return OAuthUser(
            subject=subject,
            nickname=info.get("name") or (info.get("email") or "").split("@")[0],
            avatar=info.get("picture"),
            email=info.get("email"),
            union_id=None,
            raw=info,
            access_token=token,
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
        )

    def extra_fields(self) -> list[dict]:
        return [{
            "key": "offline",
            "label": "申请离线访问（返回 refresh_token）",
            "type": "checkbox",
            "default": False,
            "hint": "纯登录不需要勾选。勾选后用户每次都要看到授权确认页，"
                    "但能拿到 refresh_token 以便后续访问 Google 日历/云端硬盘等",
        }]
