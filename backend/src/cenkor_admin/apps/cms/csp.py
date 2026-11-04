"""CMS 公开页面的安全响应头（CSP / 反嵌套 / 嗅探防护）。

## 为什么用 ``script-src 'self'`` 而不用 nonce

nonce 是一次一换的随机值，但它必须**写进 HTML** 才生效，写进去就固化了：

* 详情页渲染完会落盘静态缓存（``static_cache.record_public_page``），之后
  nginx 直接出这个文件、不再进 Python。那份 HTML 里的 nonce 永远是第一次
  渲染时的值 —— 同一个 nonce 被反复下发，等于把钥匙公开了，防护形同虚设，
  还会制造「看起来有防护」的错觉。
* 模板层已经硬拦内联 ``<script>``（``jinja_env.lint_inline_script``），
  nonce 唯一的作用对象被消灭了。
* 外链 ``<script src>`` 靠 ``'self'`` 就够，且与任何缓存机制天然兼容。

所以最终口径：**禁一切内联脚本与内联事件属性，脚本一律走 ``script()`` 外链。**

## 为什么 style-src 保留 'unsafe-inline'

主题里内联 ``style`` 属性太常见（``<div style="...">``），而 CSS 不能执行代码、
也碰不到页面之外的东西。为了它牺牲整站样式不划算 —— 真被注入 CSS，最坏结果
是页面变丑，不是丢 cookie。

## img-src / media-src 放开 https:

内容里引用外链图片、视频是正常需求（CDN、图床）。它们不能执行代码。
"""

from __future__ import annotations

from fastapi.responses import Response

__all__ = [
    "CSP_POLICY",
    "CSP_POLICY_FRAMEABLE",
    "THEME_ASSET_PREFIX",
    "html_response",
    "security_headers",
]

# 主题资源路由的对外前缀。三处必须一致：
#   1. html/模板里拼 URL（template_context.theme_asset）
#   2. api/v1 里 include_router 的 prefix
#   3. nginx 把 /api/ 转发到后端（已有，无需改）
# 改这里就够了 —— 不要在别处硬编码这个字符串。
THEME_ASSET_PREFIX = "/api/v1/public/theme-assets"

# 公网页面：不允许被任何第三方页面嵌套（frame-ancestors 'self'）。
_CSP_BASE = (
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: https:",
    "font-src 'self' data:",
    "media-src 'self' https:",
    "frame-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
)

CSP_POLICY = "; ".join((*_CSP_BASE, "frame-ancestors 'self'"))

# 后台预览页要能被后台 iframe 嵌入（可能是另一个域名），所以放开 frame-ancestors。
# 预览地址是一次性 token（_resolve_preview_entry 会校验有效期），内容也是自己写的稿子，
# 被嵌套的风险可接受。
CSP_POLICY_FRAMEABLE = "; ".join((*_CSP_BASE, "frame-ancestors *"))


def security_headers(*, allow_frame: bool = False) -> dict[str, str]:
    """构造公开页面的安全响应头。

    ``allow_frame=True`` 只给后台预览用；公网页面一律禁止外站嵌套。
    """
    headers = {
        "Content-Security-Policy": CSP_POLICY_FRAMEABLE if allow_frame else CSP_POLICY,
        # 防止浏览器把 .txt/.json 之类嗅探成 HTML 执行
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
    }
    if not allow_frame:
        # 老浏览器不认 frame-ancestors，两个都给
        headers["X-Frame-Options"] = "SAMEORIGIN"
    return headers


def html_response(
    content: str,
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
    allow_frame: bool = False,
) -> Response:
    """公开页面的统一 HTML 出口。

    全站 HTML 只从这里出，避免"某条路径忘了加安全头"。新增返回 HTML 的路由
    一律走这个函数，不要在别处直接 ``Response(media_type="text/html")``。

    ``headers`` 里的同名键会覆盖安全头（目前没有这种需求，但调用方可能带
    ``Cache-Control`` / ``X-Robots-Tag``）。
    """
    merged = {**security_headers(allow_frame=allow_frame), **(headers or {})}
    return Response(
        content=content,
        status_code=status_code,
        media_type="text/html; charset=utf-8",
        headers=merged,
    )
