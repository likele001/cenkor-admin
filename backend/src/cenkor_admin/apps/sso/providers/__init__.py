"""渠道自动发现。

往本目录丢一个 ``xxx.py``，里面定义 ``OAuthProvider`` 子类（或一个
``PROVIDER = XxxProvider()`` 模块级实例），重启后自动出现在登录页和后台
配置页 —— 不需要改任何路由、不需要改前端、不需要改注册表。

为什么用目录扫描而不是显式 import 列表：显式列表是「加渠道必须改两个文件」，
早晚会有人漏掉第二处。扫描本包目录是 O(1) 维护成本。

失败容忍：某个渠道模块 import 报错（比如少装了依赖）只记 warning 并跳过，
不能让它把整个应用启动打挂 —— 登录页少一个按钮，比整个后台起不来强得多。
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

import structlog

from .base import OAuthError, OAuthProvider, OAuthUser, ProviderConfig

log = structlog.get_logger()

_registry: dict[str, OAuthProvider] | None = None


def _build() -> dict[str, OAuthProvider]:
    found: dict[str, OAuthProvider] = {}
    for mod_info in pkgutil.iter_modules(__path__):
        if mod_info.name.startswith("_") or mod_info.name == "base":
            continue
        try:
            module: ModuleType = importlib.import_module(f"{__name__}.{mod_info.name}")
        except Exception as exc:
            log.warning(
                "sso.provider.import_failed", provider=mod_info.name, error=str(exc)
            )
            continue

        provider = getattr(module, "PROVIDER", None)
        if isinstance(provider, OAuthProvider):
            found[provider.key] = provider
            continue

        # 没显式声明就找子类，取模块内定义的第一个（排除 import 进来的基类）
        for value in vars(module).values():
            if (
                isinstance(value, type)
                and issubclass(value, OAuthProvider)
                and value is not OAuthProvider
                and value.__module__ == module.__name__
            ):
                instance = value()
                found[instance.key] = instance
                break

    return found


def all_providers() -> dict[str, OAuthProvider]:
    """全部可用渠道，按展示顺序排列。结果缓存，重启才刷新。"""
    global _registry
    if _registry is None:
        _registry = _build()
        log.info("sso.providers.loaded", providers=sorted(_registry))
    return dict(sorted(_registry.items(), key=lambda kv: (kv[1].order, kv[1].key)))


def get_provider(key: str) -> OAuthProvider | None:
    return all_providers().get(key)


__all__ = [
    "OAuthError",
    "OAuthProvider",
    "OAuthUser",
    "ProviderConfig",
    "all_providers",
    "get_provider",
]
