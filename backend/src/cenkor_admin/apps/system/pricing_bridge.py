"""应用价格视图的跨源码边界桥接（**公开侧**）。

为什么需要它
------------
应用商店的公开接口（``store_router.public_store_apps`` / ``public_store_app_detail``）
属 **公开源码**，而定价数据与「生效价 / 促销状态」的计算属 **闭源 commerce 应用** ——
公开侧不得 import 闭源，否则公开仓库无法独立运行。

做法
----
公开侧只在这里声明**契约**（一个注册点）：

- 装了 commerce：闭源在模块加载时把自己的实现注册进来，商店接口即可展示价格；
- 纯开源部署：``price_map()`` 返回空 dict，接口**静默降级** —— 不报错、只是不显示价格。

这与 ``core/hooks.py`` 的事件钩子同一思路（公开侧定契约、实现留在闭源侧），
也是本项目既有的跨边界解耦手法：``store_router.submit_app`` 派发 ``app.submitted``
事件，由闭源 ``commerce/hooks.py`` 订阅落库定价。

安全约束（重要）
----------------
provider **只能**返回买家可见的字段（价格、折扣、促销展示信息）。
``developer_id`` / 平台扣点 / 分账金额等经营数据 **一律不得从这里出去** ——
商店接口是 **匿名可访问** 的公开接口。
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Mapping, Sequence

import structlog

log = structlog.get_logger()

# 契约：async (db: AsyncSession, app_keys: Sequence[str]) -> {app_key: 价格视图 dict}
PriceMapProvider = Callable[[Any, Sequence[str]], Awaitable[Mapping[str, dict[str, Any]]]]

_provider: PriceMapProvider | None = None


def register_price_map_provider(fn: PriceMapProvider) -> None:
    """注册价格视图提供者（由闭源 commerce 在模块加载时调用）。

    Args:
        fn: 满足 ``PriceMapProvider`` 契约的异步函数。

    Note:
        重复注册（如模块被 reload）是幂等的：后注册的覆盖先注册的。
    """
    global _provider
    _provider = fn
    log.info("pricing_bridge.provider_registered",
             fn=getattr(fn, "__qualname__", repr(fn)))


def unregister_price_map_provider() -> None:
    """注销提供者，回退为「不展示价格」状态（供 commerce 卸载时调用）。"""
    global _provider
    _provider = None
    log.info("pricing_bridge.provider_unregistered")


def is_registered() -> bool:
    """当前是否已有提供者（供健康检查与测试断言使用）。"""
    return _provider is not None


async def price_map(db: Any, app_keys: Sequence[str]) -> dict[str, dict[str, Any]]:
    """批量取应用价格视图。

    价格属 **展示性数据**：任何异常都不应让商店列表整页失败，
    因此这里吞掉异常、返回空 dict 并记 warning。

    Args:
        db: 数据库会话。
        app_keys: 应用标识序列（重复项自动去重）。

    Returns:
        ``{app_key: 价格视图}``。无提供者或取数失败时返回 ``{}``；
        未建定价行的应用 **不出现在结果中** —— 调用方据此判定「免费 / 未定价」。
    """
    keys = [k for k in dict.fromkeys(app_keys) if k]
    if _provider is None or not keys:
        return {}
    try:
        got = await _provider(db, keys)
    except Exception:  # noqa: BLE001 - 展示数据，失败不得影响主流程
        log.warning("pricing_bridge.price_map_failed", count=len(keys), exc_info=True)
        return {}
    return {str(k): dict(v) for k, v in (got or {}).items()}


__all__ = [
    "PriceMapProvider",
    "register_price_map_provider",
    "unregister_price_map_provider",
    "is_registered",
    "price_map",
]
