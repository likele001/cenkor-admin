# Cenkor Platform v2.0 升级计划

> 通用企业级后台管理系统 + CMS + 前后台用户分离
> 创建日期：2026-06-10 | 状态：**执行中**

---

## 一、整体架构蓝图

```
                    ┌──────────────────────────────────────┐
                    │   Cenkor Platform (统一底座)         │
                    │   FastAPI + Vue 3 + RBAC + App Center│
                    └──────────────────────────────────────┘
                                       │
        ┌──────────────┬───────────────┼──────────────┬──────────────┐
        ▼              ▼               ▼              ▼              ▼
   ┌─────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │ CMS App │   │ OA App   │   │ ERP App  │   │ Portal   │   │ Future   │
   │ (产品/  │   │ (审批/   │   │ (进销存/ │   │ (前台    │   │ Apps...  │
   │  案例/  │   │  考勤)   │   │  财务)   │   │  网站)   │   │          │
   │  新闻)  │   │          │   │          │   │          │   │          │
   └─────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
        │
        └─── 内置通用引擎 ───┐
              • Content Type Builder
              • Field Definition Engine
              • Category & Tag (3+ 级)
              • Liquid Template Engine
              • Media Library
              • Public API Gateway
```

### 用户体系拆分

```
┌────────────────────────────────────────────┐
│           auth_users  (后台用户)            │
│  - is_superuser, login_logs                │
│  - 仅 admin.cenkor.cn 后台登录             │
│  - 拥有 RBAC 角色、权限点                  │
│  - 由超管/管理员后台创建                   │
└────────────────────────────────────────────┘
        vs
┌────────────────────────────────────────────┐
│         portal_users  (前台用户)            │
│  - 注册、找回密码、profile                 │
│  - 仅 cenkor.cn 及其子域前台登录          │
│  - 无后台权限                              │
│  - 可绑定 OAuth（飞书/微信等）             │
│  - 关联前台数据（订单/工单/订阅等）        │
└────────────────────────────────────────────┘

拆分原则：
- 不同表、不同路由前缀、不同 JWT issuer
- 可选：未来用 SSO bridge 打通（暂不做）
- 强制：portal_users 完全进不了后台（路由级隔离）
```

---

## 二、数据库 Schema（冻结）

### 2.1 内容引擎元数据

```sql
-- 内容类型（元数据，支持未来扩展）
CREATE TABLE cms_content_types (
  id SERIAL PRIMARY KEY,
  key VARCHAR(60) UNIQUE,              -- 'product' | 'case' | 'news' | 自定义
  name VARCHAR(80) NOT NULL,
  description TEXT,
  icon VARCHAR(40),
  supports_category BOOLEAN DEFAULT TRUE,
  supports_tags BOOLEAN DEFAULT TRUE,
  default_list_template TEXT,
  default_detail_template TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deleted_at TIMESTAMPTZ               -- 软删
);

-- 字段分组（实现 tabs 分组）
CREATE TABLE cms_field_groups (
  id SERIAL PRIMARY KEY,
  content_type_id INTEGER REFERENCES cms_content_types(id) ON DELETE CASCADE,
  key VARCHAR(80) NOT NULL,
  label VARCHAR(80) NOT NULL,
  sort INTEGER DEFAULT 0,
  icon VARCHAR(40),
  UNIQUE(content_type_id, key)
);

-- 字段定义（字段元数据）
CREATE TABLE cms_field_definitions (
  id SERIAL PRIMARY KEY,
  content_type_id INTEGER REFERENCES cms_content_types(id) ON DELETE CASCADE,
  field_key VARCHAR(80) NOT NULL,       -- 在 content JSONB 里的 key
  label VARCHAR(80) NOT NULL,
  field_type VARCHAR(30) NOT NULL,      -- 见 FIELD_TYPES 枚举
  required BOOLEAN DEFAULT FALSE,
  default_value TEXT,
  options JSONB,                        -- select 选项 / 验证规则
  validation JSONB,                     -- min/max/regex 等
  group_id INTEGER REFERENCES cms_field_groups(id) ON DELETE SET NULL,
  sort INTEGER DEFAULT 0,
  status VARCHAR(20) DEFAULT 'active',  -- active | disabled
  created_by INTEGER REFERENCES auth_users(id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(content_type_id, field_key)
);

-- 字段选项（select/multi_select 的候选项）
CREATE TABLE cms_field_options (
  id SERIAL PRIMARY KEY,
  definition_id INTEGER REFERENCES cms_field_definitions(id) ON DELETE CASCADE,
  value VARCHAR(80) NOT NULL,
  label VARCHAR(80) NOT NULL,
  color VARCHAR(20),
  sort INTEGER DEFAULT 0
);

-- 通用内容表
CREATE TABLE cms_entries (
  id SERIAL PRIMARY KEY,
  content_type_id INTEGER REFERENCES cms_content_types(id) ON DELETE CASCADE,
  slug VARCHAR(120),                    -- 可选，用于 URL 友好
  title VARCHAR(200) NOT NULL,
  content JSONB DEFAULT '{}'::jsonb,    -- 动态字段数据存储
  excerpt TEXT,                         -- 摘要
  cover_image VARCHAR(500),             -- 封面图
  category_id INTEGER REFERENCES cms_categories(id) ON DELETE SET NULL,
  status VARCHAR(20) DEFAULT 'draft',   -- draft | published | archived
  author_id INTEGER REFERENCES auth_users(id),
  published_at TIMESTAMPTZ,
  sort INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deleted_at TIMESTAMPTZ,               -- 软删
  UNIQUE(content_type_id, slug)
);

-- 分类（3 套独立，每套 3+ 级层级）
CREATE TABLE cms_categories (
  id SERIAL PRIMARY KEY,
  content_type_id INTEGER REFERENCES cms_content_types(id) ON DELETE CASCADE,
  parent_id INTEGER REFERENCES cms_categories(id) ON DELETE CASCADE,  -- 自引用
  slug VARCHAR(80) NOT NULL,
  name VARCHAR(80) NOT NULL,
  icon VARCHAR(40),
  color VARCHAR(20),
  sort INTEGER DEFAULT 0,
  status VARCHAR(20) DEFAULT 'active',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deleted_at TIMESTAMPTZ,               -- 软删
  UNIQUE(content_type_id, slug)
);

-- 标签
CREATE TABLE cms_tags (
  id SERIAL PRIMARY KEY,
  content_type_id INTEGER REFERENCES cms_content_types(id) ON DELETE CASCADE,
  slug VARCHAR(80) NOT NULL,
  name VARCHAR(80) NOT NULL,
  color VARCHAR(20),
  UNIQUE(content_type_id, slug)
);

-- 内容-标签多对多（一张通用表）
CREATE TABLE cms_content_tags (
  content_type_id INTEGER NOT NULL,
  content_id INTEGER NOT NULL,
  tag_id INTEGER NOT NULL REFERENCES cms_tags(id) ON DELETE CASCADE,
  PRIMARY KEY (content_type_id, content_id, tag_id)
);
```

### 2.2 现有表加 custom_fields JSONB

```sql
ALTER TABLE cms_products ADD COLUMN custom_fields JSONB DEFAULT '{}'::jsonb;
ALTER TABLE cms_cases    ADD COLUMN custom_fields JSONB DEFAULT '{}'::jsonb;
ALTER TABLE cms_news     ADD COLUMN custom_fields JSONB DEFAULT '{}'::jsonb;
```

### 2.3 用户体系拆分

```sql
-- 新增：前台用户
CREATE TABLE portal_users (
  id SERIAL PRIMARY KEY,
  username VARCHAR(80) UNIQUE,
  email VARCHAR(120) UNIQUE,
  phone VARCHAR(20),
  nickname VARCHAR(80),
  avatar VARCHAR(500),
  password_hash VARCHAR(200) NOT NULL,
  status VARCHAR(20) DEFAULT 'active',  -- active | disabled | locked
  last_login_at TIMESTAMPTZ,
  last_login_ip VARCHAR(45),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deleted_at TIMESTAMPTZ                -- 软删
);

-- 前台用户 OAuth 绑定
CREATE TABLE portal_user_oauth (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES portal_users(id) ON DELETE CASCADE,
  provider VARCHAR(30) NOT NULL,        -- feishu | wechat | github
  open_id VARCHAR(200) NOT NULL,
  union_id VARCHAR(200),
  access_token_enc TEXT,
  refresh_token_enc TEXT,
  expires_at TIMESTAMPTZ,
  UNIQUE(provider, open_id)
);

-- 现有 auth_users 保持不动，但加 type 字段区分
ALTER TABLE auth_users ADD COLUMN user_type VARCHAR(20) DEFAULT 'admin';
-- 'admin' (后台) | 'superadmin' (超管)
```

---

## 三、字段类型枚举（冻结）

| 类型 | key | 存储格式 | 校验规则 | 前端控件 |
|---|---|---|---|---|
| 单行文本 | `text` | string | max_length | `<input type="text">` |
| 多行文本 | `longtext` | string | max_length | `<textarea>` |
| 富文本 | `richtext` | string (HTML) | — | 富文本编辑器 |
| Markdown | `markdown` | string (MD) | — | Vditor 编辑器 |
| 数字 | `number` | number | min, max, step | `<input type="number">` |
| 布尔 | `boolean` | boolean | — | `<Switch>` |
| 日期 | `date` | string (ISO) | — | `<DatePicker>` |
| 日期时间 | `datetime` | string (ISO) | — | `<DateTimePicker>` |
| URL | `url` | string | url regex | `<input type="url">` |
| Email | `email` | string | email regex | `<input type="email">` |
| 电话 | `phone` | string | phone regex | `<input type="tel">` |
| 单图 | `image` | string (URL) | — | MediaPicker (单选) |
| 多图 | `images` | string[] (URL[]) | max_count | MediaPicker (多选) |
| 单文件 | `file` | string (URL) | max_size, mime_types | FilePicker (单选) |
| 多文件 | `files` | string[] (URL[]) | max_count, max_size | FilePicker (多选) |
| 单选 | `select` | string | options 列表 | `<Select>` |
| 多选 | `multiselect` | string[] | options 列表 | `<MultiSelect>` |
| 颜色 | `color` | string (hex) | — | `<ColorPicker>` |
| 原始 JSON | `json` | object | — | JSON 编辑器 |
| 重复子项 | `repeater` | object[] | min_items, max_items | Repeater 编辑器 |
| 关联内容 | `relation` | number (id) | content_type, target | Relation 选择器 |

---

## 四、API 设计（冻结）

### 4.1 后台管理 API（需 admin 权限）

#### Content Types

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/v1/cms/content-types` | 内容类型列表 |
| POST | `/api/v1/cms/content-types` | 创建内容类型 |
| PATCH | `/api/v1/cms/content-types/{id}` | 更新内容类型 |
| DELETE | `/api/v1/cms/content-types/{id}` | 软删内容类型 |

#### Field Groups

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/v1/cms/content-types/{id}/field-groups` | 字段分组列表 |
| POST | `/api/v1/cms/content-types/{id}/field-groups` | 创建字段分组 |
| PATCH | `/api/v1/cms/content-types/{id}/field-groups/{gid}` | 更新字段分组 |
| DELETE | `/api/v1/cms/content-types/{id}/field-groups/{gid}` | 删除字段分组 |

#### Field Definitions

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/v1/cms/content-types/{id}/field-definitions` | 字段定义列表 |
| POST | `/api/v1/cms/content-types/{id}/field-definitions` | 创建字段定义 |
| PATCH | `/api/v1/cms/field-definitions/{id}` | 更新字段定义 |
| DELETE | `/api/v1/cms/field-definitions/{id}` | 删除字段定义 |
| POST | `/api/v1/cms/content-types/{id}/field-definitions/reorder` | 字段排序 |

#### Field Options

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/v1/cms/field-definitions/{id}/options` | 字段选项列表 |
| POST | `/api/v1/cms/field-options` | 创建字段选项 |
| PATCH | `/api/v1/cms/field-options/{id}` | 更新字段选项 |
| DELETE | `/api/v1/cms/field-options/{id}` | 删除字段选项 |

#### Categories

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/v1/cms/categories?content_type=&parent=` | 分类列表（树形） |
| POST | `/api/v1/cms/categories` | 创建分类 |
| PATCH | `/api/v1/cms/categories/{id}` | 更新分类 |
| DELETE | `/api/v1/cms/categories/{id}` | 软删 + 检查引用 |
| POST | `/api/v1/cms/categories/reorder` | 拖拽排序 |

#### Tags

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/v1/cms/tags?content_type=` | 标签列表 |
| POST | `/api/v1/cms/tags` | 创建标签 |
| PATCH | `/api/v1/cms/tags/{id}` | 更新标签 |
| DELETE | `/api/v1/cms/tags/{id}` | 删除标签 |

#### Entries（通用内容）

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/v1/cms/entries?content_type=&category=&tag=&custom.<key>=` | 内容列表 |
| POST | `/api/v1/cms/entries` | 创建内容 |
| PATCH | `/api/v1/cms/entries/{id}` | 更新内容 |
| DELETE | `/api/v1/cms/entries/{id}` | 软删内容 |
| POST | `/api/v1/cms/entries/batch-delete` | 批量删除 |
| POST | `/api/v1/cms/entries/batch-status` | 批量改状态 |

#### 现有内容（兼容层）

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/v1/cms/products?category=&tag=&custom.<key>=` | 产品列表（扩展 custom_fields） |
| POST | `/api/v1/cms/products` | 创建产品（接受 custom_fields） |
| PATCH | `/api/v1/cms/products/{id}` | 更新产品 |
| *同上* | `cases/news` | 案例/新闻（同模式） |

### 4.2 公共 API（前台用，无需 admin 权限）

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/v1/public/site/{content_type}?line=&category=&tag=&page=` | 按类型查内容列表 |
| GET | `/api/v1/public/site/{content_type}/{id_or_slug}` | 内容详情 |
| GET | `/api/v1/public/categories?content_type=` | 分类列表 |
| GET | `/api/v1/public/tags?content_type=` | 标签列表 |
| GET | `/api/v1/public/field-definitions?content_type=` | 供前台渲染动态字段 |
| POST | `/api/v1/public/portal/auth/register` | 前台用户注册 |
| POST | `/api/v1/public/portal/auth/login` | 前台用户登录 |
| GET | `/api/v1/public/portal/me` | 前台用户信息 |
| POST | `/api/v1/public/portal/auth/forgot-password` | 忘记密码 |
| POST | `/api/v1/public/portal/auth/reset-password` | 重置密码 |

---

## 五、App 中心扩展（冻结）

### 5.1 AppManifest 扩展字段

```python
@dataclass
class AppManifest:
    key: str
    name: str
    version: str
    author: str = ""
    description: str = ""
    icon: str = "📦"
    min_platform_version: str = "0.1.0"
    dependencies: list[str] = field(default_factory=list)
    permissions_required: list[str] = field(default_factory=list)
    menus: list[dict] = field(default_factory=list)

    # ↓ 新增扩展字段 ↓

    content_types: list[dict] = field(default_factory=list)
    # 例：[{"key":"product","name":"产品","default_template":"..."}]

    field_groups: list[dict] = field(default_factory=list)
    # 例：[{"key":"basic","label":"基础信息"},{"key":"specs","label":"技术规格"}]

    field_definitions: list[dict] = field(default_factory=list)
    # 例：[{"key":"price","label":"价格","type":"number","group":"specs"}]

    categories_seed: list[dict] = field(default_factory=list)
    # 初始分类（首次安装时种入）

    public_routes_prefix: str = ""
    # 公共 API 路由前缀
```

### 5.2 InstalledApp 表增强

```sql
ALTER TABLE platform_apps ADD COLUMN permissions_grants JSONB DEFAULT '{}'::jsonb;
-- 委派权限给其他角色，例：{"content_editor": ["cms:field:read", "cms:field:write"]}
```

### 5.3 启动时自动注册

- 启动时扫描已安装 App 的 manifest
- 将 `content_types` / `field_groups` / `field_definitions` 注册到 DB（幂等）
- 种入 `categories_seed` 初始分类

---

## 六、Liquid 模板契约（冻结）

### 6.1 语法

```
{# 基础语法 #}
{{ var }}                             变量插值
{{ var | filter }}                    过滤器
{{ var | default: 'fallback' }}       默认值

{# 流程控制 #}
{% if condition %}...{% endif %}
{% if condition %}...{% elsif %}...{% else %}...{% endif %}
{% for x in collection %}...{% endfor %}
```

### 6.2 内置 filters

| Filter | 用法 | 说明 |
|---|---|---|
| `upcase` | `{{ str \| upcase }}` | 大写 |
| `downcase` | `{{ str \| downcase }}` | 小写 |
| `truncate` | `{{ str \| truncate: 100 }}` | 截断 |
| `append` | `{{ str \| append: '...' }}` | 追加 |
| `date` | `{{ date \| date: '%Y-%m-%d' }}` | 日期格式化 |
| `currency` | `{{ num \| currency }}` | 货币格式 |
| `markdown` | `{{ str \| markdown }}` | Markdown → HTML |
| `strip_html` | `{{ str \| strip_html }}` | 去 HTML |
| `json` | `{{ obj \| json }}` | 序列化 |
| `join` | `{{ arr \| join: ', ' }}` | 数组合并 |
| `size` | `{{ arr \| size }}` | 数组长度 |

### 6.3 自定义业务 filters

| Filter | 用法 | 说明 |
|---|---|---|
| `t` | `{{ product.line \| t }}` | i18n 翻译（业务线中文名） |
| `format_price` | `{{ product.content.price \| format_price }}` | 价格格式化 |
| `first` | `{{ product.content.screenshots \| first }}` | 取数组首项 |

### 6.4 前端集成

- 使用 `liquidjs` 库（~30KB）
- 封装为 `window.cmsRender(template, data)` 全局函数
- 自动注入全局变量：`now`、`site`、`theme`

---

## 七、执行时间表与任务清单

### 总览

| 周 | 轨道 1：CMS 增强 | 轨道 2：安全整改 | 轨道 3：底座演进 |
|---|---|---|---|
| W1 | M1-A 字段定义表 + Alembic | 阶段 1 紧急止血 | — |
| W2 | M1-B 字段 API + 后台 UI | — | — |
| W3 | M2-A 分类表 + 后台 | — | App 中心 UI 改造 |
| W4 | M2-B 标签 + 内容接入 | — | App 中心安装/卸载 |
| W5 | M3-A 公共 API | — | Manifest 扩展 |
| W6 | M3-B liquidjs 集成 | — | 通用 BaseContent 抽象 |
| W7 | — | 安全整改收尾 | FieldRegistry 抽象 |
| W8 | 测试 + 文档 | — | — |
| W9 | 用户体系拆分 | — | — |
| W10 | 联调 + 上线 | — | — |

---

### W1：M1-A 字段定义表 + Alembic

- [ ] **1.1** 创建 `ContentType` 模型 → `cms_content_types` 表
- [ ] **1.2** 创建 `FieldGroup` 模型 → `cms_field_groups` 表
- [ ] **1.3** 创建 `FieldDefinition` 模型 → `cms_field_definitions` 表
- [ ] **1.4** 创建 `FieldOption` 模型 → `cms_field_options` 表
- [ ] **1.5** 创建 `Entry` 模型 → `cms_entries` 通用内容表
- [ ] **1.6** 创建 `Category` 模型 → `cms_categories` 表
- [ ] **1.7** 创建 `Tag` 模型 → `cms_tags` 表
- [ ] **1.8** 创建 `ContentTag` 模型 → `cms_content_tags` 多对多关联表
- [ ] **1.9** 现有 `Product`/`Case`/`News` 模型加 `custom_fields JSONB` 列
- [ ] **1.10** 创建 `PortalUser` 模型 → `portal_users` 表
- [ ] **1.11** 创建 `PortalUserOAuth` 模型 → `portal_user_oauth` 表
- [ ] **1.12** 现有 `User`(auth_users) 模型加 `user_type VARCHAR(20) DEFAULT 'admin'`
- [ ] **1.13** 创建 `FIELD_TYPES` 枚举 + 校验规则映射 → `apps/cms/field_types.py`
- [ ] **1.14** 生成 Alembic 迁移文件并验证
- [ ] **1.15** 更新 seed.py：自动创建 product/case/news 三种 ContentType + 默认 FieldGroup

**产出文件清单：**
- `backend/src/cenkor_admin/apps/cms/models.py` — 新增 8 个模型
- `backend/src/cenkor_admin/apps/cms/field_types.py` — 字段类型枚举
- `backend/src/cenkor_admin/apps/portal/__init__.py` — 新建
- `backend/src/cenkor_admin/apps/portal/models.py` — PortalUser + OAuth
- `backend/src/cenkor_admin/apps/auth/models.py` — 加 user_type 字段
- `backend/src/cenkor_admin/scripts/seed.py` — 更新种子数据
- `backend/alembic/versions/xxx_content_engine_and_portal.py` — 迁移

---

### W2：M1-B 字段 API + 后台 UI

- [ ] **2.1** Content Types CRUD API（4 个端点）
- [ ] **2.2** Field Groups CRUD API（4 个端点）
- [ ] **2.3** Field Definitions CRUD + Reorder API（5 个端点）
- [ ] **2.4** Field Options CRUD API（4 个端点）
- [ ] **2.5** Pydantic schemas：请求/响应模型
- [ ] **2.6** 后台 UI：Content Type 列表页 `ContentTypeListView.vue`
- [ ] **2.7** 后台 UI：字段定义编辑器 `FieldDefinitionsView.vue`（拖拽排序、分组 tabs）
- [ ] **2.8** 后台 UI：`DynamicFieldRenderer.vue` 组件（20 种字段类型渲染）
- [ ] **2.9** 后台 UI：`DynamicFieldEditor.vue` 组件（20 种字段类型编辑）
- [ ] **2.10** 路由注册 + 菜单配置

**产出文件清单：**
- `backend/src/cenkor_admin/apps/cms/router.py` — 新增 17 个 API 端点
- `backend/src/cenkor_admin/apps/cms/schemas.py` — 新增 Pydantic schemas
- `frontend/admin-web/src/views/cms/ContentTypeListView.vue`
- `frontend/admin-web/src/views/cms/ContentTypeEditView.vue`
- `frontend/admin-web/src/views/cms/FieldDefinitionsView.vue`
- `frontend/admin-web/src/components/cms/DynamicFieldRenderer.vue`
- `frontend/admin-web/src/components/cms/DynamicFieldEditor.vue`
- `frontend/admin-web/src/components/cms/FieldGroupTabs.vue`

---

### W3：M2-A 分类系统 + 后台

- [ ] **3.1** Categories CRUD API + 树形查询
- [ ] **3.2** Categories 拖拽排序 API（`POST /reorder`）
- [ ] **3.3** Tags CRUD API
- [ ] **3.4** 后台 UI：分类管理页面（TreeSelect，3+ 级嵌套）
- [ ] **3.5** 后台 UI：标签管理组件（TagManager，颜色选择器）
- [ ] **3.6** 公共 API：`GET /api/v1/public/categories`、`GET /api/v1/public/tags`
- [ ] **3.7** App 中心 UI 改造（Manifest 展示优化）

**产出文件清单：**
- `backend/src/cenkor_admin/apps/cms/router.py` — 新增分类/标签 API
- `backend/src/cenkor_admin/apps/cms/public_router.py` — 新增公共分类/标签 API
- `frontend/admin-web/src/views/cms/CategoriesView.vue`
- `frontend/admin-web/src/components/cms/CategoryTree.vue`
- `frontend/admin-web/src/views/cms/TagsView.vue`
- `frontend/admin-web/src/components/cms/TagManager.vue`

---

### W4：M2-B 标签 + 通用内容接入 + 数据迁移

- [ ] **4.1** 通用内容 CRUD API（`/api/v1/cms/entries`）支持 dynamic `content` JSONB
- [ ] **4.2** 内容搜索/过滤（按 category、tag、`custom.<field_key>` 过滤）
- [ ] **4.3** 编写数据迁移脚本：products → cms_entries（含 custom_fields 映射）
- [ ] **4.4** 编写数据迁移脚本：cases → cms_entries
- [ ] **4.5** 编写数据迁移脚本：news → cms_entries
- [ ] **4.6** 适配现有 CMS router 兼容新通用内容 API（双写过渡期）
- [ ] **4.7** 后台 UI：通用内容列表页 `EntryListView.vue`
- [ ] **4.8** 后台 UI：通用内容编辑页 `EntryEditView.vue`（DynamicFieldEditor 驱动）
- [ ] **4.9** App 中心安装/卸载流程完善

**产出文件清单：**
- `backend/src/cenkor_admin/apps/cms/router.py` — 新增 entries API
- `backend/src/cenkor_admin/apps/cms/schemas.py` — Entry schemas
- `backend/src/cenkor_admin/scripts/migrate_to_entries.py` — 数据迁移脚本
- `frontend/admin-web/src/views/cms/EntryListView.vue`
- `frontend/admin-web/src/views/cms/EntryEditView.vue`

---

### W5：M3-A 公共 API 网关

- [ ] **5.1** `GET /api/v1/public/site/{content_type}` — 按类型查内容列表
- [ ] **5.2** `GET /api/v1/public/site/{content_type}/{id_or_slug}` — 内容详情
- [ ] **5.3** `GET /api/v1/public/field-definitions` — 供前台渲染动态字段
- [ ] **5.4** 前台用户注册 API（`POST /api/v1/public/portal/auth/register`）
- [ ] **5.5** 前台用户登录 API（`POST /api/v1/public/portal/auth/login`）
- [ ] **5.6** 前台用户 profile API（`GET /api/v1/public/portal/me`）
- [ ] **5.7** portal_users 的 JWT 签发（独立 issuer `cenkor-portal`，无法访问后台路由）
- [ ] **5.8** 前台用户忘记/重置密码 API
- [ ] **5.9** 路由级隔离中间件：portal token → 403 on `/api/v1/cms/` 等后台路由
- [ ] **5.10** Manifest 扩展（含 content_types）

**产出文件清单：**
- `backend/src/cenkor_admin/apps/cms/public_router.py` — 增强
- `backend/src/cenkor_admin/apps/portal/router.py` — 新建（前台用户认证）
- `backend/src/cenkor_admin/apps/portal/schemas.py` — 新建
- `backend/src/cenkor_admin/apps/portal/auth.py` — 新建（独立 JWT 签发）
- `backend/src/cenkor_admin/core/security.py` — 扩展（双 issuer 支持）
- `backend/src/cenkor_admin/api/deps.py` — 扩展（portal 依赖注入）
- `backend/src/cenkor_admin/api/v1/__init__.py` — 注册 portal 路由

---

### W6：M3-B Liquid 模板引擎集成

- [ ] **6.1** 后端：Python Liquid 模板渲染引擎（`python-liquid` 或 `liquidpy`）
- [ ] **6.2** 内置 filters 实现：upcase、downcase、truncate、date、currency、markdown、strip_html、json、join、size
- [ ] **6.3** 自定义业务 filters：`t()` i18n、`format_price`、`first`
- [ ] **6.4** `POST /api/v1/cms/templates/render` — 服务端模板预览 API
- [ ] **6.5** 前端：`window.cmsRender(template, data)` 封装（liquidjs 库）
- [ ] **6.6** 前端：自动注入全局变量（now、site、theme）
- [ ] **6.7** portal-web：公共内容展示页（产品列表/详情、案例、新闻）使用模板渲染
- [ ] **6.8** 通用 BaseContent 抽象（SQLAlchemy mixin）

**产出文件清单：**
- `backend/src/cenkor_admin/core/template_engine.py` — 新建
- `backend/src/cenkor_admin/apps/cms/template_router.py` — 新建
- `frontend/admin-web/src/lib/liquid.ts` — 新建（liquidjs 封装）
- `frontend/portal-web/src/lib/cmsRender.ts` — 新建
- `frontend/portal-web/src/views/ContentView.vue` — 新建（通用内容展示）
- `frontend/portal-web/src/views/ContentDetailView.vue` — 新建

---

### W7：安全整改 + App 中心增强

- [ ] **7.1** 密钥轮换机制（SECRET_KEY_ROTATION 支持）
- [ ] **7.2** 目录隔离（媒体按 bucket/日期/内容类型隔离）
- [ ] **7.3** API 限流（slowapi + Redis，按路由/用户/IP 分级）
- [ ] **7.4** APP_DEBUG 生产环境强制 False 验证
- [ ] **7.5** AppManifest 扩展字段落地（content_types, field_groups, field_definitions, categories_seed, public_routes_prefix）
- [ ] **7.6** 启动时自动注册 app 的 field_definitions 到 DB
- [ ] **7.7** InstalledApp 表加 `permissions_grants JSONB`
- [ ] **7.8** App 中心 UI：字段管理权分配（超管可勾选角色权限）
- [ ] **7.9** FieldRegistry 抽象（统一字段类型注册/校验/渲染分发）

**产出文件清单：**
- `backend/src/cenkor_admin/core/security.py` — 密钥轮换
- `backend/src/cenkor_admin/core/storage.py` — 目录隔离
- `backend/src/cenkor_admin/main.py` — 限流中间件
- `backend/src/cenkor_admin/apps/base.py` — Manifest 扩展
- `backend/src/cenkor_admin/apps/system/app_registry.py` — 自动注册
- `backend/src/cenkor_admin/apps/cms/field_registry.py` — 新建
- `frontend/admin-web/src/views/system/AppsView.vue` — 增强

---

### W8：测试 + 文档

- [ ] **8.1** CMS 引擎单元测试（模型、API、校验）
- [ ] **8.2** 字段类型全量测试（20 种类型的创建/编辑/校验/渲染）
- [ ] **8.3** 公共 API 集成测试
- [ ] **8.4** 前台用户认证流程测试
- [ ] **8.5** 模板渲染测试
- [ ] **8.6** 性能测试（1000+ 条目查询响应）
- [ ] **8.7** 更新 ARCHITECTURE.md
- [ ] **8.8** 更新 API 文档（OpenAPI 自动生成）
- [ ] **8.9** 编写开发者指南（如何创建新 App + 注册 content_type）

**产出文件清单：**
- `tests/` — 新增测试文件
- `ARCHITECTURE.md` — 更新
- `docs/` — 更新

---

### W9：用户体系拆分

- [ ] **9.1** portal_users 后台管理 API（管理员可查看/禁用/删除前台用户）
- [ ] **9.2** portal_user_oauth 绑定（微信/飞书 OAuth 流程）
- [ ] **9.3** 路由级隔离验证：portal token 访问后台路由返回 403
- [ ] **9.4** portal-web 全面接入新 portal API
- [ ] **9.5** 现有注册接口改为创建 portal_user（而非 auth_user）
- [ ] **9.6** 数据迁移：已注册前台用户从 auth_users 迁移到 portal_users
- [ ] **9.7** portal-web 个人中心增强（头像上传、OAuth 绑定/解绑）
- [ ] **9.8** admin-web 前台用户管理页面

**产出文件清单：**
- `backend/src/cenkor_admin/apps/portal/router.py` — 增强
- `backend/src/cenkor_admin/apps/portal/admin_router.py` — 新建（后台管理前台用户）
- `backend/src/cenkor_admin/apps/auth/router.py` — 调整注册逻辑
- `backend/src/cenkor_admin/scripts/migrate_portal_users.py` — 新建
- `frontend/portal-web/src/views/ProfileView.vue` — 增强
- `frontend/admin-web/src/views/system/PortalUsersView.vue` — 新建

---

### W10：联调 + 上线

- [ ] **10.1** 全链路 E2E 测试（后台 → CMS → 公共 API → portal-web）
- [ ] **10.2** 数据迁移完整验证
- [ ] **10.3** Docker Compose 部署验证
- [ ] **10.4** 宝塔面板部署验证
- [ ] **10.5** Nginx 配置更新（portal 子域路由）
- [ ] **10.6** .env.prod 安全审查
- [ ] **10.7** 上线清单确认
- [ ] **10.8** 正式上线

---

## 八、风险与依赖

| 风险 | 影响 | 缓解 |
|---|---|---|
| 通用内容表迁移数据丢失 | 高 | 双写过渡期 + 迁移前后校验脚本 |
| 字段类型校验规则不完善 | 中 | 逐步完善，先支持常用 8 种 |
| Liquid 模板注入攻击 | 高 | 沙箱模式 + 白名单 filters |
| portal_users JWT 泄露可访问后台 | 高 | 路由级隔离中间件 + 不同 issuer |
| Alembic 迁移冲突 | 中 | 每阶段独立迁移文件，不修改历史 |

---

## 九、验收标准

### M1 验收（W2 结束）

- [ ] 可在后台创建 ContentType（如"产品"、"案例"、"新闻"）
- [ ] 可为 ContentType 添加 FieldGroup（tabs 分组）
- [ ] 可为 ContentType 添加 FieldDefinition（20 种类型）
- [ ] 可为 select/multiselect 添加 FieldOption
- [ ] 字段支持拖拽排序
- [ ] DynamicFieldRenderer 正确渲染所有字段类型

### M2 验收（W4 结束）

- [ ] 分类支持 3+ 级层级，按 content_type 隔离
- [ ] 标签按 content_type 隔离
- [ ] 现有 products/cases/news 数据成功迁移到 cms_entries
- [ ] 通用内容列表/编辑页正常工作
- [ ] 按分类/标签/自定义字段过滤正常

### M3 验收（W6 结束）

- [ ] 公共 API 可按 content_type 查内容列表/详情
- [ ] 前台用户可注册/登录/查看 profile
- [ ] portal token 无法访问后台路由
- [ ] Liquid 模板可渲染内容（含自定义 filters）
- [ ] portal-web 可展示公共内容

### 全量验收（W10 结束）

- [ ] 所有 API 端点正常
- [ ] 数据迁移完整无丢失
- [ ] 安全整改到位
- [ ] 文档更新
- [ ] Docker 部署通过
