"""插件运行时扩展框架：统一的事件钩子注册表。

让已安装的 App（含内置 core）能在核心流程（内容保存、类型创建、媒体上传、
用户登录等）中注入自定义逻辑，而不必修改核心代码。

设计要点：
- 全局单例 ``registry``，进程内有效（多 worker 各自独立，满足单实例 CMS 场景）。
- ``@hook("entry.saved")`` 装饰器在模块被 import 时注册 handler。
- ``dispatch(hook, **payload)`` 触发订阅者，**失败隔离**：单个 handler 异常只记日志，
  不影响主流程与其余 handler。
- ``clear_app(app_key)`` 在 App 卸载时清掉其全部 handler，避免泄漏/重复触发。
"""
from __future__ import annotations

import importlib
import inspect
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Union

log = logging.getLogger(__name__)

# 同步或异步处理函数
HookHandler = Callable[..., Union[None, Awaitable[None]]]


@dataclass
class _RegisteredHandler:
    name: str
    hook: str
    fn: HookHandler
    app_key: str | None = None
    priority: int = 50


class HookRegistry:
    """全局钩子注册表（单例）。"""

    def __init__(self) -> None:
        self._handlers: dict[str, list[_RegisteredHandler]] = {}

    # ---- 注册 ----
    def register(
        self,
        hook: str,
        fn: HookHandler,
        *,
        app_key: str | None = None,
        priority: int = 50,
        name: str | None = None,
    ) -> None:
        handler = _RegisteredHandler(
            name=name or getattr(fn, "__name__", f"h{id(fn)}"),
            hook=hook,
            fn=fn,
            app_key=app_key,
            priority=priority,
        )
        self._handlers.setdefault(hook, []).append(handler)
        # 同钩子内按优先级升序执行（数字越小越先）
        self._handlers[hook].sort(key=lambda h: h.priority)
        log.debug("hook.registered", hook=hook, handler=handler.name, app=app_key)

    def hook(self, hook: str, *, app_key: str | None = None, priority: int = 50):
        """装饰器：``@hooks.hook("entry.saved", app_key="myapp")``。"""

        def deco(fn: HookHandler) -> HookHandler:
            self.register(hook, fn, app_key=app_key, priority=priority)
            return fn

        return deco

    # ---- 查询 ----
    def handlers_for(self, hook: str) -> list[_RegisteredHandler]:
        return list(self._handlers.get(hook, []))

    def all_hooks(self) -> dict[str, list[dict[str, Any]]]:
        """返回 {hook: [{name, app_key, priority}]}，供后台可视化。"""
        out: dict[str, list[dict[str, Any]]] = {}
        for hook, lst in self._handlers.items():
            out[hook] = [
                {"name": h.name, "app_key": h.app_key, "priority": h.priority}
                for h in lst
            ]
        return out

    # ---- 清理 ----
    def clear_app(self, app_key: str) -> int:
        """卸载某 App 的全部钩子，返回移除数量。"""
        removed = 0
        for hook, lst in self._handlers.items():
            before = len(lst)
            self._handlers[hook] = [h for h in lst if h.app_key != app_key]
            removed += before - len(self._handlers[hook])
        if removed:
            log.info("hook.cleared_app", app=app_key, removed=removed)
        return removed

    # ---- 触发 ----
    async def dispatch(self, hook: str, **payload: Any) -> list[Any]:
        """触发某事件的所有订阅者。

        失败隔离：单个 handler 抛异常只记 warning，不影响主流程与其余 handler。
        返回各 handler 的执行结果列表（按注册顺序）。
        """
        results: list[Any] = []
        for h in self.handlers_for(hook):
            try:
                if inspect.iscoroutinefunction(h.fn):
                    res = await h.fn(**payload)
                else:
                    res = h.fn(**payload)
                results.append(res)
            except Exception as e:  # noqa: BLE001 - 故意隔离 handler 异常
                log.warning(
                    "hook.handler_failed",
                    hook=hook,
                    handler=h.name,
                    app=h.app_key,
                    error=str(e),
                )
        return results


# 全局单例
registry = HookRegistry()


def hook(hook: str, *, app_key: str | None = None, priority: int = 50):
    """模块级便捷装饰器。"""
    return registry.hook(hook, app_key=app_key, priority=priority)


async def dispatch(hook: str, **payload: Any) -> list[Any]:
    """模块级便捷触发。"""
    return await registry.dispatch(hook, **payload)


def register_app_hooks(app_key: str, module_paths: list[str] | None = None) -> int:
    """导入（并强制重载）某 App 的钩子模块，使其 ``@hook`` 装饰器重新注册。

    - 先 ``clear_app`` 清掉旧注册，避免重装导致重复。
    - ``module_paths`` 为空时默认尝试 ``cenkor_admin.apps.{app_key}.hooks``。
    返回新注册的 handler 数量。
    """
    registry.clear_app(app_key)
    candidates = list(module_paths or [])
    candidates.append(f"cenkor_admin.apps.{app_key}.hooks")
    registered = 0
    for mod_path in candidates:
        try:
            mod = importlib.import_module(mod_path)
            importlib.reload(mod)  # 强制重跑模块级装饰器
            registered += 1
        except ModuleNotFoundError:
            continue
        except Exception as e:  # noqa: BLE001
            log.warning("app.hooks_import_failed", key=app_key, module=mod_path, error=str(e))
    return registered
