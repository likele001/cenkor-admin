# Cenkor Admin Platform — V2 架构文档

> **版本**: v2.0.0
> **更新日期**: 2026-06-10
> **状态**: 实施中（M1-M3 已完成）

---

## 目录

1. [概述](#一概述)
2. [V2 核心创新](#二v2-核心创新)
3. [内容引擎架构](#三内容引擎架构)
4. [双用户体系架构](#四双用户体系架构)
5. [模板引擎集成](#五模板引擎集成)
6. [App 中心 V2](#六app-中心-v2)
7. [安全架构](#七安全架构)
8. [API 清单](#八api-清单)
9. [数据模型总览](#九数据模型总览)
10. [测试与部署](#十测试与部署)

---

## 一、概述

### 1.1 V2 核心目标

| 目标 | V1 状态 | V2 改进 |
|------|---------|--------|
| 通用内容引擎 | 3 张硬编码表（products/cases/news） | 通用 cms_entries + 动态字段定义 |
| 字段管理 | 改代码才能改字段 | 后台 UI 增删改 + 21 种字段类型 |
| 分类标签 | 无 | 3+ 级分类树 + 标签系统 |
| 双用户体系 | auth_users 一套 | auth_users（后台）+ portal_users（前台）隔离 |
| 模板引擎 | 无 | Liquid 前后端一致 |
| App 中心 | 仅 manifest 声明 | manifest 声明 + 自动注册内容/字段/分类 |

### 1.2 V2 架构总览

```
┌────────────────────────────────────────────────────────────────┐
│                    Cenkor Platform V2                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  admin-web   │  │  portal-web  │  │  公网站点    │           │
│  │  (B 端后台)  │  │  (C 端前台)  │  │ (template)   │           │
│  │   Vue 3 SPA  │  │   Vue 3 SPA  │  │              │           │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘           │
│         │                 │                 │                   │
│         │ admin JWT       │ portal JWT      │ 不需 token        │
│         │ (cenkor-admin)  │ (cenkor-portal) │                   │
│         └────────────────┴─────────────────┘                   │
│                          ↓                                      │
│       ┌──────────────────────────────────────┐                 │
│       │       FastAPI 后端 (V2)            │                 │
│       │  ┌────────────┐  ┌────────────┐    │                 │
│       │  │ 内容引擎   │  │ App 中心   │    │                 │
│       │  │ Engine     │  │ Registry   │    │                 │
│       │  └────┬───────┘  └──────┬─────┘    │                 │
│       │       │                │           │                 │
│       │  ┌────▼────────────────▼─────┐    │                 │
│       │  │  FieldRegistry 自动注册    │    │                 │
│       │  └────┬───────────────────────┘    │                 │
│       │       │                            │                 │
│       │  ┌────▼──────────────────────────┐ │                 │
│       │  │  cms_content_types (3)         │ │                 │
│       │  │  cms_field_definitions (21 类) │ │                 │
│       │  │  cms_categories (3+ 级)        │ │                 │
│       │  │  cms_tags                      │ │                 │
│       │  │  cms_entries (通用内容)        │ │                 │
│       │  └──────────────────────────────┘ │                 │
│       └────────────────┬─────────────────┘                 │
│                        ↓                                    │
│        ┌─────────────────────────────┐                     │
│        │ PostgreSQL + JSONB 索引     │                     │
│        │ Redis 缓存 + Celery       │                     │
│        │ MinIO 对象存储            │                     │
│        └─────────────────────────────┘                     │
└────────────────────────────────────────────────────────────────┘
```

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
   ↓                          ↓
   拒绝 portal token (403)    拒绝 admin token (401)
```

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

-- 通用内容表
cms_entries (
  id, content_type_id FK,
  title, content JSONB, custom_fields JSONB,  -- ← 核心：动态字段
  category_id FK, status, author_id,
  published_at, view_count
)

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
| 数字/布尔/日期 | 5 | number, boolean, date, datetime, color |
| 联系 | 3 | url, email, phone |
| 媒体 | 4 | image, images, file, files |
| 选择 | 2 | select, multiselect |
| 高级 | 3 | json, repeater, relation |

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

## 五、模板引擎集成

### 5.1 为什么选 Liquid

| 候选 | 优点 | 缺点 | 决定 |
|------|------|------|------|
| Jinja2 | 强大 | 沙箱需自实现 | ❌ |
| **Liquid (Shopify)** | 沙箱原生、Shopify 用、liquidjs ~30KB | 学习成本 | ✅ |
| Mustache | 极简 | 无逻辑控制 | ❌ |
| Handlebars | 流行 | 沙箱需自实现 | ❌ |

### 5.2 前后端一致

```
后端：python-liquid + markdown
  ↓
公共 API /api/v1/cms/templates/render

前端：liquidjs (TypeScript)
  ↓
window.cmsRender(template, data, globals)
```

### 5.3 全局变量

```javascript
cmsRender(template, data, {
  now: new Date().toISOString(),
  site: { name: '辰科', logo: '...' },
  theme: { primary_color: '#3b82f6' },
  current_user: { id, username, nickname, avatar },
  request: { path, params, query }
})
```

### 5.4 业务 Filters

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

| Token | Issuer | Secret | 前缀 | 用途 |
|-------|--------|--------|------|------|
| admin | `cenkor-admin` | `SECRET_KEY` | admin_token | 后台所有路由 |
| portal | `cenkor-portal` | `SECRET_KEY + ":portal"` | portal_token | 前台 portal-web |

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

- bcrypt（passlib）
- bcrypt < 4.0 兼容性

### 7.5 滑动验证

- 16+ hex chars captcha_token
- 防纯脚本自动注册/登录
- 真正的强度依赖 HTTPS + 限流

---

## 八、API 清单

### 8.1 后台 API（需 admin JWT）

| 模块 | 端点数 | 路径前缀 |
|------|--------|----------|
| Auth | 15+ | `/api/v1/auth/*` |
| RBAC | 20+ | `/api/v1/rbac/*` |
| CMS 内容引擎 | 39 | `/api/v1/cms/*` |
| CMS 模板 | 3 | `/api/v1/cms/templates/*` |
| Notifications | 5 | `/api/v1/notifications/*` |
| API Keys | 5 | `/api/v1/api-keys/*` |
| System (audit/apps/settings/tasks) | 15+ | `/api/v1/system/*` |

### 8.2 公共 API（无需鉴权）

| 模块 | 端点数 | 路径 |
|------|--------|------|
| CMS 公共内容 | 6 | `/api/v1/public/*` |
| CMS 公共分类/标签 | 3 | `/api/v1/public/categories|tags|field-definitions` |
| CMS 公共模板渲染 | 1 | `/api/v1/public/templates/render` |
| Portal Auth | 5 | `/api/v1/public/portal/auth/*` |
| Portal Me | 3 | `/api/v1/public/portal/me/*` |

完整 API 文档：访问 `/api/docs`（Swagger UI）或 `/api/redoc`。

---

## 九、数据模型总览

### 9.1 V2 新增表

| 表 | 说明 |
|----|------|
| cms_content_types | 内容类型（3 行：product/case/news） |
| cms_field_groups | 字段分组（4 行） |
| cms_field_definitions | 字段定义（8 行） |
| cms_field_options | 字段候选项（7 行） |
| cms_entries | 通用内容（已迁移 11 行） |
| cms_categories | 分类（10 行，3+ 级） |
| cms_tags | 标签（0 行） |
| cms_content_tags | 内容-标签多对多 |
| portal_users | 前台用户 |
| portal_user_oauth | 前台用户 OAuth |
| portal_login_logs | 前台登录日志 |

### 9.2 现有表扩展

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

| 类型 | 文件 | 数量 |
|------|------|------|
| 单元测试 | `tests/test_field_types.py` | 28 |
| E2E 测试 | `tests/test_content_engine.py` | 25 |
| 旧测试 | `tests/test_*.py` | 47 (部分因 V2 数据迁移需更新) |

**总测试数：100+，新代码 100% 覆盖。**

### 10.2 部署

```bash
# 1. 安装依赖
cd backend
pip install -r requirements.txt

# 2. 数据库迁移
alembic upgrade head

# 3. 启动
uvicorn cenkor_admin.main:app --host 0.0.0.0 --port 8000
```

### 10.3 数据迁移

```bash
# 旧表 → cms_entries
python -m cenkor_admin.scripts.migrate_to_entries

# 该脚本幂等，可重复执行
```

详见 `docs/PLATFORM_V2_ROADMAP.md` 的 W10 联调上线部分。

---

## 附录：迁移时间线

| 周 | 主要工作 | 状态 |
|----|----------|------|
| W1 | 字段定义表 + Alembic 迁移 | ✅ |
| W2 | 字段 API + 后台 UI | ✅ |
| W3 | 分类表 + 后台 | ✅ |
| W4 | 标签 + 通用内容接入 + 数据迁移 | ✅ |
| W5 | 公共 API + Portal Auth | ✅ |
| W6 | Liquid 模板引擎集成 | ✅ |
| W7 | 网站静态页 + App 中心增强 | ✅ |
| W8 | 测试 + 文档 | 🔄 |
| W9 | 用户体系拆分收尾 | ⏳ |
| W10 | 联调 + 上线 | ⏳ |
