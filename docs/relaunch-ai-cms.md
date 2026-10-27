# Cenkor Mosaic · 重定位方案

**AI 原生内容平台** ｜ 2026-10-27 ｜ 从 `cenkor-admin` monorepo 孵化的独立产品线

---

## 一、一句话定位

> **Mosaic 是 AI 与内容之间的协议层。**
> 你用中文说清楚要什么内容，它建出模型、写出草稿、翻译成多语言，
> 再以 MCP / REST / GraphQL 三种协议交给任何 Agent 消费。

英文 tagline：**Model it in words. Serve it to agents.**

不是"又一个 CMS"。传统 CMS 服务的是**人写、人读**；Mosaic 服务的是
**人定意图、AI 生产、Agent 消费**。这两件事的产品形态根本不同。

---

## 二、为什么必须重新定位

`cenkor-admin` 现在的对外形象是「通用企业后台，20 个 app 全家桶」——
CRM / ERP / MES / CMS / 工单 / 流程 / 待办 / 知识库全塞一起。

三个硬伤：

| 问题 | 后果 |
|---|---|
| 说不出「你到底解决谁的什么问题」 | 采购方要问 8 个问题才搞懂，销售周期无限拉长 |
| 20 个 app 都做 60 分 | 没有一个能打的，客户拿最弱的那个否掉整个平台 |
| CMS 明明是全仓最完整的模块（22 表 / 5365 行 / 动态建模引擎） | 却被迫当"后台里顺便送的一个小功能"，价值被埋掉 |

**结论**：CMS 不该是 cenkor-admin 的一个功能，它应该是一个独立产品。
CRM/ERP/MES 留在平台里服务存量客户，CMS 单飞。

---

## 三、目标用户（按付费意愿排序）

| 优先级 | 人群 | 他们的痛点 | Mosaic 给什么 |
|---|---|---|---|
| **P0** | 内容团队 / 品牌市场部（5-50 人） | 多语言官网 + 案例库 + 白皮书，改个字段要等排期 | 自己一句话建模型，AI 出草稿，AI 翻译 |
| **P0** | 正在接 AI 的产品团队 | 想让 ChatGPT / Cursor / 自研 Agent 用自家内容，但 CMS 没有 Agent 接口 | 开箱 MCP Server，5 分钟接进 Claude |
| **P1** | 垂直行业 SaaS（制造/医疗/教育） | 行业内容字段复杂，通用 CMS 字段不够用 | 动态建模 + 关系字段 + 校验规则 |
| **P1** | 出海企业 | 中英日韩多语言维护成本高 | 一条命令全语言批量翻译，保留格式 |
| **P2** | 开发者 / 独立站 | 想要无头 CMS 但嫌 Strapi 重、Sanity 贵 | FastAPI 单体，一条 Docker 命令起 |

---

## 四、三大支柱（差异化全部落在这三件事上）

### 支柱 1 · Model by talking（说人话建模型）

```
输入：我要做一个制造业客户案例库，字段有客户名、所属行业（离散制造/
      流程制造/新能源）、产线数量、节能率百分比、项目周期、客户 logo、
      项目前后对比图，还要能按行业筛选

输出：ContentType(key=customer_case)
      ├─ customer_name   text        必填
      ├─ industry        select      options=[离散制造,流程制造,新能源]
      ├─ line_count      number      validation:{min:1}
      ├─ energy_saving   number      validation:{min:0,max:100} + suffix=%
      ├─ duration        text
      ├─ logo            image
      ├─ comparison      images      (before/after 组图)
      └─ 自动挂 category 支持 + 列表页默认模板
```

**这是全行业第一个把"建模"从 GUI 拖拽变成对话的产品。**
Strapi 要你在 Content-Type Builder 里点 20 次；Mosaic 让你说一遍。

技术上是复用已有的 `ContentType + FieldGroup + FieldDefinition + FieldOption`
四张表，把 LLM 输出约束到 20 种已有字段类型（`field_types.py::FIELD_TYPES`），
用 JSON Schema + 后置校验保证不会建出脏模型。

### 支柱 2 · Search by meaning（按意思找）

内容入库即向量化，检索从「关键词命中」升级到「语义命中」：

- 输入"有哪些帮客户省电的案例" → 命中 `energy_saving > 30` 但标题里没写"省电"的条目
- 对外暴露 `/api/v1/cms/semantic/search`，可直接做 RAG 的 retrieval 层
- 混合排序：向量相似度 0.7 + 关键词 BM25 0.3，避免纯向量的"幻觉式召回"

**工程取舍**：这台生产机没有 pgvector，所以实现成**双后端**——
检测到 `vector` 扩展就用原生 `<=>` 算子；没有就退化为
`double precision[]` 存向量 + 应用侧余弦计算。**零新依赖，两条路都能跑。**

### 支柱 3 · Serve to agents（Agent 原生消费）

| 协议 | 用途 | 状态 |
|---|---|---|
| REST | 传统前端 / 小程序 | ✅ 已有 |
| GraphQL | 复杂联表查询 | ✅ 已有（`graphql.py`） |
| **MCP** | **Claude / Cursor / 任意 Agent 直连** | 🆕 本次新增 |

MCP 工具集（首批 8 个）：

| 工具 | 作用 |
|---|---|
| `cms_list_content_types` | 列出所有内容模型及字段 |
| `cms_describe_content_type` | 某模型的完整 schema |
| `cms_create_content_type` | 对话式建模型 |
| `cms_search_content` | **语义检索**（核心） |
| `cms_get_entry` | 按 id/slug 取条目全文 |
| `cms_create_entry` | 创建草稿（AI 写的也走这里） |
| `cms_update_entry` | 更新字段 |
| `cms_publish_entry` | 发布 + 触发 webhook |

装好后在 Claude Desktop 的 `mcp.json` 里加五行配置，就能问：
「帮我在客户案例库里找三个新能源行业、节能率 30% 以上的案例，整理成对比表」——
Agent 自己去调 `cms_search_content`，不需要你写一行代码。

---

## 五、竞品对照

| 维度 | Strapi | Payload | Directus | Sanity | Contentful | **Mosaic** |
|---|---|---|---|---|---|---|
| 开源 | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ |
| 自托管成本 | 中 | 中 | 中 | — | — | **低（单体 FastAPI）** |
| 动态建模 | GUI | 代码 | GUI | GUI | GUI | **对话** |
| 语义检索 | 插件 | 无 | 无 | 部分 | 无 | **内置** |
| MCP / Agent 接口 | ❌ | ❌ | ❌ | ❌ | ❌ | **原生** |
| 多语言 | 插件 | ✅ | ✅ | ✅ | ✅ | ✅ 内置 + AI 批量 |
| AI 内容生成 | 第三方 | 第三方 | 第三方 | 自带（贵） | 自带（贵） | **内置 + 可溯源** |
| 数据库 | PG/MySQL/SQLite | PG/Mongo | 多种 | 闭源 | 闭源 | PG 16 |

**空位很清楚**：所有开源 CMS 都还是"给人用的编辑器 + 给前端的 API"。
没有一个把 **Agent 当一等公民**。这是 Mosaic 的位置。

不跟 Sanity / Contentful 拼生态和 CDN，只拼两件：
**建模速度和 Agent 接入**。

---

## 六、功能地图

```
┌─ 内容建模 ─────────────────────────────────────────┐
│  动态 ContentType · 字段组 · 20 种字段类型          │
│  🆕 对话式建模（NL → schema）                       │
│  🆕 模型变更影响分析（改字段会不会炸已发布内容）      │
└────────────────────────────────────────────────────┘
┌─ 内容生产 ─────────────────────────────────────────┐
│  富文本/Markdown · 版本快照 · 草稿预览 · 定时发布    │
│  🆕 AI 起草（素材 → 结构化条目）                     │
│  🆕 AI 翻译（全语言批量，保留 Markdown 结构）        │
│  🆕 AI SEO（title/desc/OG/JSON-LD）                 │
│  🆕 AI 溯源（模型、prompt 摘要、生成时间，进审核日志）│
└────────────────────────────────────────────────────┘
┌─ 内容治理 ─────────────────────────────────────────┐
│  审核流 · 审核日志 · 版本回滚 · 定时上下线           │
│  🆕 AI 内容强制标记待审（不可绕过）                  │
└────────────────────────────────────────────────────┘
┌─ 内容消费 ─────────────────────────────────────────┐
│  REST · GraphQL · Webhook · 表单 · 评论             │
│  🆕 语义检索 API · RAG 就绪                         │
│  🆕 MCP Server（stdio + HTTP）                      │
└────────────────────────────────────────────────────┘
┌─ 站点渲染 ─────────────────────────────────────────┐
│  门户（portal）· 落地页（landing）· 模板引擎         │
│  🆕 GEO 优化（面向 AI 搜索引擎的结构化输出）          │
└────────────────────────────────────────────────────┘
```

---

## 七、技术架构（复用现有底座，不推倒重来）

```
┌──────────────────────────────────────────────────────────┐
│  消费方                                                    │
│  Web / 小程序     Claude·Cursor·Agent      AI 搜索引擎      │
└───────┬──────────────────┬──────────────────────┬────────┘
        │ REST/GraphQL     │ MCP (JSON-RPC)       │ JSON-LD
┌───────▼──────────────────▼──────────────────────▼────────┐
│  Mosaic Server（FastAPI · 单进程 · 可直接 Docker 起）      │
│                                                           │
│  ┌──────────────── 已有底座（22 表 / 5365 行）──────────┐  │
│  │ cms_content_types  cms_field_definitions             │  │
│  │ cms_entries  cms_entry_versions  cms_entry_translations│ │
│  │ cms_categories  cms_tags  cms_media  cms_forms        │  │
│  │ cms_entry_review_log  cms_entry_previews              │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────── 本次新增 AI 层 ──────────────────────┐  │
│  │ core/llm.py        多 provider 客户端（httpx，零依赖）│  │
│  │ apps/cms/ai/       copilot · embedding · search       │  │
│  │ apps/cms/mcp/      JSON-RPC 2.0 · stdio + HTTP        │  │
│  │ cms_embeddings     content_hash 增量向量化            │  │
│  │ cms_ai_generations 生成溯源（模型/prompt/token/耗时）  │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
                    │
        ┌───────────▼───────────┐
        │  PostgreSQL 16        │
        │  pgvector 有→原生检索 │
        │  无→应用侧余弦（默认）│
        └───────────────────────┘
```

### 数据模型增量（3 张表）

| 表 | 作用 | 关键列 |
|---|---|---|
| `cms_embeddings` | 条目向量 | `entry_id` / `field` / `dim` / `vector double precision[]` / `content_hash` / `model` |
| `cms_ai_generations` | AI 生成溯源 | `kind` / `target` / `provider` / `model` / `prompt_digest` / `tokens_in/out` / `latency_ms` / `status` |
| `cms_content_types` 加列 | 标记 AI 建的模型 | `created_by_ai bool` / `ai_spec jsonb` |

`content_hash` 是增量向量化的关键：只有内容真的变了才重新 embedding，省钱。

### 为什么复用而不用新框架

| 候选 | 否决理由 |
|---|---|
| 重写成 Strapi 插件 | Node 生态，与现有 Python 团队脱节，且拿不到"对话建模"的控制权 |
| 用 Payload 二次开发 | TS 强耦合，MCP/向量要绕过它的 ORM |
| 纯自研新服务 | 建模/版本/审核/多语言要重做一遍，3 周变 3 个月 |

现有 `cms` 模块把最难的部分（动态建模 + 版本 + 多语言 + 审核）都做完了，
**这批代码是资产，缺的只是上层 AI 和对外协议。**

---

## 八、路线图

| 阶段 | 交付 | 验收标准 |
|---|---|---|
| **M1（本次）** | LLM 客户端 · 对话建模 · AI 起草/翻译/SEO · 语义检索 · MCP Server · 迁移 | 空库能起、每模块 import 通过、MCP 用 Claude 实测能搜到内容 |
| **M2** | 管理端 AI 面板（Vue）、建模向导、翻译工作台 | 页面能跑通全流程，非技术用户 10 分钟上手 |
| **M3** | 独立产品化：独立品牌站点、Docker 一键部署、独立文档站 | `curl \| bash` 一条命令起，30 分钟从零到有内容 |
| **M4** | 生态：MCP 市场收录、Strapi/WordPress 迁移工具、Webhook→Agent 触发 | 可从主流 CMS 一键迁入 |

---

## 九、命名（三选一，我推第一个）

| 方案 | 全称 | 理由 | 风险 |
|---|---|---|---|
| **✅ Cenkor Mosaic** | Mosaic · AI 原生内容平台 | Mosaic=镶嵌/拼装，直指"内容模型自由拼装"；短、好念、`mosaic` 域名被占但 `mosaic.cenkor.com` 或 `mosaiccms.io` 可用 | 有同名公司（非 CMS 领域） |
| Cenkor Loom | Loom · AI 内容织造 | 织布=把零散素材织成内容；中文「织造」很贴 | Loom 已被录屏工具强占 |
| Cenkor Atlas | Atlas · 内容地图 | 强调"内容结构化" | 太泛，撞名严重 |

**建议**：对外叫 **Mosaic**，域名走 `mosaiccms.dev` / `getmosaic.io`，
中文对外统一「Mosaic 内容平台」，不硬造中文品牌名（AI 时代中英混排更自然）。

---

## 十、一句话总结

> 别人做的是「**给人用的 CMS**」，Mosaic 做的是「**给 AI 用的内容底座**」。
> 人负责定意图，AI 负责生产，Agent 负责消费——三条通道各归其位。
