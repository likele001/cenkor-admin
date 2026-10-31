"""Jinja2 沙箱引擎（CMS 主题体系）

三层防护：
1. 属性访问：`_` 前缀与 Jinja 内部属性一律拒绝，callable 属性不可读
2. 调用：只有打了 ``__cms_api__`` 标记的白名单函数和 ``{% macro %}`` 可调用
3. globals：清空内置，只保留业务注入；``range`` 限流，``*`` 运算限长

渲染隔离开在 apps/cms/render.py：executor 线程 + 超时 + 输出上限。
CPU/内存的硬限制需要子进程 + setrlimit，属后续阶段。

模板名解析走 contextvar 注入的 resolver（DB 优先，内置主题兜底），
这样一个 Environment 单例可以同时服务多站点，不会串模板。
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import markdown as _md
from jinja2 import BaseLoader, ChainableUndefined, Template, TemplateNotFound, TemplateSyntaxError
from jinja2.exceptions import SecurityError
from jinja2.runtime import Macro
from jinja2.sandbox import ImmutableSandboxedEnvironment
from jinja2.utils import Namespace
from markupsafe import Markup

__all__ = [
    "CmsLoader",
    "CmsSandbox",
    "TemplateSyntaxError",
    "clear_template_cache",
    "get_env",
    "get_template_meta",
    "is_safe_template_name",
    "render_source",
    "render_template_file",
    "set_resolver",
    "validate_source",
]

# ---------------------------------------------------------------- 常量

MAX_OUTPUT_BYTES = 2 * 1024 * 1024      # 单页输出上限 2MB
MAX_RANGE = 10000                       # range() 上限，挡住死循环
MAX_CACHE_ENTRIES = 600

# 模板源解析器：name -> 源码；None 表示不存在
SourceResolver = Callable[[str], "str | None"]

_resolver: Any = None  # contextvars.ContextVar，延后初始化以免 import 顺序问题
try:
    import contextvars

    _resolver = contextvars.ContextVar("cms_tpl_resolver", default=None)
except Exception:  # pragma: no cover
    pass


# ---------------------------------------------------------------- 模板名校验

_NAME_RE = re.compile(r"^[A-Za-z0-9_\-./]+\.(?:html|xml|txt|json|css|js)$")


def is_safe_template_name(name: str) -> bool:
    """只允许主题内的相对路径，拒绝穿越、绝对路径、隐藏文件。"""
    if not name or len(name) > 255:
        return False
    if name.startswith(("/", "\\")) or "\\" in name or ".." in name or "\x00" in name:
        return False
    if not _NAME_RE.match(name):
        return False
    return all(part and not part.startswith("_") for part in name.split("/"))


# ---------------------------------------------------------------- Loader


class CmsLoader(BaseLoader):
    """按 contextvar 里的 resolver 取模板，用于 extends / include / import。"""

    def get_source(self, environment, template):
        if not is_safe_template_name(template):
            raise TemplateNotFound(template)
        var = _resolver
        resolver = var.get() if var is not None else None
        if resolver is None:
            raise TemplateNotFound(template)
        source = resolver(template)
        if source is None:
            raise TemplateNotFound(template)
        # 缓存交给上层（get_template 按源码 md5 缓存），这里声明永不过期即可
        return source, template, lambda: True


# ---------------------------------------------------------------- 沙箱


class CmsSandbox(ImmutableSandboxedEnvironment):
    """用户模板运行环境。"""

    intercepted_binops = frozenset({"*"})

    # ---- 属性：挡住下划线 / callable
    def is_safe_attribute(self, obj: Any, attr: str, value: Any) -> bool:
        if not super().is_safe_attribute(obj, attr, value):
            return False
        return not callable(value)

    # ---- 调用：只放行白名单 API 和宏
    def is_safe_callable(self, obj: Any) -> bool:
        if getattr(obj, "__cms_api__", False):
            return True
        return bool(isinstance(obj, Macro))

    # ---- 乘法：挡住 `'x' * 10**9` 这种一次分配撑爆内存
    def call_binop(self, context, operator, left, right):
        if operator == "*":
            n = right if isinstance(right, int) else (left if isinstance(left, int) else None)
            seq = left if isinstance(right, int) else right
            if (
                isinstance(n, int) and n > 0
                and isinstance(seq, (str, bytes, list, tuple))
                and len(seq) * n > MAX_OUTPUT_BYTES
            ):
                raise SecurityError("输出过大：乘法结果超过上限")
        return super().call_binop(context, operator, left, right)


# ---------------------------------------------------------------- 过滤器


def _to_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _f_date(value: Any, fmt: str = "%Y-%m-%d") -> str:
    dt = _to_dt(value)
    if dt is None:
        return str(value) if value not in (None, "") else ""
    try:
        return dt.strftime(fmt)
    except Exception:
        return str(value)


def _f_date_iso(value: Any) -> str:
    dt = _to_dt(value)
    return dt.isoformat() if dt else ""


def _f_timesince(value: Any) -> str:
    dt = _to_dt(value)
    if dt is None:
        return ""
    now = datetime.now(tz=dt.tzinfo or UTC)
    secs = int((now - dt).total_seconds())
    if secs < 0:
        return _f_timesince_future(-secs)
    for unit, size in (("年", 31536000), ("个月", 2592000), ("天", 86400),
                       ("小时", 3600), ("分钟", 60)):
        if secs >= size:
            return f"{secs // size} {unit}前"
    return "刚刚"


def _f_timesince_future(secs: int) -> str:
    for unit, size in (("年", 31536000), ("个月", 2592000), ("天", 86400),
                       ("小时", 3600), ("分钟", 60)):
        if secs >= size:
            return f"{secs // size} {unit}后"
    return "即将"


def _f_markdown(text: Any) -> Markup:
    if not text:
        return Markup("")
    html = _md.markdown(
        str(text),
        extensions=["fenced_code", "tables", "sane_lists"],
        output_format="html",
    )
    return Markup(html)


def _f_currency(value: Any, symbol: str = "¥") -> str:
    try:
        return f"{symbol}{float(value or 0):,.2f}"
    except (TypeError, ValueError):
        return f"{symbol}0.00"


def _f_number_format(value: Any, decimal: int = 0) -> str:
    try:
        return f"{float(value or 0):,.{decimal}f}"
    except (TypeError, ValueError):
        return "0"


def _f_asset_url(path: Any) -> str:
    if not path:
        return ""
    p = str(path)
    if p.startswith(("http://", "https://", "//", "data:")):
        return p
    return p if p.startswith("/") else f"/{p}"


def _f_thumb(url: Any, size: str = "300x200") -> str:
    if not url:
        return ""
    u = str(url)
    if "?" in u:
        return f"{u}&resize={size}"
    return f"{u}?resize={size}"


def _f_reading_time(text: Any) -> int:
    if not text:
        return 0
    plain = re.sub(r"<[^>]+>", "", str(text))
    return max(1, round(len(plain) / 500))


def _f_slugify(text: Any) -> str:
    from slugify import slugify as _s

    try:
        return _s(str(text or ""))
    except Exception:
        return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")


def _f_excerpt(text: Any, length: int = 160) -> str:
    plain = re.sub(r"<[^>]+>", "", str(text or ""))
    plain = re.sub(r"\s+", " ", plain).strip()
    col = plain[:length]
    return col + "…" if len(plain) > length else col


def _f_striptags(text: Any) -> str:
    return re.sub(r"<[^>]+>", "", str(text or ""))


def _f_truncate_words(text: Any, count: int = 30, suffix: str = "…") -> str:
    words = str(text or "").split()
    if len(words) <= count:
        return " ".join(words)
    return " ".join(words[:count]) + suffix


_TRANSLATIONS = {
    "enterprise": "企业应用",
    "ai": "AI 应用",
    "manufacturing": "智能制造",
    "article": "文章",
    "product": "产品",
    "news": "新闻",
    "case": "案例",
}


def _f_t(value: Any) -> str:
    if value is None:
        return ""
    return _TRANSLATIONS.get(str(value), str(value))


def _f_highlight(text: Any, keyword: Any) -> Markup:
    raw = str(text or "")
    kw = str(keyword or "").strip()
    if not kw:
        return Markup(_escape(raw))
    safe = _escape(raw)
    return Markup(re.sub(re.escape(_escape(kw)), f"<mark>{_escape(kw)}</mark>", safe, flags=re.I))


def _escape(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _f_to_json_safe(value: Any) -> Markup:
    """脚本内嵌用：转义 < / > & 防提前闭合 script。"""
    dumped = json.dumps(value, ensure_ascii=False, default=str)
    dumped = dumped.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return Markup(dumped)


def _safe_range(*args: Any):
    try:
        r = range(*args)
    except TypeError as exc:
        raise SecurityError(f"range 参数非法: {exc}") from exc
    if len(r) > MAX_RANGE:
        raise SecurityError(f"range 上限 {MAX_RANGE}，模板里的循环次数太多")
    return r


def _safe_dict(*args: Any, **kwargs: Any):
    return dict(*args, **kwargs)


def _safe_namespace(**kwargs: Any):
    return Namespace(**kwargs)


# 这三个是模板可调的内置助手，走和业务 API 同一套白名单标记。
# 直接给内置 dict 打属性会失败（不可变类型），所以统一用包装函数。
for _fn in (_safe_range, _safe_dict, _safe_namespace):
    _fn.__cms_api__ = True  # type: ignore[attr-defined]


def _register_filters(env: CmsSandbox) -> None:
    env.filters.update({
        "date": _f_date,
        "date_iso": _f_date_iso,
        "timesince": _f_timesince,
        "markdown": _f_markdown,
        "md": _f_markdown,
        "currency": _f_currency,
        "format_price": _f_currency,
        "number_format": _f_number_format,
        "asset_url": _f_asset_url,
        "thumb": _f_thumb,
        "reading_time": _f_reading_time,
        "slugify": _f_slugify,
        "excerpt": _f_excerpt,
        "striptags": _f_striptags,
        "truncate_words": _f_truncate_words,
        "t": _f_t,
        "trans": _f_t,
        "highlight": _f_highlight,
        "json_safe": _f_to_json_safe,
    })


# ---------------------------------------------------------------- 环境与缓存

_ENV: CmsSandbox | None = None
_TEMPLATE_CACHE: dict[str, Template] = {}
_CACHE_LOCK = threading.Lock()


def get_env() -> CmsSandbox:
    global _ENV
    if _ENV is None:
        env = CmsSandbox(
            loader=CmsLoader(),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
            undefined=_make_undefined(),
            auto_reload=False,
        )
        _register_filters(env)
        # 只留安全的内置助手，range 换限流版
        env.globals.clear()
        env.globals.update({
            "range": _safe_range,
            "dict": _safe_dict,
            "namespace": _safe_namespace,
        })
        _ENV = env
    return _ENV


def _make_undefined():
    """链式缺失不炸（{{ a.b.c }} 打印为空），但真实错误仍然暴露。

    用 ChainableUndefined 而不是 StrictUndefined：用户模板里
    ``{{ item.seo.title }}`` 而 seo 为 None 时不该整页 500。
    """
    return ChainableUndefined


def set_resolver(resolver: SourceResolver):
    """在当前上下文绑定模板源解析器，返回 token 供 reset。"""
    var = _resolver
    if var is None:  # pragma: no cover
        raise RuntimeError("contextvars 不可用")
    return var.set(resolver)


def reset_resolver(token) -> None:
    var = _resolver
    if var is not None:
        var.reset(token)


def clear_template_cache() -> None:
    with _CACHE_LOCK:
        _TEMPLATE_CACHE.clear()
    if _ENV is not None:
        _ENV.cache.clear()


def _compile(source: str, name: str = "<template>") -> Template:
    key = hashlib.sha1(f"{name}\x00{source}".encode()).hexdigest()
    tpl = _TEMPLATE_CACHE.get(key)
    if tpl is not None:
        return tpl
    with _CACHE_LOCK:
        tpl = _TEMPLATE_CACHE.get(key)
        if tpl is None:
            tpl = get_env().from_string(source)
            if len(_TEMPLATE_CACHE) > MAX_CACHE_ENTRIES:
                _TEMPLATE_CACHE.clear()
            _TEMPLATE_CACHE[key] = tpl
    return tpl


def render_source(source: str, context: dict[str, Any], *, name: str = "<template>") -> str:
    """渲染模板源码，返回字符串。异常原样抛出由上层处理。"""
    tpl = _compile(source, name)
    # Jinja globals 里已有 range 等，业务上下文单独传
    out = tpl.render(**context)
    if len(out.encode()) > MAX_OUTPUT_BYTES:
        raise SecurityError("页面输出超过 2MB 上限")
    return out


def render_template_file(name: str, context: dict[str, Any]) -> str:
    """按名字取模板（走 resolver）并渲染。"""
    var = _resolver
    resolver = var.get() if var is not None else None
    if resolver is None:
        raise TemplateNotFound(name)
    source = resolver(name)
    if source is None:
        raise TemplateNotFound(name)
    return render_source(source, context, name=name)


def validate_source(source: str, *, name: str = "<template>") -> tuple[bool, dict[str, Any] | None]:
    """校验语法。返回 (ok, error)；error 含 line/col/message，供编辑器定位。"""
    if not source or not source.strip():
        return True, None
    env = get_env()
    try:
        env.from_string(source)
        return True, None
    except TemplateSyntaxError as exc:
        return False, {
            "message": exc.message or str(exc),
            "line": exc.lineno or 1,
            "col": 1,
            "type": "syntax",
        }
    except SecurityError as exc:
        return False, {"message": str(exc), "line": 1, "col": 1, "type": "security"}
    except Exception as exc:
        return False, {"message": str(exc), "line": 1, "col": 1, "type": "unknown"}


def get_template_meta(source: str) -> dict[str, Any]:
    """粗提模板里引用的变量/模板/过滤器，给编辑器做提示用。"""
    extends = re.findall(r"{%-?\s*extends\s+[\"']([^\"']+)[\"']", source)
    includes = re.findall(r"{%-?\s*(?:include|import|from)\s+[\"']([^\"']+)[\"']", source)
    blocks = re.findall(r"{%-?\s*block\s+([A-Za-z0-9_]+)", source)
    return {"extends": extends, "includes": includes, "blocks": blocks}
