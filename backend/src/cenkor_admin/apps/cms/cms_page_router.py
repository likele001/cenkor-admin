"""CMS App · 页面渲染路由（HTML 页面专用前缀）。

**为什么要单独一个前缀**

nginx 把站点上「静态文件没命中」的路径转发回后端，让后端按后台配置的
URL 规则反解地址。这个转发以前落在 ``/api/v1/public`` —— 那是 JSON 接口的
地盘，一日用户把某条内容的地址配成 ``/site``、``/news``、``/search`` 这类
名字，转发过去就会撞上同名 JSON 接口：浏览器拿到一段 JSON、状态码 200，
页面彻底渲染错乱，而且日志里一条错都看不到（那本来就是个合法接口）。

所以页面渲染单独占一个前缀 ``/api/v1/page``：

- 里面**只有** HTML 页面路由 + 兜底反解，不跟任何 JSON 接口抢名字
- 官网静态站读 JSON 仍然走 ``/api/v1/public``，两套互不干扰

这里只把 ``public_router`` 里的 HTML 页面处理器**再挂一份**到本 router，
``/api/v1/public`` 下的原路由保持不变 —— 官网和后台前端已经在用那些路径，
动不得。

⚠️ 兜底路由必须排在这些页面路由**之后**：``{full_path:path}`` 是通配路由，
排在前面会把 ``/page/article/``、``/page/sitemap.xml`` 全吃掉。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms import public_router
from cenkor_admin.apps.cms.public_router import resolve_custom_path
from cenkor_admin.core.db import get_db

router = APIRouter()

# 页面处理器清单：只挑 HTML 页面，JSON 接口（/site、/news、/products…）不在内。
_PAGE_HANDLERS: tuple[tuple[str, str], ...] = (
    ("/article/", "article_index"),
    ("/product/", "product_index"),
    ("/case/", "case_index"),
    ("/news/", "news_index"),
    ("/category/{slug}/", "category_page"),
    ("/tag/{slug}/", "tag_page"),
    ("/{kind}/page/{n}/", "kind_paged"),
    ("/category/{slug}/page/{n}/", "category_paged"),
    ("/tag/{slug}/page/{n}/", "tag_paged"),
    ("/search/", "search_page"),
    ("/article/{slug}", "article_page"),
    ("/product/{slug}", "product_page"),
    ("/case/{slug}", "case_page"),
    ("/p/{slug}", "single_page"),
    ("/preview/{token}", "preview_entry_html"),
    ("/sitemap.xml", "sitemap_xml"),
    ("/llms.txt", "llms_txt"),
)

for _path, _attr in _PAGE_HANDLERS:
    _fn = getattr(public_router, _attr, None)
    if _fn is None:  # pragma: no cover - 处理器改名时的显式失败
        raise RuntimeError(f"public_router 缺少页面处理器 {_attr}，页面路由无法挂载")
    router.add_api_route(
        _path,
        _fn,
        methods=["GET"],
        include_in_schema=False,
        operation_id=f"page_{_attr}",
    )


@router.get("/{full_path:path}", include_in_schema=False)
async def catch_all_path(
    request: Request, full_path: str, db: AsyncSession = Depends(get_db)
) -> Response:
    """按后台配置的 URL 规则反解地址。实现在 public_router 里。"""
    return await resolve_custom_path(request, full_path, db)
