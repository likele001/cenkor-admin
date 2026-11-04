"""模板组件沙箱（widget）—— 让第三方模板拿到交互能力，又不给它同源权限。

## 为什么必须是 iframe

模板一旦能执行脚本，它就是**本站脚本**：能读 cookie、能发同源请求、能改父页面
DOM。CSP 的 ``script-src 'self'`` 只保证脚本来自本站，管不了脚本干什么 ——
所以「信任这个模板」和「给它同源 JS」是同义词。而商店里的模板没有理由被信任
到这一步。

``widget()`` 把交互部分放进一个 iframe，并且：

* ``sandbox="allow-scripts"``，**没有** ``allow-same-origin``
  → iframe 内文档被强制成 opaque origin：读不到父页面 DOM、读不到 cookie 与
    localStorage，父页面也读不到它的 DOM，两边只能靠 postMessage 通信。
* 宿主页响应头自带 ``sandbox allow-scripts``
  → 有人在地址栏直接打开 widget URL 也一样受限。这不是「只有被嵌入时才安全」
    的防护，而是文件本身就没有特权。
* 子文档 CSP ``default-src 'none'`` + ``connect-src 'none'``
  → 脚本画得出东西，但发不出请求、提交不了表单、弹不出窗口。

## 为什么脚本用 sha256 哈希而不是 'self'

opaque origin 下 CSP 的 ``'self'`` 匹配不到任何东西（文档没有可用 origin 参与
匹配），外链脚本会被拦下 —— 这是 sandbox iframe 里最经典的坑。哈希匹配与
origin 无关，把唯一该跑的那一段脚本钉死，比 ``'unsafe-inline'`` 严格得多，
也不依赖浏览器对 self 的实现差异。

## 参数怎么传

走 URL 的 query 参数（base64url 编码的 JSON），不走 postMessage。理由：
postMessage 需要父页面有脚本参与，而父页面的严格 CSP 恰恰禁内联脚本 ——
真要发消息就得让模板带一个同源 ``assets/*.js``，那等于把沙箱的门又打开了。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from html import escape
from typing import Any

from markupsafe import Markup

__all__ = [
    "DEFAULT_HEIGHT",
    "DEFAULT_WIDGET_TITLE",
    "MAX_ARGS_BYTES",
    "MAX_HEIGHT",
    "MIN_HEIGHT",
    "WIDGET_NAME_RE",
    "WIDGET_PREFIX",
    "build_host_page",
    "decode_args",
    "encode_args",
    "widget_csp",
    "widget_iframe",
]

# 宿主页的对外前缀。三处必须一致：helper 拼 URL、api/v1 include_router 的 prefix、
# widget_router 里的路由路径。改这里就够了，别处不要硬编码。
WIDGET_PREFIX = "/api/v1/public/theme-widgets"

# widget 名同时是文件名（widgets/<name>.html）与 URL 片段，收紧到小写。
WIDGET_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,47}$")

# 参数上限。base64 后约 5.5KB，nginx 默认 header 上限 8KB，留足余量。
# 更大的数据应该走接口按需拉取，而不是塞进 URL。
MAX_ARGS_BYTES = 4096

DEFAULT_HEIGHT = 320
MIN_HEIGHT = 80
# 上限不是审美问题：一个 1200px 以上的 widget 会把首屏整个占掉，
# 而它自己是 lazyload 的，站长打开页面先看到一大片空白。
MAX_HEIGHT = 1200

DEFAULT_WIDGET_TITLE = "嵌入组件"


# ---------------------------------------------------------------- 参数编解码


def encode_args(args: Any) -> str:
    """把 widget 参数编成 URL 安全串（base64url，无 padding）。

    序列化用 ``ensure_ascii=False`` 保留中文可读性；真正的注入防护在
    ``_json_literal`` 里做（把 ``<`` 转成 ``\\u003c``），这里只负责编码。
    """
    if not isinstance(args, dict):
        raise ValueError("widget 参数必须是对象")
    raw = json.dumps(args, ensure_ascii=False, separators=(",", ":"))
    data = raw.encode("utf-8")
    if len(data) > MAX_ARGS_BYTES:
        raise ValueError(f"widget 参数超过 {MAX_ARGS_BYTES} 字节上限")
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def decode_args(token: str) -> dict[str, Any]:
    """解 URL 里的参数串。任何异常都归零成空对象 —— 参数坏了不该 500。

    widget 宿主页是公开地址，谁都能构造 ``?d=xxx``。所以这里必须把恶意输入
    当成常态：非 base64、非 UTF-8、非 JSON、非对象，一律当没传。
    """
    if not token:
        return {}
    if len(token) > MAX_ARGS_BYTES * 2:
        return {}
    try:
        pad = "=" * (-len(token) % 4)
        data = base64.urlsafe_b64decode(token + pad)
    except (binascii.Error, ValueError):
        return {}
    if len(data) > MAX_ARGS_BYTES:
        return {}
    try:
        obj = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return obj if isinstance(obj, dict) else {}


# ---------------------------------------------------------------- 宿主页


def _json_literal(obj: Any) -> str:
    """安全的 ``<script type="application/json">`` 文本内容。

    把 ``<`` / ``>`` / ``&`` 全部转成 JSON 的 ``\\uXXXX`` 形式。JSON.parse 之后
    值与原文完全一致，但 HTML 解析器再也看不到能闭合标签的序列 —— 这是唯一
    能同时挡住 ``</script>`` 与 ``<!--`` 的写法（后者会让 HTML 词法器进入
    escaped 状态，导致后续 ``</script>`` 不闭合，页面结构整个错位）。
    """
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _escape_script_body(js: str) -> str:
    """把内联脚本里的 ``</script`` 改成 ``<\\/script``。

    只替换这一个序列，不动其它 ``</`` —— ``a < /re/.test(b)`` 这种合法代码
    不能被误伤。改完的内容才是写进 HTML 的最终形态，哈希也必须基于它算。
    """
    return re.sub(r"</(script)", r"<\\/\1", js, flags=re.IGNORECASE)


def widget_csp(script_body: str | None) -> str:
    """widget 宿主页的 CSP。带 ``sandbox`` 指令，顶层打开也受限。"""
    parts = [
        # 关键：没有 allow-same-origin。这是整个沙箱的支点。
        "sandbox allow-scripts",
        "default-src 'none'",
        "style-src 'unsafe-inline'",
        "img-src data: https:",
        "media-src https:",
        "font-src data:",
        # 脚本只能画自己，不许联网 —— 数据由 URL 参数给，不需要它主动拉
        "connect-src 'none'",
        "form-action 'none'",
        "base-uri 'none'",
        # 连嵌套都不许：它自己就是被嵌的那一层，没有再嵌别人的需求
        "frame-src 'none'",
        "object-src 'none'",
    ]
    if script_body:
        digest = base64.b64encode(hashlib.sha256(script_body.encode("utf-8")).digest()).decode("ascii")
        parts.append(f"script-src 'sha256-{digest}'")
    else:
        parts.append("script-src 'none'")
    return "; ".join(parts)


_HOST_SHELL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{title}</title>
<style>
/* 只做一件小事：让作者的组件贴着容器边缘排。主题的视觉应该由 widget 自己带，
   平台不替它决定字体和颜色 —— 那属于模板的职责。 */
html, body {{ margin: 0; padding: 0; }}
*, *::before, *::after {{ box-sizing: border-box; }}
.cms-widget-root {{ width: 100%; min-height: 100%; }}
</style>
</head>
<body>
<div class="cms-widget-root">{structure}</div>
<script type="application/json" id="cms-widget-data">{data}</script>
{script_tag}
</body>
</html>
"""


def build_host_page(
    *,
    structure: str,
    script: str | None,
    args: dict[str, Any],
    title: str = DEFAULT_WIDGET_TITLE,
) -> tuple[str, str]:
    """组装 widget 宿主页。返回 ``(html, csp)``，两者必须同生同死。

    调用方不要自己拼 CSP —— 哈希与内联脚本的最终文本强绑定，分开写必然对不上，
    对不上的表现是「脚本静默不执行」，最难查的一类问题。
    """
    script_body: str | None = None
    script_tag = ""
    if script:
        script_body = _escape_script_body(script)
        script_tag = f"<script>{script_body}</script>"

    html = _HOST_SHELL.format(
        title=escape(title or DEFAULT_WIDGET_TITLE),
        structure=structure,
        data=_json_literal(args),
        script_tag=script_tag,
    )
    return html, widget_csp(script_body)


def widget_iframe(src: str, *, height: int = DEFAULT_HEIGHT, title: str = "") -> Markup:
    """iframe 标签。``sandbox`` 只有 ``allow-scripts``，一个都不多加。

    尤其不能加 ``allow-same-origin`` —— 它和 ``allow-scripts`` 同时出现时，
    sandbox 等于没开（脚本能自己把 origin 拿回来），这是最经典的自杀式配置。
    """
    h = max(MIN_HEIGHT, min(int(height or DEFAULT_HEIGHT), MAX_HEIGHT))
    return Markup(
        '<iframe class="cms-widget" src="{}" sandbox="allow-scripts" loading="lazy"'
        ' referrerpolicy="no-referrer"'
        ' style="width:100%;border:0;display:block;height:{}px"'
        ' title="{}"></iframe>'
    ).format(src, h, escape(title or DEFAULT_WIDGET_TITLE))
