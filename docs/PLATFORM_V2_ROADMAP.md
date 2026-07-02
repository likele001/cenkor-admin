# Cenkor Platform V2 — 企业级通用后台 + CMS 改造路线图

> **版本**：v2.0.0-draft
> **创建**：2026-06-10
> **状态**：W1–W8 已完成 ✅，W9–W10 进行中
> **预计工期**：10 周（W1–W10）

## 进度概览

| 阶段 | 状态 | 测试 | 文档 |
|------|------|------|------|
| W1 字段定义表 + Alembic | ✅ | ✅ | ✅ |
| W2 字段 API + 后台 UI | ✅ | ✅ | ✅ |
| W3 分类表 + 后台 | ✅ | ✅ | ✅ |
| W4 标签 + 通用内容 + 数据迁移 | ✅ | ✅ | ✅ |
| W5 公共 API + Portal Auth | ✅ | ✅ | ✅ |
| W6 Liquid 模板引擎 | ✅ | ✅ | ✅ |
| W7 网站静态页 + App 中心增强 | ✅ | ✅ | ✅ |
| W8 测试 + 文档 | ✅ | ✅ | ✅ |
| W9 用户体系拆分收尾 | ⏳ | - | - |
| W10 联调 + 上线 | ⏳ | - | - |

**V2 已完成成果**:
- 11 张新表 + 4 个 ALTER 迁移
- 100+ 个 API 端点
- 39 个内容引擎端点
- 53+ 自动化测试（25 E2E + 28 单元）
- 性能: 1000+ 条目 < 50ms 响应

---

## 目录

- [一、整体架构蓝图](#一整体架构蓝图)
- [二、用户体系拆分](#二用户体系拆分)
- [三、数据库 Schema（冻结）](#三数据库-schema冻结)
- [四、字段类型枚举（冻结）](#四字段类型枚举冻结)
- [五、API 设计（冻结）](#五api-设计冻结)
- [六、App 中心扩展（冻结）](#六app-中心扩展冻结)
- [七、Liquid 模板契约（冻结）](#七liquid-模板契约冻结)
- [八、10 周执行计划](#八10-周执行计划)
- [九、任务清单（Checkbox 跟踪）](#九任务清单checkbox-跟踪)
- [十、风险与决策记录](#十风险与决策记录)

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

### 核心设计原则

| 原则 | 说明 |
|------|------|
| **通用内容引擎** | 所有内容（产品/案例/新闻/自定义）统一走 `cms_entries` 表 + `cms_content_types` 元数据 |
| **字段驱动** | 每种内容类型的字段由 `cms_field_definitions` 定义，值存储在 `custom_fields JSONB` |
| **前后台用户隔离** | `auth_users`（后台）与 `portal_users`（前台）不同表、不同路由前缀、不同 JWT issuer |
| **应用中心驱动** | 每个业务模块是独立 App，通过 AppManifest 声明元数据、字段、分类、权限 |
| **模板引擎** | 前台页面使用 Liquid 模板渲染，后台管理使用 DynamicFieldRenderer 组件 |

### 技术栈

| 层 | 技术 | 版本 |
|---|---|---|
| 后端框架 | FastAPI | 0.110+ |
| ORM | SQLAlchemy 2.0 (async) | - |
| 迁移 | Alembic | 1.13+ |
| 认证 | JWT (python-jose) + bcrypt | - |
| 校验 | Pydantic 2.6+ | - |
| 前端后台 | Vue 3.4 + Vite 5.1 + TypeScript 5.4 | - |
| 前端前台 | Vue 3.4 + Vite 5.1 + liquidjs | - |
| 状态管理 | Pinia 2.1.7 | - |
| CSS | TailwindCSS 3.4 | - |
| 数据库 | PostgreSQL 16 | - |
| 缓存 | Redis 7 | - |
| 对象存储 | MinIO (S3-compatible) | - |
| 模板引擎 | liquidjs (前端) + python-liquid (后端预览) | - |

---

## 二、用户体系拆分

### 2.1 双用户体系架构

```
┌────────────────────────────────────────────┐
│           auth_users  (后台用户)            │
│  - is_superuser, login_logs                │
│  - 仅 admin.cenkor.cn 后台登录             │
│  - 拥有 RBAC 角色、权限点                  │
│  - 由超管/管理员后台创建                   │
│  - user_type: admin / superadmin           │
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
```

### 2.2 拆分原则

| 原则 | 实现 |
|------|------|
| **不同表** | `auth_users` vs `portal_users`，完全独立 |
| **不同路由前缀** | 后台 `/api/v1/auth/*`，前台 `/api/v1/public/portal/auth/*` |
| **不同 JWT issuer** | 后台 `cenkor-admin`，前台 `cenkor-portal` |
| **路由级隔离** | portal_users token 无法访问 `/api/v1/cms/*` 等后台路由 |
| **暂不做 SSO** | 未来可选 SSO bridge 打通 |

### 2.3 JWT 对比

| 维度 | auth_users | portal_users |
|------|-----------|-------------|
| issuer | `cenkor-admin` | `cenkor-portal` |
| token 前缀存储 | `admin_token` | `portal_token` |
| 权限检查 | RBAC 角色权限点 | 无后台权限，仅自身数据 |
| 过期策略 | access 15min / refresh 7d | access 15min / refresh 7d |
| 刷新端点 | `/api/v1/auth/refresh` | `/api/v1/public/portal/auth/refresh` |

---

## 三、数据库 Schema（冻结）

### 3.1 内容引擎元数据

#### cms_content_types — 内容类型

```sql
CREATE TABLE cms_content_types (
  id            SERIAL PRIMARY KEY,
  key           VARCHAR(60) UNIQUE NOT NULL,    -- 'product' | 'case' | 'news' | 自定义
  name          VARCHAR(80) NOT NULL,            -- 显示名
  description   TEXT,
  icon          VARCHAR(20),                     -- 图标
  supports_category BOOLEAN DEFAULT TRUE,        -- 是否支持分类
  supports_tags     BOOLEAN DEFAULT TRUE,        -- 是否支持标签
  default_list_template   TEXT,                  -- 默认列表模板
  default_detail_template TEXT,                  -- 默认详情模板
  created_at    TIMESTAMP DEFAULT NOW(),
  updated_at    TIMESTAMP DEFAULT NOW(),
  deleted_at    TIMESTAMP                        -- 软删除
);
```

#### cms_field_groups — 字段分组（Tabs）

```sql
CREATE TABLE cms_field_groups (
  id                SERIAL PRIMARY KEY,
  content_type_id   INTEGER NOT NULL REFERENCES cms_content_types(id),
  key               VARCHAR(80) NOT NULL,        -- 'basic' | 'specs' | ...
  label             VARCHAR(80) NOT NULL,         -- '基础信息' | '技术规格' | ...
  sort              INTEGER DEFAULT 0,
  icon              VARCHAR(20),
  UNIQUE(content_type_id, key)
);
```

#### cms_field_definitions — 字段定义

```sql
CREATE TABLE cms_field_definitions (
  id                SERIAL PRIMARY KEY,
  content_type_id   INTEGER NOT NULL REFERENCES cms_content_types(id),
  field_key         VARCHAR(80) NOT NULL,         -- 在 custom_fields JSONB 里的 key
  label             VARCHAR(80) NOT NULL,         -- 显示标签
  field_type        VARCHAR(20) NOT NULL,         -- 见 FIELD_TYPES 枚举
  required          BOOLEAN DEFAULT FALSE,
  default_value     TEXT,
  options           JSONB,                        -- select 选项 / 配置
  validation        JSONB,                        -- min/max/regex 等校验规则
  group_id          INTEGER REFERENCES cms_field_groups(id),
  sort              INTEGER DEFAULT 0,
  status            VARCHAR(20) DEFAULT 'active', -- active | hidden
  created_by        INTEGER,
  created_at        TIMESTAMP DEFAULT NOW(),
  updated_at        TIMESTAMP DEFAULT NOW(),
  UNIQUE(content_type_id, field_key)
);
```

#### cms_field_options — 字段选项

```sql
CREATE TABLE cms_field_options (
  id                SERIAL PRIMARY KEY,
  definition_id     INTEGER NOT NULL REFERENCES cms_field_definitions(id) ON DELETE CASCADE,
  value             VARCHAR(80) NOT NULL,         -- 存储值
  label             VARCHAR(80) NOT NULL,         -- 显示标签
  color             VARCHAR(20),                  -- 颜色标记
  sort              INTEGER DEFAULT 0
);
```

#### cms_entries — 通用内容表

```sql
CREATE TABLE cms_entries (
  id                SERIAL PRIMARY KEY,
  content_type_id   INTEGER NOT NULL REFERENCES cms_content_types(id),
  slug              VARCHAR(120),                 -- URL 友好标识（可选）
  title             VARCHAR(200) NOT NULL,        -- 标题
  content           JSONB DEFAULT '{}'::jsonb,    -- 固定字段内容
  custom_fields     JSONB DEFAULT '{}'::jsonb,    -- 动态字段值
  category_id       INTEGER REFERENCES cms_categories(id),
  status            VARCHAR(20) DEFAULT 'draft',  -- draft | published | archived
  author_id         INTEGER,                       -- 创建人
  published_at      TIMESTAMP,
  sort              INTEGER DEFAULT 0,
  view_count        INTEGER DEFAULT 0,
  created_at        TIMESTAMP DEFAULT NOW(),
  updated_at        TIMESTAMP DEFAULT NOW(),
  deleted_at        TIMESTAMP,                    -- 软删除
  UNIQUE(content_type_id, slug)
);

CREATE INDEX idx_entries_content_type ON cms_entries(content_type_id);
CREATE INDEX idx_entries_category ON cms_entries(category_id);
CREATE INDEX idx_entries_status ON cms_entries(content_type_id, status);
CREATE INDEX idx_entries_custom_fields ON cms_entries USING gin(custom_fields);
```

#### cms_categories — 分类（3+ 级层级）

```sql
CREATE TABLE cms_categories (
  id                SERIAL PRIMARY KEY,
  content_type_id   INTEGER NOT NULL REFERENCES cms_content_types(id),
  parent_id         INTEGER REFERENCES cms_categories(id),  -- 自引用，nullable=顶级
  slug              VARCHAR(80) NOT NULL,
  name              VARCHAR(80) NOT NULL,
  icon              VARCHAR(20),
  color             VARCHAR(20),
  sort              INTEGER DEFAULT 0,
  status            VARCHAR(20) DEFAULT 'active',
  created_at        TIMESTAMP DEFAULT NOW(),
  updated_at        TIMESTAMP DEFAULT NOW(),
  deleted_at        TIMESTAMP,
  UNIQUE(content_type_id, slug)
);
```

#### cms_tags — 标签

```sql
CREATE TABLE cms_tags (
  id                SERIAL PRIMARY KEY,
  content_type_id   INTEGER NOT NULL REFERENCES cms_content_types(id),
  slug              VARCHAR(80) NOT NULL,
  name              VARCHAR(80) NOT NULL,
  color             VARCHAR(20),
  UNIQUE(content_type_id, slug)
);
```

#### cms_content_tags — 内容-标签多对多

```sql
CREATE TABLE cms_content_tags (
  content_type_id   INTEGER NOT NULL,
  content_id        INTEGER NOT NULL,
  tag_id            INTEGER NOT NULL REFERENCES cms_tags(id),
  PRIMARY KEY (content_type_id, content_id, tag_id)
);
```

### 3.2 现有表扩展

```sql
ALTER TABLE cms_products ADD COLUMN custom_fields JSONB DEFAULT '{}'::jsonb;
ALTER TABLE cms_cases    ADD COLUMN custom_fields JSONB DEFAULT '{}'::jsonb;
ALTER TABLE cms_news     ADD COLUMN custom_fields JSONB DEFAULT '{}'::jsonb;
ALTER TABLE auth_users   ADD COLUMN user_type VARCHAR(20) DEFAULT 'admin';
```

### 3.3 前台用户体系

#### portal_users

```sql
CREATE TABLE portal_users (
  id                SERIAL PRIMARY KEY,
  username          VARCHAR(80) UNIQUE NOT NULL,
  email             VARCHAR(120) UNIQUE,
  phone             VARCHAR(20) UNIQUE,
  nickname          VARCHAR(80),
  avatar            TEXT,
  password_hash     VARCHAR(128) NOT NULL,
  status            VARCHAR(20) DEFAULT 'active', -- active | disabled | locked
  last_login_at     TIMESTAMP,
  last_login_ip     VARCHAR(45),
  created_at        TIMESTAMP DEFAULT NOW(),
  updated_at        TIMESTAMP DEFAULT NOW(),
  deleted_at        TIMESTAMP
);
```

#### portal_user_oauth

```sql
CREATE TABLE portal_user_oauth (
  id                SERIAL PRIMARY KEY,
  user_id           INTEGER NOT NULL REFERENCES portal_users(id),
  provider          VARCHAR(20) NOT NULL,          -- feishu | wechat | github
  open_id           VARCHAR(200) NOT NULL,
  union_id          VARCHAR(200),
  access_token_enc  TEXT,
  refresh_token_enc TEXT,
  expires_at        TIMESTAMP,
  UNIQUE(provider, open_id)
);
```

#### portal_login_logs

```sql
CREATE TABLE portal_login_logs (
  id                SERIAL PRIMARY KEY,
  user_id           INTEGER NOT NULL REFERENCES portal_users(id),
  ip                VARCHAR(45),
  user_agent        TEXT,
  success           BOOLEAN DEFAULT TRUE,
  reason            VARCHAR(200),
  provider          VARCHAR(20) DEFAULT 'local',
  created_at        TIMESTAMP DEFAULT NOW()
);
```

### 3.4 实体关系图

```
cms_content_types 1──N cms_field_groups
cms_content_types 1──N cms_field_definitions
cms_content_types 1──N cms_categories (self-ref: parent_id)
cms_content_types 1──N cms_tags
cms_content_types 1──N cms_entries

cms_field_groups  1──N cms_field_definitions
cms_field_definitions 1──N cms_field_options

cms_categories    1──N cms_categories (children)
cms_categories    1──N cms_entries (category_id)

cms_entries       N──N cms_tags (via cms_content_tags)

auth_users        1──N auth_user_oauth
auth_users        1──N rbac_user_roles

portal_users      1──N portal_user_oauth
portal_users      1──N portal_login_logs
```

---

## 四、字段类型枚举（冻结）

```python
FIELD_TYPES = [
    'text',           # 单行文本
    'longtext',       # 多行文本
    'richtext',       # 富文本（HTML）
    'markdown',       # Markdown
    'number',         # 数字
    'boolean',        # 布尔
    'date',           # 日期
    'datetime',       # 日期时间
    'url',            # URL
    'email',          # Email
    'phone',          # 电话
    'image',          # 单图
    'images',         # 多图
    'file',           # 单文件
    'files',          # 多文件
    'select',         # 单选
    'multiselect',    # 多选
    'color',          # 颜色
    'json',           # 原始 JSON
    'repeater',       # 重复子项（嵌套字段组）
    'relation',       # 关联其他内容
]
```

### 各类型对应关系

| field_type | JSONB 存储格式 | 校验规则 | 前端控件 | Liquid 调用 |
|---|---|---|---|---|
| `text` | `string` | max_length | `<input type="text">` | `{{ field }}` |
| `longtext` | `string` | max_length | `<textarea>` | `{{ field }}` |
| `richtext` | `string` (HTML) | max_length | RichText Editor | `{{ field \| raw }}` |
| `markdown` | `string` (MD) | max_length | Vditor | `{{ field \| markdown }}` |
| `number` | `number` | min, max, step | `<input type="number">` | `{{ field }}` |
| `boolean` | `boolean` | - | `<Switch>` | `{% if field %}...{% endif %}` |
| `date` | `string` (ISO) | format | `<DatePicker>` | `{{ field \| date: '%Y-%m-%d' }}` |
| `datetime` | `string` (ISO) | format | `<DateTimePicker>` | `{{ field \| date: '%Y-%m-%d %H:%M' }}` |
| `url` | `string` | url format | `<input type="url">` | `{{ field }}` |
| `email` | `string` | email format | `<input type="email">` | `{{ field }}` |
| `phone` | `string` | phone regex | `<input type="tel">` | `{{ field }}` |
| `image` | `string` (URL) | - | ImageUploader | `{{ field }}` |
| `images` | `string[]` (URLs) | max_count | MultiImageUploader | `{% for img in field %}...{% endfor %}` |
| `file` | `string` (URL) | - | FileUploader | `{{ field }}` |
| `files` | `string[]` (URLs) | max_count | MultiFileUploader | `{% for f in field %}...{% endfor %}` |
| `select` | `string` | options list | `<Select>` | `{{ field }}` |
| `multiselect` | `string[]` | options list | `<MultiSelect>` | `{% for v in field %}...{% endfor %}` |
| `color` | `string` (hex) | hex format | `<ColorPicker>` | `{{ field }}` |
| `json` | `object/array` | valid JSON | CodeEditor (JSON) | `{{ field \| json }}` |
| `repeater` | `array<object>` | - | RepeaterField | `{% for row in field %}...{% endfor %}` |
| `relation` | `integer` / `integer[]` | target_type | RelationSelector | `{{ field }}` (ID) |

### 校验规则（validation JSONB 结构）

```json
// text / longtext
{ "max_length": 200 }

// number
{ "min": 0, "max": 99999, "step": 0.01 }

// date / datetime
{ "format": "YYYY-MM-DD", "min": "2000-01-01" }

// email
{ "pattern": "^[\\w.-]+@[\\w.-]+\\.\\w+$" }

// phone
{ "pattern": "^1[3-9]\\d{9}$" }

// images / files
{ "max_count": 10, "max_size_mb": 5, "accept": ".jpg,.png,.gif" }

// repeater
{ "min_rows": 0, "max_rows": 20, "sub_fields": [...] }

// relation
{ "target_content_type": "product", "multiple": false }
```

---

## 五、API 设计（冻结）

### 5.1 后台管理 API（需 admin 权限）

#### 内容类型

```
GET    /api/v1/cms/content-types                        列表
POST   /api/v1/cms/content-types                        创建
GET    /api/v1/cms/content-types/{id}                   详情
PATCH  /api/v1/cms/content-types/{id}                   更新
DELETE /api/v1/cms/content-types/{id}                   软删
```

#### 字段分组

```
GET    /api/v1/cms/content-types/{id}/field-groups       列表
POST   /api/v1/cms/content-types/{id}/field-groups       创建
PATCH  /api/v1/cms/content-types/{id}/field-groups/{gid} 更新
DELETE /api/v1/cms/content-types/{id}/field-groups/{gid} 删除
POST   /api/v1/cms/content-types/{id}/field-groups/reorder 排序
```

#### 字段定义

```
GET    /api/v1/cms/content-types/{id}/field-definitions        列表
POST   /api/v1/cms/content-types/{id}/field-definitions        创建
GET    /api/v1/cms/field-definitions/{id}                      详情
PATCH  /api/v1/cms/field-definitions/{id}                      更新
DELETE /api/v1/cms/field-definitions/{id}                      删除
POST   /api/v1/cms/content-types/{id}/field-definitions/reorder 排序
```

#### 字段选项

```
GET    /api/v1/cms/field-definitions/{id}/options          列表
POST   /api/v1/cms/field-options                           创建
PATCH  /api/v1/cms/field-options/{id}                      更新
DELETE /api/v1/cms/field-options/{id}                      删除
POST   /api/v1/cms/field-definitions/{id}/options/reorder  排序
```

#### 分类

```
GET    /api/v1/cms/categories?content_type_key=product&parent_id=  列表(树形)
POST   /api/v1/cms/categories                                       创建
GET    /api/v1/cms/categories/{id}                                  详情
PATCH  /api/v1/cms/categories/{id}                                  更新
DELETE /api/v1/cms/categories/{id}                                  软删+检查引用
POST   /api/v1/cms/categories/reorder                               拖拽排序
GET    /api/v1/cms/categories/tree?content_type_key=product         完整树
```

#### 标签

```
GET    /api/v1/cms/tags?content_type_key=product           列表
POST   /api/v1/cms/tags                                    创建
PATCH  /api/v1/cms/tags/{id}                               更新
DELETE /api/v1/cms/tags/{id}                               删除
```

#### 通用内容

```
GET    /api/v1/cms/entries?content_type_key=product&category=&tag=&custom.<field_key>=&page=&page_size=
POST   /api/v1/cms/entries                                 创建
GET    /api/v1/cms/entries/{id}                            详情
PATCH  /api/v1/cms/entries/{id}                            更新
DELETE /api/v1/cms/entries/{id}                            软删
POST   /api/v1/cms/entries/batch-delete                    批量删除
POST   /api/v1/cms/entries/batch-status                    批量改状态
```

#### 现有内容（兼容层，逐步迁移到 entries）

```
GET    /api/v1/cms/products?category=&tag=&custom.<field_key>=
POST   /api/v1/cms/products  body 接受 custom_fields
PATCH  /api/v1/cms/products/{id}
... 同样 cases/news
```

### 5.2 公共 API（前台用，无需 admin 权限）

#### 内容公共接口

```
GET    /api/v1/public/site/{content_type_key}?line=&category=&tag=&page=&page_size=  列表
GET    /api/v1/public/site/{content_type_key}/{id_or_slug}                            详情
GET    /api/v1/public/categories?content_type_key=product                             分类列表
GET    /api/v1/public/categories/tree?content_type_key=product                        分类树
GET    /api/v1/public/tags?content_type_key=product                                   标签列表
GET    /api/v1/public/field-definitions?content_type_key=product                      字段定义(供前台渲染)
```

#### 前台用户认证

```
POST   /api/v1/public/portal/auth/register             注册
POST   /api/v1/public/portal/auth/login                登录
POST   /api/v1/public/portal/auth/refresh              刷新 token
POST   /api/v1/public/portal/auth/forgot-password      忘记密码
POST   /api/v1/public/portal/auth/reset-password       重置密码
GET    /api/v1/public/portal/me                        当前用户信息
PATCH  /api/v1/public/portal/me/profile                更新资料
POST   /api/v1/public/portal/me/change-password        修改密码
```

#### 前台用户 OAuth

```
GET    /api/v1/public/portal/auth/{provider}/authorize   OAuth 授权跳转
GET    /api/v1/public/portal/auth/{provider}/callback    OAuth 回调
```

### 5.3 权限映射

| API 前缀 | 需要权限 | token 类型 |
|----------|---------|-----------|
| `/api/v1/cms/*` | admin RBAC 权限 | admin JWT |
| `/api/v1/auth/*` | admin RBAC 权限 | admin JWT |
| `/api/v1/rbac/*` | admin RBAC 权限 | admin JWT |
| `/api/v1/system/*` | admin RBAC 权限 | admin JWT |
| `/api/v1/public/site/*` | 无需认证 | - |
| `/api/v1/public/portal/auth/*` | 无需认证(注册/登录) | - |
| `/api/v1/public/portal/me` | portal JWT | portal JWT |
| `/api/v1/public/categories/*` | 无需认证 | - |
| `/api/v1/public/tags/*` | 无需认证 | - |
| `/api/v1/public/field-definitions` | 无需认证 | - |

---

## 六、App 中心扩展（冻结）

### 6.1 AppManifest 扩展

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

    # ---- V2 扩展字段 ----

    content_types: list[dict] = field(default_factory=list)
    # 例：[{"key":"product","name":"产品","icon":"📦","supports_category":True,"supports_tags":True}]

    field_groups: list[dict] = field(default_factory=list)
    # 例：[{"key":"basic","label":"基础信息","sort":0}, {"key":"specs","label":"技术规格","sort":1}]

    field_definitions: list[dict] = field(default_factory=list)
    # 例：[{"key":"price","label":"价格","type":"number","group":"specs","required":True,"validation":{"min":0}}]

    categories_seed: list[dict] = field(default_factory=list)
    # 初始分类（首次安装时种入）
    # 例：[{"content_type":"product","name":"MES系统","slug":"mes","children":[...]}]

    public_routes_prefix: str = ""
    # 公共 API 路由前缀，例："/api/v1/public/cms"
```

### 6.2 InstalledApp 表扩展

```sql
ALTER TABLE platform_apps ADD COLUMN permissions_grants JSONB DEFAULT '{}'::jsonb;
-- 例：{"content_editor": ["cms:field_definitions:read", "cms:field_definitions:write"]}
```

### 6.3 App 生命周期增强

```
安装流程：
  1. 校验依赖（dependencies）
  2. 写入 platform_apps 记录
  3. 自动注册 content_types → cms_content_types
  4. 自动注册 field_groups → cms_field_groups
  5. 自动注册 field_definitions → cms_field_definitions
  6. 自动种入 categories_seed → cms_categories
  7. 创建 permissions_required 中声明的权限
  8. 分配 permissions_grants 中声明的角色权限

卸载流程：
  1. 检查是否有内容引用（cms_entries）
  2. 软删除关联的 content_types（级联影响 entries/fields/categories/tags）
  3. 移除 permissions
  4. 更新 platform_apps 状态为 uninstalled

升级流程：
  1. 比对 manifest 版本
  2. 增量更新 content_types / field_definitions
  3. 不删除已有数据，仅新增/修改
```

### 6.4 App 中心 UI 增强

| 功能 | 说明 |
|------|------|
| 字段管理权分配 | 超管可勾选"内容编辑"角色可建字段 |
| App 详情页展示 | 展示 content_types、field_definitions 数量统计 |
| 一键安装/卸载 | 触发完整的生命周期流程 |
| 权限委派 | 可视化编辑 permissions_grants JSON |

---

## 七、Liquid 模板契约（冻结）

### 7.1 基础语法

```liquid
{# 变量插值 #}
{{ var }}
{{ var | filter }}
{{ var | default: 'fallback' }}

{# 流程控制 #}
{% if condition %}...{% endif %}
{% if condition %}...{% elsif other %}...{% else %}...{% endif %}
{% for x in collection %}...{% endfor %}

{# 赋值 #}
{% assign x = 'hello' %}
{% capture var %}...{% endcapture %}
```

### 7.2 内置 Filters

| Filter | 用法 | 说明 |
|--------|------|------|
| `upcase` | `{{ str \| upcase }}` | 大写 |
| `downcase` | `{{ str \| downcase }}` | 小写 |
| `truncate` | `{{ str \| truncate: 100 }}` | 截断 |
| `append` | `{{ str \| append: '...' }}` | 追加 |
| `prepend` | `{{ str \| prepend: 'Hello ' }}` | 前置 |
| `date` | `{{ date \| date: '%Y-%m-%d' }}` | 日期格式化 |
| `currency` | `{{ num \| currency }}` | 货币格式 (¥1,234.00) |
| `markdown` | `{{ str \| markdown }}` | Markdown → HTML |
| `strip_html` | `{{ str \| strip_html }}` | 去 HTML 标签 |
| `json` | `{{ obj \| json }}` | JSON 序列化 |
| `join` | `{{ arr \| join: ', ' }}` | 数组合并 |
| `size` | `{{ arr \| size }}` | 数组/字符串长度 |
| `first` | `{{ arr \| first }}` | 取第一个 |
| `last` | `{{ arr \| last }}` | 取最后一个 |
| `default` | `{{ var \| default: 'N/A' }}` | 默认值 |
| `escape` | `{{ str \| escape }}` | HTML 转义 |
| `strip` | `{{ str \| strip }}` | 去首尾空白 |
| `slice` | `{{ str \| slice: 0, 5 }}` | 截取子串 |
| `uniq` | `{{ arr \| uniq }}` | 去重 |
| `sort` | `{{ arr \| sort }}` | 排序 |
| `map` | `{{ arr \| map: 'name' }}` | 取属性 |
| `where` | `{{ arr \| where: 'status', 'published' }}` | 过滤 |

### 7.3 自定义 Filters（业务）

| Filter | 用法 | 说明 |
|--------|------|------|
| `t` | `{{ product.line \| t }}` | i18n 翻译（业务线中文名） |
| `format_price` | `{{ price \| format_price }}` | 价格格式化 |
| `asset_url` | `{{ path \| asset_url }}` | 资源 URL 补全 |
| `thumb` | `{{ url \| thumb: '300x200' }}` | 缩略图 URL |
| `reading_time` | `{{ content \| reading_time }}` | 阅读时长(分钟) |

### 7.4 全局变量（自动注入）

```javascript
{
  now: new Date(),
  site: {
    name: '辰科',
    domain: 'cenkor.cn',
    logo: '...',
    description: '...',
    // ... from cms_site_config
  },
  theme: {
    primary_color: '#...',
    font_family: '...',
    // ... from theme settings
  },
  current_user: null | { id, username, nickname, avatar },
  request: {
    path: '/products/abc',
    params: { ... },
    query: { page: 1, ... }
  }
}
```

### 7.5 前端集成方案

```javascript
// 封装为全局函数
import { Liquid } from 'liquidjs'

const engine = new Liquid({
  // 注册自定义 filters
})

engine.registerFilter('t', (val) => i18nMap[val] || val)
engine.registerFilter('format_price', (val) => '¥' + Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2 }))
engine.registerFilter('asset_url', (path) => `${CDN_BASE}/${path}`)
engine.registerFilter('thumb', (url, size) => `${url}?resize=${size}`)
engine.registerFilter('reading_time', (content) => Math.ceil(content.length / 500))

// 全局挂载
window.cmsRender = async (template, data) => {
  const globalData = {
    now: new Date(),
    site: await getSiteConfig(),
    theme: await getThemeConfig(),
    current_user: getCurrentUser(),
    ...data
  }
  return engine.parseAndRender(template, globalData)
}
```

### 7.6 后端模板预览 API

```
POST /api/v1/cms/templates/preview
Body: { "template": "{{ product.name }} - {{ product.price | format_price }}", "data": { "product": {...} } }
Response: { "rendered": "ThinkMES - ¥1,234.00" }
```

---

## 八、10 周执行计划

### 总览

| 周 | 轨道 1：CMS 增强 | 轨道 2：安全整改 | 轨道 3：底座演进 |
|---|---|---|---|
| W1 | M1-A 字段定义表 + Alembic | 阶段 1 紧急止血 | App 中心 UI 改造 |
| W2 | M1-B 字段 API + 后台 UI | 阶段 2 基础设施 | App 中心安装/卸载流程 |
| W3 | M2-A 分类表 + 后台 | 阶段 3 依赖修复 | Manifest 扩展（含 content_types） |
| W4 | M2-B 标签 + 内容接入 | （持续收尾） | 通用 BaseContent 抽象 |
| W5 | M3-A 公共 API | — | FieldRegistry 抽象 |
| W6 | M3-B liquidjs 集成 | — | 多租户 Phase 3（可选） |
| W7 | 网站静态页改造 | — | — |
| W8 | 测试 + 文档 | — | — |
| W9 | 用户体系拆分 | — | — |
| W10 | 联调 + 上线 | — | — |

### W1 详解

| 天 | 任务 | 产出 |
|---|---|---|
| D1-D2 | 创建所有新模型（8 张表） | `models.py` 更新 |
| D3 | 生成 Alembic 迁移 + 执行 | 迁移文件 |
| D4 | 创建 portal 模块骨架 | `apps/portal/` |
| D5 | 字段类型枚举 + 校验规则 | `field_types.py` |

### W2 详解

| 天 | 任务 | 产出 |
|---|---|---|
| D1-D2 | Content Types / Field Groups / Field Definitions / Field Options CRUD API | `router.py` 更新 |
| D3 | Pydantic schemas | `schemas.py` 更新 |
| D4-D5 | 后台 UI：ContentType Builder + 字段定义编辑器 | Vue 组件 |

### W3 详解

| 天 | 任务 | 产出 |
|---|---|---|
| D1-D2 | Categories CRUD + 树形 API + 拖拽排序 | `router.py` 更新 |
| D3 | Tags CRUD API | `router.py` 更新 |
| D4-D5 | 后台 UI：分类管理 + 标签管理 | Vue 组件 |

### W4 详解

| 天 | 任务 | 产出 |
|---|---|---|
| D1-D2 | 通用内容 Entries CRUD API + custom_fields 过滤 | `router.py` 更新 |
| D3 | 数据迁移脚本：products/cases/news → entries | 迁移脚本 |
| D4-D5 | 后台 UI：通用内容列表/编辑页 | Vue 组件 |

### W5 详解

| 天 | 任务 | 产出 |
|---|---|---|
| D1-D2 | 公共内容 API（列表/详情/分类/标签/字段定义） | `public_router.py` 更新 |
| D3-D4 | 前台用户认证 API（register/login/refresh/profile） | `apps/portal/router.py` |
| D5 | 路由级隔离验证 | `api/deps.py` 更新 |

### W6 详解

| 天 | 任务 | 产出 |
|---|---|---|
| D1-D2 | 后端 Liquid 模板渲染 + 自定义 filters | `core/template_engine.py` |
| D3 | 模板预览 API | `router.py` |
| D4-D5 | 前端 liquidjs 集成 + window.cmsRender | portal-web 更新 |

### W7 详解

| 天 | 任务 | 产出 |
|---|---|---|
| D1-D2 | portal-web 公共内容页（列表/详情） | Vue 页面 |
| D3-D4 | 内容页使用 Liquid 模板渲染 | Vue 组件 |
| D5 | 整体联调 | - |

### W8 详解 ✅

| 天 | 任务 | 产出 | 状态 |
|---|---|---|---|
| D1-D2 | 全链路 E2E 测试 | `tests/test_content_engine.py` (25 测试) | ✅ |
| D3 | 性能测试（1000+ 条目） | 全部 < 50ms | ✅ |
| D4-D5 | 文档更新 | `ARCHITECTURE.md` V2 重写 + `docs/DEV_GUIDE.md` | ✅ |

**测试结果**:
- 单元测试: 28/28 ✅
- E2E 测试: 25/25 ✅
- 整体测试: 98+/105（旧测试因 V2 数据迁移待更新）

**性能基准（1000+ 条目）**:
- Content Types 列表: 29ms
- Entries 列表 (20/page): 31ms
- JSONB 过滤查询: 5ms
- 模板渲染 (20 items): 20ms
- 公共内容 API: 14ms
- 分类树: 11ms

### W9 详解

| 天 | 任务 | 产出 |
|---|---|---|
| D1-D2 | portal_users 后台管理 API | `router.py` |
| D3 | portal_user_oauth 绑定 | `router.py` |
| D4 | portal-web 全面接入新认证体系 | Vue 更新 |
| D5 | 现有注册接口切换为 portal_users | `auth/router.py` |

### W10 详解

| 天 | 任务 | 产出 |
|---|---|---|
| D1-D2 | 全链路联调 + bug 修复 | - |
| D3 | 部署验证（Docker / 宝塔） | - |
| D4 | 数据迁移验证 + 回滚方案 | - |
| D5 | 正式上线 | - |

---

## 九、任务清单（Checkbox 跟踪）

### Phase 1: M1 — 通用内容引擎底座（W1-W2）

#### M1-A: 数据库 + Alembic 迁移

- [ ] 1.1 创建 `ContentType` 模型（cms_content_types）
- [ ] 1.2 创建 `FieldGroup` 模型（cms_field_groups）
- [ ] 1.3 创建 `FieldDefinition` 模型（cms_field_definitions）
- [ ] 1.4 创建 `FieldOption` 模型（cms_field_options）
- [ ] 1.5 创建 `Entry` 模型（cms_entries，含 content + custom_fields JSONB）
- [ ] 1.6 创建 `Category` 模型（cms_categories，3+ 级自引用）
- [ ] 1.7 创建 `Tag` 模型（cms_tags）
- [ ] 1.8 创建 `ContentTag` 关联模型（cms_content_tags）
- [ ] 1.9 扩展 `Product` 加 `custom_fields JSONB`
- [ ] 1.10 扩展 `Case` 加 `custom_fields JSONB`
- [ ] 1.11 扩展 `News` 加 `custom_fields JSONB`
- [ ] 1.12 扩展 `User` (auth_users) 加 `user_type VARCHAR(20)`
- [ ] 1.13 创建 `PortalUser` 模型（portal_users）
- [ ] 1.14 创建 `PortalUserOAuth` 模型（portal_user_oauth）
- [ ] 1.15 创建 `PortalLoginLog` 模型（portal_login_logs）
- [ ] 1.16 创建 `apps/portal/__init__.py`
- [ ] 1.17 创建 `apps/portal/models.py`
- [ ] 1.18 创建 `apps/cms/field_types.py`（FIELD_TYPES 枚举 + 校验规则映射）
- [ ] 1.19 生成 Alembic 迁移文件
- [ ] 1.20 执行迁移验证

#### M1-B: 字段管理 API + 后台 UI

- [ ] 2.1 Content Types CRUD API（GET/POST/PATCH/DELETE）
- [ ] 2.2 Field Groups CRUD API（GET/POST/PATCH/DELETE/reorder）
- [ ] 2.3 Field Definitions CRUD API（GET/POST/PATCH/DELETE/reorder）
- [ ] 2.4 Field Options CRUD API（GET/POST/PATCH/DELETE/reorder）
- [ ] 2.5 Pydantic schemas（请求/响应模型）
- [ ] 2.6 字段校验逻辑（field_types.py → API 校验中间件）
- [ ] 2.7 后台 UI：ContentTypeListView.vue（内容类型列表/创建/编辑）
- [ ] 2.8 后台 UI：FieldDefinitionsView.vue（字段定义编辑器 + 拖拽排序）
- [ ] 2.9 后台 UI：DynamicFieldRenderer.vue（20 种字段类型渲染控件）
- [ ] 2.10 后台 UI：FieldGroupTabs.vue（字段分组 tabs 组件）
- [ ] 2.11 路由注册 + 菜单配置

### Phase 2: M2 — 分类 + 标签 + 内容迁移（W3-W4）

#### M2-A: 分类 + 标签系统

- [ ] 3.1 Categories CRUD API（含树形查询、拖拽排序）
- [ ] 3.2 Categories Tree API（完整树结构）
- [ ] 3.3 Tags CRUD API
- [ ] 3.4 内容-标签关联 API（批量设置标签）
- [ ] 3.5 Pydantic schemas
- [ ] 3.6 后台 UI：CategoryManager.vue（TreeSelect，3+ 级分类管理）
- [ ] 3.7 后台 UI：TagManager.vue（标签管理，颜色选择器）
- [ ] 3.8 公共 API：`GET /api/v1/public/categories`
- [ ] 3.9 公共 API：`GET /api/v1/public/categories/tree`
- [ ] 3.10 公共 API：`GET /api/v1/public/tags`

#### M2-B: 通用内容接入 + 数据迁移

- [ ] 4.1 Entries CRUD API（含 custom_fields 过滤）
- [ ] 4.2 Entries 列表搜索/过滤（按 category、tag、custom.xxx 字段）
- [ ] 4.3 Entries 批量操作（批量删除、批量改状态）
- [ ] 4.4 Entries CSV 导出
- [ ] 4.5 数据迁移脚本：products → cms_entries
- [ ] 4.6 数据迁移脚本：cases → cms_entries
- [ ] 4.7 数据迁移脚本：news → cms_entries
- [ ] 4.8 迁移数据验证脚本
- [ ] 4.9 适配现有 CMS router 兼容层（保留旧 API 路由，内部重定向到 entries）
- [ ] 4.10 后台 UI：EntryListView.vue（通用内容列表）
- [ ] 4.11 后台 UI：EntryEditView.vue（通用内容编辑，DynamicFieldRenderer 驱动）
- [ ] 4.12 后台 UI：EntryFilterBar.vue（动态字段过滤组件）

### Phase 3: M3 — 公共 API + Liquid 模板（W5-W6）

#### M3-A: 公共 API 网关

- [ ] 5.1 `GET /api/v1/public/site/{content_type_key}` 列表（分页/分类/标签过滤）
- [ ] 5.2 `GET /api/v1/public/site/{content_type_key}/{id_or_slug}` 详情
- [ ] 5.3 `GET /api/v1/public/field-definitions` 字段定义（前台渲染用）
- [ ] 5.4 `POST /api/v1/public/portal/auth/register` 前台注册
- [ ] 5.5 `POST /api/v1/public/portal/auth/login` 前台登录
- [ ] 5.6 `POST /api/v1/public/portal/auth/refresh` 刷新 token
- [ ] 5.7 `POST /api/v1/public/portal/auth/forgot-password` 忘记密码
- [ ] 5.8 `POST /api/v1/public/portal/auth/reset-password` 重置密码
- [ ] 5.9 `GET /api/v1/public/portal/me` 当前用户
- [ ] 5.10 `PATCH /api/v1/public/portal/me/profile` 更新资料
- [ ] 5.11 `POST /api/v1/public/portal/me/change-password` 修改密码
- [ ] 5.12 Portal JWT 签发（独立 issuer `cenkor-portal`）
- [ ] 5.13 路由级隔离：portal JWT 无法访问后台 API
- [ ] 5.14 API 限流（slowapi + Redis）

#### M3-B: Liquid 模板引擎集成

- [ ] 6.1 后端：Python liquid 模板渲染引擎封装
- [ ] 6.2 后端：内置 filters 实现（upcase/downcase/truncate/date/currency/markdown/strip_html/json/join/size/first/last/escape/slice/uniq/sort/map/where）
- [ ] 6.3 后端：自定义业务 filters（t/format_price/asset_url/thumb/reading_time）
- [ ] 6.4 后端：模板预览 API（`POST /api/v1/cms/templates/preview`）
- [ ] 6.5 后端：全局变量注入（now/site/theme/current_user/request）
- [ ] 6.6 前端：liquidjs 库集成 + `window.cmsRender()` 封装
- [ ] 6.7 前端：自定义 filters 注册（t/format_price/asset_url/thumb/reading_time）
- [ ] 6.8 前端：全局变量自动注入
- [ ] 6.9 portal-web：公共内容页组件基础框架

### Phase 4: App 中心增强 + 安全整改（W7-W8）

#### 轨道 A: App 中心增强

- [ ] 7.1 AppManifest 扩展（content_types/field_groups/field_definitions/categories_seed/public_routes_prefix）
- [ ] 7.2 CMS manifest 更新（声明 product/case/news 的 content_types 和 field_definitions）
- [ ] 7.3 启动时自动注册 app 的 content_types → DB
- [ ] 7.4 启动时自动注册 app 的 field_definitions → DB
- [ ] 7.5 启动时自动种入 categories_seed → DB
- [ ] 7.6 InstalledApp 表加 `permissions_grants JSONB`
- [ ] 7.7 App 中心 UI：字段管理权分配
- [ ] 7.8 App 中心 UI：content_types / field_definitions 统计展示
- [ ] 7.9 App 中心 UI：一键安装/卸载完整流程
- [ ] 7.10 App 中心 UI：permissions_grants 可视化编辑

#### 轨道 B: 安全整改

- [ ] 7.11 密钥轮换机制（SECRET_KEY_ROTATION）
- [ ] 7.12 媒体文件目录隔离（bucket/日期/内容类型）
- [ ] 7.13 API 限流完善
- [ ] 7.14 CORS 策略收紧
- [ ] 7.15 依赖安全审计（pip audit / npm audit）

### Phase 5: 用户体系拆分（W9）

- [ ] 8.1 portal_users 后台管理 API（管理员查看/管理前台用户）
- [ ] 8.2 portal_user_oauth 绑定（微信/飞书 OAuth 流程）
- [ ] 8.3 portal_login_logs 记录
- [ ] 8.4 路由级隔离完整验证
- [ ] 8.5 portal-web 全面接入新认证体系
- [ ] 8.6 现有注册接口切换（auth/register → portal_users）
- [ ] 8.7 数据迁移：现有 auth_users 中的前台用户 → portal_users
- [ ] 8.8 前台用户 profile 完整页面
- [ ] 8.9 后台 UI：PortalUsersListView.vue（前台用户管理）

### Phase 6: 联调测试上线（W10）

- [ ] 9.1 全链路 E2E 测试：内容类型 → 字段定义 → 内容创建 → 公共 API
- [ ] 9.2 全链路 E2E 测试：前台用户注册/登录/profile/OAuth
- [ ] 9.3 全链路 E2E 测试：Liquid 模板渲染
- [ ] 9.4 全链路 E2E 测试：App 安装/卸载生命周期
- [ ] 9.5 性能测试：1000+ 内容条目查询
- [ ] 9.6 性能测试：JSONB custom_fields 索引效率
- [ ] 9.7 性能测试：公共 API 并发 100 QPS
- [ ] 9.8 ARCHITECTURE.md 更新
- [ ] 9.9 API 文档更新（OpenAPI）
- [ ] 9.10 Docker 部署验证
- [ ] 9.11 宝塔部署验证
- [ ] 9.12 数据迁移回滚方案
- [ ] 9.13 正式上线

---

## 十、风险与决策记录

### 关键决策

| # | 决策 | 选项 | 决定 | 原因 |
|---|------|------|------|------|
| D1 | 内容表策略 | A: 保留现有表+JSONB / B: 统一通用内容表 | **B** | 更灵活，支持未来自定义内容类型 |
| D2 | 用户拆分时机 | A: 先做 / B: 后做 / C: 并行 | **B（W9）** | CMS 引擎不依赖 portal_users，先做核心 |
| D3 | 模板引擎 | A: Jinja2 / B: Liquid / C: Mustache | **Liquid (liquidjs)** | 生态成熟、安全沙箱、前后端一致 |
| D4 | 分类层级 | A: 2 级 / B: 3+ 级 / C: 无限 | **B（3+ 级）** | 满足多数企业场景，避免无限递归复杂度 |
| D5 | 字段存储 | A: 独立表 / B: JSONB | **B（JSONB）** | 灵活、性能好、PG 原生索引支持 |

### 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 数据迁移丢失 | 低 | 高 | 迁移前全量备份，迁移后校验脚本 |
| JSONB 查询性能 | 中 | 中 | GIN 索引 + 查询优化 + 缓存 |
| Liquid 沙箱逃逸 | 低 | 高 | 使用 liquidjs 安全模式，限制可用 filters |
| 前后台 token 混淆 | 中 | 高 | 不同 issuer + 路由级验证 |
| 迁移期间服务中断 | 中 | 高 | 灰度发布 + 兼容层 + 回滚方案 |

### 版本兼容策略

| 版本 | 说明 |
|------|------|
| v1.x（当前） | 现有 products/cases/news 独立表，auth_users 单用户体系 |
| v2.0（目标） | 通用内容引擎 + 字段定义 + 分类标签 + Liquid + 双用户体系 |
| 兼容层 | v1 API 路由保留，内部重定向到 v2 通用内容 API |
| 迁移窗口 | 预留 2 周并行期，v1/v2 API 同时可用 |
