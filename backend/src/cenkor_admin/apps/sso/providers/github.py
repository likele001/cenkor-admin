"""GitHub OAuth。

选它做第一个落地渠道，因为它是唯一「零门槛」的：不需要企业认证、不需要备案、
不需要审核，注册个 OAuth App 立刻就能用。用它先把整条链路跑通，
再验证其他渠道时就能确定问题出在渠道本身而不是框架。

注意两个 GitHub 特有坑：
1. ``/user`` 必须带 ``User-Agent``，否则 403（GitHub API 的硬性要求）。
2. ``email`` 字段经常是 null（用户把邮箱设成私密），必须再查 ``/user/emails``
   拿 primary + verified 的那条。
"""

from __future__ import annotations

import httpx

from .base import OAuthError, OAuthProvider, OAuthUser, ProviderConfig

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"
EMAILS_URL = "https://api.github.com/user/emails"
UA = {"User-Agent": "Cenkor-SSO", "Accept": "application/vnd.github+json"}


class GithubProvider(OAuthProvider):
    key = "github"
    name = "GitHub"
    icon = "🐙"
    scopes = ("read:user", "user:email")
    supports_pkce = True
    order = 50
    note = "开发者账号，注册 OAuth App 即可，无需审核"

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
            "scope": " ".join(self.scopes),
            "state": state,
            "allow_signup": "true",
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
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }
        if code_verifier:
            body["code_verifier"] = code_verifier

        async with httpx.AsyncClient(timeout=15, headers=UA) as client:
            r = await client.post(
                TOKEN_URL, json=body, headers={"Accept": "application/json"}
            )
            if r.status_code >= 400:
                raise OAuthError(f"GitHub 换取 token 失败（HTTP {r.status_code}）")
            data = r.json()
            # GitHub 报错也是 200，靠 error 字段
            if data.get("error"):
                raise OAuthError(
                    f"GitHub 授权失败：{data.get('error_description') or data['error']}"
                )
            token = data.get("access_token")
            if not token:
                raise OAuthError("GitHub 未返回 access_token")

            auth = {"Authorization": f"Bearer {token}", **UA}
            ru = await client.get(USER_URL, headers=auth)
            if ru.status_code >= 400:
                raise OAuthError(f"GitHub 读取用户信息失败（HTTP {ru.status_code}）")
            info = ru.json()

            subject = str(info.get("id") or "")
            if not subject:
                raise OAuthError("GitHub 未返回用户 id")

            email = info.get("email")
            if not email:
                # 邮箱设了私密就必须走 /user/emails，只取已验证的主邮箱
                try:
                    re_ = await client.get(EMAILS_URL, headers=auth)
                    if re_.status_code < 400:
                        for item in re_.json() or []:
                            if item.get("primary") and item.get("verified"):
                                email = item.get("email")
                                break
                except httpx.HTTPError:
                    email = None  # 拿不到邮箱不是致命错误，登录仍可继续

            return OAuthUser(
                subject=subject,
                nickname=info.get("name") or info.get("login") or f"github_{subject}",
                avatar=info.get("avatar_url"),
                email=email,
                union_id=None,  # GitHub 没有 union_id 概念
                raw=info,
                access_token=token,
                expires_in=None,  # GitHub token 不过期（除非用户撤销）
            )
