# Cenkor Admin Platform — 架构与技术选型

> 一个生产级、可私有化、**应用中心驱动的**企业管理后台底座。
> 第一个落地应用：**辰科官网 CMS**。

| 项 | 值 |
|----|---|
| **目标** | 替代/升级现有 KeleAdmin (PHP) 栈，用 FastAPI + Vue3 重建 |
| **首期应用** | 辰科官网 CMS（管理产品/案例/新闻/媒体/站点配置）|
| **核心创新** | 应用中心（App Center）—— 业务功能模块化为可插拔的"App" |
| **栈一致性** | 复用现有 LightMes / BizCloud / OpenAI 网关 的 FastAPI + Vue3 |
| **设计语言** | 复用 `/www/wwwroot/website/` 的 OKLCH + Plus Jakarta Sans + Bento |

---

## 1. 目标与边界

### 1.1 在做什么

```
┌─────────────────────────────────────────────────────────────┐
│                      Cenkor Admin Platform                  │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────┐ │
│  │  用户中心  │ │  权限中心  │ │  应用中心  │ │ 审计日志 │ │
│  └────────────┘ └────────────┘ └────────────┘ └──────────┘ │
│  ┌──────────────────────────────────────────────────────┐  │
│  │   App: 辰科官网 CMS   App: 待定2   App: 待定3         │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 显式不做什么（MVP 阶段）

- ❌ 工作流引擎（PlantFlow 已独立）
- ❌ 复杂报表 / BI（用 Metabase 等替代）
- ❌ 消息推送通道实现（先用 Webhook + 数据库标记）
- ❌ 多租户**完全数据隔离**（先做软隔离：tenant_id 字段；硬隔离留到 Phase 3）
- ❌ SSO（先用账号密码 + 飞书扫码）

### 1.3 关键非功能需求

| 维度 | 目标 |
|------|------|
| **可用** | 99.9%（< 8.7 小时/年 downtime）|
| **P99 接口延迟** | < 300ms（不含外部依赖）|
| **数据备份** | RPO ≤ 1 小时，RTO ≤ 4 小时 |
| **部署** | 单机 Docker Compose → 后续 K8s |
| **审计** | 关键操作 100% 留痕 |
| **私有化** | 单镜像离线部署，外部依赖最小化 |

---

## 2. 整体架构

### 2.1 部署拓扑

```
                    ┌─────────────────┐
                    │   Nginx (LB)    │
                    │  静态 + 反代     │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
       ┌──────▼──────┐ ┌─────▼──────┐ ┌─────▼──────┐
       │  admin-web  │ │   api      │ │   api      │
       │   (Vue3)    │ │  (FastAPI) │ │  (FastAPI) │
       │  Port 8080  │ │  Port 8000 │ │  Port 8001 │
       └─────────────┘ └─────┬──────┘ └─────┬──────┘
                             │              │
              ┌──────────────┴──────────────┴─────┐
              │                                   │
       ┌──────▼───────┐  ┌──────────┐  ┌──────────▼──┐
       │ PostgreSQL   │  │  Redis   │  │   MinIO     │
       │   16         │  │  7       │  │  (S3 兼容)  │
       └──────────────┘  └──────────┘  └─────────────┘
```

**两套前端**（共用设计系统）：
1. **admin-web** —— 后台（B 端），深色 + 侧边栏
2. **portal-web** —— 用户中心（C 端），浅色 + 顶部导航
3. **公网站点** —— 现有 `/www/wwwroot/website/`，**通过 CMS API 拿数据**（不是另建一套）

### 2.2 后端架构（FastAPI 分层）

```
HTTP Request
    ↓
[ Middleware: 鉴权 / 限流 / 请求日志 / CORS ]
    ↓
[ Router: 按 App 分组注册 ]
    ↓
[ Service: 业务逻辑（事务、跨表）]
    ↓
[ Repository: 数据访问（SQLAlchemy 2.0 async）]
    ↓
[ Model: ORM 实体 ]
    ↓
PostgreSQL / Redis / MinIO
```

**关键设计**：
- **App 模块化**：每个 App 是一个 Python package，目录 `apps/{app_name}/`，包含 `router.py` / `service.py` / `models.py` / `schemas.py` / `frontend/`（前端模块）
- **Plugin 机制**：`AppManifest` 描述元数据，应用启动时扫描 + 数据库校验已安装 App
- **依赖注入**：FastAPI Depends 统一注入 `db` / `current_user` / `tenant` / `permissions`

### 2.3 前端架构（Vue 3）

```
admin-web/
├── src/
│   ├── apps/                      ← App 目录（与后端对应）
│   │   └── cms/
│   │       ├── routes.ts
│   │       ├── views/
│   │       └── components/
│   ├── core/                      ← 平台核心（不可被 App 覆盖）
│   │   ├── layout/                ← 侧边栏 / 顶栏 / 面包屑
│   │   ├── auth/
│   │   ├── api/                   ← Axios + interceptors
│   │   ├── components/            ← 通用组件（Table / Form / Dialog）
│   │   ├── composables/
│   │   ├── stores/                ← Pinia
│   │   └── styles/                ← 共享设计 token
│   ├── router/
│   └── main.ts
```

**App 动态加载**：
- 后端返回 `GET /api/apps/installed` → 已装 App 列表
- 前端根据 manifest 注册路由
- 用户中心（C 端）走另一套路由，但共享 `core/` 和 `styles/`

---

## 3. 技术选型（含理由）

### 3.1 后端

| 技术 | 版本 | 选它/不选它的理由 |
|------|------|------------------|
| **Python** | 3.11+ | 性能提升、原生 async、错误信息友好。**选** |
| **FastAPI** | 0.110+ | 异步、OpenAPI 自动生成、Pydantic 集成、TS-like 类型。**选** |
| **Django** | — | 太重，admin 是它强项但耦合 ORM/模板/表单。**不选** |
| **Flask** | — | 同步为主、扩展分散。**不选** |
| **NestJS** | — | 优秀，但跟你 FastAPI 栈分叉。**不选** |
| **SQLAlchemy** | 2.0+ async | 成熟、Async 完善、关系映射强大。**选** |
| **Tortoise ORM** | — | 也不错，但生态比 SQLAlchemy 小。**不选** |
| **Pydantic** | v2 | 性能 5-50x v1、严格模式。**选** |
| **Alembic** | — | SQLAlchemy 官方迁移工具。**选** |
| **PostgreSQL** | 16 | JSONB / GIN 索引 / 部分索引 / Row-Level Security。**选** |
| **MySQL** | — | 也能用，但 PG 的 JSONB/RLS/数组更适合 CMS 这种半结构化数据。**不选** |
| **Redis** | 7 | 缓存 + Celery broker + 限流计数器。**选** |
| **Celery** | — | 任务队列成熟。**选**。**不用** dramatiq/arq（生态） |
| **MinIO** | latest | S3 兼容、自托管、文件存储。**选** |
| **JWT** | python-jose | access + refresh 双 token。**选** |
| **passlib[bcrypt]** | — | 密码哈希。**选** |
| **structlog** | — | 结构化日志，便于 ELK 聚合。**选** |
| **Prometheus + Grafana** | — | 监控标配。**选**（后期） |

### 3.2 前端（Admin Web）

| 技术 | 版本 | 选它/不选它的理由 |
|------|------|------------------|
| **Vue** | 3.4+ | 你的栈、Composition API + `<script setup>` 现代化。**选** |
| **React** | — | PlantFlow 用了，但分散。**不选**（保持栈一致） |
| **Vite** | 5+ | 启动快、HMR 优秀。**选** |
| **TypeScript** | 5+ | 类型安全、IDE 体验。**选** |
| **Pinia** | 2+ | 状态管理。**选** |
| **Vue Router** | 4 | 官方路由。**选** |
| **shadcn-vue** | — | 可复制粘贴的组件、Radix Vue 底子、**设计自由度高**。**选** |
| Element Plus | — | 中后台成熟但视觉偏"中"——和官网 OKLCH 调性冲突。**不选** |
| Ant Design Vue | — | 同上。**不选** |
| **TanStack Query (Vue Query)** | 5 | 缓存/重试/失效、数据驱动。**选** |
| **VeeValidate + Zod** | — | 表单 + schema 校验、TS 友好。**选** |
| **vue-i18n** | 9 | 多语言。**选** |
| **Tailwind CSS** | 3 | 与官网同源、设计 token 共享。**选** |
| **ECharts** | 5 | 图表。**选** |
| **unplugin-vue-components** | — | 按需自动引入。**选** |
| **Day.js** | — | 轻量时间。**选** |
| **Vitest** | — | 单元测试。**选** |
| **Playwright** | — | E2E 测试。**选** |

### 3.3 DevOps / 工具

| 用途 | 选型 |
|------|------|
| **容器化** | Docker + Docker Compose（先）/ K8s（后期） |
| **CI/CD** | GitHub Actions |
| **包管理** | Poetry (后端) / pnpm (前端) |
| **代码规范** | Ruff (py) / ESLint + Prettier (vue) |
| **类型检查** | mypy strict (py) / tsc strict (vue) |
| **pre-commit** | 是 |
| **文档** | MkDocs Material（部署到 docs.cenkor.cn） |
| **API 文档** | FastAPI 自带 `/docs`（Swagger UI） |
| **依赖扫描** | Trivy / Dependabot |
| **Secrets** | .env（dev）→ 1Password CLI / HashiCorp Vault（prod） |

---

## 4. 核心模块设计

### 4.1 鉴权 & 用户

**双 Token 模型**：
```
access_token:  15 min, JWT, 含 user_id / roles / permissions
refresh_token: 7 day, JWT, 仅含 user_id + token_version
```

**Token 旋转**：每次 refresh 旧 refresh token 失效（token_version++）。
**撤销**：登出时只增加 token_version；紧急情况支持黑名单（Redis SET）。

**用户字段**：
```
id, tenant_id, username, email, phone, password_hash,
avatar, nickname, status (active/disabled/locked),
last_login_at, last_login_ip, created_at, updated_at,
deleted_at (软删)
```

**登录方式（MVP）**：
1. 账号 + 密码（必选）
2. 飞书 OAuth 授权（推荐办公场景）
3. 企业微信 OAuth（私企偏好）
4. 邮箱验证码（找回密码）

### 4.2 RBAC（角色权限）

**核心模型**：
```
User ─< UserRole >─ Role ─< RolePermission >─ Permission
                                       │
                                       └─ 关联到 Menu / API
```

**Permission 设计**：
- `code` 字段：人类可读，如 `cms:product:create`
- `type` 字段：`menu` / `api` / `data` / `ui`
- 支持通配：`cms:product:*` 包含 `cms:product:create` / `read` / `update` / `delete`
- 后端中间件校验；前端 `<HasPermission code="...">` 组件控制显示

**Permission 缓存**：登录后写入 Redis `user:{id}:permissions`（SET），过期 1h 或主动失效。

### 4.3 多租户（Phase 3 完整版）

**MVP 阶段**：单租户模式（tenant_id 恒为 1），所有表带 `tenant_id` 字段但不强校验。
**Phase 3 完整版**：
- **共享数据库，共享 schema，列隔离**（`tenant_id` 列 + Row-Level Security）
- **数据库级隔离**（每租户一个 schema / 一个 database）—— **不选**，运维成本太高
- 租户切换：登录后选租户，token 里带 `current_tenant_id`

### 4.4 应用中心（核心创新）

**设计目标**：业务功能模块化，新增功能 = 新增一个 App 包，平台零改动。

**App Manifest（YAML 或 DB 存）**：
```yaml
key: cms
name: 辰科官网 CMS
version: 1.0.0
author: Cenkor
description: 官网内容管理
icon: 📰
min_platform_version: 1.0.0
dependencies: []          # 依赖其他 app
permissions_required:    # 安装时申请的权限
  - cms:product:*
  - cms:case:*
  - cms:news:*
  - media:upload
menus:                    # 自动注册到后台菜单
  - path: /cms/products
    title: 产品管理
    icon: package
    parent: content
  - path: /cms/cases
    title: 案例管理
    parent: content
```

**加载机制**：
1. **后端启动**：扫描 `apps/` 目录，读取每个 App 的 `manifest.py`，与 DB `apps` 表对比
2. **DB 已有但代码没有** → 标记 "missing"
3. **代码有但 DB 没有** → 标 "not_installed"
4. **都匹配但版本不同** → 标 "needs_upgrade"
5. **路由注册**：用 `app.include_router()` 在 startup 时按状态注册

**App 内目录约定**：
```
apps/cms/
├── manifest.py            ← 元数据
├── __init__.py
├── router.py              ← FastAPI APIRouter
├── service.py
├── models.py              ← SQLAlchemy
├── schemas.py             ← Pydantic
├── migrations/            ← Alembic
└── frontend/              ← 前端模块（独立打包或 monorepo）
    ├── routes.ts
    ├── views/
    └── components/
```

**安装流程（管理员操作）**：
1. 上传 App 包（zip / git URL）
2. 平台读取 manifest，展示权限申请清单
3. 管理员确认 → 执行 `app install`：
   - 跑 migrations
   - 初始化默认数据
   - 注册菜单 / 权限
   - 写入 `apps` 表 `installed_at`
4. 卸载：反向操作，软删（标记 uninstalled_at）

### 4.5 审计日志

**记录维度**：
```
user_id, tenant_id, app_key, action (create/read/update/delete/login/...),
resource_type, resource_id, request_id, ip, user_agent,
status (success/failure), error_code, duration_ms,
diff (JSON, 变更前后), created_at
```

**存储**：PostgreSQL 分区表（按月分区），保留 1 年（可配置）。
**查询**：admin 提供筛选 UI（按用户/时间/App/资源）。
**导出**：CSV / JSON。

### 4.6 通知 / 站内信（MVP 简化版）

- 站内消息表 + WebSocket 推送（FastAPI + WebSocket）
- 邮件发送：异步（Celery）调用 SMTP
- 短信 / 微信 / 飞书 webhook：留扩展点

### 4.7 文件存储（MinIO）

- **公开桶**：`cenkor-public`（网站图片，公开读）
- **私有桶**：`cenkor-private`（用户头像、内部文档，预签名 URL 访问）
- 上传走平台代理，不直接暴露 MinIO

---

## 5. 数据模型（关键表）

```sql
-- 用户/认证
users (id, tenant_id, username, email, phone, password_hash, avatar, 
       nickname, status, last_login_at, last_login_ip, created_at, updated_at, deleted_at)
user_oauth (id, user_id, provider, open_id, union_id, access_token_enc, refresh_token_enc, expires_at)

-- RBAC
roles (id, tenant_id, code, name, description, is_system, created_at, updated_at)
permissions (id, code, type, name, description, created_at)
menus (id, parent_id, code, title, icon, path, component, sort, status, type)
role_permissions (role_id, permission_id)
role_menus (role_id, menu_id)
user_roles (user_id, role_id)

-- 应用中心
apps (id, key, version, installed_at, updated_at, status, config_json)
app_dependencies (app_id, depends_on_app_id, min_version)

-- 审计
audit_logs (id, request_id, user_id, tenant_id, app_key, action, resource_type, 
            resource_id, status, ip, user_agent, duration_ms, diff, error_code, created_at)
PRIMARY KEY (id, created_at)  -- 月分区

-- CMS 应用（第一个 App）
products (id, slug, name, tagline, line, stack, desc, features JSONB, 
          sort, status, created_at, updated_at, deleted_at)
cases (id, industry, name, desc, tag, href, sort, status, created_at, updated_at, deleted_at)
news (id, slug, title, excerpt, content_md, cover_image, author_id, 
      published_at, status, view_count, created_at, updated_at, deleted_at)
site_config (id, key, value JSONB, description, updated_by, updated_at)
media (id, bucket, key, url, mime, size, width, height, uploader_id, 
       alt, created_at, deleted_at)

-- 站内消息
notifications (id, user_id, type, title, content, link, read_at, created_at)
```

**索引策略**：
- 软删字段加 `WHERE deleted_at IS NULL` 部分索引
- JSONB 字段加 GIN 索引（features / value）
- 全文搜索（中文）：PG 10+ 的 `to_tsvector('jiebacfg', ...)` 或集成 Meilisearch

---

## 6. API 设计

**RESTful + 资源子集**：
```
GET    /api/{app}/{resource}              列表
POST   /api/{app}/{resource}              创建
GET    /api/{app}/{resource}/{id}         详情
PATCH  /api/{app}/{resource}/{id}         更新
DELETE /api/{app}/{resource}/{id}         删除
POST   /api/{app}/{resource}/{id}/actions  动作（恢复、发布、置顶等）
```

**特殊**：
```
POST   /api/auth/login
POST   /api/auth/refresh
POST   /api/auth/logout
GET    /api/auth/me                       当前用户信息（含 permissions / menus）

GET    /api/apps                          平台 + 已装 App 列表
POST   /api/apps/install
POST   /api/apps/{key}/upgrade
DELETE /api/apps/{key}

GET    /api/admin/users
...
```

**约定**：
- 所有接口 `application/json; charset=utf-8`
- 列表统一返回 `{ items, total, page, page_size }`
- 错误统一 `{ code, message, request_id, details? }`
- 鉴权：除 `/auth/login` 外需 `Authorization: Bearer <access_token>`
- 多租户：`X-Tenant-Id` header（Phase 3）
- 限流：Redis 滑动窗口，按 user_id / ip
- 审计：所有写操作 middleware 记录

**OpenAPI**：FastAPI 自动生成 `/api/openapi.json` + Swagger UI `/api/docs`，前端用 `openapi-typescript-codegen` 生成 TS 类型。

---

## 7. 前端架构

### 7.1 设计 Token 共享

把 `/www/wwwroot/website/input.css` 里的 OKLCH 抽成单独包 `@cenkor/design-tokens`：
- 颜色（OKLCH 19 个）
- 字体（Plus Jakarta Sans + JetBrains Mono）
- 间距、圆角、阴影、动效
- Tailwind config preset

**admin-web** 和 **portal-web** 都装这个包，保证视觉一致。

### 7.2 路由

```
admin-web：
  /login
  /                                        ← Dashboard
  /system/users
  /system/roles
  /system/menus
  /system/apps
  /system/audit
  /cms/products
  /cms/cases
  /cms/news
  /cms/site
  /cms/media
  /<app_key>/...                           ← 动态加载 App 路由

portal-web（C 端用户中心）：
  /
  /login
  /register
  /forgot-password
  /profile
  /orders
  /api-keys
```

### 7.3 关键组件

- **AppLayout**（侧边栏 + 顶栏 + 面包屑 + 内容区）
- **AuthGuard**（无 token 跳 /login）
- **PermissionGuard**（`<HasPermission code="...">`）
- **DataTable**（分页 / 搜索 / 排序 / 批量操作 / 列自定义）
- **FormBuilder**（基于 schema 自动渲染：input / select / upload / richtext / json editor）
- **Upload**（拖拽 / 粘贴 / 进度 / 预览）
- **RichEditor**（TipTap / Vditor，中文友好）
- **JsonEditor**（JSON Schema 表单）

---

## 8. 项目结构（最终）

```
cenkor-admin/
├── docker-compose.yml             # 一键起 PG / Redis / MinIO
├── docker-compose.prod.yml       # 生产（独立）
├── ARCHITECTURE.md                # 本文档
├── README.md
├── .github/workflows/ci.yml
│
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/                   # 跨 App 共享 migrations
│   │   └── versions/
│   ├── src/cenkor_admin/
│   │   ├── main.py
│   │   ├── core/                  # 平台核心
│   │   │   ├── config.py
│   │   │   ├── db.py
│   │   │   ├── redis.py
│   │   │   ├── storage.py
│   │   │   ├── security.py
│   │   │   ├── audit.py
│   │   │   ├── i18n.py
│   │   │   └── exceptions.py
│   │   ├── auth/                  # 鉴权子模块
│   │   ├── users/                 # 用户管理
│   │   ├── rbac/                  # 角色权限
│   │   ├── menus/
│   │   ├── tenants/
│   │   ├── apps/                  # 应用中心
│   │   ├── audit/
│   │   ├── notifications/
│   │   └── apps/                  # 业务 App
│   │       ├── __init__.py
│   │       └── cms/               # 第一个 App
│   │           ├── manifest.py
│   │           ├── router.py
│   │           ├── service.py
│   │           ├── models.py
│   │           └── schemas.py
│   ├── tests/
│   └── scripts/
│
├── frontend/
│   ├── packages/
│   │   └── design-tokens/         # 共享 token
│   ├── admin-web/                 # B 端后台
│   │   ├── src/
│   │   │   ├── core/              # 平台核心
│   │   │   ├── apps/              # 业务 App
│   │   │   │   └── cms/
│   │   │   ├── router/
│   │   │   ├── stores/
│   │   │   └── main.ts
│   │   ├── package.json
│   │   └── vite.config.ts
│   ├── portal-web/                # C 端用户中心
│   │   └── (类似 admin-web)
│   └── public-site-bridge/        # 官网数据桥
│       └── (把 /www/wwwroot/website/ 改为 API 拉数据)
│
└── deploy/
    ├── nginx/
    ├── docker/
    └── k8s/                       # 后期
```

---

## 9. 阶段交付计划

### Phase 1：MVP 底座 + 辰科官网 CMS（3 周）

**Week 1：骨架 + 鉴权**
- 仓库搭建、Docker Compose 起来、CI 通
- 后端：FastAPI 骨架、配置、DB、Redis、MinIO 接入
- 前端：admin-web 骨架、路由、布局、登录页
- 鉴权：JWT、登录 / 刷新 / 登出

**Week 2：用户 + RBAC + 应用中心底座**
- 用户 CRUD（含飞书 OAuth）
- 角色 / 权限 / 菜单 CRUD
- 应用中心：manifest、扫描、安装、卸载
- 前端：用户、角色、权限、应用管理 UI

**Week 3：辰科官网 CMS App**
- 产品 / 案例 / 新闻 CRUD
- 媒体库（MinIO 接入）
- 站点配置
- 官网接入 CMS API（/www/wwwroot/website/ 改为拉数据）
- E2E：登录 → 创建产品 → 官网刷新可见

### Phase 2：生产加固（2 周）

- 审计日志（中间件 + 查询 UI）
- 站内消息 + WebSocket
- 通知（邮件、webhook）
- 多语言（i18n + 翻译文件）
- 安全：限流、CSRF、SQL 注入检测
- 测试覆盖：unit 70% / E2E 关键路径

### Phase 3：规模化（2+ 周）

- 多租户完整版（软隔离 → RLS）
- App 依赖管理 + 版本升级
- 监控（Prometheus + Grafana 仪表盘）
- 备份 / 恢复脚本
- 性能：DB 索引、Redis 缓存、CDN
- 文档站点

---

## 10. 风险与开放问题

### 10.1 已锁定决策 ✅

| # | 问题 | 决定 | 备注 |
|---|------|------|------|
| 1 | **数据库** | **PostgreSQL 16 优先**，DB 层抽象兼容 MySQL 8 | 详见 §10.4 兼容层设计 |
| 2 | **登录方式** | 账号密码 + 飞书 OAuth | 飞书用 OAuth 2.0 标准流 |
| 3 | **应用中心级别** | **MVP：代码级模块化**（App 是 Python 包，部署时打包，运行时不能装卸）| Phase 2 评估是否升级 |
| 4 | **前端组件库** | shadcn-vue | 复制粘贴式，不锁死 |
| 5 | **官网数据桥** | **改造 `/www/wwwroot/website/` 用 JS 拉 CMS API**（静态 + 动态化）| 失败时降级用本地 site-data.js |
| 6 | **代码组织** | **Monorepo**（pnpm workspace + Python single package）| 单 git 仓库 |
| 7 | **租户模型** | 单租户（MVP） | Phase 3 升级软多租户 |

### 10.2 数据库凭据（MVP 默认）

> ⚠️ **生产部署前必须修改**。开发/测试用，存放在 `.env`（gitignored）。

| 项 | 值 |
|----|---|
| **类型** | PostgreSQL 16 |
| **Host** | `localhost:5432`（dev）|
| **Database** | `cenkor` |
| **Username** | `cenkor` |
| **Password** | `li123456`（**弱密码，必须改**）|

对应环境变量：
```bash
DATABASE_URL=postgresql+asyncpg://cenkor:li123456@localhost:5432/cenkor
DATABASE_URL_SYNC=postgresql://cenkor:li123456@localhost:5432/cenkor
```

### 10.3 风险

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| 应用中心过度设计、拖累 MVP | 中 | 中 | MVP 简化：只做模块化目录 + manifest 读取，**不实现**运行时装卸 |
| FastAPI 异步生态踩坑 | 中 | 中 | 锁版本、SQLAlchemy 2.0 async 文档读全、CI 跑并发测试 |
| 现有 KeleAdmin (PHP) 迁移数据 | 高 | 中 | 不迁移，做数据导入脚本（一次性） |
| 团队对 Vue3 + TypeScript 不熟 | 中 | 中 | shadcn-vue 提供现成模板，2 周内可上手 |
| 私部署网络环境复杂 | 中 | 高 | 提供离线安装包、Docker 镜像压缩方案 |
| PG vs MySQL 兼容层有遗漏 | 中 | 中 | 锁 SQLAlchemy Core 写法、避开方言特有语法、CI 双 DB 跑测试（后期） |

### 10.4 PG/MySQL 兼容层设计

通过 SQLAlchemy 2.0 + 严格 Core 风格 + 避开方言特性实现 90% 兼容：

**能跨 DB 的写法**：
- ✅ 数据类型：`String` / `Integer` / `Boolean` / `DateTime` / `Float` / `Text` / `Numeric` / `LargeBinary`
- ✅ 关系：`ForeignKey` / `relationship` / `backref`
- ✅ 索引：`index=True` / `UniqueConstraint`
- ✅ 查询：`select` / `filter` / `join` / `func`（用 `sqlalchemy.func`，不用方言函数）
- ✅ JSON：默认用 `JSON` 类型（PG 上是 JSONB，MySQL 上是 JSON，行为略不同但 API 一致）

**有差异、要避免或抽象**：
- ⚠️ **JSON 路径查询**：PG 用 `data['key']`，MySQL 用 `JSON_EXTRACT(data, '$.key')` → 用 SQLAlchemy 的 `JSON` + Python 端过滤
- ⚠️ **全文搜索**：PG 有 `to_tsvector`，MySQL 有 `FULLTEXT` → 抽象 `SearchBackend` 接口，两套实现
- ⚠️ **UUID**：PG 原生 `UUID` 类型，MySQL 存 `CHAR(32)` → 默认用 `String(36)` 存 UUID 字符串
- ⚠️ **数组**：PG 原生数组，MySQL 没有 → 用 JSON 存数组
- ⚠️ **ON CONFLICT / ON DUPLICATE KEY**：方言差异 → 用 SQLAlchemy 2.0 的 `Insert` + `on_conflict_do_update`（PG）/ `insert.values` + 业务判断（MySQL）
- ⚠️ **AUTO INCREMENT**：PG 用 `SERIAL`/`IDENTITY`，MySQL 用 `AUTO_INCREMENT` → SQLAlchemy `Sequence` 抽象

**配置切换**（`config.py`）：
```python
class Settings(BaseSettings):
    DATABASE_URL: str  # postgresql+asyncpg://... 或 mysql+aiomysql://...
    
    @property
    def db_dialect(self) -> str:
        return "postgresql" if "postgresql" in self.DATABASE_URL else "mysql"
```

**CI 跑双 DB 矩阵**（Phase 2 加）：
```yaml
strategy:
  matrix:
    db: [postgres-16, mysql-8]
```

### 10.5 替代方案（如果你不想自建）

| 方案 | 优势 | 劣势 |
|------|------|------|
| **Refine + Supabase** | 几天出原型 | 私有化难、Supabase 锁定 |
| **Directus** | 开箱即用、Headless | 二次开发受限 |
| **NocoDB** | 极简、Airtable 风 | UI 偏弱、复杂业务吃力 |
| **Appsmith** | 可视化搭建 | 性能/规模有限 |

**自建 vs 现成**：你已经想自建通用底座 + 辰科官网 CMS + 应用中心——**这是"自建"的合理理由**。但如果你只是想管官网，**Directus 半天就能搞定**。建议先确认范围（10.2 的 6 个问题）再开干。

---

## 11. 参考资源

- FastAPI 官方文档：https://fastapi.tiangolo.com
- SQLAlchemy 2.0 异步：https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- shadcn-vue：https://www.shadcn-vue.com
- TanStack Query Vue：https://tanstack.com/query/latest/docs/framework/vue/overview
- VeeValidate + Zod：https://vee-validate.logaretm.com
- Refine（参考架构）：https://refine.dev
- Vue Vben Admin（参考实现）：https://vvbin.cn/doc-next
- PlantFlow 你的现有项目（参考 n8n + Dify 合并设计）：本地 `/www/wwwroot/plantflow` 或 GitHub

---

**下一步**：等你拍板 10.2 的 6 个问题，我就出**详细 API 文档 + DB schema DDL + 第一个 PR 草案**（项目骨架）。
