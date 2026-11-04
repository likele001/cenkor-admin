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
import structlog
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
    "app_template_filters",
    "app_template_functions",
    "bind_app_function",
    "clear_template_cache",
    "flush_compiled_templates",
    "get_env",
    "get_template_meta",
    "is_safe_template_name",
    "lint_inline_script",
    "register_template_api",
    "render_source",
    "render_template_file",
    "set_resolver",
    "unregister_template_api",
    "validate_source",
    "validate_theme_source",
]

log = structlog.get_logger()

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

        # 过期判断按**源码指纹**，不能返回常量 True。
        # Jinja 的 env 缓存 key 是模板名、不含主题，恒真的 uptodate 会让
        # 换主题后的同名模板（layout.html / list.html）继续用上一个主题的版本。
        # 编译缓存那层（_compile）本来就按 name+source 做 key，不受影响。
        digest = hashlib.sha1(source.encode()).hexdigest()

        def _uptodate() -> bool:
            current = resolver(template)
            return current is not None and hashlib.sha1(current.encode()).hexdigest() == digest

        return source, template, _uptodate


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
    # 记录「已被占用」的过滤器名：Jinja 内置（abs / default / attr …）+ 上面这 19 个。
    # App 注册同名过滤器会被拒，避免静默覆盖核心行为。
    global _BUILTIN_FILTER_NAMES
    _BUILTIN_FILTER_NAMES = frozenset(env.filters)


_BUILTIN_FILTER_NAMES: frozenset[str] = frozenset()


# ---------------------------------------------------------------- 第三方模板标签
#
# 站点主题的 16 个数据 API + 16 个过滤器属于核心内置（apps/cms/template_context.py），
# 不在这里。这里管的是 App 自己带进来的标签：
#
#     apps/<key>/template_tags.py
#         FUNCTIONS = {"<name>": fn}   # fn(ctx, *args, **kwargs)
#         FILTERS   = {"<name>": fn}   # fn(value, *args)
#
# 启动时由 api/v1/__init__.py 的 _discover_and_register 自动发现并注册。
#
# 为什么函数收 ctx：App 的标签通常不是从零算起，而是「复用已有能力再加工」——
# 取 6 条内容再补一个 App 自有字段。ctx 是 TemplateContext 实例，
# 直接调 ctx.content_list(...) 就拿到绑定当前站点的数据，不用自己拿 session。
#
# 安全边界：注册进来的函数 = 把能力暴露给**所有能编辑站点模板的人**。
# 只注册只读、结果可控的纯函数，不要在标签里做写操作或扇出外部请求。

_RESERVED_TEMPLATE_NAMES = frozenset({
    # 预注入变量
    "page", "item", "items", "pagination", "base_url", "theme_css", "theme_name", "now",
    # 内置数据 API
    "content_list", "content", "related", "search", "categories", "category_tree",
    "tags", "nav", "site", "site_meta", "asset", "url", "comments", "form",
    "media_list", "trans",
})

_TAG_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{0,39}$")
_APP_KEY_RE = re.compile(r"^[a-z_][a-z0-9_]{0,49}$")

_APP_FUNCTIONS: dict[str, dict[str, Any]] = {}
_APP_FILTERS: dict[str, dict[str, Any]] = {}
_TAG_LOCK = threading.RLock()


def _tag_error(app_key: str, name: Any, *, kind: str) -> str | None:
    """校验标签名格式；不通过返回原因，通过返回 None。"""
    if not isinstance(name, str) or not _TAG_NAME_RE.match(name):
        return (
            f"{kind}名 {name!r} 不合法：只允许小写字母、数字、下划线，"
            f"不以数字开头，长度 ≤ 40"
        )
    return None


def register_template_api(
    app_key: str,
    *,
    functions: dict[str, Any] | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, int]:
    """注册一个 App 的模板函数 / 过滤器，返回实际接受的数量。

    幂等：同一个 app_key 重复注册会覆盖自己的旧条目（热重载友好）。
    跨 App 重名、撞内置、名字不合法、不可调用 —— 一律跳过并记 warning，
    不抛异常，避免一个坏 App 拖垮全站模板。
    """
    if not isinstance(app_key, str) or not _APP_KEY_RE.match(app_key):
        raise ValueError(f"app_key 不合法：{app_key!r}（只允许小写字母、数字、下划线）")

    accepted_fns: dict[str, Any] = {}
    accepted_flt: dict[str, Any] = {}
    with _TAG_LOCK:
        for kind, items, bucket, reserved, out in (
            ("模板函数", functions or {}, _APP_FUNCTIONS, _RESERVED_TEMPLATE_NAMES, accepted_fns),
            ("过滤器", filters or {}, _APP_FILTERS, _BUILTIN_FILTER_NAMES, accepted_flt),
        ):
            for name, fn in items.items():
                err = _tag_error(app_key, name, kind=kind)
                if err is None and name in reserved:
                    err = f"{kind}名 {name!r} 已被内置占用，换个名字（建议加前缀，如 {app_key}_{name}）"
                if err is None and not callable(fn):
                    err = f"{kind} {name!r} 不是可调用对象"
                if err is None:
                    owner = next(
                        (k for k, v in bucket.items() if k != app_key and name in v), None
                    )
                    if owner:
                        err = f"{kind}名 {name!r} 已被 App {owner!r} 占用"
                if err:
                    log.warning("template_api.rejected", app=app_key, error=err)
                    continue
                bucket.setdefault(app_key, {})[name] = fn
                out[name] = fn

        if _ENV is not None:
            for name, fn in accepted_flt.items():
                _ENV.filters[name] = fn

    if accepted_fns or accepted_flt:
        # 已编译的模板可能把「未定义名」固化过，清一层编译缓存最稳
        flush_compiled_templates()
        log.info(
            "template_api.registered",
            app=app_key,
            functions=len(accepted_fns),
            filters=len(accepted_flt),
        )
    return {"functions": len(accepted_fns), "filters": len(accepted_flt)}


def unregister_template_api(app_key: str) -> dict[str, int]:
    """摘掉某个 App 的全部模板标签（卸载 / 停用时调用）。"""
    with _TAG_LOCK:
        fns = _APP_FUNCTIONS.pop(app_key, {})
        flts = _APP_FILTERS.pop(app_key, {})
        if _ENV is not None:
            for name in flts:
                _ENV.filters.pop(name, None)
    if fns or flts:
        flush_compiled_templates()
        log.info(
            "template_api.unregistered",
            app=app_key,
            functions=len(fns),
            filters=len(flts),
        )
    return {"functions": len(fns), "filters": len(flts)}


def app_template_functions() -> dict[str, Any]:
    """所有 App 注册的模板函数（扁平化，注册时已保证跨 App 不重名）。"""
    with _TAG_LOCK:
        return {n: f for items in _APP_FUNCTIONS.values() for n, f in items.items()}


def app_template_filters() -> dict[str, Any]:
    with _TAG_LOCK:
        return {n: f for items in _APP_FILTERS.values() for n, f in items.items()}


def bind_app_function(fn: Any, ctx: Any) -> Any:
    """把 ctx 绑到 App 模板函数的第一个参数上，并打沙箱放行标记。"""

    def _bound(*args: Any, **kwargs: Any) -> Any:
        return fn(ctx, *args, **kwargs)

    _bound.__cms_api__ = True  # type: ignore[attr-defined]
    _bound.__name__ = getattr(fn, "__name__", "app_template_function")
    _bound.__doc__ = getattr(fn, "__doc__", None)
    return _bound


def _apply_app_filters(env: CmsSandbox) -> None:
    with _TAG_LOCK:
        for items in _APP_FILTERS.values():
            for name, fn in items.items():
                env.filters[name] = fn


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
            # 关掉 Jinja 自带的模板缓存：它的 key 是 (loader, 模板名)、不含主题，
            # auto_reload=False 又让它在命中时不问 uptodate —— 换主题后同名模板
            # （layout.html / list.html）会继续用上一个主题的版本。
            # 编译缓存由 _compile 负责，key 是「名字 + 源码 sha1」，不会串。
            cache_size=0,
            auto_reload=False,
        )
        _register_filters(env)
        _apply_app_filters(env)
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
    # cache_size=0 时 Jinja 不建 cache 对象（_ENV.cache is None），必须判空。
    # 少这一句，保存模板/切换主题的"善后"环节会先抛 AttributeError，
    # 表面看像是保存失败。
    if _ENV is not None and _ENV.cache is not None:
        _ENV.cache.clear()


def flush_compiled_templates() -> None:
    """只清 Jinja 自身按**模板名**缓存的编译产物。

    这一层缓存的 key 是 (loader, name)，**不含源码**。预览时用不同的 resolver
    解析同名模板（编辑器里还没保存的内容），不清就会一直拿到上一次编译的旧版本 ——
    现象是「改了 partials/header.html，预览还是老样子」，而保存后又能变
    （保存走 invalidate，把两层都清了），于是用户会以为是编辑器坏了。

    比 clear_template_cache() 轻：不动按源码 md5 缓存的那层，
    重新编译后立刻又能命中。
    """
    env = _ENV
    if env is None:
        return
    # cache_size=0 时 Jinja 根本不建 cache 对象（env.cache is None）。
    # 这里必须判空 —— 否则每次保存模板/切换主题，清理缓存这一步就先炸了，
    # 而异常发生在"善后"环节，看上去像是保存失败。
    if env.cache is None:
        return
    with _CACHE_LOCK:
        env.cache.clear()


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


# ---------------------------------------------------------------- 内联脚本检查

# 会被严格 CSP（script-src 'self'）拦下的内联事件属性。
# 不写成 `on[a-z]+=` 是因为那样会把 `content="..."` 里的 `ontent=` 也匹配上。
_EVENT_NAMES = (
    "click|dblclick|load|error|change|input|submit|reset|select|"
    "focus|blur|mouse[a-z]+|key[a-z]+|touch[a-z]+|pointer[a-z]+|"
    "drag[a-z]*|drop|contextmenu|wheel|scroll|animation[a-z]+|transition[a-z]+"
)
_RE_INLINE_EVENT = re.compile(rf"(?<![\w-])on(?:{_EVENT_NAMES})\s*=", re.IGNORECASE)
_RE_SCRIPT_OPEN = re.compile(r"<script\b[^>]*>", re.IGNORECASE)
_RE_SCRIPT_SRC = re.compile(r"\bsrc\s*=", re.IGNORECASE)
# 不执行脚本的 type：结构化数据 / 模板片段
_RE_SCRIPT_INERT = re.compile(
    r"""type\s*=\s*["']?(?:application/ld\+json|application/json|text/template|text/x-template)""",
    re.IGNORECASE,
)
_RE_JS_URL = re.compile(
    r"""\b(?:href|src|action|formaction)\s*=\s*["']?\s*javascript:""", re.IGNORECASE
)


def _line_col(source: str, pos: int) -> tuple[int, int]:
    line = source.count("\n", 0, pos) + 1
    last_nl = source.rfind("\n", 0, pos)
    return line, pos - last_nl


def lint_inline_script(source: str) -> dict[str, Any] | None:
    """挑出会被严格 CSP 拦掉的写法。返回第一条问题（带 line/col），没有则 None。

    为什么要提前吵：这类写法是**必然失效**，不是风格问题。``script-src 'self'``
    下内联脚本一律不执行，作者看代码找不出毛病、上线却是空白 —— 最难自查的
    一类故障。所以放在保存前报，不放到线上等。

    放行的三种情况：

    * ``<script src="...">``         外链，'self' 允许
    * ``type="application/ld+json"`` 结构化数据，浏览器不执行
    * ``type="text/template"``       模板片段，同样不执行
    """
    if not source:
        return None

    for m in _RE_SCRIPT_OPEN.finditer(source):
        tag = m.group(0)
        if _RE_SCRIPT_SRC.search(tag) or _RE_SCRIPT_INERT.search(tag):
            continue
        line, col = _line_col(source, m.start())
        return {
            "message": (
                "内联 <script> 会被 CSP 拦下，已不执行。"
                "请把脚本放到 assets/ 下，用 {{ script('assets/xxx.js') }} 引入"
            ),
            "line": line,
            "col": col,
            "type": "csp",
        }

    m = _RE_INLINE_EVENT.search(source)
    if m:
        line, col = _line_col(source, m.start())
        return {
            "message": (
                f"内联事件属性 {m.group(0).strip()} 会被 CSP 拦下，"
                "请改用外链脚本里的 addEventListener"
            ),
            "line": line,
            "col": col,
            "type": "csp",
        }

    m = _RE_JS_URL.search(source)
    if m:
        line, col = _line_col(source, m.start())
        return {
            "message": "javascript: 伪协议会被 CSP 拦下，请用 <a> 配合外链脚本绑定事件",
            "line": line,
            "col": col,
            "type": "csp",
        }

    return None


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


def validate_theme_source(
    source: str, *, name: str = "<template>", path: str | None = None
) -> tuple[bool, dict[str, Any] | None]:
    """主题专用校验：语法 + 会被 CSP 拦掉的写法。

    语法错误优先报 —— 那是根本跑不起来的问题，CSP 是跑起来但跑不对的问题。

    ``path`` 决定要不要跑 CSP 检查：只有 html/xml 会被 CSP 管到。css / js 文件里
    出现 ``<script>`` 字样是完全正常的（模板字符串、注释、文档示例），一律按
    html 去查会天天误报。不给 path 时按 html 处理 —— 编辑器默认就在写模板。
    """
    ok, err = validate_source(source, name=name)
    if not ok:
        return ok, err

    target = (path or "").strip().lower()
    if target and not target.endswith((".html", ".xml")):
        return True, None

    lint = lint_inline_script(source)
    if lint is not None:
        return False, lint
    return True, None


def get_template_meta(source: str) -> dict[str, Any]:
    """粗提模板里引用的变量/模板/过滤器，给编辑器做提示用。"""
    extends = re.findall(r"{%-?\s*extends\s+[\"']([^\"']+)[\"']", source)
    includes = re.findall(r"{%-?\s*(?:include|import|from)\s+[\"']([^\"']+)[\"']", source)
    blocks = re.findall(r"{%-?\s*block\s+([A-Za-z0-9_]+)", source)
    return {"extends": extends, "includes": includes, "blocks": blocks}
