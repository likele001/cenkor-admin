"""Liquid 模板引擎封装（前后端一致 liquidjs / python-liquid）

使用方式：
    from cenkor_admin.core.template_engine import render_template, validate_template

    result = render_template('Hello {{ name }}!', {'name': 'World'})
    valid, error = validate_template('{{ invalid ')
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import markdown as md
from liquid import Environment, StrictUndefined
from liquid.exceptions import LiquidError


# ============================================================
# 引擎实例（单例）
# ============================================================

def _create_env() -> Environment:
    env = Environment()
    _register_filters(env)
    return env


_ENV: Environment | None = None


def get_env() -> Environment:
    global _ENV
    if _ENV is None:
        _ENV = _create_env()
    return _ENV


# ============================================================
# Filters 注册
# ============================================================

def _register_filters(env: Environment) -> None:
    """注册内置 filters + 业务 filters"""

    # ---- 字符串 ----
    env.add_filter("upcase", lambda s: str(s).upper() if s is not None else "")
    env.add_filter("downcase", lambda s: str(s).lower() if s is not None else "")
    env.add_filter("capitalize", lambda s: str(s).capitalize() if s is not None else "")

    def _truncate(s: str, length: int = 100, suffix: str = "...") -> str:
        s = str(s) if s is not None else ""
        if len(s) <= length:
            return s
        return s[:length].rstrip() + suffix

    env.add_filter("truncate", _truncate)
    env.add_filter("append", lambda s, suffix="": str(s or "") + str(suffix))
    env.add_filter("prepend", lambda s, prefix="": str(prefix) + str(s or ""))
    env.add_filter("strip", lambda s: str(s).strip() if s is not None else "")
    env.add_filter("lstrip", lambda s: str(s).lstrip() if s is not None else "")
    env.add_filter("rstrip", lambda s: str(s).rstrip() if s is not None else "")

    def _slice(s: str, start: int = 0, length: int | None = None) -> str:
        s = str(s) if s is not None else ""
        if length is None:
            return s[start:]
        return s[start:start + length]

    env.add_filter("slice", _slice)

    def _replace(s: str, old: str, new: str = "", count: int = -1) -> str:
        if s is None:
            return ""
        return str(s).replace(old, new, count)

    env.add_filter("replace", _replace)
    env.add_filter("remove", lambda s, sub="": _replace(s, sub, ""))

    # ---- 转义 ----
    env.add_filter("escape", lambda s: str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))
    env.add_filter("strip_html", lambda s: re.sub(r"<[^>]+>", "", str(s or "")))

    # ---- 日期 ----
    def _date(value: Any, fmt: str = "%Y-%m-%d") -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except Exception:
                return value
        if not isinstance(value, datetime):
            return str(value)
        try:
            return value.strftime(fmt)
        except Exception:
            return str(value)

    env.add_filter("date", _date)

    # ---- 数字 / 货币 ----
    def _currency(value, symbol: str = "¥", default: str = "0.00") -> str:
        try:
            v = float(value or 0)
            return f"{symbol}{v:,.2f}"
        except (TypeError, ValueError):
            return f"{symbol}{default}"

    env.add_filter("currency", _currency)
    env.add_filter("abs", lambda v: abs(float(v or 0)))

    def _round(v, precision: int = 0, method: str = "common"):
        try:
            f = float(v or 0)
            if method == "floor":
                import math
                return math.floor(f * 10 ** precision) / 10 ** precision
            if method == "ceil":
                import math
                return math.ceil(f * 10 ** precision) / 10 ** precision
            return round(f, precision)
        except (TypeError, ValueError):
            return 0

    env.add_filter("round", _round)

    # ---- 数组 ----
    env.add_filter("size", lambda x: len(x) if x is not None else 0)
    env.add_filter("first", lambda x: x[0] if x and len(x) > 0 else None)
    env.add_filter("last", lambda x: x[-1] if x and len(x) > 0 else None)

    def _join(arr, sep: str = ", ") -> str:
        if not arr:
            return ""
        return sep.join(str(x) for x in arr)

    env.add_filter("join", _join)

    def _uniq(arr):
        if not arr:
            return []
        seen = []
        for x in arr:
            if x not in seen:
                seen.append(x)
        return seen

    env.add_filter("uniq", _uniq)

    def _sort(arr, key: str | None = None, reverse: bool = False):
        if not arr:
            return []
        if key and arr and isinstance(arr[0], dict):
            result = sorted(arr, key=lambda x: x.get(key, ""), reverse=reverse)
        else:
            result = sorted(arr, reverse=reverse)
        return result

    env.add_filter("sort", _sort)

    def _map(arr, key: str):
        if not arr:
            return []
        return [x.get(key) for x in arr if isinstance(x, dict)]

    env.add_filter("map", _map)

    def _where(arr, key: str, value: Any = None):
        if not arr:
            return []
        if value is None:
            return [x for x in arr if isinstance(x, dict) and x.get(key)]
        return [x for x in arr if isinstance(x, dict) and x.get(key) == value]

    env.add_filter("where", _where)

    def _compact(arr):
        if not arr:
            return []
        return [x for x in arr if x not in (None, "", 0, False, [], {})]

    env.add_filter("compact", _compact)

    def _reverse(arr):
        if not arr:
            return []
        return list(reversed(arr))

    env.add_filter("reverse", _reverse)

    # ---- 序列化 ----
    import json
    env.add_filter("json", lambda v: json.dumps(v, ensure_ascii=False, default=str))

    # ---- Markdown ----
    def _markdown(text: str) -> str:
        if not text:
            return ""
        return md.markdown(
            str(text),
            extensions=["fenced_code", "tables", "sane_lists"],
            output_format="html",
        )

    env.add_filter("markdown", _markdown)

    # ---- 默认值 ----
    def _default(v, fallback=""):
        if v is None or v == "" or v == [] or v == {}:
            return fallback
        return v

    env.add_filter("default", _default)

    # ============================================================
    # 业务自定义 filters
    # ============================================================

    # t：i18n 翻译（业务线中文名等）
    _I18N_MAP: dict[str, str] = {
        "enterprise": "企业应用",
        "ai": "AI 应用",
        "manufacturing": "智能制造",
    }

    def _t(value: str) -> str:
        if value is None:
            return ""
        return _I18N_MAP.get(str(value), str(value))

    env.add_filter("t", _t)

    # format_price：价格格式化（带千分位 + 货币符号）
    def _format_price(value, currency: str = "¥") -> str:
        try:
            v = float(value or 0)
            return f"{currency}{v:,.2f}"
        except (TypeError, ValueError):
            return f"{currency}0.00"

    env.add_filter("format_price", _format_price)

    # asset_url：资源 URL 补全（相对路径 → 完整 URL）
    _CDN_BASE = ""

    def _asset_url(path: str) -> str:
        if not path:
            return ""
        if path.startswith(("http://", "https://", "//")):
            return path
        if path.startswith("/"):
            return _CDN_BASE + path
        return _CDN_BASE + "/" + path

    env.add_filter("asset_url", _asset_url)

    # thumb：缩略图 URL（占位实现，约定 key 规则）
    def _thumb(url: str, size: str = "300x200") -> str:
        if not url:
            return ""
        if "?" in url:
            return f"{url}&resize={size}"
        return f"{url}?resize={size}"

    env.add_filter("thumb", _thumb)

    # reading_time：估算阅读时长（分钟，按 500 字/分钟）
    def _reading_time(content: str) -> int:
        if not content:
            return 0
        # 去除 HTML 标签
        text = re.sub(r"<[^>]+>", "", str(content))
        # 中英文按字符计
        return max(1, round(len(text) / 500))

    env.add_filter("reading_time", _reading_time)

    # 数字格式（千分位）
    def _number_format(value, decimal: int = 0) -> str:
        try:
            return f"{float(value or 0):,.{decimal}f}"
        except (TypeError, ValueError):
            return "0"

    env.add_filter("number_format", _number_format)


# ============================================================
# 渲染 API
# ============================================================

def render_template(template: str, data: dict | None = None) -> str:
    """渲染 Liquid 模板

    Args:
        template: Liquid 模板字符串
        data: 数据字典

    Returns:
        渲染后的字符串

    Raises:
        ValueError: 模板语法错误
    """
    if not template:
        return ""
    env = get_env()
    try:
        tpl = env.from_string(template)
        return tpl.render(**(data or {}))
    except LiquidError as e:
        raise ValueError(f"模板渲染失败: {e}")


def render_template_safe(template: str, data: dict | None = None) -> tuple[str, str | None]:
    """安全渲染（捕获异常）

    Returns:
        (rendered, error)
    """
    try:
        return render_template(template, data), None
    except Exception as e:
        return "", str(e)


def validate_template(template: str) -> tuple[bool, str | None]:
    """校验模板语法

    Returns:
        (valid, error_message)
    """
    if not template:
        return True, None
    try:
        env = get_env()
        env.from_string(template)
        return True, None
    except Exception as e:
        return False, str(e)


def inject_globals(data: dict, *, site: dict | None = None, current_user: dict | None = None, request: dict | None = None) -> dict:
    """注入全局变量

    在用户提供的 data 基础上注入：
    - now: 当前时间
    - site: 站点配置
    - theme: 主题配置（默认空）
    - current_user: 当前用户
    - request: 请求上下文
    """
    globals_ = {
        "now": datetime.now().isoformat(),
        "site": site or {},
        "theme": {},
        "current_user": current_user,
        "request": request or {},
    }
    globals_.update(data or {})
    return globals_


__all__ = [
    "render_template",
    "render_template_safe",
    "validate_template",
    "inject_globals",
    "get_env",
]
