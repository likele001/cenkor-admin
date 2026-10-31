# CMS AI 能力

Mosaic CMS 的 AI 层。四项能力：**对话式建模 · AI 起草 · AI 翻译 · 语义检索**。

> 设计前提：**AI 是可选增强，不是运行必需。**
> 未配置 `AI_API_KEY` 时，AI 端点返回 503 并给出明确提示，
> CMS 的传统能力（建模 UI / 版本 / 多语言 / 审核 / REST / GraphQL / MCP 只读工具）完全不受影响。

---

## 一、配置

```env
AI_ENABLED=true
AI_PROVIDER=openai                                  # 仅用于溯源标注
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=sk-xxx
AI_CHAT_MODEL=gpt-4o-mini
AI_EMBED_MODEL=text-embedding-3-small
AI_EMBED_DIM=1536
AI_TIMEOUT_SECONDS=60
AI_MAX_RETRIES=2
AI_TEMPERATURE=0.3
```

### 支持的模型服务

只要是 **OpenAI 兼容协议** 就能接，改 `AI_BASE_URL` + `AI_CHAT_MODEL` 即可：

| 服务 | `AI_BASE_URL` | 备注 |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | 默认 |
| DeepSeek | `https://api.deepseek.com/v1` | 无 embedding 接口，需另配 |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `text-embedding-v3` |
| Moonshot | `https://api.moonshot.cn/v1` | |
| 智谱 | `https://open.bigmodel.cn/api/paas/v4` | |
| 本地 vLLM / Ollama | `http://127.0.0.1:8000/v1` | |
| 自建网关 | 你自己的地址 | |

> ⚠️ embedding 和 chat 可以来自不同服务商，但当前实现共用一个 `AI_BASE_URL`。
> 若 chat 服务商不提供 embedding，需要在该 base_url 上做转发，或等后续支持双 base_url。

---

## 二、四项能力

### 2.1 对话式建模

```
POST /api/v1/cms/ai/content-types/propose    # 出草案，不落库
POST /api/v1/cms/ai/content-types/apply      # 确认落库
```

**输入**：

```json
{ "description": "做一个制造业客户案例库，字段有客户名、所属行业（离散制造/流程制造/新能源）、产线数量、节能率百分比、项目周期、客户 logo、项目前后对比图，要能按行业筛选" }
```

**输出**（摘要）：

```json
{
  "key": "customer_case",
  "name": "客户案例",
  "fields": [
    {"field_key": "customer_name", "field_type": "text",   "required": true},
    {"field_key": "industry",      "field_type": "select", "options": {"choices": ["离散制造","流程制造","新能源"]}},
    {"field_key": "line_count",    "field_type": "number", "validation": {"min": 1}},
    {"field_key": "energy_saving", "field_type": "number", "validation": {"min": 0, "max": 100}},
    {"field_key": "logo",          "field_type": "image"},
    {"field_key": "comparison",    "field_type": "images"}
  ],
  "key_conflict": false,
  "_meta": {"model": "gpt-4o-mini", "tokens_in": 820, "latency_ms": 3100}
}
```

**为什么不会把库搞坏**——模型输出经过四道消毒（`copilot.sanitize_content_type`）：

1. `field_type` 必须在 20 种已有类型里，越界直接丢弃
2. `field_key` 强制规整为小写 snake_case，且必须以字母开头
3. 系统字段（`id`/`status`/`title`/`created_at`…）直接拒绝
4. `select`/`multiselect` 没有候选值的，降级为 `text`

### 2.2 AI 起草

```
POST /api/v1/cms/ai/entries/draft         # 出草稿，不落库
POST /api/v1/cms/ai/entries/draft/save    # 落库（强制 draft）
```

给一段素材或大纲，产出结构完整的条目。**硬约束**：素材里没有的具体数字、客户名、日期，
模型必须留空并用「（待补充）」标出，不允许编造。

### 2.3 AI 翻译

```
POST /api/v1/cms/ai/entries/{id}/translate
{ "langs": ["en-US", "ja-JP"], "overwrite": false }
```

- 保留 JSON 结构、markdown 标记、URL、代码块
- 译文写入 `cms_entry_translations`，状态 `draft`
- 已存在的语言默认跳过（`overwrite=true` 才覆盖）
- 单语言失败不影响其他语言

### 2.4 语义检索

```
GET /api/v1/cms/ai/search?q=帮客户省电的制造业案例&limit=10
GET /api/v1/cms/ai/entries/{id}/similar
```

**混合排序**，不是纯向量：

```
最终分 = 0.7 × 向量余弦 + 0.3 × 关键词得分
```

纯向量在短查询上容易召回「语义相近但主题无关」的内容。加关键词可以让任何一边的强信号都被捞上来。

中文分词用 **bigram**（`节能案例` → `节能`/`能案`/`案例`）——
直接用 `\w+` 会把整句中文当一个 token，永远匹配不上，这个坑踩过。

---

## 三、向量存储

### 3.1 为什么不用 pgvector

线上 PG 未必装了该扩展，装扩展要停机重启，而「AI 能不能用」不该被一个扩展卡住。

当前实现：`cms_embeddings.vector` 用 PG 原生 **`double precision[]`** 存，
检索时拉到内存算余弦。`search.py` 里保留 `has_pgvector()` 探测，
装了扩展的环境会走原生算子——**两条路都能跑，对调用方透明**。

### 3.2 增量向量化（省钱的关键）

每条向量旁存一份 `content_hash`（源文本的 sha256 前 32 位）。
内容没变就不重新调 embedding 接口。

```
POST /api/v1/cms/ai/vectors/rebuild
{ "limit": 50 }              # 批量补齐
{ "entry_id": 123, "force": true }   # 强制重算某条（换模型后用）
```

**换 embedding 模型后必须带 `force=true` 全量重算**，否则新旧向量维度不一致会算错。

### 3.3 维度说明

`AI_EMBED_DIM` 只是参考值。实际维度以接口返回为准，写进 `cms_embeddings.dim`。
检索时维度不一致的向量会被跳过（`_cosine_py` 里做了长度校验）。

---

## 四、数据表

| 表 | 作用 | 关键列 |
|---|---|---|
| `cms_embeddings` | 条目向量 | `entry_id` / `field` / `lang` / `vector` / `dim` / `content_hash` / `model` |
| `cms_ai_generations` | 生成溯源 | `kind` / `target` / `provider` / `model` / `prompt_digest` / `tokens_in/out` / `latency_ms` / `status` |

**建表方式**：走 alembic —— `core/20261031_1310_cms_ai_tables.py`
（五张表：`cms_embeddings` / `cms_ai_generations` / `cms_ai_providers` /
`cms_ai_capabilities` / `cms_ai_prompts`）。启动时 `ensure_cms_ai_schema()`
只剩校验职责，不再执行任何 DDL。

> 2026-10-31 起所有 DDL 统一收进 alembic。原先的 `apps/cms/ai/schema.sql` 已删除：
> 它在**应用启动后**执行，而 alembic 在**启动前**执行，两者顺序相反，
> 导致 `003_embed_dims` / `004_vector_pgvector` 这类 ALTER 永远等不到表 ——
> 那两条 SQL 从来没被任何脚本自动执行过，只在生产手工跑过一次。
>
> pgvector 是可选依赖：装了就用 `vector(1024)` + HNSW 余弦索引；
> 没装（CI / docker 的 `postgres:16-alpine`）自动降级为 `double precision[]`，
> 检索走应用内余弦，不报错。装好后跑 `backend/scripts/enable_pgvector.py` 升级列类型。

---

## 五、溯源与成本

每次 AI 调用写一条 `cms_ai_generations`：

```json
{
  "kind": "entry_draft",
  "target": "content_type:7",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "prompt_digest": "a1b2c3...",
  "tokens_in": 1240, "tokens_out": 890,
  "latency_ms": 5200,
  "status": "ok",
  "created_by": 1
}
```

只存 prompt 摘要不存原文——够审计、够归因，又不把业务数据再复制一份。

```bash
GET /api/v1/cms/ai/usage?days=30
```

按 `kind` 汇总调用次数、token 消耗、平均耗时，用于算成本。

---

## 六、可观测日志

| 事件 | 含义 |
|---|---|
| `llm.chat` | 一次补全成功（含 token / 耗时） |
| `llm.retry` / `llm.network_retry` | 退避重试 |
| `llm.json_repair` | 输出不是合法 JSON，回灌修复一次 |
| `cms.ai.field_type_rejected` | 模型给了不存在的字段类型，已丢弃 |
| `cms.ai.reserved_field_rejected` | 模型试图创建系统字段，已拒绝 |
| `cms.vectorized` | 条目向量化完成 |
| `cms.search` | 检索（候选数 / 命中数） |
| `cms.ai.schema_ready` | AI 表就绪 |

---

## 七、已知限制

1. **chat 与 embedding 共用一个 base_url**——服务商分离时需要网关转发
2. **无 pgvector 时全量内存检索**，候选上限 20000 条；超过需要装 pgvector
3. **numpy 可选**：装了走矩阵运算（快 1~2 个数量级），没装走纯 Python
4. **翻译不处理图片本地化**，只翻文本字段
5. **管理端 UI 未做**——当前只有 API 和 MCP，前端 AI 面板在下一阶段
