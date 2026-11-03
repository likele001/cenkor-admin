"""微信开放平台 / 公众号网页授权。

两种模式，靠 ``extra.mode`` 选（后台配置页有下拉）：

- ``qrconnect``（默认）：PC 网站扫码登录，走 open.weixin.qq.com/connect/qrconnect，
  scope=snsapi_login。需要在「微信开放平台 → 网站应用」里创建应用并通过审核。
- ``oauth2``：公众号内嵌 H5 授权，走 open.weixin.qq.com/connect/oauth2/authorize，
  scope=snsapi_userinfo。需要在「公众号后台 → 网页授权域名」里配置域名。

三个必须记住的坑：

1. **锚点位置**：``#wechat_redirect`` 必须拼在整个 URL 最末尾。用 urlencode
   拼接时它会被转义成 %23 导致页面打不开，所以这里手工追加。
2. **错误也是 200**：微信所有接口都用 ``errcode != 0`` 表示失败，HTTP 状态码
   永远是 200，必须解析 body。
3. **没有邮箱**：微信不给 email，所以前台账号的 email 必须允许为空。
   这也是为什么不能拿 email 做账号唯一锚点。
"""

from __future__ import annotations

import json

import httpx

from .base import OAuthError, OAuthProvider, OAuthUser, ProviderConfig

QRCONNECT_URL = "https://open.weixin.qq.com/connect/qrconnect"
OAUTH2_URL = "https://open.weixin.qq.com/connect/oauth2/authorize"
TOKEN_URL = "https://api.weixin.qq.com/sns/oauth2/access_token"
USERINFO_URL = "https://api.weixin.qq.com/sns/userinfo"


class WechatProvider(OAuthProvider):
    key = "wechat"
    name = "微信"
    icon = "💬"
    scopes = ("snsapi_login",)
    supports_pkce = False  # 微信不支持 PKCE，硬传 code_challenge 会被忽略
    order = 10
    note = "扫码登录（网站应用）或公众号内授权，需微信开放平台网站应用通过审核"

    def authorize_url(
        self,
        cfg: ProviderConfig,
        redirect_uri: str,
        state: str,
        code_challenge: str | None = None,
    ) -> str:
        mode = str(cfg.extra.get("mode") or "qrconnect").lower()
        if mode == "oauth2":
            base = OAUTH2_URL
            scope = str(cfg.extra.get("scope") or "snsapi_userinfo")
            params = {
                "appid": cfg.client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": scope,
                "state": state,
            }
            return self._q(base, params) + "#wechat_redirect"

        params = {
            "appid": cfg.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "snsapi_login",
            "state": state,
        }
        return self._q(QRCONNECT_URL, params) + "#wechat_redirect"

    async def exchange(
        self,
        cfg: ProviderConfig,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> OAuthUser:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                TOKEN_URL,
                params={
                    "appid": cfg.client_id,
                    "secret": cfg.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                },
            )
            data = self._body(r, "换取 token")
            if data.get("errcode"):
                raise OAuthError(
                    f"微信授权失败：{data.get('errmsg') or '未知错误'}"
                    f"（errcode={data.get('errcode')}）"
                )
            token = data.get("access_token")
            openid = data.get("openid")
            if not token or not openid:
                raise OAuthError("微信未返回 access_token 或 openid")

            ru = await client.get(
                USERINFO_URL,
                params={"access_token": token, "openid": openid, "lang": "zh_CN"},
            )
            info = self._body(ru, "读取用户信息")
            if info.get("errcode"):
                raise OAuthError(
                    f"微信读取用户信息失败：{info.get('errmsg') or '未知错误'}"
                )

        return OAuthUser(
            subject=str(openid),
            # 微信昵称含 emoji 和生僻字，原样存，前端渲染即可
            nickname=info.get("nickname") or "微信用户",
            avatar=info.get("headimgurl"),
            email=None,  # 微信不提供邮箱
            union_id=info.get("unionid") or data.get("unionid"),
            raw=info,
            access_token=token,
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
        )

    @staticmethod
    def _body(resp: httpx.Response, action: str) -> dict:
        """微信 body 是 JSON 但 Content-Type 常写成 text/plain，不能靠 resp.json()。

        昵称含中文时必须按 UTF-8 解码，requests 的默认猜测会出乱码。
        """
        try:
            return json.loads(resp.content.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise OAuthError(f"微信{action}返回了无法解析的内容") from exc

    def extra_fields(self) -> list[dict]:
        return [{
            "key": "mode",
            "label": "接入模式",
            "type": "select",
            "default": "qrconnect",
            "options": [
                {"value": "qrconnect", "label": "网站扫码登录（微信开放平台网站应用）"},
                {"value": "oauth2", "label": "公众号内 H5 授权（服务号）"},
            ],
            "hint": "扫码需网站应用审核通过；公众号授权需在公众号后台配置「网页授权域名」",
        }]
