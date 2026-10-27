"""MCP Server · JSON-RPC 2.0 分发 + 传输层

为什么自己实现而不装官方 SDK：
1. 交付物要能离线部署，少一个依赖少一个坑
2. MCP 的传输层（initialize / tools / resources）协议面很窄，自己实现约 300 行，
   换来对鉴权、事务、错误码的完全控制
3. 我们的工具实现依赖项目自己的 AsyncSession，不走 SDK 的 asyncio 运行器反而更简单

支持两种传输：
- **HTTP**：POST /api/v1/cms/mcp（Streamable HTTP，也兼容旧 SSE 客户端）
- **stdio**：`python -m cenkor_admin.apps.cms.mcp.stdio`（Claude Desktop 用）

协议方法：
    initialize / notifications/initialized / ping
    tools/list / tools/call
    resources/list / resources/read
"""

from __future__ import annotations

import json
import traceback
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cenkor_admin.apps.cms.mcp.tools import call_tool, tool_catalog
from cenkor_admin.apps.cms.models import ContentType
from cenkor_admin.core.llm import LLMNotConfiguredError

SERVER_NAME = "mosaic-cms"
SERVER_VERSION = "1.0.0"

# 服务端支持的协议版本（新→旧）；initialize 时按客户端请求协商
SUPPORTED_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
LATEST_VERSION = SUPPORTED_VERSIONS[0]

# JSON-RPC 标准错误码
ERR_PARSE = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603


class McpProtocolError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def _ok(msg_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _err(msg_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": msg_id, "error": error}


class McpServer:
    """无状态分发器。一次请求开一个 session，请求结束即提交/回滚。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # ---------------- 主入口 ----------------
    async def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """处理单条 JSON-RPC 消息。

        返回 None 表示这是通知（notification），按规范不得响应。
        """
        if not isinstance(message, dict):
            return _err(None, ERR_INVALID_REQUEST, "消息必须是 JSON 对象")

        msg_id = message.get("id")
        method = message.get("method")
        params = message.get("params") or {}
        is_notification = "id" not in message

        if not method or not isinstance(method, str):
            return None if is_notification else _err(msg_id, ERR_INVALID_REQUEST, "缺少 method")

        # 通知：只做副作用，不返回
        if is_notification:
            if method == "notifications/initialized":
                logger.debug("mcp.client_initialized")
            return None

        try:
            result = await self._dispatch(method, params)
            return _ok(msg_id, result)
        except McpProtocolError as exc:
            return _err(msg_id, exc.code, exc.message, exc.data)
        except LLMNotConfiguredError as exc:
            # AI 未配置不该让 Agent 看到 500，给出可读提示
            return _err(msg_id, ERR_INTERNAL, f"AI 未配置：{exc}")
        except PermissionError as exc:
            return _err(msg_id, ERR_INVALID_REQUEST, str(exc))
        except ValueError as exc:
            return _err(msg_id, ERR_INVALID_PARAMS, str(exc))
        except Exception as exc:
            logger.error("mcp.dispatch_failed", method=method, error=str(exc))
            logger.debug("mcp.traceback", tb=traceback.format_exc())
            return _err(msg_id, ERR_INTERNAL, f"内部错误：{exc}")

    async def _dispatch(self, method: str, params: dict[str, Any]) -> Any:
        if method == "initialize":
            return self._initialize(params)
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": tool_catalog()}
        if method == "tools/call":
            return await self._tools_call(params)
        if method == "resources/list":
            return await self._resources_list()
        if method == "resources/read":
            return await self._resources_read(params)
        if method == "prompts/list":
            return {"prompts": []}
        raise McpProtocolError(ERR_METHOD_NOT_FOUND, f"不支持的方法：{method}")

    # ---------------- 各方法 ----------------
    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        requested = str(params.get("protocolVersion") or "")
        version = requested if requested in SUPPORTED_VERSIONS else LATEST_VERSION
        logger.info("mcp.initialize", client_version=requested, negotiated=version)
        return {
            "protocolVersion": version,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
            },
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": (
                "这是 Mosaic CMS 的内容接口。"
                "先调 cms_list_content_types 看有哪些内容模型，"
                "再用 cms_search_content 按意思找内容（支持自然语言，不必用精确关键词）。"
                "创建内容只能产生草稿，发布需要显式调用 cms_publish_entry。"
            ),
        }

    async def _tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not name:
            raise McpProtocolError(ERR_INVALID_PARAMS, "缺少工具名 name")

        async with self._session_factory() as session:
            try:
                text = await call_tool(session, str(name), arguments)
                await session.commit()
                return {"content": [{"type": "text", "text": text}], "isError": False}
            except (ValueError, PermissionError, LLMNotConfiguredError) as exc:
                await session.rollback()
                # 业务错误以 isError=true 返回，让模型自己决定怎么补救
                return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
            except Exception as exc:
                await session.rollback()
                logger.error("mcp.tool_failed", tool=name, error=str(exc))
                return {
                    "content": [{"type": "text", "text": f"工具执行失败：{exc}"}],
                    "isError": True,
                }

    async def _resources_list(self) -> dict[str, Any]:
        """把每个内容类型暴露成一个 resource，Agent 可以像读文件一样浏览 schema。"""
        async with self._session_factory() as session:
            rows = (
                (await session.execute(select(ContentType).order_by(ContentType.key)))
                .scalars()
                .all()
            )

        return {
            "resources": [
                {
                    "uri": f"cms://content-types/{ct.key}",
                    "name": f"内容类型：{ct.name}",
                    "description": ct.description or f"{ct.name} 的字段定义",
                    "mimeType": "application/json",
                }
                for ct in rows
            ]
        }

    async def _resources_read(self, params: dict[str, Any]) -> dict[str, Any]:
        uri = str(params.get("uri") or "")
        prefix = "cms://content-types/"
        if not uri.startswith(prefix):
            raise McpProtocolError(ERR_INVALID_PARAMS, f"不支持的资源 URI：{uri}")

        key = uri[len(prefix) :].strip("/")
        async with self._session_factory() as session:
            text = await call_tool(session, "cms_describe_content_type", {"key": key})

        return {"contents": [{"uri": uri, "mimeType": "application/json", "text": text}]}


# ---------------------------------------------------------------------------
# 便捷函数：给 HTTP 路由用
# ---------------------------------------------------------------------------
def parse_body(raw: bytes) -> dict[str, Any] | list[dict[str, Any]]:
    """解析请求体，兼容单条与批量（JSON-RPC batch）。"""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise McpProtocolError(ERR_PARSE, f"JSON 解析失败：{exc}") from exc
    if not isinstance(data, (dict, list)):
        raise McpProtocolError(ERR_INVALID_REQUEST, "请求体必须是对象或数组")
    return data


async def handle_http_request(
    server: McpServer, raw: bytes
) -> tuple[dict[str, Any] | list[Any] | None, int]:
    """处理一次 HTTP 请求体，返回 (响应体, HTTP 状态码)。"""
    try:
        payload = parse_body(raw)
    except McpProtocolError as exc:
        return _err(None, exc.code, exc.message), 400

    if isinstance(payload, list):
        # 批量：逐条处理，丢弃通知的 None
        responses: list[Any] = []
        for item in payload:
            r = await server.handle(item)
            if r is not None:
                responses.append(r)
        return (responses or None), 200

    response = await server.handle(payload)
    return response, 200


__all__ = [
    "LATEST_VERSION",
    "SERVER_NAME",
    "SERVER_VERSION",
    "McpProtocolError",
    "McpServer",
    "handle_http_request",
]
