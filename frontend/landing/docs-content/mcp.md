# MCP 接入指南

Mosaic CMS 内置 MCP（Model Context Protocol）服务端，让 Claude Desktop、Cursor、
或任何自研 Agent **直接读写内容**，不用写一行胶水代码。

---

## 一、它能做什么

装上之后，你可以直接对 Agent 说：

> 「帮我在客户案例库里找三个新能源行业、节能率 30% 以上的案例，整理成对比表」

> 「照这份会议纪要，给 news 内容类型起草一篇新闻稿，然后翻译成英文」

Agent 会自己调 `cms_search_content`、`cms_get_entry`、`cms_create_entry`、`cms_translate_entry`
完成整件事。

---

## 二、10 个工具

| 工具 | 类型 | 说明 |
|---|---|---|
| `cms_list_content_types` | 只读 | 列出所有内容模型 |
| `cms_describe_content_type` | 只读 | 查看某个模型的完整字段定义 |
| `cms_search_content` | 只读 | **语义检索**，用自然语言找内容 |
| `cms_get_entry` | 只读 | 按 id / slug 取单条内容全文 |
| `cms_create_content_type` | 写 | 自然语言建模型（默认只出草案，`confirm=true` 才落库） |
| `cms_ai_draft_entry` | 写 | AI 起草内容（不落库） |
| `cms_create_entry` | 写 | 新建内容（**只能是草稿**） |
| `cms_update_entry` | 写 | 更新字段（合并式，不是整体替换） |
| `cms_translate_entry` | 写 | AI 翻译到多语言 |
| `cms_publish_entry` | 写 | 发布草稿 |

**资源（resources）**：每个内容类型同时以 `cms://content-types/<key>` 暴露，
Agent 可以像读文件一样加载 schema。

**安全设计**：
- 读操作开放，写操作受 `MCP_ALLOW_WRITE` 开关控制
- `cms_create_content_type` 默认只返回草案，不会因为 Agent 一句话就把库结构改了
- `cms_create_entry` 强制 `status=draft`，Agent 无法直接发布
- 权限校验失败返回可读文本而非 500，Agent 能自己调整策略

---

## 三、配置

### 3.1 服务端（必做）

在 `backend/.env` 里设置密钥：

```env
MCP_ENABLED=true
MCP_API_KEY=<随机长串，建议 openssl rand -hex 24>
MCP_ALLOW_WRITE=true      # 想给 Agent 只读权限就设 false
```

重启后端生效。

> 密钥生成：`openssl rand -hex 24`
> **不要把密钥提交进 git**，`.env` 已在 `.gitignore` 内。

### 3.2 方式一：HTTP（远程 / 生产环境）

端点：`https://<你的域名>/api/v1/cms/mcp`

**Claude Desktop / Cursor 等支持 HTTP 传输的客户端**：

```json
{
  "mcpServers": {
    "mosaic-cms": {
      "type": "http",
      "url": "https://your-domain.com/api/v1/cms/mcp",
      "headers": {
        "X-MCP-Key": "<你的 MCP_API_KEY>"
      }
    }
  }
}
```

也支持 `Authorization: Bearer <key>`，两种写法等价。

### 3.3 方式二：stdio（本机直连数据库）

适合本地开发、或不想把 MCP 端点暴露到公网。

```json
{
  "mcpServers": {
    "mosaic-cms": {
      "command": "/www/server/pyporject_evn/cenkor/bin/python",
      "args": ["-m", "cenkor_admin.apps.cms.mcp.stdio"],
      "env": {
        "PYTHONPATH": "/www/wwwroot/cenkor-admin/backend/src",
        "AI_ENABLED": "true",
        "AI_API_KEY": "<你的模型密钥>"
      }
    }
  }
}
```

> stdio 模式下进程直接读 `backend/.env`，数据库连接、AI 配置都从那里取。

---

## 四、手工验证

不用客户端，用 curl 就能确认端点活着：

```bash
KEY="你的 MCP_API_KEY"

# 1. 握手
curl -s https://your-domain.com/api/v1/cms/mcp \
  -H "X-MCP-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize",
       "params":{"protocolVersion":"2025-06-18","capabilities":{},
                 "clientInfo":{"name":"curl","version":"1"}}}' | jq .

# 2. 看有哪些内容模型
curl -s https://your-domain.com/api/v1/cms/mcp \
  -H "X-MCP-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call",
       "params":{"name":"cms_list_content_types","arguments":{}}}' | jq -r '.result.content[0].text'
```

期望：第一步返回 `protocolVersion` 与 `serverInfo.name = mosaic-cms`；
第二步返回内容类型 JSON 数组。

---

## 五、协议支持范围

| 方法 | 支持 |
|---|---|
| `initialize` | ✅ 版本协商（2025-06-18 / 2025-03-26 / 2024-11-05） |
| `notifications/initialized` | ✅ 返回 202，无 body（符合规范） |
| `ping` | ✅ |
| `tools/list` / `tools/call` | ✅ |
| `resources/list` / `resources/read` | ✅ |
| `prompts/list` | ✅ 返回空列表 |
| JSON-RPC 批量请求 | ✅ |
| 错误码 | ✅ -32700 / -32600 / -32601 / -32602 / -32603 |

---

## 六、常见问题

**Q：返回 `MCP 未配置密钥`**
`.env` 里 `MCP_API_KEY` 为空。填上并重启后端。

**Q：返回 `MCP 密钥无效`**
请求头没带或带了错的。检查 `X-MCP-Key` / `Authorization: Bearer`。

**Q：`cms_search_content` 报「AI 未配置」**
语义检索依赖 embedding 接口，需要配 `AI_ENABLED=true` + `AI_API_KEY`。
没配时其余工具（列表、取详情、建条目）仍可用。

**Q：Agent 建了模型但没生效**
`cms_create_content_type` 默认只返回草案。确认无误后带 `"confirm": true` 再调一次。

**Q：想让 Agent 只读，不给写权限**
`.env` 设 `MCP_ALLOW_WRITE=false`，写工具会返回「MCP 写操作已被禁用」。
