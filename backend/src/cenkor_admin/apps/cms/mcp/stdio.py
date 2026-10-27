"""MCP stdio 传输入口。

给 Claude Desktop / Cursor 等本机客户端用：

    python -m cenkor_admin.apps.cms.mcp.stdio

在客户端配置里：
{
  "mcpServers": {
    "mosaic-cms": {
      "command": "/path/to/python",
      "args": ["-m", "cenkor_admin.apps.cms.mcp.stdio"],
      "env": { "PYTHONPATH": "/path/to/backend/src", "AI_API_KEY": "..." }
    }
  }
}

约定：stdout 只写 JSON-RPC 消息（一行一条），所有日志走 stderr。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from loguru import logger

from cenkor_admin.apps.cms.mcp.server import McpServer
from cenkor_admin.core.db import AsyncSessionLocal


def _setup_logging() -> None:
    """日志全部重定向到 stderr —— stdout 是协议通道，写脏了客户端会解析失败。"""
    logger.remove()
    logger.add(sys.stderr, level=os.getenv("MCP_LOG_LEVEL", "INFO"))


async def _serve() -> None:
    _setup_logging()
    server = McpServer(AsyncSessionLocal)
    logger.info("mcp.stdio.start")

    while True:
        # 同步读 stdin，放线程池里跑，避免阻塞事件循环
        line = await asyncio.to_thread(sys.stdin.readline)
        if not line:
            logger.info("mcp.stdio.eof")
            break

        line = line.strip()
        if not line:
            continue

        try:
            message = json.loads(line)
        except ValueError as exc:
            resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"JSON 解析失败：{exc}"},
            }
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            continue

        try:
            response = await server.handle(message)
        except Exception as exc:
            logger.error("mcp.stdio.handler_failed", error=str(exc))
            response = {
                "jsonrpc": "2.0",
                "id": message.get("id") if isinstance(message, dict) else None,
                "error": {"code": -32603, "message": f"内部错误：{exc}"},
            }

        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


def main() -> None:
    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
