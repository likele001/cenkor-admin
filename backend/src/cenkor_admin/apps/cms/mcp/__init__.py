"""CMCP · Mosaic CMS 的 Agent 接入层

结构：
    tools.py  工具定义与实现（10 个）
    server.py JSON-RPC 2.0 分发 + 协议协商
    stdio.py  本机 stdio 传输入口（Claude Desktop / Cursor）
    router.py HTTP 端点（POST /api/v1/cms/mcp）

对外只有一件事要让 Agent 知道：**先说人话，剩下交给我。**
"""

from __future__ import annotations

__all__ = ["server", "tools"]
