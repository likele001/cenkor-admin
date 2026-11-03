"""抖音开放平台（网站应用 / H5 授权）。

抖音的接口风格和其他渠道差别最大，有三个必须注意的地方：

1. **字段名不同**：抖音叫 ``client_key`` 而不是 ``client_id``，
   ``client_secret`` 保持一致。配置里统一存 client_id，发给抖音时改名。
2. **结果层层嵌套**：业务错误码藏在 ``data.error_code``，不是顶层。
   只要 ``error_code != 0`` 就是失败，``data.description`` 是可读原因。
3. **申请门槛高**：必须企业主体 + 网站已备案，个人开发者拿不到授权。
   代码可以先接好，等你资质下来直接填 key 即可。
"""

from __future__ import annotations

import httpx

from .base import OAuthError, OAuthProvider, OAuthUser, ProviderConfig

AUTHORIZE_URL = "https://open.douyin.com/platform/oauth/connect/"
TOKEN_URL = "https://open.douyin.com/oauth/access_token/"
USERINFO_URL = "https://open.douyin.com/oauth/userinfo/"


class DouyinProvider(OAuthProvider):
    key = "douyin"
    name = "抖音"
    icon = "🎵"
    scopes = ("user_info",)
    supports_pkce = False
    order = 20
    note = "需抖音开放平台企业主体 + 网站备案，审核通过后可获取用户昵称头像"

    def authorize_url(
        self,
        cfg: ProviderConfig,
        redirect_uri: str,
        state: str,
        code_challenge: str | None = None,
    ) -> str:
        # 抖音用 client_key，参数名和其他渠道不同
        params = {
            "client_key": cfg.client_id,
            "response_type": "code",
            "scope": ",".join(self.scopes),
            "redirect_uri": redirect_uri,
            "state": state,
        }
        return self._q(AUTHORIZE_URL, params)

    async def exchange(
        self,
        cfg: ProviderConfig,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> OAuthUser:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                TOKEN_URL,
                json={
                    "client_key": cfg.client_id,
                    "client_secret": cfg.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                },
            )
            data = self._data(r, "换取 token")
            token = data.get("access_token")
            open_id = data.get("open_id")
            if not token or not open_id:
                raise OAuthError("抖音未返回 access_token 或 open_id")

            ru = await client.get(
                USERINFO_URL, params={"open_id": open_id, "access_token": token}
            )
            info = self._data(ru, "读取用户信息")

        return OAuthUser(
            subject=str(open_id),
            nickname=info.get("nickname") or "抖音用户",
            # avatar_larger 是 800x800，avatar 是 168x168，优先用大的
            avatar=info.get("avatar_larger") or info.get("avatar"),
            email=None,  # 抖音不提供邮箱
            union_id=info.get("union_id"),
            raw=info,
            access_token=token,
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
        )

    @staticmethod
    def _data(resp: httpx.Response, action: str) -> dict:
        """拆抖音的 {data: {...}, message: "..."} 外壳，并把 error_code 转成异常。"""
        try:
            payload = resp.json()
        except ValueError as exc:
            raise OAuthError(f"抖音{action}返回了无法解析的内容") from exc

        data = payload.get("data") or {}
        err_code = data.get("error_code")
        # 0 或缺失都当成功：userinfo 接口成功时不带 error_code
        if err_code not in (None, 0):
            reason = data.get("description") or payload.get("message") or "未知错误"
            raise OAuthError(f"抖音{action}失败：{reason}（error_code={err_code}）")
        return data
