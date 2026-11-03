"""SSO · 渠道适配器基类。

设计原则（为什么这么切）：

**provider 只管「从第三方换出用户信息」这一件事。**
它不碰数据库、不碰用户表、不签发 token、不关心是前台还是后台。
落库与发 token 归 realm（见 ``apps/sso/store.py``）。

把「哪个渠道」和「哪套账号体系」拆成两个正交维度后：
- 加渠道 = 在 ``providers/`` 丢一个类，不用动任何路由；
- 加端（比如以后给开发者门户开登录）= 加一个 AccountStore，不用动任何渠道。

反面教材就是改造前的代码：飞书 OAuth 在 admin 和 portal 的 router 里各抄了
80 行，加 4 个渠道就是 8 份复制代码。
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode


@dataclass(slots=True)
class ProviderConfig:
    """单个渠道的运行期配置（来自 ``system_settings``，secret 已在读取时解密）。"""

    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    # 渠道特有字段，如抖音的 client_key 与 client_secret 语义不同、
    # 微信服务号的网页授权需要额外 scope 等。统一塞 extra，避免基类膨胀。
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def configured(self) -> bool:
        """两个凭证都填了才算配好。缺一个就当我没配，别让用户跳到第三方的报错页。"""
        return bool(self.client_id and self.client_secret)


@dataclass(slots=True)
class OAuthUser:
    """渠道返回的规范化用户信息。

    ``subject`` 是唯一身份锚点，各渠道对应不同字段：
    微信 openid / 抖音 open_id / Google sub / GitHub id / 飞书 open_id。
    """

    subject: str
    nickname: str = ""
    avatar: str | None = None
    email: str | None = None
    union_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    access_token: str | None = None
    refresh_token: str | None = None
    expires_in: int | None = None


class OAuthError(RuntimeError):
    """渠道返回的业务错误（区别于网络异常）。

    消息会透到前端，所以**绝不能把 client_secret 拼进去**。渠道返回的原始
    errmsg 可能包含 appid 等半敏感信息，这里只保留可读的错误描述。
    """


class OAuthProvider(abc.ABC):
    """渠道适配器基类。子类只需实现 authorize_url 与 exchange。"""

    key: str = ""
    name: str = ""
    icon: str = "🔗"
    scopes: tuple[str, ...] = ()
    # 是否支持 PKCE。微信、抖音开放平台不支持，硬套会拿不到 code。
    supports_pkce: bool = False
    # 登录页展示顺序，数字小的靠前
    order: int = 100
    # 一句话说明，后台配置页展示
    note: str = ""

    @abc.abstractmethod
    def authorize_url(
        self,
        cfg: ProviderConfig,
        redirect_uri: str,
        state: str,
        code_challenge: str | None = None,
    ) -> str:
        """拼授权页地址。必须是纯函数，不发请求。"""

    @abc.abstractmethod
    async def exchange(
        self,
        cfg: ProviderConfig,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> OAuthUser:
        """用 code 换 token，再换用户信息。任何失败抛 OAuthError。"""

    def extra_fields(self) -> list[dict[str, Any]]:
        """渠道特有配置项，供后台配置页自动渲染。

        返回结构::

            [{
              "key": "mode",
              "label": "接入模式",
              "type": "select",            # text / select / checkbox 三种
              "default": "qrconnect",
              "options": [{"value": "...", "label": "..."}],
              "hint": "一句话说明",
            }]

        为什么要做成声明式：微信要选扫码还是公众号授权、Google 要选是否申请
        离线访问 —— 如果这些差异写进前端模板，加渠道就得改前端。交给渠道
        自己声明，前端只按 type 渲染三种控件即可。
        """
        return []

    @staticmethod
    def _q(url: str, params: dict[str, Any]) -> str:
        """拼 query。空值一律丢掉——第三方对空参数比缺参数更挑剔。"""
        clean = {k: v for k, v in params.items() if v not in (None, "")}
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}{urlencode(clean)}"


__all__ = ["OAuthError", "OAuthProvider", "OAuthUser", "ProviderConfig"]
