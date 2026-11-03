# Cenkor Admin Platform — V2 架构文档

> **版本**: v3.0.0
> **更新日期**: 2026-11-01
> **状态**: 已上线运行。M1–M3 完成；2026-10 起新增 **主题模板工作台（Jinja2）· URL 伪静态规则 · 页面构建器 · AI 内容中心 · 多站点隔离**，见第十一章。
>
> ⚠️ **本文档以「当前代码实际行为」为准。** 与历史规划不一致处已直接改写，不保留旧结论；
> 只有确实还在跑的兼容逻辑才会标注为「历史兼容」。

---

## 目录

1. [概述](#一概述)
2. [V2 核心创新](#二v2-核心创新)
3. [内容引擎架构](#三内容引擎架构)
4. [双用户体系架构](#四双用户体系架构)
5. [模板引擎](#五模板引擎)
6. [App 中心 V2](#六app-中心-v2)
7. [安全架构](#七安全架构)
8. [API 清单](#八api-清单)
9. [数据模型总览](#九数据模型总览)
10. [测试与部署](#十测试与部署)
11. [2026-10 新增能力](#十一2026-10-新增能力)

---

## 一、概述

### 1.1 V2 核心目标

| 目标 | V1 状态 | V2 改进 |
|------|---------|--------|
| 通用内容引擎 | 3 张硬编码表（products/cases/news） | 通用 cms_entries + 动态字段定义 |
| 字段管理 | 改代码才能改字段 | 后台 UI 增删改 + **21 种**字段类型 |
| 分类标签 | 无 | 3+ 级分类树 + 标签系统 |
| 双用户体系 | auth_users 一套 | auth_users（后台）+ portal_users（前台）隔离 |
| 模板引擎 | 无 | **Jinja2**（站点主题渲染）；Liquid 仅保留一个兼容端点，见第五章 |
| App 中心 | 仅 manifest 声明 | manifest 声明 + 自动注册内容/字段/分类 |

### 1.2 V2 架构总览

```
前端层
├── admin-web        B 端后台       Vue 3 SPA     admin JWT
├── portal-web       C 端前台       Vue 3 SPA     portal JWT
├── developer-web    开发者门户      Vue 3 SPA     admin JWT
└── 官网 / 公站       Jinja2 主题     nginx 出 HTML  免 token（读只读 API）
         │
         ↓
后端层  FastAPI（127.0.0.1:8002，宝塔 Python 项目 cenkor 托管）
├── 内容引擎         内容类型 / 字段定义 / 条目（cms_entries）
├── App 中心         manifest 声明 + 启动自动注册 + FieldRegistry
├── 模板工作台       Jinja2 主题文件 / 在线编辑 / 预览 / 切换生效
├── 页面渲染         /api/v1/page/*  →  HTML 直出（2026-10 新增）
├── URL 规则         四层就近优先，老地址 301
└── AI 内容中心      17 个菜单：生产 / 质检 / 分发 / 配置
         │
         ↓
数据层
├── PostgreSQL 16    主库，public schema 共 256 张表
├── Redis 7          db5（宿主机共享实例，按库号给各项目分）
└── 对象存储          七牛云 Kodo（主）+ 本地 MinIO（双写备份）
```

> 上图是**当前实际形态**，不是设计稿。改之前请先用 `ss -tlnp`、`\dt` 自己对一遍。

---

## 二、V2 核心创新

### 2.1 通用内容引擎

**设计原则**：所有内容（产品/案例/新闻/自定义）统一走 `cms_entries` 表，差异化由 `cms_field_definitions` 驱动。

**V1 → V2 对比**：

```
V1:
  cms_products (硬编码 schema) + cms_cases + cms_news
  ↓ 增删字段 → 改代码 + 数据库迁移

V2:
  cms_entries (id, title, content JSONB, custom_fields JSONB, ...)
  + cms_content_types (product/case/news/自定义)
  + cms_field_definitions (动态字段元数据)
  ↓ 增删字段 → 后台 UI 操作，零代码
```

> ⚠️ **「统一」指的是「自定义内容都走 cms_entries」，不是「原来的三张表已废弃」。**
> `cms_products` / `cms_cases` / `cms_news` **仍在生产使用**（固定表单，字段写死、不能加），
> 与 `cms_entries` 并存、互不干扰。这是有意的：
> 官网三个固定板块的表单稳定，不需要为它们引入动态字段的开销。
> 后台菜单也如实分两套：产品 / 案例 / 新闻 vs 通用内容。

### 2.2 双用户体系

**核心原则**：前后台用户完全隔离，路由级强制鉴权。

```
auth_users (后台)        portal_users (前台)
   ↓                          ↓
 admin JWT                portal JWT
 issuer:                   issuer:
 cenkor-admin            cenkor-portal
 secret:                  secret:
 SECRET_KEY             SECRET_KEY + ":portal"
   ↓                          ↓
 后台 API                  前台 API
 /api/v1/cms/*             /api/v1/public/portal/*
 /api/v1/auth/*            /api/v1/public/site/*
                           /api/v1/page/*（站点页面渲染，见 5.2）
   ↓                          ↓
   拒绝 portal token (403)    拒绝 admin token (401)
```

> `/api/v1/page/*` 是 **2026-10 新加的独立前缀**，专门接站点页面渲染（原来是 nginx 直出静态页）。
> 它和 `/api/v1/public/*` 的区别：`public` 给前端 JS 取数据用（JSON），`page` 直接出 HTML 给爬虫和首屏。

---

## 三、内容引擎架构

### 3.1 数据模型

```sql
-- 内容类型（元数据）
cms_content_types (
  key VARCHAR(60) UNIQUE,         -- 'product' | 'case' | 'news' | 自定义
  supports_category BOOL, supports_tags BOOL
)

-- 字段分组（实现 Tabs UI）
cms_field_groups (
  content_type_id FK, key, label, sort
)

-- 字段定义（21 种类型）
cms_field_definitions (
  content_type_id FK, field_key, label, field_type,
  required, default_value, options JSONB, validation JSONB,
  group_id FK, sort
)

-- 字段候选项（select / multiselect）
cms_field_options (definition_id FK, value, label, color, sort)

-- 通用内容表（实际列，2026-11 核实）
cms_entries (
  id, content_type_id FK,
  slug,                       -- 网址短名
  title,
  content JSONB,              -- ← 固定字段
  custom_fields JSONB,        -- ← 动态字段（GIN 索引）
  category_id FK, status, author_id, sort, view_count,
  seo JSONB,                  -- SEO 三件套
  site_id FK,                 -- 多站点隔离
  url_path,                   -- URL 伪静态自定义地址
  ai_origin, ai_generation_id,-- AI 产出标记（人写的内容为 NULL）
  published_at, scheduled_at, expire_at,
  created_at, updated_at, deleted_at
)

-- 关键唯一约束（语义上很重要，别忽略）
--   uq_entry_site_ct_slug      (site_id, content_type_id, slug)
--     → slug 只在「同一站点 + 同一内容类型」内唯一，跨类型可重名
--   uq_cms_entries_site_url_path (site_id, url_path)
--     → 自定义地址全站唯一，冲突会直接写不进去

-- 分类（3+ 级自引用）
cms_categories (id, content_type_id FK, parent_id FK, slug, name, ...)

-- 标签
cms_tags (id, content_type_id FK, slug, name, color)

-- 多对多关联
cms_content_tags (content_type_id, content_id, tag_id)
```

### 3.2 21 种字段类型

| 类别 | 数量 | 类型 |
|------|------|------|
| 文本 | 4 | text, longtext, richtext, markdown |
| 数字/布尔/日期 | 4 | number, boolean, date, datetime |
| 联系 | 3 | url, email, phone |
| 媒体 | 4 | image, images, file, files |
| 选择 | 2 | select, multiselect |
| 高级 | 3 | json, repeater, relation |
| 其他 | 1 | color（色值，默认 `#000000`） |

详见 `apps/cms/field_types.py`。

### 3.3 字段值存储

```json
// CMS Entries 表的实际存储
{
  "id": 1,
  "content_type_id": 1,        // product
  "title": "ThinkMES",
  "content": {                // 固定字段（content JSONB）
    "name": "ThinkMES",
    "tagline": "...",
    "line": "manufacturing",
    "features": [...]
  },
  "custom_fields": {          // 动态字段（custom_fields JSONB）
    "price": 9999,
    "screenshots": ["url1", "url2"],
    "license": "Apache-2.0"
  },
  "category_id": 1,
  "status": "published"
}
```

### 3.4 GIN 索引性能

```sql
-- custom_fields GIN 索引（支持任意 key 查询）
CREATE INDEX ix_cms_entries_custom_fields
ON cms_entries USING gin(custom_fields);

-- 查询示例
SELECT * FROM cms_entries
WHERE custom_fields @> '{"license": "Apache-2.0"}';
```

---

## 四、双用户体系架构

### 4.1 路由级隔离

```
请求进入 → 检查 Authorization Bearer token
  ↓
尝试 admin SECRET 解码
  ↓
成功 → 验证 issuer/load user → 进入后台路由
失败 → 尝试 portal SECRET
  ↓
成功 → 返回 403 "前台用户无法访问后台管理接口"
  ↓
两侧都失败 → 返回 401
```

### 4.2 隔离中间件

```python
async def get_current_user(creds, db):
    try:
        payload = decode_token(creds.credentials)  # admin key
    except JWTError:
        try:
            portal_payload = decode_portal_token(creds.credentials)  # portal key
            if portal_payload.get("iss") == PORTAL_JWT_ISSUER:
                raise HTTPException(403, "前台用户无法访问后台管理接口")
        except HTTPException:
            raise
        ...
        raise HTTPException(401, "Token 无效")
    # ... 继续 admin 流程
```

---

## 五、模板引擎

> ⚠️ **选型结论已变更。** V2 设计阶段选的是 Liquid，实际落地改成 **Jinja2（服务端渲染）**。
> Liquid 只剩一个历史兼容端点还在跑（见 5.6），新代码不要再用。

### 5.1 现状：Jinja2 服务端渲染

站点主题由后端用 **Jinja2** 渲染成 HTML 直出。核心实现：

| 文件 | 职责 |
|---|---|
| `core/jinja_env.py` | 环境管理、resolver 切换、编译缓存、`validate_source` / `render_source` |
| `apps/cms/render.py` | 主题解析（DB 主题 > 内置主题）、渲染超时、缓存失效 |
| `apps/cms/template_router.py` | 模板 API：校验 / 预览 / 文件读写 / 主题管理 |
| `apps/cms/cms_page_router.py` | 站点页面入口（`/api/v1/page/*`），接手原来 nginx 直出的动态页面 |

对比 Liquid 方案的实际取舍：

| 维度 | Liquid（原选型） | Jinja2（实际采用） |
|---|---|---|
| 渲染位置 | 前后端同构（liquidjs + python-liquid） | **仅服务端**，前端拿 HTML |
| 沙箱 | 原生沙箱 | 靠 resolver 白名单 + 禁用危险全局实现 |
| 能力 | 需自定义 filters | 模板继承、宏、include 齐全，写主题更快 |
| SEO | 需前端渲染后再爬 | **HTML 直出**，爬虫拿到的就是最终内容 |

关键收益是最后一条：直出 HTML 对 SEO 和首屏都更稳，代价是失去了前端同构能力（不再需要）。

### 5.2 渲染链路

```
浏览器 GET /article/xxx.html
   ↓
nginx  →  /api/v1/page/article/xxx.html
   ↓
cms_page_router（按 URL 规则反解出 类型/栏目/标签/详情）
   ↓
resolve_theme（先查 DB 主题，没有则用 builtin_theme）
   ↓
jinja_env 渲染 layout.html + detail.html + partials/*
   ↓
HTML 直出（可选落盘到静态缓存，默认关闭）
```

**首页是例外**：`GET /` 由 nginx 直接返回静态 `index.html`，**不经过主题渲染**。改模板永远改不动首页。

### 5.3 主题文件结构

```
layout.html          # 骨架（header / footer / 插槽）
detail.html          # 详情页
page.html            # 单页（关于我们等）
list.html            # 列表页
404.html             # 找不到
partials/meta.html   # <head> 内的 meta / SEO
partials/header.html # 站头
partials/footer.html # 站尾
partials/card.html   # 列表卡片
partials/pagination.html
macros/ui.html       # 可复用宏
assets/style.css     # 内联进 <style>，无独立 js 入口
```

### 5.4 模板 API（后台，需 `cms:site:read` / `write`）

| 端点 | 用途 |
|---|---|
| `POST /api/v1/cms/templates/validate` | 编译期报错定位到**行 / 列**，编辑器标红用 |
| `POST /api/v1/cms/templates/preview` | 渲染任意模板字符串（带 data） |
| `POST /api/v1/cms/templates/preview-page` | **按主题上下文预览**：能调 `content_list` / `site` / `nav` 全部数据 API，支持未保存的跨文件覆盖 |
| `GET/PUT /api/v1/cms/templates/files` | 主题文件读写（在线编辑器后端） |
| `.../themes` | 主题增删、**切换生效**、与内置版逐行对比、zip 导入导出 |

> **`preview-page` 的语义坑**：要渲染的目标模板放 `source`，其它未保存文件放 `overrides`。
> `overrides[path]` 会覆盖同名文件，把目标模板也塞进 `overrides` 会被自己的空串盖掉。

### 5.5 三个必须知道的约束

1. **编译缓存按模板名缓存、key 不含源码。** `{% include %}` 出来的 partial 一旦编译过，
   换 resolver 也拿不到新内容 → 预览渲染前必须 `flush_compiled_templates()`。
   `render_source` 那层按源码 md5 缓存，不受影响。
2. **预览 iframe 是 `sandbox=""`**，禁脚本。主题 JS 改动保存生效后线上才看得到。
3. **保存 ≠ 生效**，要显式「设为生效」。

### 5.6 历史兼容：还在跑的 Liquid

只有一个端点仍用 Liquid（`core/template_engine.py`，python-liquid）：

```
POST /api/v1/public/templates/render   ← 供老的 portal-web 调用
```

它**不参与站点主题渲染**，返回结构固定为 `{rendered}`。新功能不要再接这个端点；
`docs/dev_guide.md` 里的「Liquid 模板开发」章节讲的是这一段历史内容。

### 5.7 主题级业务 Filters

| Filter | 用途 |
|--------|------|
| `t` | i18n 翻译（business line → 中文） |
| `format_price` | 价格格式化（¥1,234.00） |
| `asset_url` | 资源 URL 补全 |
| `thumb` | 缩略图 URL |
| `reading_time` | 估算阅读时长 |

---

## 六、App 中心 V2

### 6.1 V2 扩展字段

```python
@dataclass
class AppManifest:
    key: str
    name: str
    version: str

    # V2 新增：内容声明
    content_types: list[dict]      # 声明本 App 的内容类型
    field_groups: list[dict]       # 字段分组模板
    field_definitions: list[dict]  # 字段定义
    categories_seed: list[dict]    # 初始分类
    public_routes_prefix: str      # 公共 API 前缀
```

### 6.2 启动自动注册

```python
# 启动时（main.py lifespan）
for key, manifest in scan_app_manifests().items():
    if key not in installed_keys:
        install_app(db, key)
        # install_app 内部自动调用 FieldRegistry
        # 注册 content_types / field_groups / field_definitions / categories_seed
```

### 6.3 FieldRegistry

```python
class FieldRegistry:
    async def register_content_type(db, key, name, **kwargs) -> ContentType
    async def register_field_group(db, content_type_id, key, label, **kwargs) -> FieldGroup
    async def register_field_definition(db, content_type_id, field_key, label, field_type, **kwargs) -> FieldDefinition
    async def register_field_option(db, definition_id, value, label, **kwargs) -> FieldOption
    async def register_category(db, content_type_id, slug, name, parent_id=None, **kwargs) -> Category
    async def register_from_manifest(db, manifest) -> dict  # 一次性注册所有
```

### 6.4 权限委派

```json
// InstalledApp.permissions_grants
{
  "content_editor": [
    "cms:field_definitions:read",
    "cms:field_definitions:write",
    "cms:entries:read",
    "cms:entries:write"
  ],
  "content_viewer": [
    "cms:field_definitions:read",
    "cms:entries:read"
  ]
}
```

后台 UI 可视化编辑，PUT `/api/v1/system/apps/{key}/permissions-grants`。

---

## 七、安全架构

### 7.1 JWT 双签发

| Token | Issuer（`iss` 声明） | Secret 派生 | 客户端携带 | 用途 |
|-------|--------|--------|------|------|
| admin | `cenkor-admin` | `SECRET_KEY` | `Authorization: Bearer`；admin-web 存 localStorage `cenkor_token` | 后台所有路由 |
| portal | `cenkor-portal` | `SECRET_KEY + ":portal"` | `Authorization: Bearer` | 前台 portal-web |

> 两个 token **不是一个东西**：用错会在服务端被识别并明确拒绝 ——
> portal token 打后台接口返回 **403**（「前台用户无法访问后台管理接口」），
> admin token 打前台接口返回 **401**。别把它当成「权限不够」，是走错了门。

### 7.2 SECRET_KEY 轮换

```bash
# 步骤 1: 生成新 key
NEW_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# 步骤 2: 部署配置（同时支持新旧 key）
SECRET_KEY="$NEW_KEY"
SECRET_KEY_OLD="<旧 key>"

# 步骤 3: 验证所有旧 token 仍可解码

# 步骤 4: 观察一段时间后清除 SECRET_KEY_OLD
```

`decode_token` 依次尝试所有 key（最新的优先），轮换无停机。

### 7.3 CORS 收紧

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,  # 不允许 "*"
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "X-Request-Id"],
    expose_headers=["X-Request-Id", "Content-Language"],
    max_age=600,
)
```

### 7.4 密码哈希

- bcrypt（passlib），全站唯一入口 `core/pwd.py`
- 依赖约束 `bcrypt>=4.1,<5`：4.1 起删除 `__about__`，由 `core/pwd.py` 补兼容垫片；
  `<5` 是为规避 5.0 把超 72 字节口令由静默截断改为抛 `ValueError`
- 哈希输出 `$2b$12$`，与 bcrypt 3.x / 4.x 完全互通，历史口令零迁移
- 不要在别处新建 `CryptContext`：参数分叉会导致「改完密码登录不了」

### 7.5 滑动验证

- 16+ hex chars captcha_token
- 防纯脚本自动注册/登录
- 真正的强度依赖 HTTPS + 限流

---

## 八、API 清单

### 8.1 后台 API（需 admin JWT）

| 模块 | 路径前缀 | 职责 |
|------|----------|------|
| Auth | `/api/v1/auth/*` | 登录 / 刷新 / 用户信息 |
| RBAC | `/api/v1/rbac/*` | 用户、角色、菜单、权限 |
| CMS 内容引擎 | `/api/v1/cms/*` | 内容类型 / 字段 / 分类 / 标签 / 条目 / 审核 / 版本 |
| CMS 模板 | `/api/v1/cms/templates/*` | 主题文件读写、校验、预览、主题切换（见 5.4） |
| CMS 站点与规则 | `/api/v1/cms/site*`、`/api/v1/cms/url-rules*` | 站点配置、多站点、URL 伪静态规则 |
| CMS AI | `/api/v1/cms/ai*` | AI 起草 / 批量 / 知识库 / 质检 / 分发 |
| 页面构建 | `/api/v1/builder/*` | 可视化搭建的页面与区块 |
| Notifications | `/api/v1/notifications/*` | 站内通知 |
| API Keys | `/api/v1/api-keys/*` | 对外开放密钥 |
| System | `/api/v1/system/*` | 审计 / 应用 / 设置 / 任务 / 代码生成 |

> 这里**不写端点数** —— 每加一个功能数字就假，靠不住。要看实时清单，开发环境启动后访问 `/api/docs`。

### 8.2 公共 API（无需鉴权）

| 模块 | 路径 | 职责 |
|------|------|------|
| CMS 公共内容 | `/api/v1/public/*` | 内容类型 / 分类 / 标签 / 字段定义 / 条目（JSON） |
| 固定板块 | `/api/v1/public/products` · `/cases` · `/news` | 三个固定板块的公开列表与详情 |
| 公共模板渲染 | `/api/v1/public/templates/render` | **Liquid 历史兼容**，仅老 portal-web 用（见 5.6） |
| 站点页面渲染 | `/api/v1/page/*` | **直接出 HTML**，接 nginx 的站点页面请求（见 5.2） |
| Portal Auth | `/api/v1/public/portal/auth/*` | 前台会员登录 / 注册 |
| Portal Me | `/api/v1/public/portal/me/*` | 前台会员自身信息 |
| RAG 检索 | `/api/v1/public/rag` | 对外 chunk 检索，给外部 AI / Agent 接入（配了 `MCP_API_KEY` 就要带 key） |
| 表单 / 评论 / 埋点 | `/api/v1/public/*` | 表单提交、评论、访问统计 |

完整 API 文档：**开发环境**访问 `/api/docs`（Swagger UI）或 `/api/redoc`；生产环境已关闭文档端点。

---

## 九、数据模型总览

### 9.1 V2 新增表

| 表 | 说明 | 2026-11-01 实测行数 |
|----|------|------|
| cms_content_types | 内容类型 | **5** |
| cms_field_groups | 字段分组 | — |
| cms_field_definitions | 字段定义（21 种类型可选） | **14** |
| cms_field_options | 字段候选项 | — |
| cms_entries | 通用内容 | **53** |
| cms_categories | 分类（3+ 级） | **12** |
| cms_tags | 标签 | **3** |
| cms_content_tags | 内容-标签多对多 | — |
| portal_users | 前台用户 | **24** |
| portal_user_oauth | 前台用户 OAuth | — |
| portal_login_logs | 前台登录日志 | — |

> **行数是快照，不是契约。** 写在这里只为让人有个量级概念（比如「这站到底用了多少内容」）。
> 需要准数直接查库：`select count(*) from cms_entries;`。别把行数当断言写进文档。
>
> 2026-10 起另有站点隔离相关列与表（`cms_sites` 等），见第十一章。

### 9.2 固定表单三表：仍在生产使用

| 表 | 2026-11-01 实测 |
|----|------|
| cms_products | **25 行** |
| cms_cases | **3 行** |
| cms_news | **16 行** |

三张表都带 `custom_fields` 列。它们**没有**被 `cms_entries` 取代，后台菜单里也仍是独立入口
（产品 / 案例 / 新闻）。新增字段的 `custom_fields` 是这个板块自己的扩展位，
与「内容类型 → 字段定义」那套动态机制**互不干扰** —— 在内容类型里加字段，不会改变这三张表的表单。

### 9.3 现有表扩展

| 表 | 新增列 |
|----|--------|
| auth_users | `user_type` |
| cms_products | `custom_fields` |
| cms_cases | `custom_fields` |
| cms_news | `custom_fields` |
| platform_apps | `permissions_grants` |

---

## 十、测试与部署

### 10.1 测试覆盖

最近一次全量跑（2026-10-31）：

```
pytest   → 93 passed / 25 skipped
ruff     → All checks passed
vue-tsc  → 零错误
vite build → 成功
```

> 以前这里写的是「总测试数 100+，新代码 100% 覆盖」——**别信这种话**。
> 覆盖率没有接 CI 度量，写「100%」只是自我安慰。要看真实情况就跑 pytest，
> 看 passed / skipped 各多少；skipped 里有一部分是依赖外部服务（七牛、模型 API）的用例。

### 10.2 部署

> **生产部署见 [`docs/deploy.md`](docs/deploy.md)** —— 本机生产是「宿主机 + 宝塔」：
> 后端由宝塔 Python 项目 `cenkor` 托管（用户 `www`，端口 `8002`），
> PostgreSQL / Redis 为宿主机原生服务；
> **对象存储主用七牛云 Kodo，本地 MinIO 仅作双写备份**（`cloud_storage_config.active_provider = qiniu`）。
> 以下为**本地开发**启动方式。

```bash
# 1. 安装依赖
cd backend
pip install -r requirements.txt

# 2. 数据库迁移（生产环境由后端 lifespan 自动执行）
alembic upgrade heads

# 3. 本地开发启动
uvicorn cenkor_admin.main:app --host 0.0.0.0 --port 8000
```

> ⚠️ 生产**禁止**手动 `kill` / `nohup` 起 Python 进程：宝塔自带守护与自愈，
> 手动起的进程会抢端口，让宝塔反复 `address already in use`。
> 需要重启时：先 kill 掉占端口的残留，**不要手动拉起**，等宝塔自愈接管。

### 10.3 数据迁移

```bash
# 旧表 → cms_entries
python -m cenkor_admin.scripts.migrate_to_entries

# 该脚本幂等，可重复执行
```

详见 `docs/roadmap.md` 的 W10 联调上线部分。

---

## 附录：迁移时间线

| 周 | 主要工作 | 状态 |
|----|----------|------|
| W1 | 字段定义表 + Alembic 迁移 | ✅ |
| W2 | 字段 API + 后台 UI | ✅ |
| W3 | 分类表 + 后台 | ✅ |
| W4 | 标签 + 通用内容接入 + 数据迁移 | ✅ |
| W5 | 公共 API + Portal Auth | ✅ |
| W6 | 模板引擎集成（**原计划 Liquid，实际落地为 Jinja2**，见第五章） | ✅ |
| W7 | 网站静态页 + App 中心增强 | ✅ |
| W8 | 测试 + 文档 | ✅ |
| W9 | 用户体系拆分收尾 | ✅ |
| W10 | 联调 + 上线 | ✅ |
| **W11+** | **2026-10 起的新增能力，见第十一章** | ✅ 已上线 |

---

## 十一、2026-10 新增能力

V2 之后又落了一整批能力。**本章是本文档此前完全缺失的部分** —— 如果你只看了前九章，
会以为这个系统还停在「内容引擎 + 双用户体系」的阶段。

### 11.1 主题模板工作台（Jinja2）

见第五章。要点：后台在线编辑主题文件、实时预览（支持未保存的跨文件覆盖）、
与内置主题逐行对比、zip 导入导出、切换生效。

- 表：`cms_templates`
- 入口：后台「内容管理 → 模板预览」（`/cms/templates`）
- 模板文件落在主题目录，DB 里存版本与生效状态

### 11.2 URL 伪静态规则

全站地址形态后台可配，**四层就近优先**：

| 层级 | 配在哪 | 作用范围 |
|---|---|---|
| 1（最优先） | 内容编辑页「自定义地址」 | 单条内容 |
| 2 | 栏目（分类）管理 | 该栏目**自己的页面地址** |
| 3 | 标签管理 | 该标签页的地址 |
| 4（兜底） | 站点配置 → URL 规则 | 其余全部 |

**语义红线**：栏目级规则**不改**该栏目下内容的详情页地址。否则改一次栏目，
底下几百篇文章链接全变，SEO 直接崩。

改完老地址 **301 跳新地址**，canonical 跟着收敛。保存需 `cms:site:write` 权限
（只读角色能看能预览，保存按钮不显示）。

### 11.3 页面构建器

可视化拖拽搭页面：区块库拖到画布、点区块改属性（图片 src / alt / 自定义 HTML 等）。

- 表：`cms_pages`
- API：`/api/v1/builder/*`，公开侧走 `/api/v1/public/*`
- 入口：后台「内容管理 → 页面构建」（`/builder/pages`），权限 `settings:read`

### 11.4 AI 内容中心

整块 AI 生产链路，后台独立顶级菜单，**17 个二级菜单**。按职责分四组：

| 组 | 菜单 | 落表 |
|---|---|---|
| 生产 | AI 驾驶舱、AI 内容工作台、批量生产、AI 建模向导、落地页工坊、知识库 | `cms_ai_sessions` / `cms_ai_generations` / `cms_ai_batch_jobs` / `cms_ai_batch_items` |
| 质检 | 内容体检、AI 质量台、问答自测、选题缺口、内容效果 | `cms_ai_reviews` / `cms_ai_entry_digests` / `cms_entry_stats_daily` |
| 分发 | 分发渠道、工作流编排 | `cms_publish_channels` / `cms_publish_jobs` / `cms_workflows` / `cms_workflow_runs` / `cms_workflow_steps` |
| 配置 | AI 能力配置、提示词管理、AI 用量、AI 记忆 | `cms_ai_providers` / `cms_ai_capabilities` / `cms_ai_prompts` / `cms_ai_prices` / `cms_ai_memory` |

约束：AI 产出**全部落草稿**，不自动发布；批量单次上限 200 篇；并发 1 稳、4 易被服务商限流。

### 11.5 多站点隔离

一份部署跑多个站点，内容与配置按站点隔离。

- 表：`cms_sites`、`cms_site_config`
- API：`/api/v1/cms/sites*`
- 与「站点配置」的区别：`cms_site_config` 是**当前站点**的键值对（品牌名、邮箱等），
  `cms_sites` 是站点清单本身

### 11.6 知识库与 RAG

把产品手册 / FAQ / 历史方案切成分片做向量检索，让 AI 写稿和问答有据可依。

- 表：`cms_kb_docs`（源文档）→ `cms_kb_chunks`（分片）→ `cms_embeddings`（向量，pgvector）
- 对外检索：`GET /api/v1/public/rag`，返回带 `source_url` / `heading_path` 的片段，可直接拼进 RAG prompt
- 鉴权：配了 `MCP_API_KEY` 就必须带 `X-MCP-Key` 或 Bearer

### 11.7 内容分发

把站内内容推到站外渠道（公众号等），带任务队列与结果记录。

- 表：`cms_publish_channels`、`cms_publish_jobs`
- 失败原因写在任务记录里，不吞错

### 11.8 表单 / 评论 / 埋点

| 能力 | 表 | 说明 |
|---|---|---|
| 表单问卷 | `cms_forms` / `cms_form_submissions` | 落地页表单直接进线索池 |
| 评论 | `cms_comments` | 内容下的评论，有后台审核入口 |
| 访问埋点 | `cms_track_events` | 页面访问统计，喂给「内容效果」 |
| 内容健康 | `cms_ai_entry_digests` / `cms_entry_stats_daily` | 体检与每日统计 |

### 11.9 数据表全景

到 2026-11-01，`public` schema 共 **256 张表**。其中 `cms_*` 约 40 张。

查法：

```sql
select count(*) from information_schema.tables where table_schema='public';
select table_name from information_schema.tables
 where table_schema='public' and table_name like 'cms_%' order by 1;
```

> 文档里**不要再逐表罗列全部** —— 会立刻过时。上面按能力分组列关键表，
> 要全量就查库。


