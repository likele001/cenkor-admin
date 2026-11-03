"""Cenkor SSO · 可插拔第三方登录。

结构::

    providers/         每个渠道一个文件，丢进来即生效
      base.py          OAuthProvider 抽象 + OAuthUser + ProviderConfig
      wechat.py  douyin.py  feishu.py  google.py  github.py
    config.py          system_settings 读写（secret 走 core.secrets 加密）
    state.py           state / PKCE / ticket 三个一次性凭证
    store.py           AccountStore：按 realm 落库发 token
    router.py          public_router（匿名）+ router（管理）
    manifest.py        AppManifest，供应用中心装/卸/停

加一个渠道要做的全部事情：在 ``providers/`` 里加一个文件。
不用改路由、不用改前端、不用改这个 __init__.py。
"""

from __future__ import annotations

from . import config, state, store
from .providers import (
    OAuthError,
    OAuthProvider,
    OAuthUser,
    ProviderConfig,
    all_providers,
    get_provider,
)

__all__ = [
    "OAuthError",
    "OAuthProvider",
    "OAuthUser",
    "ProviderConfig",
    "all_providers",
    "config",
    "get_provider",
    "state",
    "store",
]
