# AI 配置 · 后台可视化管理

> 入口：后台「CMS → AI 设置」（`/cms/ai-settings`），仅管理员可见。

## 为什么不再写 `.env`

`.env` 有三个绕不过去的硬伤：

1. **改一次要重启**——换模型是日常操作，不该每次都重启进程。
2. **看不到状态**——密钥填错了界面毫无反馈，只能等用户报错。
3. **只有一份**——chat 用便宜的、embedding 用另一家、看图用第三家，`.env` 越写越乱。

所以配置搬进数据库，`.env` 降级为**兜底**：后台绑定了就以后台为准，没绑定才回退环境变量。
老部署升级后立刻可用，不会因为「还没去界面点一遍」而全线不可用。

## 数据模型

### `cms_ai_providers` · 服务商通道

一家服务商 = 一个 `base_url` + 一把密钥 + 一套连接参数。

| 列 | 说明 |
|---|---|
| `slug` | 唯一标识，如 `dashscope`，供日志引用 |
| `kind` | 协议族：`openai` / `azure` / `ollama` |
| `base_url` | 填到 `/v1` 为止。误填 `/chat/completions` 会被自动裁掉 |
| `api_key_enc` | **Fernet 密文**，前缀 `enc:v1:` |
| `api_key_hint` | 末四位掩码（`****cdef`），列表页零解密 |
| `extra_headers` | 网关自定义鉴权头（JSONB） |
| `timeout_seconds` / `max_retries` | 连接参数 |
| `last_test_at` / `last_test_ok` / `last_test_error` | 上次连通性测试留痕 |

### `cms_ai_capabilities` · 能力绑定

`capability` 作主键，语义是「每类能力只有一套生效配置」——结构简单、读取零歧义。
将来要做多模型轮询或故障转移，另加 fallback 表即可，不必改这张。

| 能力 | 状态 | 用途 |
|---|---|---|
| `chat` | 已接入 | 建模、起草、翻译、SEO |
| `embedding` | 已接入 | 语义检索与相似度 |
| `vision` | 已接入 | 看图说话、图文审校 |
| `image` | 已接入 | 封面图、配图生成 |
| `rerank` | 仅配置 | 检索精排，预留 |
| `asr` | 仅配置 | 音视频转文字，预留 |
| `tts` | 仅配置 | 文案转语音，预留 |

参数按能力白名单过滤：`chat` 认 `temperature / max_tokens / top_p / frequency_penalty`，
`embedding` 认 `dim / batch`，`image` 认 `size / quality / n / style`。
**未知键直接丢弃、越界值夹到边界**——避免「温度填 500」这种把请求打成 400 的低级故障。

## 密钥安全

- 加密密钥由 `SECRET_KEY` 经 HMAC-SHA256 派生，不新增配置项
- 明文只在内存里存在一次；接口永远只回传掩码
- **编辑时回传掩码等于「不修改」**——这是必须的，否则改个超时时间就会把密钥覆盖成 `****cdef`
- `SECRET_KEY` 轮换后旧密文解不开：不会 500，而是标记 `key_error` 并降级，界面提示重新填写

## 配置优先级

```
后台绑定（cms_ai_capabilities）  ── 命中则用，source = db
      ↓ 未绑定或服务商停用
环境变量（AI_*）                ── source = env
      ↓ 都没有
未配置                          ── 能力不可用，端点返回 503
```

`GET /api/v1/cms/ai/overview` 的 `capabilities[].source` 直接告诉你每一项当前走哪条路。

## 缓存与刷新

`get_llm_for()` 是同步调用，不能在里面查库。所以：

- **启动预热**：`main.py` 的 lifespan 里加载一次（日志 `ai.registry.ready`）
- **写入即刷**：任何配置写操作提交后立刻 `load(force=True)`
- **TTL 兜底**：30 秒过期，过期后由下一个异步调用点后台补刷
- 多 worker 部署时，其他进程靠 TTL 兜底，最长 30 秒生效

## 界面操作

1. **服务商** 标签页 → `+ 添加服务商`，可点预设一键填充（OpenAI / 通义 / DeepSeek / Kimi / 智谱 / 硅基流动 / 本地 Ollama）
2. 填密钥 → 保存 → 点「测试」，看 `/models` 是否可达、延迟多少
3. **能力绑定** 标签页 → 选能力 → 选服务商 + 填模型名 + 调参数 → 保存
4. 点「测试」验证真实调用（chat 发一句话、embedding 返回维度、vision 传 1x1 像素、image 出图）

## API 清单

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/cms/ai/overview` | 总览：各能力是否就绪、来源 |
| GET | `/api/v1/cms/ai/presets` | 内置服务商预设 |
| GET | `/api/v1/cms/ai/providers` | 服务商列表 |
| POST | `/api/v1/cms/ai/providers` | 新增 |
| PATCH | `/api/v1/cms/ai/providers/{id}` | 修改（密钥留空/回传掩码 = 不改） |
| DELETE | `/api/v1/cms/ai/providers/{id}` | 删除（被绑定则 409） |
| POST | `/api/v1/cms/ai/providers/{id}/test` | 连通性测试 |
| GET | `/api/v1/cms/ai/capabilities` | 能力绑定总览 + 参数规格 |
| PUT | `/api/v1/cms/ai/capabilities/{cap}` | 绑定/更新 |
| DELETE | `/api/v1/cms/ai/capabilities/{cap}` | 解绑 |
| POST | `/api/v1/cms/ai/capabilities/{cap}/test` | 按绑定实测 |

权限：读 `cms:ai:read`，写 `cms:ai:manage`，超管自动放行。

## 常见坑

**DeepSeek 没有 embedding**——只配 chat 的话语义检索不可用。要么给 `embedding` 单独绑一家
（通义 `text-embedding-v3` 或硅基流动 `BAAI/bge-m3`），要么放弃语义检索。

**image 的 size 各家不一致**——OpenAI 用 `1024x1024`，国内服务常见 `1024*1024`。
填错会返回明确报错，界面上一眼能看出来，不是静默失败。

**换 embedding 模型要重建向量**——不同模型维度不同，历史向量作废。
换完跑一次 `POST /api/v1/cms/ai/vectors/rebuild` 全量重算。

**服务商删不掉**——先解绑占用的能力。这是故意的：静默删掉会让线上某项能力突然不可用。

## 环境变量（兜底路径）

后台完全不用时，`.env` 里这些仍然有效：

```env
AI_ENABLED=false                    # 总开关
AI_PROVIDER=openai                  # 仅溯源标注
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=                         # 留空则 AI 功能全部降级
AI_CHAT_MODEL=gpt-4o-mini
AI_EMBED_MODEL=text-embedding-3-small
AI_EMBED_BASE_URL=                  # embedding 单独一家时填
AI_EMBED_API_KEY=
AI_EMBED_DIM=1536
AI_VISION_MODEL=                    # 留空则该能力未启用
AI_IMAGE_BASE_URL=
AI_IMAGE_API_KEY=
AI_IMAGE_MODEL=
AI_TIMEOUT_SECONDS=60
AI_MAX_RETRIES=2
AI_TEMPERATURE=0.3
AI_EMBED_BATCH=32
```
