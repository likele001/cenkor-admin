"""版本号比较：商店目录、市场链路、平台自检共用的一份口径。

放在独立模块而不是任一 router 里，是为了让 ``store_router`` 与 ``market_router``
都能顶层导入 —— ``store_router`` 只在文件末尾才导入 ``market_router``（避循环），
顶层拿不到它里的工具函数。

为什么要统一：此前「有没有新版本」在两处算法不同 —— 商店目录用 ``installed != version``
字符串不等，于是装着 1.10 看到 1.9 也会催你升级（降级被当成升级）；市场链路用数字元组。
同一个「可升级」计数在两个页面上可以对不上号。
"""
from __future__ import annotations

from typing import Any

# 至少补齐到的段数：1.2 与 1.2.0 视为同一版本，不该因为写短了就被判成「更旧」
_MIN_PARTS = 3


def ver_tuple(v: Any) -> tuple[int, ...]:
    """语义化版本 → 可比较元组。非数字段记 0，``-pre``/``+build`` 后缀忽略。"""
    core = str(v or "").strip().split("+", 1)[0].split("-", 1)[0]
    parts: list[int] = []
    for seg in core.split("."):
        num = "".join(ch for ch in seg if ch.isdigit())
        parts.append(int(num) if num else 0)
    while len(parts) < _MIN_PARTS:
        parts.append(0)
    return tuple(parts)


def ver_gt(a: Any, b: Any) -> bool:
    """a 严格新于 b。空/缺值按 0.0.0 处理 —— 催升级要保守，宁可不说。"""
    return ver_tuple(a) > ver_tuple(b)
