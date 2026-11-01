# Cenkor Platform V2 — 开发者指南

> 面向**新接入 Cenkor Platform V2 的开发者**。
> 涵盖：用生成器起步、手写 App、内容类型与字段、前端插件、迁移与打包、鉴权与运维。
>
> 姊妹文档：[apps/development_guide.md](apps/development_guide.md)（应用开发规范与商店交付口径）、
> [template-guide.md](template-guide.md)（站点主题，写前台模板看这份）、[migrations.md](migrations.md)（迁移图细节）。

---

## 目录

- [快速开始](#快速开始)
- [三种扩展形态：先选对路](#三种扩展形态先选对路)
- [五分钟起一个 App（生成器）](#五分钟起一个-app生成器)
- [手写 App：manifest 全字段](#手写-appmanifest-全字段)
- [后端路由与权限](#后端路由与权限)
- [内容类型与字段定义](#内容类型与字段定义)
- [前端：插件机制](#前端插件机制)
- [数据库迁移](#数据库迁移)
- [打包与安装](#打包与安装)
- [API 鉴权与跨域](#api-鉴权与跨域)
- [部署与运维](#部署与运维)
- [常见问题](#常见问题)

---

## 快速开始

> ⚠️ 本节是**本地开发机**的启动方式（后端 8000 + 前端 dev server）。
> **生产部署**（宿主机 + 宝塔，后端 `8002`）见 [`deploy.md`](deploy.md)。

### 环境要求

| 工具 | 版本 | 备注 |
|------|------|------|
| Python | 3.11+ | 生产实测 3.13（宝塔虚拟环境 `/www/server/pyporject_evn/cenkor`） |
| Node.js | 18+ | |
| PostgreSQL | 16+ | |
| Redis | 7+ | |
| 对象存储 | 兼容 S3 或七牛云 | 本地开发可用 MinIO；生产主存储是**七牛云 Kodo**（见 `cloud_storage_config.active_provider`） |

### 克隆与启动

```bash
git clone https://github.com/likele001/cenkor-admin.git
cd cenkor-admin

# 后端
cd backend
pip install -r requirements.txt
cp ../.env.example .env
# 编辑 .env 填 DB / Redis / 对象存储等配置
alembic upgrade heads
python -m cenkor_admin.scripts.seed
uvicorn cenkor_admin.main:app --host 0.0.0.0 --port 8000

# 前端（后台）
cd ../frontend/admin-web
pnpm install
pnpm dev          # http://localhost:5173

# 前端（前台）
cd ../frontend/portal-web
npm install
npm run dev       # http://localhost:5175
```

### 默认账号

- 后台：`admin@cenkor.cn`（**无默认口令**，初始口令随机生成、首次 seed 时只打印一次；忘记可 `bash scripts/reset-admin-password.sh` 重置）
- 前台：注册即可

### 前端包管理与构建故障排查

各前端目录用哪个包管理器，**看锁文件**，不要混用（混用会弄坏 node_modules 软链）：

| 目录 | 包管理器 | 安装命令（在该目录内执行） |
|------|----------|------------------------------|
| `frontend/admin-web` | **pnpm**（有 pnpm-lock.yaml） | `pnpm install` |
| `frontend/developer-web` | **pnpm**（有 pnpm-lock.yaml） | `pnpm install` |
| `frontend/portal-web` | npm（无锁文件） | `npm install` |
| `frontend/landing-web` | npm（有 package-lock.json） | `npm install` |

依赖环境损坏时的修复顺序（**注意：`pnpm install --force` 必须 cd 进对应前端目录跑，仓库根目录无效**）：

```bash
cd frontend/admin-web
pnpm install --force          # 重建 node_modules 软链
pnpm rebuild esbuild vue-demi # 补跑被跳过的构建脚本
pnpm build                    # 验证：vue-tsc 类型检查 + vite 构建
```

两个已知坑：

1. **pnpm 10+ 默认跳过依赖构建脚本**：esbuild 会缺二进制导致 vite 报错。已在各 `pnpm-workspace.yaml` 配置 `allowBuilds`（pnpm 11）+ `onlyBuiltDependencies`（pnpm 10）放行 esbuild / vue-demi，不要删。
2. **`vue-tsc@2.0.0` 官方发布残缺（缺 index.js，上游坏包）**：报错特征 `Cannot find module '../index.js'`，重装也无法修复，必须升级版本：
   ```bash
   pnpm add -D vue-tsc@2.2.10
   ```
   admin-web / developer-web 已钉到 2.2.10；新拉仓库若 lockfile 又解析到 2.0.0，同样用这条命令修。

---

## 三种扩展形态：先选对路

**这一步选错，后面全白干。** 平台有三种扩展方式，改的东西完全不同：

| 形态 | 你改哪里 | 会不会被平台升级覆盖 | 适用 |
|---|---|---|---|
| **A. 插件式 App**（官方路径，推荐） | 新建 `apps/{key}/` 独立目录，前端产出 `plugin.js` | **不会**。与主程序解耦，装/卸都在后台 | 业务功能、行业模块 |
| **B. 内置应用** | 直接改 `apps/{key}/` 里的平台自带模块（cms / crm / erp…） | **会**。上游更新时可能冲突 | 给平台本身做贡献 |
| **C. 站点主题** | 后台「CMS → 模板工作台」写 Jinja2 模板 | 不会 | 官网/公站外观 |

> ⚠️ **别把 A 做成 B**：在 `frontend/admin-web/src/views/` 里加 Vue 页面、在
> `router/index.ts` 里注册路由，属于**改主程序**（形态 B）。平台一升级，你的改动就
> 和新版本打架。插件式 App 的前端由平台在运行时动态加载，不动 admin-web 一行代码。

本章余下内容主要讲 **形态 A**；形态 C 见 [template-guide.md](template-guide.md)。

---

## 五分钟起一个 App（生成器）

平台自带 CRUD 代码生成器 `scripts/gen-app.py`，输入一份 YAML，直接产出可运行的后端 + 前端插件 + 迁移。

### 1. 写 spec

复制样例改：`scripts/templates/app/spec.sample.yaml`

```yaml
key: inventory                    # 应用 key：小写字母 + 下划线，会做目录名与 Python 包名
name: 库存管理
version: 1.0.0
icon: "📦"
category: business                # business / productivity / content / system / ai
author: Cenkor Team
description: 库存基础资料：仓库 / 库位
sort: 80                          # 菜单排序

entities:                         # 一个实体 = 一张表 + 一套 CRUD + 一个页面
  - key: warehouse
    name: 仓库
    title: 仓库
    subtitle: 仓库基础资料
    fields:
      - { name: code,   type: string,  len: 32,  required: true, unique: true, label: 仓库编码, list: true, search: true }
      - { name: name,   type: string,  len: 100, required: true,                label: 仓库名称, list: true, search: true }
      - { name: type,   type: enum,    choices: [成品仓, 原料仓, 半成品仓],      label: 仓库类型, list: true, filter: true }
      - { name: enable, type: bool,    default: true,                          label: 是否启用, list: true, filter: true }
      - { name: remark, type: text,                                             label: 备注 }

  - key: location
    name: 库位
    title: 库位
    subtitle: 仓库下的库位
    fields:
      - { name: code,      type: string, len: 32, required: true, unique: true, label: 库位编码, list: true, search: true }
      - { name: name,      type: string, len: 100, required: true,              label: 库位名称, list: true }
      - { name: warehouse_id, type: fk,  entity: warehouse,                     label: 所属仓库, list: true, filter: true }
      - { name: capacity,  type: decimal, precision: 10, scale: 2,             label: 容量, list: true }
```

字段类型：`string` / `text` / `enum` / `bool` / `int` / `decimal` / `date` / `datetime` / `fk`。
`list: true` 进列表列，`search: true` 进模糊搜索，`filter: true` 进筛选下拉。

### 2. 生成

在**仓库根目录**执行：

```bash
PYTHONPATH=backend/src python3 scripts/gen-app.py --spec scripts/templates/app/spec.sample.yaml
```

> ⚠️ **`--versions-dir` 必须指向 `backend/alembic/versions`（父目录），不要指向 `core/`
> 之类的子目录**。生成器会递归收集所有子目录的迁移来算 head。
> （2026-11-01 之前只扫顶层，会报「迁移图没有 head」—— 已修。）

两种模式：

| `--mode` | 迁移落到哪 | 用在哪 |
|---|---|---|
| `package`（默认） | App 目录内的 `alembic/versions/` | 随 ZIP 分发 |
| `builtin` | 全局链 `backend/alembic/versions/`，挂开源链 head | 平台内置应用 |

`builtin` 会顺延闭源链入口以保证迁移图仍唯一 head。

### 3. 产物长什么样

```
apps/inventory/
├── manifest.py                     # 菜单 / 权限 / 公共路由前缀
├── models.py                       # SQLAlchemy 模型
├── router.py                       # CRUD 路由（自动挂载到 /api/v1/inventory）
├── app.spec.yaml                   # spec 快照（以后重新生成用）
├── alembic/versions/
│   └── 20261101_094336_create_inventory.py
└── frontend/
    ├── package.json
    ├── vite.config.js              # 打包成 iife 单文件，vue 走 external
    ├── dist/plugin.js              # ← 构建产物，平台动态加载它
    └── src/
        ├── main.js                 # 入口：window.__registerPlugin({...})
        ├── api.js                  # 复用 __PLUGIN_API__（自带 401 刷新 token）
        ├── nav.js
        ├── components/             # PageShell / DataTable / FormDrawer / SearchBar
        └── pages/                  # 每个实体一个 View
```

生成完会自动自检：包结构完整、语法可编译、菜单与路由一致、迁移仍唯一 head。

### 4. 跑起来

```bash
# 确认迁移挂载点正常
bash scripts/check-migration-graph.py

# 装进本地后端 → 重启后启动流程自动注册 manifest、权限、菜单
alembic upgrade heads

cd apps/inventory/frontend && npm install && npm run build   # 产出 dist/plugin.js
cp -r dist ../../../static/apps/inventory/                   # 插件静态目录
```

刷新后台，「库存管理」菜单出现、页面可增删改查。手工改页面后重新 `npm run build` 即可，**不需要重启后端**（`plugin.js` 是按 `?v=<mtime>` 拉取的）。

---

## 手写 App：manifest 全字段

不用生成器也能手写。目录至少 `manifest.py` + `__init__.py`。

### 目录结构（真实形态）

```
apps/my_app/                        # key 用下划线，目录名即 Python 包名
├── __init__.py                     # 必需
├── manifest.py                     # 必需：MANIFEST 对象
├── models.py                       # 可选：SQLAlchemy 模型
├── router.py                       # 可选：后台 API（会被自动挂载）
├── public_router.py                # 可选：免鉴权 API（⚠️ 不会自动挂载，见下章）
├── schemas.py                      # 可选：Pydantic
├── service.py                      # 可选：业务逻辑
├── hooks.py                        # 可选：@hook 处理器（插件钩子）
├── alembic/versions/               # 可选：本 App 的迁移
├── frontend/                       # 可选：前端插件源码
│   ├── vite.config.js
│   ├── dist/plugin.js              # 构建产物
│   └── src/main.js
└── static/                         # 可选：其它静态资源
```

> **`key` 命名**：小写字母 + 下划线（`my_app`、`cloud_storage`、`my_todo`）。
> 目录名同时是 Python 包名，且 `api/v1/__init__.py` 以目录名做路由前缀，
> **不要用连字符或大写**。

### manifest.py

```python
"""My App · 元数据"""
from cenkor_admin.apps.base import AppManifest

MANIFEST = AppManifest(
    # ---- 基础 ----
    key="my_app",                              # 唯一标识
    name="我的应用",
    version="0.1.0",                           # semver
    author="Cenkor Team",
    description="这是一个示例 App",
    icon="🧪",                                 # emoji
    category="productivity",                   # business / productivity / content / system / ai

    # ---- 依赖 ----
    min_platform_version="0.1.0",
    dependencies=[],                            # 依赖的其他 App key

    # ---- 权限 ----
    permissions_required=[
        "my_app:item:read",
        "my_app:item:write",
        "my_app:admin",
    ],

    # ---- 菜单 ----
    menus=[
        {
            "key": "my_app",
            "title": "我的应用",
            "icon": "appstore",
            "sort": 60,
            "children": [
                {"key": "my_app:items", "title": "条目管理", "path": "/my_app/items"},
            ],
        }
    ],

    # ---- 内容引擎（可选）----
    content_types=[
        {
            "key": "myitem",
            "name": "条目",
            "icon": "📄",
            "supports_category": True,
            "supports_tags": True,
        }
    ],
    field_groups=[
        {"content_type": "myitem", "key": "basic", "label": "基础信息", "sort": 0},
        {"content_type": "myitem", "key": "advanced", "label": "高级", "sort": 1},
    ],
    field_definitions=[
        {
            "content_type": "myitem", "key": "priority", "label": "优先级",
            "type": "select", "group": "basic",
            "options": [
                {"value": "low", "label": "低", "color": "#84cc16"},
                {"value": "high", "label": "高", "color": "#ef4444"},
            ],
        },
        {
            "content_type": "myitem", "key": "url", "label": "链接",
            "type": "url", "group": "basic",
        },
    ],
    categories_seed=[
        # 支持 children 嵌套，最多 3+ 级
        {"content_type": "myitem", "slug": "general", "name": "通用"},
        {"content_type": "myitem", "slug": "important", "name": "重要"},
    ],

    # ---- 公共 API 前缀（仅元数据，见「后端路由与权限」）----
    public_routes_prefix="/api/v1/my_app",

    # ---- 高级（可选）----
    license_required=False,          # True：未授权一律 402（商店收费应用）
    price_model="free",              # free / one_time / seat
    price_cents=0,
    period_days=365,                 # 仅 seat 生效
    schema_managed=False,            # True：本 App 的表由 apps/<key>/schema.sql 管理
    schema_file="schema.sql",
    hooks=[],                        # 钩子模块 dotted path，缺省试 apps.<key>.hooks
)
```

### 启动时自动完成什么

1. 扫描 `apps/*/manifest.py`，找到 `MANIFEST` → 写入 `platform_apps` 表
2. 依据 manifest 同步**权限码**与**菜单**到 RBAC（超管自动拥有）
3. 调用 `FieldRegistry.register_from_manifest()` 注册 content_types / field_groups /
   field_definitions / field_options / categories_seed（幂等，重复启动不重复插）
4. 扫描 `apps/*/router.py` → 自动挂载到 `/api/v1/{key}`

**无需手动执行 install**。改了 manifest 重启后端即生效。

---

## 后端路由与权限

这是最容易踩坑的一章，**自动挂载的规则不直观**。

### 自动挂载：只认 `router.py`

`backend/src/cenkor_admin/api/v1/__init__.py` 的 `_discover_and_register()` 规则：

- 扫描 `apps/` 下**不以 `_` 开头**的目录
- **只找 `router.py`**，没有就跳过
- 挂到 `/api/v1/{目录名}`，并统一加三道守卫：
  1. `get_current_user` —— **必须登录**（默认就不许匿名访问）
  2. `app_enabled_dependency(key)` —— 应用被停用则拒绝
  3. 业务权限（你自定义的路由里用 `require_permission(...)`）

```python
# apps/my_app/router.py —— 自动挂到 /api/v1/my_app
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.core.db import get_db
from . import models

router = APIRouter()


@router.get("/items", response_model=dict)
async def list_items(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("my_app:item:read")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return {"items": [], "total": 0}
```

### `public_router.py` 不会自动挂载

**这是最常见的错觉。** 放在 `apps/{key}/public_router.py` 里的路由**不会**出现在
API 上 —— 自动发现只找 `router.py`。要提供免鉴权接口，必须二选一：

| 做法 | 说明 |
|---|---|
| **挂到 `router.py` 里**，路径避开鉴权 | 但 `router.py` 整体带 `get_current_user`，「避开」做不到 |
| **手工在主程序注册**（改 `api/v1/__init__.py`） | 平台内置 App 的做法；属形态 B，会被升级覆盖 |

平台自己的做法就是在 `api/v1/__init__.py` 里逐条 include：

```python
from cenkor_admin.apps.my_app.public_router import router as my_app_public
api_v1_router.include_router(my_app_public, prefix="/public", tags=["my_app"])
```

> **`public_routes_prefix` 只是元数据**：它会被写进 App 注册信息（商店展示用），
> **不参与任何路由挂载**。别以为填了它接口就自动暴露。

### 权限码规范

平台实际用的是**三段式** `{app}:{resource}:{action}`，管理级用两段式：

```
{app}:{resource}:read      crm:customer:read
{app}:{resource}:write     crm:customer:write
{app}:{resource}:delete    crm:customer:delete
{app}:{resource}:export    crm:customer:export
{app}:admin                crm:admin          # 应用级管理
```

只写两段式（`my_app:read`）在功能上不会报错，但与全平台既有权限码风格不一致，
RBAC 授权页会显得很乱。**跟着三段式走。**

### 内建依赖

```python
from cenkor_admin.api.deps import (
    get_current_user,               # 仅校验登录
    require_permission,             # 校验权限码
    require_superuser,              # 超管
)
from cenkor_admin.core.db import get_db
```

> 生成器产出的 `router.py` 里，凡是需要补业务校验/跨 App 写的地方都标了
> `# TODO(business)`，按需补。

---

## 内容类型与字段定义

### 21 种字段类型

真相源：`apps/cms/field_types.py` 的 `FIELD_TYPES`。

| 分组 | 类型 |
|---|---|
| 文本 | `text` `longtext` `richtext` `markdown` |
| 数字/布尔/日期 | `number` `boolean` `date` `datetime` `color` |
| 联系 | `url` `email` `phone` |
| 媒体 | `image` `images` `file` `files` |
| 选择 | `select` `multiselect` |
| 高级 | `json` `repeater` `relation` |

新增类型要同时改：`FIELD_TYPES`、`FIELD_DEFAULTS`、`VALIDATION_RULES`、
`validate_field_value()`、前端 `DynamicFieldRenderer.vue`。

### 三种加字段的方式

| 方式 | 位置 | 适用 |
|---|---|---|
| 后台 UI | 内容管理 → 内容类型 → 「+ 字段」 | 临时/运营期调整 |
| API | `POST /api/v1/cms/content-types/{id}/field-definitions` | 脚本化 |
| manifest | `field_definitions` 里声明 | 应用自带的核心字段（推荐） |

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"field_key":"score","label":"评分","field_type":"number","required":false,
       "validation":{"min":0,"max":100}}' \
  http://localhost:8002/api/v1/cms/content-types/1/field-definitions
```

### 查询自定义字段值（⚠️ 别信 `custom.xxx=`）

`GET /api/v1/cms/entries` **支持**的查询参数只有这些：

```
content_type_key  category_id  tag_id  status  search
include_deleted   ai_origin    page     page_size
```

**没有 `custom.<field>=<value>` 这种写法。** FastAPI 对未知 query 参数**静默忽略**，
所以写成 `?custom.license=Apache-2.0` 不会报错，但**返回的是全量数据** —— 排查起来极其费时。

要按自定义字段筛，两条路：

```python
# 1) 后端内存过滤（数据量小）
entries = (await db.execute(select(Entry).where(Entry.content_type_id == ct_id))).scalars().all()
hits = [e for e in entries if (e.custom_fields or {}).get("license") == "Apache-2.0"]
```

```sql
-- 2) SQL 直接查（走 GIN 索引，数据量大用这个）
SELECT * FROM cms_entries
WHERE content_type_id = :ct_id
  AND custom_fields @> '{"license": "Apache-2.0"}'::jsonb;
```

`custom_fields` 上的 GIN 索引已由迁移创建。

---

## 前端：插件机制

**这是与「改 admin-web」差别最大的一章。** 平台允许 App 在运行时把自己的前端
挂进后台，不需要重新构建 admin-web、也不需要重启后端。

### 加载链路

```
admin-web 启动
   ↓  POST/GET /api/v1/system/apps/plugins        → 拿到已安装且有前端的 App 列表
   ↓  对每个 App 注入 <script src="/.app-assets/{key}/plugin.js?v={mtime}">
plugin.js 执行 → window.__registerPlugin({ id, routes, menus, locales })
   ↓  PluginManager 合并：router.addRoute('layout', ...) + 侧边栏菜单 + i18n
```

对应实现：`frontend/admin-web/src/core/plugin.ts`；静态资源由后端
`app.mount("/.app-assets", StaticFiles(...))` 提供，目录是
`backend/src/cenkor_admin/static/apps/{key}/`。

### 插件合约

```ts
interface PluginDefinition {
  id: string                                     // 必须等于 manifest 的 key
  version: string
  name?: string
  routes?: {
    path: string                                 // 相对路径，无前导斜杠：'my_app/items'
    name: string                                 // 唯一路由名：'my-app-items'
    component: () => Promise<any>                // 或同步组件
    meta?: { permission?: string }               // ← 前端权限守卫用这个
  }[]
  menus?: { key: string; title: string; path: string; icon?: string; sort?: number }[]
  locales?: Record<string, Record<string, string>>
}
```

三个必须对齐的点：

1. **`routes[].path`** 与 manifest `menus[].children[].path` 一致（后者带前导斜杠，前者不带）
2. **`routes[].name`** 全局唯一，建议 `{app}-{entity}`
3. **`meta.permission`** 与后端 `require_permission(...)` 的权限码一致，否则菜单能点、页面 403

### 入口文件

```js
// frontend/src/main.js
import 'vue'                                          // 共享 admin-web 的 Vue
import ElementPlusCss from 'element-plus/dist/index.css?inline'
import ItemListView from './pages/ItemListView.vue'

// Element Plus 的 CSS 以 <style> 注入（iife 单文件没有独立的 css 产物）
if (typeof document !== 'undefined') {
  const style = document.createElement('style')
  style.setAttribute('data-my_app-plugin', 'element-plus')
  style.textContent = ElementPlusCss
  document.head.appendChild(style)
}

window.__registerPlugin({
  id: 'my_app',
  version: '1.0.0',
  name: '我的应用',
  routes: [
    { path: 'my_app/items', name: 'my-app-items', component: ItemListView,
      meta: { permission: 'my_app:item:read' } },
  ],
  menus: [
    { key: 'my_app:items', title: '条目管理', path: '/my_app/items', icon: 'menu', sort: 61 },
  ],
  locales: { 'zh-CN': { my_app: { title: '我的应用' } } },
})
```

### 构建配置（关键：external vue）

```js
// frontend/vite.config.js
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  build: {
    lib: { entry: 'src/main.js', formats: ['iife'], name: 'MyAppPlugin', fileName: () => 'plugin.js' },
    rollupOptions: {
      external: ['vue'],                  // ← 必须。否则 plugin 内联一份 Vue，
      output: { globals: { vue: 'Vue' }, inlineDynamicImports: true },
    },                                    //   响应式与组件实例会和宿主不兼容
  },
})
```

`admin-web/src/main.ts` 会把 Vue 挂到 `window.Vue` 供插件共享。

### 调接口：用 `__PLUGIN_API__`

插件不需要自己管 token。平台注入两个全局：

- `window.__PLUGIN_TOKEN__` —— 当前 token
- `window.__PLUGIN_API__(method, path, body?)` —— 带鉴权、**自带 401 自动刷新 token**

```js
// frontend/src/api.js
const BASE = '/api/v1/my_app'
async function invoke(method, path, body) {
  if (typeof window.__PLUGIN_API__ === 'function') {
    return window.__PLUGIN_API__(method, BASE + path, body)
  }
  // 兜底（独立调试时）
  const token = localStorage.getItem('cenkor_token') || window.__PLUGIN_TOKEN__ || ''
  const resp = await fetch(BASE + path, {
    method,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) },
    body: body != null ? JSON.stringify(body) : undefined,
  })
  if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail || resp.statusText)
  return resp.status === 204 ? null : resp.json()
}
```

### 跳到别的页面

```js
// frontend/src/nav.js
export function go(path) {
  if (window.__PLUGIN_NAV__) return window.__PLUGIN_NAV__(path)
  window.history.pushState({}, '', path)
}
```

### 部署插件

```
backend/src/cenkor_admin/static/apps/{key}/plugin.js
```

即后端包内的 `<cenkor_admin>/static/apps/<key>/`，由 `/.app-assets` 挂载暴露。

```bash
# 站在 backend/src/cenkor_admin/apps/my_app/frontend 目录下
npm run build
cp -r dist/* ../../../static/apps/my_app/     # 注意是三级：frontend → my_app → apps → cenkor_admin
```

改完前端**不用重启后端**，平台按 `?v=<mtime>` 拉新文件；浏览器强刷一次即可。

> 插件内如果自己调用了 `router.push`、要用 `<router-link>`，用平台注入的
> `__PLUGIN_NAV__`；不要直接 new 一个 vue-router。

---

## 站点模板标签：给主题加自定义标签

先明确一件事：**这套系统的「标签」不是短代码**。没有 `{dede:arclist}`、没有
`[gallery]`、没有 `<?php ?>`。所谓标签就是 Jinja2 里的**函数调用 + 过滤器**：

```jinja
{% for r in content_list('article', limit=6) %}
  <a href="{{ r.url }}">{{ r.title }}</a>
{% endfor %}

{{ content.text|markdown }}
```

内置的是 **16 个数据 API + 16 个过滤器（19 个名字）**，主体在
`apps/cms/template_context.py`（API，方法上打 `@cms_api`）与 `core/jinja_env.py`
（过滤器，`_register_filters`）。完整清单看
[template-guide.md](template-guide.md) §五、§六，或直接在后台
「CMS → 模板工作台 → 标签速查」里点选插入。

### 内置标签不能覆盖，但 App 可以加自己的

App 目录下放一个 `template_tags.py`，声明两个 dict 就行，**启动时自动发现**，
不用改核心、不用在别处登记：

```
apps/my_app/
├── __init__.py
├── router.py
├── template_tags.py     # ← 新增，有它就会被注册
└── models.py
```

```python
# apps/my_app/template_tags.py
from sqlalchemy import select
from cenkor_admin.apps.my_app import models


def my_app_specials(ctx, limit: int = 6) -> list[dict]:
    """App 自有的「精选」列表，供主题模板调用。

    ctx 是 TemplateContext —— 顺手就能用 ctx.content_list() / ctx.nav()
    / ctx.url() 拿到绑定当前站点的数据，不用自己拿 session、不用管多站点。
    """
    limit = max(1, min(int(limit or 6), 30))          # 一律夹上限
    rows = ctx.session.execute(
        select(models.Special).order_by(models.Special.sort).limit(limit)
    ).scalars().all()
    return [{"id": r.id, "title": r.title, "url": r.url} for r in rows]


def my_app_domain(url) -> str:
    """过滤器：从 URL 取主机名。"""
    from urllib.parse import urlparse
    return urlparse(str(url or "")).netloc


FUNCTIONS = {
    "my_app_specials": my_app_specials,   # 模板里 {{ my_app_specials(3) }}
}

FILTERS = {
    "my_app_domain": my_app_domain,       # 模板里 {{ item.url|my_app_domain }}
}
```

主题里直接用：

```jinja
{% for s in my_app_specials(limit=3) %}
  <a href="{{ s.url }}">{{ s.title }}</a>
{% endfor %}
```

### 两种标签的签名不一样

| 类型 | 注册位置 | 签名 | 拿到 ctx |
|---|---|---|---|
| 函数 | `FUNCTIONS` | `fn(ctx, *args, **kwargs)` | ✅ 第一个参数固定是 ctx |
| 过滤器 | `FILTERS` | `fn(value, *args)` | ❌ 标准 Jinja 过滤器，只有值 |

> 为什么函数一定要收 `ctx`：App 的标签通常不是从零算起，而是**复用已有能力再加工**。
> 有了 ctx 就能 `ctx.content_list(...)` 拿条目再补一个自有字段，
> 而不必自己建 engine、自己拼站点过滤条件。

### 注册规则（不满足就静默跳过，不炸站点）

| 规则 | 说明 |
|---|---|
| 名字格式 | `^[a-z_][a-z0-9_]{0,39}$`，小写字母/数字/下划线，不以数字开头，≤40 字符 |
| 撞内置 | 16 个数据 API、9 个预注入变量、Jinja 内置过滤器 —— 一律拒绝 |
| 跨 App 重名 | 先注册的赢，后来的被拒。**建议统一加 App 前缀**：`my_app_xxx` |
| 同 App 重复注册 | 覆盖自己的旧条目（热更新友好） |
| 被拒表现 | 记一条 `template_api.rejected` warning，函数不可用，其余照常 |

被拒不会抛异常 —— 一个写错的 App 不该拖垮全站模板。排查时 grep 日志：

```bash
grep 'template_api' /www/wwwlogs/python/cenkor/error.log | tail
# template_api.registered    app=my_app functions=1 filters=1
# template_api.rejected      app=my_app error='模板函数名 ... 撞上内置模板标签'
```

### 停用与卸载

- **停用 App 不会摘掉它的模板标签。** 路由有 `app_enabled_dependency` 守卫，
  模板标签没有「一次请求」可挂 —— 注册进来就全局可用。
  所以标签里**只做只读查询**，别假设调用方一定是启用状态。
- **卸载 App 要显式摘除**，否则同名标签会一直留在模块单例里：

```python
from cenkor_admin.core.jinja_env import unregister_template_api
unregister_template_api("my_app")
```

### ⚠️ 安全边界：注册标签 = 交出执行能力

模板由**所有能进「模板工作台」的人**编辑。你把函数注册进模板，
等于把这份能力交给他们。所以：

- 只注册**只读、结果可控的纯函数**（查库、格式化、算 URL）
- **不要**在标签里做写操作、发外部 HTTP、读文件、执行命令
- 返回值别超过 2MB（单页输出上限，超了直接 `SecurityError`）
- 别返回 ORM 对象或带敏感字段的 dict —— 模板能读属性，`{{ x.__class__ }}` 这类
  虽然被沙箱挡住了，但普通字段照样能读出来

沙箱本身还会挡：`_` 开头属性、非白名单 callable、超大乘法、`..` 模板名穿越。

### 主题侧的自定义标签：用 macro

写主题的人不需要碰 Python。常用片段直接写 `{% macro %}`，就是模板内的自定义标签：

```jinja
{# macros/card.html #}
{% macro card(r) %}
  <article class="card">
    <h3>{{ r.title }}</h3>
    <time>{{ r.published_at|date }}</time>
  </article>
{% endmacro %}

{# layout.html #}
{% from 'macros/card.html' import card %}
{% for r in content_list('article', limit=6) %}{{ card(r) }}{% endfor %}
```

沙箱明确放行 `Macro` 调用，这是唯一不需要改后端就能「造标签」的方式。

---

## 数据库迁移

> 完整规则见 [migrations.md](migrations.md)。这里只讲扩展 App 相关的部分。

### 目录分层

`backend/alembic/versions/` **不是扁平的**，按来源分目录，`alembic.ini` 的
`version_locations` 逐条列出：

```
backend/alembic/versions/
├── core/         平台核心
├── erp/  crm/  mes/  commerce/    各 App 自有
└── ext/          扩展与闭源
```

**教训**：新增迁移别放错目录，`alembic revision` 用
`--version-path alembic/versions/core`（或对应 App 目录）显式指定。

### 生成与校验

```bash
cd backend
PYTHONPATH=src alembic revision --autogenerate -m "create my_app tables" \
  --version-path alembic/versions/ext
alembic upgrade heads
bash ../scripts/check-migration-graph.py     # 断链 / 重复 / 多 head 自检
```

### 公开链与闭源链

迁移图分两条链，靠**挂载点**串联：

- 会进开源仓库的迁移，必须**插在挂载点之前**（当前挂载点是 `gen_inventory`）
- `alembic revision --autogenerate` 默认把 `down_revision` 写成当前 head —— 在闭源部署里
  那是闭源 head，**必须手工改成公开 revision**，否则公开仓库拉下来会断链

用生成器的 `--mode builtin` 会自动处理这道顺延，手写迁移要自己盯。

---

## 打包与安装

```bash
bash scripts/package-app.sh my_app 1.0.0
```

产物：`backend/src/cenkor_admin/apps/my_app/release/my_app-1.0.0.zip`

包内含：`manifest.py` / `__init__.py` / 后端代码 / `alembic/versions` / `frontend/dist`
（排除 `node_modules`、`release`、`__pycache__`、`.git`）。

安装流程（后台「应用中心」上传，或 `POST /api/v1/store/submissions`）：

1. 解压并校验 `manifest.py`
2. 校验 `key` 唯一、`version` 合法、依赖满足
3. 代码落到 `apps/{key}/`，前端产物落到 `static/apps/{key}/`
4. 执行迁移
5. 注册权限与菜单
6. 状态置为 `installed`

> **`dev_method` 三种交付形态**（`platform` / `extension` / `standalone`）与产品归属，
> 见 [apps/development_guide.md](apps/development_guide.md) 第十一节。

---

## API 鉴权与跨域

### 后台 API（admin JWT）

```bash
# 1. 登录
curl -X POST -H "Content-Type: application/json" \
  -d '{"username":"admin@cenkor.cn","password":"<你的初始口令>","captcha_token":"任意16+hex"}' \
  http://localhost:8002/api/v1/auth/login

# 2. 带 token
curl -H "Authorization: Bearer <access_token>" \
  http://localhost:8002/api/v1/cms/content-types
```

### 前台 API（portal JWT）

前缀 `/api/v1/public/portal/*`，issuer `cenkor-portal`：

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"username":"user1","email":"u@example.com","password":"test123456","captcha_token":"任意16+hex"}' \
  http://localhost:8002/api/v1/public/portal/auth/register
```

### 公共 API（免鉴权）

```bash
curl http://localhost:8002/api/v1/public/site/product
curl http://localhost:8002/api/v1/public/categories?content_type_key=product
```

站点 HTML 直出接口是另一套前缀：`/api/v1/page/*`（详见 [template-guide.md](template-guide.md)）。

### 跨域

```bash
# 开发
CORS_ORIGINS=http://localhost:5173,http://localhost:5175,http://localhost:8002
# 生产
CORS_ORIGINS=https://admin.example.com,https://portal.example.com
```

- ❌ 生产禁止 `*`
- ✅ 明确列出每个允许的源
- ✅ 保持 `allow_credentials=True`

---

## 部署与运维

### 环境变量

```bash
APP_NAME="Cenkor Admin"
APP_ENV="production"        # development | staging | production
DEBUG=False                 # 生产必须 False

SECRET_KEY="<强随机字符串>"
SECRET_KEY_OLD=""           # 轮换用，逗号分隔
COOKIE_SECURE=True

DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/db"
DATABASE_URL_SYNC="postgresql+psycopg2://user:pass@host:5432/db"   # Alembic 用
REDIS_URL="redis://host:6379/0"

# 对象存储（S3 兼容；生产主存储为七牛云 Kodo，在后台「云存储」里配）
S3_ENDPOINT="https://minio.example.com"
S3_ACCESS_KEY="..."
S3_SECRET_KEY="..."
S3_BUCKET_PUBLIC="..."
S3_BUCKET_PRIVATE="..."

FEISHU_APP_ID="..."         # 飞书 OAuth（可选）
FEISHU_APP_SECRET="..."
SMTP_HOST="smtp.example.com"
SMTP_PORT=587
SMTP_USER="..."
SMTP_PASSWORD="..."
```

### 启动顺序

1. PostgreSQL
2. Redis
3. 对象存储
4. 后端（先启动：自动执行 App 扫描 + FieldRegistry 注册 + App 路由挂载）
5. 前端

### 监控

- 健康检查：`GET /api/health`
- 审计日志：`GET /api/v1/system/audit`（需 `system:audit:read`）
- 审计统计：`GET /api/v1/system/audit/stats`

> **`/api/docs`、`/api/redoc`、`/api/openapi.json` 只在 `DEBUG=True` 时注册**
> （见 `main.py`）。生产默认关闭，访问返回 404 —— 这不是故障。

### 备份

```bash
# 数据库
pg_dump -U cenkor cenkor > /backup/cenkor_$(date +%Y%m%d).sql

# 对象存储：生产主存储是七牛云 Kodo，用 qshell / 官方 SDK 拉取；
# 本地 MinIO 备份池用 mc：
mc mirror cenkor-public /backup/minio/public/
```

### SECRET_KEY 轮换

```bash
NEW_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
# 1. 部署：SECRET_KEY 填新、SECRET_KEY_OLD 填旧
# 2. 观察数日，等旧 token 自然过期
# 3. 清空 SECRET_KEY_OLD
```

---

## 常见问题

### Q1: 新增字段后旧数据怎么办？

1. 启动时自动注册（新字段默认空）
2. 旧数据该字段为 `null` / `{}`，用 `default_value` 兜底
3. 需要按它查询时走 `custom_fields @> '...'::jsonb`（GIN 索引已建）

### Q2: 怎么改字段类型？

**别直接改** `field_type`，历史数据格式不兼容。正确做法：建新字段（新 key）→
写脚本迁移数据 → 删旧字段。

### Q3: App 卸载后数据怎么办？

content_types **软删**（写 `deleted_at`），field_groups / definitions 级联软删；
categories / tags / entries 保留，不影响前台展示。

要彻底清理，注意 `cms_content_types.key` 是**内容类型**的 key，不是 App 的 key：

```sql
-- 先确认要删的内容类型（myitem 是你 manifest 里 content_types[].key）
SELECT id, key, name FROM cms_content_types WHERE key = 'myitem' AND deleted_at IS NOT NULL;
DELETE FROM cms_content_types WHERE key = 'myitem';
```

### Q4: portal token 能访问后台吗？

❌ 不能。会被中间件拦截返回 403：

```json
{ "detail": "前台用户无法访问后台管理接口" }
```

这是 V2 的核心安全特性，不可关闭。

### Q5: 字段类型不够用？

新增类型要同步改五处：`FIELD_TYPES` / `FIELD_DEFAULTS` / `VALIDATION_RULES` /
`validate_field_value()` / 前端 `DynamicFieldRenderer.vue`。

### Q6: 模板引擎能调用 Python 函数吗？

**能，但不是随便调。** 主题模板跑在沙箱里，只有两类可调用：

1. **内置数据 API**（16 个）—— `apps/cms/template_context.py` 里打了 `@cms_api` 的方法，
   由 `as_globals()` 注入。
2. **App 注册的标签** —— App 目录下 `template_tags.py` 声明 `FUNCTIONS` / `FILTERS`，
   启动时自动注册，见上文「站点模板标签」。

除此之外的 Python 对象（包括 `env.globals` 里的内建）**一律不可调**：
`core/jinja_env.py` 里 `env.globals.clear()` 只保留 `range` / `dict` / `namespace`，
`is_safe_callable` 也只放行带 `__cms_api__` 标记的函数和 `{% macro %}`。

⚠️ **不要去 `core/jinja_env.py` 里硬加全局变量。** 那是核心单例，改了所有站点共用，
而且下次升级会把你覆盖掉。要加就写 `template_tags.py`。

- **老的 Liquid 兼容链路** → `core/template_engine.py` 只允许白名单 filter，
  `POST /api/v1/public/templates/render` 仍在服务 portal-web 的历史页面。
  已注册的 filter 在 `_register_filters` 里，新增要重启后端。

### Q7: 怎么调试模板？

**站点主题（Jinja2）** —— 后台「CMS → 模板工作台」在线编辑 + 实时预览，也可直接调接口：

| 接口 | 用途 |
|---|---|
| `POST /api/v1/cms/templates/preview-page` | 按主题上下文渲染整页（能调 `content_list` / `site` / `nav`） |
| `POST /api/v1/cms/templates/preview` | 渲染模板字符串，不抛错，给编辑器用 |
| `POST /api/v1/cms/templates/render` | 渲染模板字符串，失败抛 400 |
| `POST /api/v1/cms/templates/validate` | 语法校验，失败带 `line` / `col` |

**Liquid 兼容链路** —— 只剩 `POST /api/v1/public/templates/render` 一个端点
（免鉴权，服务 portal-web 的历史页面）。**不要用它写站点主题。**

> 预览 iframe 是 `sandbox=""`（禁脚本），主题里的 JS 改动**保存后才生效**。

### Q8: 多租户怎么实现？

平台当前的多站隔离靠 **`site_id`**（`cms_sites` 表，内容/分类/条目都带 `site_id`，
并有唯一约束 `uq_cms_entries_site_url_path`）。

`tenant_id` 只出现在 `auth_users` / `rbac` / 审计表上（默认 1，历史遗留软字段），
**不是多站点机制的载体**，不要拿它做隔离判定。

### Q9: 性能调优

- **JSONB**：`custom_fields` 已建 GIN 索引，避免全表扫
- **分类/标签**：复合索引 `(content_type_id, parent_id)`
- **JWT 解码**：单 token < 1ms，无需缓存
- **N+1**：用 `selectinload` 预加载（`content_engine_router.py` 已用）

### Q10: 插件页面白屏 / 菜单点了 403

按这三条查：

1. `plugin.js` 是否在 `static/apps/{key}/` 下，`GET /.app-assets/{key}/plugin.js` 是否 200
2. `frontend/dist/plugin.js` 里 `id` 是否等于 manifest 的 `key`
3. `routes[].meta.permission` 是否与后端权限码一致（403 多半是这里对不上）

浏览器控制台看 `__registerPlugin` 是否被调用、`routes` 是否注册成功。

### Q11: 生成器报「迁移图没有 head」

`--versions-dir` 指错了。它必须指向 `backend/alembic/versions`（父目录，生成器递归收集），
不能指到 `core/` 这种子目录。（2026-11-01 之前的版本只扫顶层，同样报这个错，升级后即可。）

---

## 附录

### A. 完整字段类型参考

```python
# apps/cms/field_types.py
FIELD_TYPES = [
    'text', 'longtext', 'richtext', 'markdown',    # 文本
    'number', 'boolean', 'date', 'datetime',        # 数字/布尔/日期
    'url', 'email', 'phone',                        # 联系
    'image', 'images', 'file', 'files',             # 媒体
    'select', 'multiselect',                        # 选择
    'color', 'json', 'repeater', 'relation',        # 高级
]
```

### B. API 文档

仅在 `DEBUG=True` 时可用：

- Swagger UI：`http://localhost:8002/api/docs`
- ReDoc：`http://localhost:8002/api/redoc`
- OpenAPI JSON：`http://localhost:8002/api/openapi.json`

生产环境默认关闭。

### C. 项目结构

```
cenkor-admin/
├── backend/
│   ├── alembic/
│   │   ├── versions/                # 按来源分目录：core / erp / crm / mes / commerce / ext
│   │   └── env.py
│   ├── src/cenkor_admin/
│   │   ├── apps/                    # App 中心（内置应用）
│   │   │   ├── base.py              #   AppManifest 定义
│   │   │   ├── cms/                 #   内容引擎
│   │   │   │   ├── field_types.py   #   字段类型枚举
│   │   │   │   ├── field_registry.py#   字段/内容类型注册器
│   │   │   │   ├── models.py
│   │   │   │   ├── router.py
│   │   │   │   ├── public_router.py
│   │   │   │   ├── template_router.py     # 模板工作台（Jinja2 主题）
│   │   │   │   ├── content_engine_router.py
│   │   │   │   └── cms_page_router.py     # /api/v1/page  HTML 直出
│   │   │   ├── auth/ rbac/ portal/ system/ notification/
│   │   │   └── crm/ erp/ mes/ workflow/ payment/ ...
│   │   ├── codegen/
│   │   │   └── builder.py           # 生成器核心（scripts/gen-app.py 是 CLI 薄封装）
│   │   ├── core/
│   │   │   ├── config.py  db.py  security.py
│   │   │   ├── jinja_env.py         # Jinja2 主题引擎
│   │   │   └── template_engine.py   # Liquid（仅兼容端点在用）
│   │   ├── static/apps/             # App 前端插件产物 → /.app-assets
│   │   ├── api/                     # 路由注册（api/v1/__init__.py 负责 App 自动挂载）
│   │   └── main.py
│   └── tests/
├── frontend/
│   ├── admin-web/                   # 后台 SPA
│   │   └── src/core/plugin.ts       #   插件管理器（动态加载 plugin.js）
│   ├── developer-web/               # 开发者门户
│   ├── portal-web/                  # C 端前台（含 cms-render.ts Liquid 兼容）
│   └── landing-web/                 # 落地页
├── scripts/
│   ├── gen-app.py                   # CRUD 代码生成器
│   ├── package-app.sh               # 打包 ZIP
│   ├── check-migration-graph.py      # 迁移图自检
│   ├── check-doc-facts.py           # 文档事实自检
│   └── sync-docs-to-knowledge.sh    # 文档站同步
├── docs/                            # ← 本文档所在
└── architecture.md
```
