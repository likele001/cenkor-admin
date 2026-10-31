"""CMS App · 兜底路由（按后台配置的 URL 规则反解地址）。

**为什么单独一个文件**

`{full_path:path}` 这种通配路由会吃掉它后面注册的所有路径。Starlette 按
注册顺序匹配，谁先注册谁先命中。而 `api/v1/__init__.py` 里 public 前缀下
挂着一堆子路由：

    /public/comments   /public/forms    /public/lp/*    /public/track
    /public/portal/*   /public/pages/*  /public/templates/render

兜底路由要是留在 `cms_public_router` 里（它是最先 include 的），这些子路由
就全被它遮蔽 —— 表现是接口返回 CMS 的 HTML 404 页面，`track.js` 埋点脚本
直接失效，而且日志里一条 ERROR 都没有，极难排查。

所以兜底路由单独放这里，在 `api/v1/__init__.py` 的**最后** include。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.public_router import resolve_custom_path
from cenkor_admin.core.db import get_db

router = APIRouter()


@router.get("/{full_path:path}", include_in_schema=False)
async def catch_all_path(
    request: Request, full_path: str, db: AsyncSession = Depends(get_db)
) -> Response:
    """按后台配置的 URL 规则反解地址。实现在 public_router 里。"""
    return await resolve_custom_path(request, full_path, db)
