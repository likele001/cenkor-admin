# Cenkor Platform 改造执行计划

> 通用企业级后台管理系统 + CMS + 前后台用户分离
> 创建日期：2026-06-10
> 状态：**执行中**

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
│  - user_type: 'admin' | 'superadmin'       │
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

### 2.1 新增：内容引擎元数据

#### cms_content_types（内容类型）

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | SERIAL | PK | |
| key | VARCHAR(60) | UNIQUE, NOT NULL | 'product' / 'case' / 'news' / 自定义 |
| name | VARCHAR(80) | NOT NULL | 显示名称 |
| description | TEXT | | 描述 |
| icon | VARCHAR(40) | | 图标 |
| supports_category | BOOLEAN | DEFAULT true | 是否启用分类 |
| supports_tags | BOOLEAN | DEFAULT true | 是否启用标签 |
| default_list_template | TEXT | | 列表页默认模板 |
| default_detail_template | TEXT | | 详情页默认模板 |
| created_at | TIMESTAMPTZ | DEFAULT now() | |
| updated_at | TIMESTAMPTZ | DEFAULT now() | |
| deleted_at | TIMESTAMPTZ | NULL | 软删 |

#### cms_field_groups（字段分组 / Tabs）

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | SERIAL | PK | |
| content_type_id | INTEGER | FK → cms_content_types.id | |
| key | VARCHAR(60) | NOT NULL | 分组标识 |
| label | VARCHAR(80) | NOT NULL | 显示名称 |
| sort | INTEGER | DEFAULT 0 | 排序 |
| icon | VARCHAR(40) | | 图标 |

UNIQUE(content_type_id, key)

#### cms_field_definitions（字段定义）

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | SERIAL | PK | |
| content_type_id | INTEGER | FK → cms_content_types.id | |
| field_key | VARCHAR(80) | NOT NULL | custom_fields JSONB 中的 key |
| label | VARCHAR(80) | NOT NULL | 显示名称 |
| field_type | VARCHAR(20) | NOT NULL | 见字段类型枚举 |
| required | BOOLEAN | DEFAULT false | |
| default_value | TEXT | | 默认值 |
| options | JSONB | DEFAULT '{}' | select 选项 / 验证规则 |
| validation | JSONB | DEFAULT '{}' | min/max/regex 等 |
| group_id | INTEGER | FK → cms_field_groups.id, NULL | 字段分组 |
| sort | INTEGER | DEFAULT 0 | 排序 |
| status | VARCHAR(10) | DEFAULT 'active' | active / disabled |
| created_by | INTEGER | FK → auth_users.id, NULL | |
| created_at | TIMESTAMPTZ | DEFAULT now() | |
| updated_at | TIMESTAMPTZ | DEFAULT now() | |

UNIQUE(content_type_id, field_key)

#### cms_field_options（字段候选项）

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | SERIAL | PK | |
| definition_id | INTEGER | FK → cms_field_definitions.id | |
| value | VARCHAR(80) | NOT NULL | 存储值 |
| label | VARCHAR(80) | NOT NULL | 显示名称 |
| color | VARCHAR(20) | | 颜色标识 |
| sort | INTEGER | DEFAULT 0 | |

#### cms_categories（分类，3 套独立，每套 3+ 级层级）

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | SERIAL | PK | |
| content_type_id | INTEGER | FK → cms_content_types.id | |
| parent_id | INTEGER | FK → cms_categories.id, NULL | 自引用 |
| slug | VARCHAR(80) | NOT NULL | URL 标识 |
| name | VARCHAR(80) | NOT NULL | |
| icon | VARCHAR(40) | | |
| color | VARCHAR(20) | | |
| sort | INTEGER | DEFAULT 0 | |
| status | VARCHAR(10) | DEFAULT 'active' | |
| created_at | TIMESTAMPTZ | DEFAULT now() | |
| updated_at | TIMESTAMPTZ | DEFAULT now() | |
| deleted_at | TIMESTAMPTZ | NULL | 软删 |

UNIQUE(content_type_id, slug)

#### cms_tags（标签）

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | SERIAL | PK | |
| content_type_id | INTEGER | FK → cms_content_types.id | |
| slug | VARCHAR(80) | NOT NULL | |
| name | VARCHAR(80) | NOT NULL | |
| color | VARCHAR(20) | | |

UNIQUE(content_type_id, slug)

#### cms_content_tags（内容-标签多对多）

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| content_type_id | INTEGER | NOT NULL | |
| content_id | INTEGER | NOT NULL | |
| tag_id | INTEGER | FK → cms_tags.id | |

PRIMARY KEY (content_type_id, content_id, tag_id)

### 2.2 通用内容表

#### cms_entries（通用内容，替代独立的 products/cases/news）

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | SERIAL | PK | |
| content_type_id | INTEGER | FK → cms_content_types.id | |
| slug | VARCHAR(120) | | URL 标识（可选） |
| title | VARCHAR(200) | NOT NULL | |
| content | JSONB | DEFAULT '{}' | 标准字段（富文本、摘要等） |
| custom_fields | JSONB | DEFAULT '{}' | 动态字段（由 field_definitions 定义） |
| category_id | INTEGER | FK → cms_categories.id, NULL | |
| cover_image | VARCHAR(500) | | 封面图 |
| author_id | INTEGER | FK → auth_users.id, NULL | |
| status | VARCHAR(20) | DEFAULT 'draft' | draft / published / archived |
| published_at | TIMESTAMPTZ | NULL | |
| sort | INTEGER | DEFAULT 0 | |
| line | VARCHAR(20) | | 业务线标识（兼容旧字段） |
| created_at | TIMESTAMPTZ | DEFAULT now() | |
| updated_at | TIMESTAMPTZ | DEFAULT now() | |
| deleted_at | TIMESTAMPTZ | NULL | 软删 |

UNIQUE(content_type_id, slug) WHERE slug IS NOT NULL

INDEX: idx_entries_ct_status (content_type_id, status)
INDEX: idx_entries_ct_category (content_type_id, category_id)
INDEX: idx_entries_published (content_type_id, status, published_at DESC)
GIN INDEX: idx_entries_custom_fields (custom_fields)

### 2.3 现有表加 custom_fields JSONB（过渡期兼容）

```sql
ALTER TABLE cms_products ADD COLUMN custom_fields JSONB DEFAULT '{}'::jsonb;
ALTER TABLE cms_cases    ADD COLUMN custom_fields JSONB DEFAULT '{}'::jsonb;
ALTER TABLE cms_news     ADD COLUMN custom_fields JSONB DEFAULT '{}'::jsonb;
```

### 2.4 用户体系拆分

#### portal_users（前台用户，新表）

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | SERIAL | PK | |
| username | VARCHAR(60) | UNIQUE, NOT NULL | |
| email | VARCHAR(120) | UNIQUE | |
| phone | VARCHAR(20) | | |
| nickname | VARCHAR(60) | | |
| avatar | VARCHAR(500) | | |
| password_hash | VARCHAR(128) | NOT NULL | |
| status | VARCHAR(10) | DEFAULT 'active' | active / disabled / locked |
| last_login_at | TIMESTAMPTZ | NULL | |
| last_login_ip | VARCHAR(45) | NULL | |
| created_at | TIMESTAMPTZ | DEFAULT now() | |
| updated_at | TIMESTAMPTZ | DEFAULT now() | |
| deleted_at | TIMESTAMPTZ | NULL | 软删 |

#### portal_user_oauth（前台用户 OAuth）

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | SERIAL | PK | |
| user_id | INTEGER | FK → portal_users.id | |
| provider | VARCHAR(20) | NOT NULL | feishu / wechat / github |
| open_id | VARCHAR(200) | NOT NULL | |
| union_id | VARCHAR(200) | | |
| access_token_enc | TEXT | | 加密存储 |
| refresh_token_enc | TEXT | | |
| expires_at | TIMESTAMPTZ | NULL | |

UNIQUE(provider, open_id)

#### auth_users 变更

```sql
ALTER TABLE auth_users ADD COLUMN user_type VARCHAR(20) DEFAULT 'admin';
-- 'admin' (后台) | 'superadmin' (超管)
-- 前台用户不再用此表
```

---

## 三、字段类型枚举（冻结）

| 类型 | key | 存储格式 | 后端校验 | 前端控件 | 模板调用 |
|------|-----|----------|----------|----------|----------|
| 单行文本 | `text` | string | max_length | `<input type="text">` | `{{ field.value }}` |
| 多行文本 | `longtext` | string | max_length | `<textarea>` | `{{ field.value }}` |
| 富文本 | `richtext` | string (HTML) | sanitize | RichTextEditor | `{{ field.value \| raw }}` |
| Markdown | `markdown` | string | - | VditorEditor | `{{ field.value \| markdown }}` |
| 数字 | `number` | number | min, max | `<input type="number">` | `{{ field.value }}` |
| 布尔 | `boolean` | boolean | - | `<Switch>` | `{% if field.value %}` |
| 日期 | `date` | string (ISO) | date_format | `<DatePicker>` | `{{ field.value \| date: '%Y-%m-%d' }}` |
| 日期时间 | `datetime` | string (ISO) | datetime_format | `<DateTimePicker>` | `{{ field.value \| date: '%Y-%m-%d %H:%M' }}` |
| URL | `url` | string | url_format | `<input type="url">` | `{{ field.value }}` |
| Email | `email` | string | email_format | `<input type="email">` | `{{ field.value }}` |
| 电话 | `phone` | string | phone_format | `<input type="tel">` | `{{ field.value }}` |
| 单图 | `image` | string (URL) | url_format | ImageUploader | `{{ field.value }}` |
| 多图 | `images` | string[] | url_format[] | MultiImageUploader | `{% for img in field.value %}` |
| 单文件 | `file` | object {url, name, size} | - | FileUploader | `{{ field.value.url }}` |
| 多文件 | `files` | object[] | - | MultiFileUploader | `{% for f in field.value %}` |
| 单选 | `select` | string | in_options | `<Select>` | `{{ field.value }}` |
| 多选 | `multiselect` | string[] | in_options[] | `<MultiSelect>` | `{% for v in field.value %}` |
| 颜色 | `color` | string (hex) | hex_format | ColorPicker | `{{ field.value }}` |
| JSON | `json` | any | valid_json | CodeEditor | `{{ field.value \| json }}` |
| 重复子项 | `repeater` | object[] | nested_fields | RepeaterEditor | `{% for item in field.value %}` |
| 关联 | `relation` | number \| number[] | exists_check | RelationPicker | `{{ field.value }}` |

---

## 四、API 设计（冻结）

### 4.1 后台管理 API（需 admin 权限）

#### Content Types

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/cms/content-types` | 列表 |
| POST | `/api/v1/cms/content-types` | 创建 |
| PATCH | `/api/v1/cms/content-types/{id}` | 更新 |
| DELETE | `/api/v1/cms/content-types/{id}` | 软删 |

#### Field Groups

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/cms/content-types/{id}/field-groups` | 列表 |
| POST | `/api/v1/cms/content-types/{id}/field-groups` | 创建 |
| PATCH | `/api/v1/cms/content-types/{id}/field-groups/{gid}` | 更新 |
| DELETE | `/api/v1/cms/content-types/{id}/field-groups/{gid}` | 删除 |

#### Field Definitions

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/cms/content-types/{id}/field-definitions` | 列表（含分组） |
| POST | `/api/v1/cms/content-types/{id}/field-definitions` | 创建 |
| PATCH | `/api/v1/cms/field-definitions/{id}` | 更新 |
| DELETE | `/api/v1/cms/field-definitions/{id}` | 删除 |
| POST | `/api/v1/cms/content-types/{id}/field-definitions/reorder` | 排序 |

#### Field Options

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/cms/field-definitions/{id}/options` | 列表 |
| POST | `/api/v1/cms/field-options` | 创建 |
| PATCH | `/api/v1/cms/field-options/{id}` | 更新 |
| DELETE | `/api/v1/cms/field-options/{id}` | 删除 |

#### Categories

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/cms/categories?content_type=product&parent=` | 树/列表 |
| POST | `/api/v1/cms/categories` | 创建 |
| PATCH | `/api/v1/cms/categories/{id}` | 更新 |
| DELETE | `/api/v1/cms/categories/{id}` | 软删 + 检查引用 |
| POST | `/api/v1/cms/categories/reorder` | 拖拽排序 |

#### Tags

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/cms/tags?content_type=product` | 列表 |
| POST | `/api/v1/cms/tags` | 创建 |
| PATCH | `/api/v1/cms/tags/{id}` | 更新 |
| DELETE | `/api/v1/cms/tags/{id}` | 删除 |

#### Entries（通用内容 CRUD）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/cms/entries?content_type=product&category=&tag=&custom.<field_key>=` | 列表 |
| POST | `/api/v1/cms/entries` | 创建（接受 custom_fields） |
| GET | `/api/v1/cms/entries/{id}` | 详情 |
| PATCH | `/api/v1/cms/entries/{id}` | 更新 |
| DELETE | `/api/v1/cms/entries/{id}` | 软删 |
| POST | `/api/v1/cms/entries/batch-delete` | 批量删除 |
| POST | `/api/v1/cms/entries/batch-status` | 批量改状态 |
| GET | `/api/v1/cms/entries/export?content_type=product` | CSV 导出 |

#### 兼容旧路由（过渡期保留）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/cms/products` | → 转发到 entries?content_type=product |
| POST | `/api/v1/cms/products` | → 转发到 entries |
| ... | 同理 cases / news | |

### 4.2 公共 API（前台用）

#### 内容查询

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/public/site/{content_type}?line=&category=&tag=&page=` | 内容列表 |
| GET | `/api/v1/public/site/{content_type}/{id_or_slug}` | 内容详情 |
| GET | `/api/v1/public/categories?content_type=product` | 分类列表 |
| GET | `/api/v1/public/tags?content_type=product` | 标签列表 |
| GET | `/api/v1/public/field-definitions?content_type=product` | 字段定义（供前台渲染动态字段） |

#### 前台用户 Auth

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/public/portal/auth/register` | 注册 |
| POST | `/api/v1/public/portal/auth/login` | 登录 |
| POST | `/api/v1/public/portal/auth/refresh` | 刷新 Token |
| POST | `/api/v1/public/portal/auth/forgot-password` | 忘记密码 |
| POST | `/api/v1/public/portal/auth/reset-password` | 重置密码 |
| GET | `/api/v1/public/portal/me` | 当前用户 |
| PATCH | `/api/v1/public/portal/me` | 更新 Profile |
| POST | `/api/v1/public/portal/auth/change-password` | 改密码 |

#### 前台用户 OAuth

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/public/portal/auth/feishu/authorize` | 飞书授权跳转 |
| GET | `/api/v1/public/portal/auth/feishu/callback` | 飞书回调 |

---

## 五、App 中心扩展（冻结）

### AppManifest 扩展字段

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

    # 扩展字段：
    content_types: list[dict] = field(default_factory=list)
    # 例：[{"key":"product","name":"产品","default_template":"..."}]

    field_groups: list[dict] = field(default_factory=list)
    # 例：[{"key":"basic","label":"基础信息"}, {"key":"specs","label":"技术规格"}]

    field_definitions: list[dict] = field(default_factory=list)
    # 例：[{"key":"price","label":"价格","type":"number","group":"specs"}]

    categories_seed: list[dict] = field(default_factory=list)
    # 初始分类（首次安装时种入）

    public_routes_prefix: str = ""
    # 公共 API 路由前缀
```

### InstalledApp 表扩展

```sql
ALTER TABLE platform_apps ADD COLUMN permissions_grants JSONB DEFAULT '{}'::jsonb;
-- 委派权限给其他角色，例：{"content_editor": ["cms:field:read", "cms:field:write"]}
```

### 启动行为变更

- 启动时扫描所有 app manifest，自动注册 content_types / field_groups / field_definitions 到 DB
- 首次安装时种入 categories_seed 数据
- App 中心 UI 支持超管分配「字段管理权」给角色

---

## 六、Liquid 模板契约（冻结）

### 基础语法

```liquid
{{ var }}                             变量插值
{{ var | filter }}                    过滤器
{{ var | default: 'fallback' }}       默认值
```

### 流程控制

```liquid
{% if condition %}...{% endif %}
{% if condition %}...{% elsif %}...{% else %}...{% endif %}
{% for x in collection %}...{% endfor %}
```

### 内置 filters

| filter | 用法 | 说明 |
|--------|------|------|
| upcase | `{{ str \| upcase }}` | 大写 |
| downcase | `{{ str \| downcase }}` | 小写 |
| truncate | `{{ str \| truncate: 100 }}` | 截断 |
| append | `{{ str \| append: '...' }}` | 追加 |
| date | `{{ date \| date: '%Y-%m-%d' }}` | 日期格式化 |
| currency | `{{ num \| currency }}` | 货币格式 |
| markdown | `{{ str \| markdown }}` | Markdown → HTML |
| strip_html | `{{ str \| strip_html }}` | 去 HTML |
| json | `{{ obj \| json }}` | 序列化 |
| join | `{{ arr \| join: ', ' }}` | 数组合并 |
| size | `{{ arr \| size }}` | 数组长度 |

### 自定义 filters（业务）

| filter | 用法 | 说明 |
|--------|------|------|
| t | `{{ product.line \| t }}` | i18n 翻译（业务线中文名） |
| format_price | `{{ product.custom_fields.price \| format_price }}` | 价格格式化 |
| first | `{{ product.custom_fields.screenshots \| first }}` | 取首元素 |

### 前端集成

- 库：liquidjs（~30KB）
- 封装：`window.cmsRender(template, data)`
- 全局变量注入：`now`、`site`、`theme`

### 后端渲染 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/cms/templates/render` | 服务端模板预览 |
| POST | `/api/v1/cms/templates/validate` | 模板语法校验 |

---

## 七、执行时间表（冻结）

### 总览

| 周 | 轨道 1：CMS 增强 | 轨道 2：安全整改 | 轨道 3：底座演进 |
|----|-------------------|------------------|------------------|
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

---

### W1 详细任务清单

#### M1-A：数据库模型 + Alembic 迁移（W1 前 3 天）

- [ ] **1.1** 创建 `cms_content_types` 模型 → `backend/src/cenkor_admin/apps/cms/models.py`
- [ ] **1.2** 创建 `cms_field_groups` 模型 → 同上
- [ ] **1.3** 创建 `cms_field_definitions` 模型 → 同上
- [ ] **1.4** 创建 `cms_field_options` 模型 → 同上
- [ ] **1.5** 创建 `cms_entries` 通用内容表模型 → 同上
- [ ] **1.6** 创建 `cms_categories` 模型（3+ 级自引用） → 同上
- [ ] **1.7** 创建 `cms_tags` 模型 → 同上
- [ ] **1.8** 创建 `cms_content_tags` 多对多关联模型 → 同上
- [ ] **1.9** 现有 Product/Case/News 加 `custom_fields JSONB` → 同上
- [ ] **1.10** 创建 `portal_users` 模型 → `backend/src/cenkor_admin/apps/portal/models.py`（新建）
- [ ] **1.11** 创建 `portal_user_oauth` 模型 → 同上
- [ ] **1.12** auth_users 加 `user_type` 字段 → `backend/src/cenkor_admin/apps/auth/models.py`
- [ ] **1.13** 创建 `FIELD_TYPES` 枚举 + 校验规则映射 → `backend/src/cenkor_admin/apps/cms/field_types.py`（新建）
- [ ] **1.14** 生成 Alembic 迁移 → `backend/alembic/versions/xxx_content_engine_and_portal.py`
- [ ] **1.15** 执行迁移并验证 → `alembic upgrade head`
- [ ] **1.16** 创建 portal app 目录 → `backend/src/cenkor_admin/apps/portal/__init__.py`

#### M1-B：字段管理 API + Schemas（W1 后 2 天）

- [ ] **2.1** Content Types CRUD schemas → `backend/src/cenkor_admin/apps/cms/schemas.py`
- [ ] **2.2** Content Types CRUD API 路由 → `backend/src/cenkor_admin/apps/cms/router.py`
- [ ] **2.3** Field Groups CRUD schemas + API → 同上
- [ ] **2.4** Field Definitions CRUD + Reorder schemas + API → 同上
- [ ] **2.5** Field Options CRUD schemas + API → 同上
- [ ] **2.6** 注册新路由到 `/api/v1/` → `backend/src/cenkor_admin/api/v1/__init__.py`
- [ ] **2.7** 权限点种子数据（cms:content-type:*, cms:field:*, cms:category:*, cms:tag:*） → `backend/src/cenkor_admin/scripts/seed.py`

---

### W2 详细任务清单

#### 后台 UI：字段定义管理页面

- [ ] **3.1** ContentTypeListView.vue → `frontend/admin-web/src/views/cms/ContentTypeListView.vue`
- [ ] **3.2** ContentTypeEditView.vue → `frontend/admin-web/src/views/cms/ContentTypeEditView.vue`
- [ ] **3.3** FieldDefinitionsView.vue（含分组 tabs + 拖拽排序） → `frontend/admin-web/src/views/cms/FieldDefinitionsView.vue`
- [ ] **3.4** DynamicFieldRenderer.vue（20 种字段类型渲染） → `frontend/admin-web/src/components/cms/DynamicFieldRenderer.vue`
- [ ] **3.5** FieldOptionEditor.vue（select/multiselect 候选项编辑） → `frontend/admin-web/src/components/cms/FieldOptionEditor.vue`
- [ ] **3.6** 注册路由 + 菜单项 → `frontend/admin-web/src/router/index.ts`

---

### W3 详细任务清单

#### M2-A：分类系统

- [ ] **4.1** Categories CRUD API（含树形查询） → `backend/src/cenkor_admin/apps/cms/router.py`
- [ ] **4.2** Categories Reorder API → 同上
- [ ] **4.3** Tags CRUD API → 同上
- [ ] **4.4** Category schemas（含树形响应） → `backend/src/cenkor_admin/apps/cms/schemas.py`
- [ ] **4.5** 后台 UI：CategoryManager.vue（TreeSelect，3+ 级拖拽） → `frontend/admin-web/src/components/cms/CategoryManager.vue`
- [ ] **4.6** 后台 UI：TagManager.vue（颜色选择器） → `frontend/admin-web/src/components/cms/TagManager.vue`
- [ ] **4.7** 公共 API：`GET /api/v1/public/categories` + `GET /api/v1/public/tags` → `backend/src/cenkor_admin/apps/cms/public_router.py`
- [ ] **4.8** Manifest 扩展：AppManifest 加 content_types / field_groups / field_definitions / categories_seed → `backend/src/cenkor_admin/apps/base.py`

---

### W4 详细任务清单

#### M2-B：通用内容接入 + 数据迁移

- [ ] **5.1** 通用内容 CRUD API（`/api/v1/cms/entries`） → `backend/src/cenkor_admin/apps/cms/router.py`
- [ ] **5.2** 内容搜索/过滤（按 category / tag / custom.<field_key>） → 同上
- [ ] **5.3** Entry schemas（含 custom_fields 动态字段） → `backend/src/cenkor_admin/apps/cms/schemas.py`
- [ ] **5.4** 数据迁移脚本（products/cases/news → cms_entries） → `backend/src/cenkor_admin/scripts/migrate_to_entries.py`（新建）
- [ ] **5.5** 兼容旧路由（/cms/products → 转发到 entries?content_type=product） → `backend/src/cenkor_admin/apps/cms/router.py`
- [ ] **5.6** 后台 UI：EntryListView.vue（通用内容列表） → `frontend/admin-web/src/views/cms/EntryListView.vue`
- [ ] **5.7** 后台 UI：EntryEditView.vue（DynamicFieldRenderer 驱动） → `frontend/admin-web/src/views/cms/EntryEditView.vue`
- [ ] **5.8** InstalledApp 加 permissions_grants JSONB → `backend/src/cenkor_admin/apps/system/models.py`

---

### W5 详细任务清单

#### M3-A：公共 API 网关

- [ ] **6.1** `GET /api/v1/public/site/{content_type}` 列表查询 → `backend/src/cenkor_admin/apps/cms/public_router.py`
- [ ] **6.2** `GET /api/v1/public/site/{content_type}/{id_or_slug}` 详情查询 → 同上
- [ ] **6.3** `GET /api/v1/public/field-definitions` 字段定义 → 同上
- [ ] **6.4** Portal Auth API：register / login / refresh → `backend/src/cenkor_admin/apps/portal/router.py`（新建）
- [ ] **6.5** Portal Auth API：forgot-password / reset-password → 同上
- [ ] **6.6** Portal Auth API：me / profile / change-password → 同上
- [ ] **6.7** Portal JWT 独立签发（不同 issuer / 不同 SECRET） → `backend/src/cenkor_admin/apps/portal/security.py`（新建）
- [ ] **6.8** 路由级隔离中间件（portal token 禁止访问 /api/v1/cms/ 等后台路由） → `backend/src/cenkor_admin/core/security.py`
- [ ] **6.9** 注册 portal 路由到 /api/v1/public/portal/ → `backend/src/cenkor_admin/api/v1/__init__.py`
- [ ] **6.10** FieldRegistry 抽象（统一管理字段类型注册/校验/渲染） → `backend/src/cenkor_admin/apps/cms/field_registry.py`（新建）

---

### W6 详细任务清单

#### M3-B：Liquid 模板引擎集成

- [ ] **7.1** 后端 Python Liquid 引擎封装 → `backend/src/cenkor_admin/core/template_engine.py`（新建）
- [ ] **7.2** 内置 filters 实现 → 同上
- [ ] **7.3** 自定义业务 filters（t, format_price, first） → 同上
- [ ] **7.4** `POST /api/v1/cms/templates/render` 预览 API → `backend/src/cenkor_admin/apps/cms/router.py`
- [ ] **7.5** `POST /api/v1/cms/templates/validate` 校验 API → 同上
- [ ] **7.6** 前端：安装 liquidjs → `frontend/portal-web/package.json`
- [ ] **7.7** 前端：`window.cmsRender(template, data)` 封装 → `frontend/portal-web/src/lib/cms-render.ts`（新建）
- [ ] **7.8** 前端：全局变量注入（now, site, theme） → 同上
- [ ] **7.9** portal-web：公共内容页（产品列表/详情、案例、新闻） → `frontend/portal-web/src/views/`

---

### W7 详细任务清单

#### 网站静态页改造

- [ ] **8.1** portal-web：首页模板 → `frontend/portal-web/src/views/HomeView.vue`
- [ ] **8.2** portal-web：产品列表/详情页 → `frontend/portal-web/src/views/ProductListView.vue` / `ProductDetailView.vue`
- [ ] **8.3** portal-web：案例列表/详情页 → `frontend/portal-web/src/views/CaseListView.vue` / `CaseDetailView.vue`
- [ ] **8.4** portal-web：新闻列表/详情页 → `frontend/portal-web/src/views/NewsListView.vue` / `NewsDetailView.vue`
- [ ] **8.5** portal-web：通用布局 + 导航 → `frontend/portal-web/src/layouts/`
- [ ] **8.6** App 中心 UI：字段管理权分配 → `frontend/admin-web/src/views/system/AppsView.vue`

---

### W8 详细任务清单

#### 测试 + 文档

- [ ] **9.1** 后端单元测试：字段定义 CRUD → `tests/`
- [ ] **9.2** 后端单元测试：分类标签 CRUD → `tests/`
- [ ] **9.3** 后端单元测试：通用内容 CRUD + custom_fields → `tests/`
- [ ] **9.4** 后端单元测试：公共 API → `tests/`
- [ ] **9.5** 后端单元测试：Portal Auth → `tests/`
- [ ] **9.6** 后端单元测试：Liquid 模板渲染 → `tests/`
- [ ] **9.7** E2E 测试：后台完整流程 → `tests/e2e/`
- [ ] **9.8** 性能测试：1000+ 条目查询 → `tests/perf/`
- [ ] **9.9** 更新 ARCHITECTURE.md → `ARCHITECTURE.md`
- [ ] **9.10** 更新 API 文档 → OpenAPI auto-generated

---

### W9 详细任务清单

#### 用户体系拆分

- [ ] **10.1** portal_users 后台管理 API（管理员 CRUD 前台用户） → `backend/src/cenkor_admin/apps/portal/router.py`
- [ ] **10.2** portal_user_oauth 绑定/解绑 API → 同上
- [ ] **10.3** 路由级隔离验证测试 → `tests/`
- [ ] **10.4** portal-web 改造：注册/登录 API 切换到 portal 路由 → `frontend/portal-web/src/views/`
- [ ] **10.5** portal-web 改造：auth store 适配 portal token → `frontend/portal-web/src/stores/auth.ts`
- [ ] **10.6** 现有 auth register 接口标记为 internal（不再公开） → `backend/src/cenkor_admin/apps/auth/router.py`
- [ ] **10.7** 后台 UI：前台用户管理页 → `frontend/admin-web/src/views/system/PortalUsersView.vue`
- [ ] **10.8** 种子数据：portal_users 相关权限点 → `backend/src/cenkor_admin/scripts/seed.py`

---

### W10 详细任务清单

#### 联调 + 上线

- [ ] **11.1** 全链路 E2E 测试（后台 → 公共 API → portal-web） → `tests/e2e/`
- [ ] **11.2** 数据迁移完整演练（生产数据 → cms_entries） → `scripts/`
- [ ] **11.3** Docker Compose 构建验证 → `docker-compose.yml`
- [ ] **11.4** 宝塔部署验证 → `deploy/`
- [ ] **11.5** 性能基准测试 → `tests/perf/`
- [ ] **11.6** 安全审计（密钥轮换 / 目录隔离 / API 限流） → `docs/`
- [ ] **11.7** 更新所有文档 → `docs/`
- [ ] **11.8** 正式上线 → 🎉

---

## 八、新增文件清单

### 后端新增文件

| 文件路径 | 说明 |
|----------|------|
| `backend/src/cenkor_admin/apps/cms/field_types.py` | 字段类型枚举 + 校验规则 |
| `backend/src/cenkor_admin/apps/cms/field_registry.py` | 字段类型注册中心 |
| `backend/src/cenkor_admin/apps/portal/__init__.py` | Portal App 入口 |
| `backend/src/cenkor_admin/apps/portal/models.py` | PortalUser + PortalUserOAuth |
| `backend/src/cenkor_admin/apps/portal/router.py` | Portal Auth + 管理 API |
| `backend/src/cenkor_admin/apps/portal/schemas.py` | Portal Pydantic schemas |
| `backend/src/cenkor_admin/apps/portal/security.py` | Portal JWT 独立签发 |
| `backend/src/cenkor_admin/apps/portal/manifest.py` | Portal App Manifest |
| `backend/src/cenkor_admin/core/template_engine.py` | Liquid 模板引擎封装 |
| `backend/src/cenkor_admin/scripts/migrate_to_entries.py` | 数据迁移脚本 |
| `backend/alembic/versions/xxx_content_engine_and_portal.py` | Alembic 迁移 |

### 前端新增文件（admin-web）

| 文件路径 | 说明 |
|----------|------|
| `frontend/admin-web/src/views/cms/ContentTypeListView.vue` | 内容类型列表 |
| `frontend/admin-web/src/views/cms/ContentTypeEditView.vue` | 内容类型编辑 |
| `frontend/admin-web/src/views/cms/FieldDefinitionsView.vue` | 字段定义编辑器 |
| `frontend/admin-web/src/views/cms/EntryListView.vue` | 通用内容列表 |
| `frontend/admin-web/src/views/cms/EntryEditView.vue` | 通用内容编辑 |
| `frontend/admin-web/src/components/cms/DynamicFieldRenderer.vue` | 动态字段渲染 |
| `frontend/admin-web/src/components/cms/FieldOptionEditor.vue` | 字段选项编辑 |
| `frontend/admin-web/src/components/cms/CategoryManager.vue` | 分类管理器 |
| `frontend/admin-web/src/components/cms/TagManager.vue` | 标签管理器 |
| `frontend/admin-web/src/views/system/PortalUsersView.vue` | 前台用户管理 |

### 前端新增文件（portal-web）

| 文件路径 | 说明 |
|----------|------|
| `frontend/portal-web/src/lib/cms-render.ts` | Liquid 渲染封装 |
| `frontend/portal-web/src/views/HomeView.vue` | 首页 |
| `frontend/portal-web/src/views/ProductListView.vue` | 产品列表 |
| `frontend/portal-web/src/views/ProductDetailView.vue` | 产品详情 |
| `frontend/portal-web/src/views/CaseListView.vue` | 案例列表 |
| `frontend/portal-web/src/views/CaseDetailView.vue` | 案例详情 |
| `frontend/portal-web/src/views/NewsListView.vue` | 新闻列表 |
| `frontend/portal-web/src/views/NewsDetailView.vue` | 新闻详情 |
| `frontend/portal-web/src/layouts/PortalLayout.vue` | 前台布局 |

---

## 九、修改文件清单

### 后端修改文件

| 文件路径 | 变更内容 |
|----------|----------|
| `backend/src/cenkor_admin/apps/cms/models.py` | 新增 7 个模型 + 现有模型加 custom_fields |
| `backend/src/cenkor_admin/apps/cms/router.py` | 新增字段/分类/标签/内容路由 |
| `backend/src/cenkor_admin/apps/cms/schemas.py` | 新增字段/分类/标签/内容 schemas |
| `backend/src/cenkor_admin/apps/cms/public_router.py` | 新增公共查询 API |
| `backend/src/cenkor_admin/apps/cms/manifest.py` | Manifest 扩展 content_types 等 |
| `backend/src/cenkor_admin/apps/auth/models.py` | auth_users 加 user_type |
| `backend/src/cenkor_admin/apps/base.py` | AppManifest 扩展字段 |
| `backend/src/cenkor_admin/apps/system/models.py` | InstalledApp 加 permissions_grants |
| `backend/src/cenkor_admin/core/security.py` | 路由级隔离中间件 |
| `backend/src/cenkor_admin/api/v1/__init__.py` | 注册新路由 |
| `backend/src/cenkor_admin/scripts/seed.py` | 新增种子数据 |

### 前端修改文件（admin-web）

| 文件路径 | 变更内容 |
|----------|----------|
| `frontend/admin-web/src/router/index.ts` | 新增路由 + 菜单 |
| `frontend/admin-web/src/views/system/AppsView.vue` | App 中心 UI 增强 |

### 前端修改文件（portal-web）

| 文件路径 | 变更内容 |
|----------|----------|
| `frontend/portal-web/src/router/index.ts` | 新增公共内容页路由 |
| `frontend/portal-web/src/stores/auth.ts` | 适配 portal token |
| `frontend/portal-web/src/views/LoginView.vue` | API 切换到 portal 路由 |
| `frontend/portal-web/src/views/RegisterView.vue` | API 切换到 portal 路由 |
| `frontend/portal-web/package.json` | 加 liquidjs 依赖 |

---

## 十、风险与注意事项

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 数据迁移丢失 | 高 | 迁移前全量备份；迁移脚本幂等；迁移后校验条数 |
| 旧 API 兼容性 | 中 | 过渡期保留旧路由，转发到新通用 API |
| custom_fields 查询性能 | 中 | GIN 索引；常用过滤字段可提升为独立列 |
| Liquid 模板注入 | 高 | 沙箱模式；禁止任意 Python 执行 |
| Portal JWT 泄露访问后台 | 高 | 不同 issuer + 中间件强制校验 |
| 前后台用户混淆 | 高 | 完全隔离表 + 路由前缀 + JWT issuer 差异 |
