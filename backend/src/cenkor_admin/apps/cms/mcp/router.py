"""MCP HTTP 端点

    POST /api/v1/cms/mcp         JSON-RPC 2.0（Streamable HTTP）
    GET  /api/v1/cms/mcp/tools   工具清单（人工调试 / 文档用）

鉴权策略（二选一，MCP_API_KEY 优先）：
1. 配了 MCP_API_KEY → 请求头 X-MCP-Key 或 Authorization: Bearer <key> 必须匹配
2. 没配 → 回退要求登录用户（浏览器 / 后台内调用）

为什么允许 Bearer：多数 MCP 客户端只会填 Authorization 头，
额外要求自定义头会让「粘上去就能用」这件最大的优点消失。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms.mcp.server import (
    SERVER_NAME,
    SERVER_VERSION,
    McpServer,
    handle_http_request,
)
from cenkor_admin.apps.cms.mcp.tools import tool_catalog
from cenkor_admin.core.config import get_settings
from cenkor_admin.core.db import AsyncSessionLocal

router = APIRouter(prefix="/mcp", tags=["cms-mcp"])


def _extract_token(request: Request) -> str:
    header_key = (request.headers.get("x-mcp-key") or "").strip()
    if header_key:
        return header_key
    auth = (request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


async def _authorize(request: Request) -> None:
    """校验访问权。抛 HTTPException 表示拒绝。

    简化决策：MCP 端点**只接受密钥**，不做「没配密钥就回退登录态」。
    理由——调用方永远是外部 Agent，它没有 Cookie；留个模糊的回退分支只会
    让配置缺失时的报错变成 401，排查成本高。缺密钥就直接告诉用户去配。
    后台内部调试走 GET /mcp/tools（要求登录）。
    """
    settings = get_settings()
    if not settings.MCP_ENABLED:
        raise HTTPException(status_code=403, detail="MCP 已关闭（MCP_ENABLED=false）")

    expected = (settings.MCP_API_KEY or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MCP 未配置密钥：请在 .env 设置 MCP_API_KEY=<随机长串> 后重试",
        )

    if _extract_token(request) != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MCP 密钥无效：请在 X-MCP-Key 或 Authorization: Bearer 里带上正确密钥",
        )


@router.post("", summary="MCP JSON-RPC 入口")
async def mcp_endpoint(request: Request) -> Any:
    await _authorize(request)

    raw = await request.body()
    if not raw:
        raise HTTPException(status_code=400, detail="请求体为空")

    server = McpServer(AsyncSessionLocal)
    payload, http_status = await handle_http_request(server, raw)

    # 通知类请求（只有 notifications/*）按规范返回 202 且无 body
    if payload is None:
        return Response(status_code=202)

    return JSONResponse(status_code=http_status, content=payload)


@router.get("/tools", summary="列出 MCP 提供的工具（调试用）")
async def list_tools(
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "server": {"name": SERVER_NAME, "version": SERVER_VERSION},
        "count": len(tool_catalog()),
        "tools": tool_catalog(),
    }
