# Cenkor Admin 应用开发规范

> 版本：1.2.0  
> 更新日期：2026-11-01
>
> **本文覆盖两类交付形态**（真相源：后端 `store_router.DEV_METHODS`）：
> - **第壹部分 · 平台内置应用**（`dev_method=platform`）：装进 cenkor-admin 自身，用 `manifest.py` + SQLAlchemy 模型 + alembic 迁移 + `frontend/dist/plugin.js` → 第二～十节。
> - **第贰部分 · 产品扩展包**（`dev_method=extension`）：热挂载到 MES 实例（cenkormes / cenkor-process），用 `manifest.json` + `router.py` + `migrations.sql` + `frontend/plugin.js` → 第十二～十八节。
>
> 若你开发的是**卖给 MES 客户的付费扩展**，直接跳到【第贰部分】。第十一节（product / dev_method）是两类共用的取值口径，先看它。
>
> 想跳过手写、直接起一个带 CRUD 的应用：`scripts/gen-app.py`，见
> [../dev_guide.md](../dev_guide.md) 的「五分钟起一个 App」。

## 一、概述

Cenkor Admin 支持通过应用（App）扩展平台功能。每个应用是一个独立的模块，可以：

- 注册新的内容类型和字段
- 添加后台管理页面（前端以 `plugin.js` 运行时挂载，**不改主程序**）
- 注册 API 路由（`router.py` 自动挂载到 `/api/v1/{key}`）
- 添加菜单和权限
- 提供公共 API

## 第壹部分 · 平台内置应用（dev_method=platform）

> 面向把功能装进 cenkor-admin 平台自身的内置应用。产品扩展包请看第贰部分。

## 二、应用结构

### 2.1 目录结构

手写一个最小应用只需两个文件；用生成器（`scripts/gen-app.py`）产出的是完整形态：

```
my_app/                          # key 用下划线，目录名同时是 Python 包名
├── manifest.py                  # 必需：应用清单
├── __init__.py                  # 必需：Python 包标识
├── models.py                    # 可选：数据库模型
├── router.py                    # 可选：后台 API（自动挂载到 /api/v1/{key}）
├── public_router.py             # 可选：免鉴权 API（⚠️ 不会自动挂载，见 §4.3）
├── schemas.py                   # 可选：Pydantic 模型
├── service.py                   # 可选：业务逻辑
├── hooks.py                     # 可选：插件钩子处理器
├── alembic/versions/            # 可选：本应用的迁移（package 模式）
├── frontend/                    # 可选：前端插件源码
│   ├── package.json
│   ├── vite.config.js           # 打包为 iife 单文件，vue 走 external
│   ├── dist/plugin.js           # ← 构建产物，平台运行时加载
│   └── src/main.js              # 入口：window.__registerPlugin({...})
└── release/                     # 打包产物（package-app.sh 生成，不进版本库）
```

> 应用内**不放** `static/`：前端产物统一落在平台级的
> `backend/src/cenkor_admin/static/apps/{key}/`，由 `/.app-assets` 暴露。

> ⚠️ **`key` 不要用连字符**：目录名即 Python 包名，且 `api/v1/__init__.py` 拿目录名
> 直接做路由前缀。全平台既有 App（`cloud_storage` / `my_todo` / `quick_notes`）
> 一律下划线小写。

> ⚠️ **商业闭源应用的存放位置有专门要求**（公开仓库不收录其源码），
> 见「九、安全规范 → 9.3 仓库边界与商业源码保护」。

### 2.2 manifest.py（必需）

每个应用必须在根目录定义 `manifest.py`，导出 `MANIFEST` 对象：

```python
"""我的应用 manifest"""
from cenkor_admin.apps.base import AppManifest

MANIFEST = AppManifest(
    # ---- 基础信息 ----
    key="my_app",                    # 唯一标识（小写英文 + 下划线；目录名即包名）
    name="我的应用",                  # 显示名称
    version="1.0.0",                 # 语义化版本号
    author="开发者名称",              # 作者
    description="应用描述",           # 简短描述
    icon="📦",                       # Emoji 图标
    category="productivity",         # 分类：business / productivity / content / system / ai

    # ---- 依赖 ----
    min_platform_version="0.1.0",    # 最低平台版本
    dependencies=[],                 # 依赖的其他 App key

    # ---- 权限 ----
    # 三段式 {app}:{resource}:{action}，管理级用两段 {app}:admin
    permissions_required=[
        "my_app:item:read",          # 读取权限
        "my_app:item:write",         # 写入权限
        "my_app:admin",              # 应用级管理权限
    ],

    # ---- 菜单 ----
    menus=[
        {
            "key": "my_app",
            "title": "我的应用",
            "icon": "box",           # 图标名称
            "sort": 70,              # 排序（数字越小越靠前）
            "children": [
                {"key": "my_app:item", "title": "数据列表", "path": "/my_app/items"},
            ],
        },
    ],

    # ---- 内容引擎（可选）----
    content_types=[
        {"key": "my_item", "name": "我的项目", "icon": "📋",
         "supports_category": True, "supports_tags": True},
    ],
    field_groups=[
        {"content_type": "my_item", "key": "basic", "label": "基础信息", "sort": 0},
    ],
    field_definitions=[
        {"content_type": "my_item", "key": "name", "label": "名称",
         "type": "text", "group": "basic", "required": True},
        {"content_type": "my_item", "key": "description", "label": "描述",
         "type": "richtext", "group": "basic"},
    ],
    categories_seed=[
        # 支持 children 嵌套，最多 3+ 级
        {"content_type": "my_item", "slug": "general", "name": "通用"},
    ],

    # ---- 公共 API 前缀 ----
    # ⚠️ 仅是元数据（写进 App 注册信息供商店展示），不参与路由挂载。
    public_routes_prefix="/api/v1/my_app",

    # ---- 高级（可选）----
    license_required=False,          # True：未授权一律 402（商店收费应用）
    price_model="free",              # free / one_time / seat
    price_cents=0,
    period_days=365,                 # 仅 seat 生效
    schema_managed=False,            # True：本应用的表由 apps/<key>/schema.sql 管理
    hooks=[],                        # 钩子模块 dotted path，缺省试 apps.<key>.hooks
)
```

## 三、字段类型

| 类型 | 说明 | 存储格式 |
|------|------|----------|
| `text` | 单行文本 | string |
| `longtext` | 多行文本 | string |
| `richtext` | 富文本（HTML） | string |
| `markdown` | Markdown | string |
| `number` | 数字 | number |
| `boolean` | 布尔 | boolean |
| `date` | 日期 | "YYYY-MM-DD" |
| `datetime` | 日期时间 | ISO 8601 |
| `color` | 颜色 | "#hex" |
| `url` | URL | string |
| `email` | 邮箱 | string |
| `phone` | 电话 | string |
| `image` | 单图（URL） | string |
| `images` | 多图（URL 数组） | string[] |
| `file` | 单文件（URL） | string |
| `files` | 多文件（URL 数组） | string[] |
| `select` | 单选 | string |
| `multiselect` | 多选 | string[] |
| `json` | JSON | any |
| `repeater` | 重复子项 | array |
| `relation` | 关联其他内容 | number (ID) |

## 四、API 路由

### 4.1 路由文件

在 `router.py` 中定义 FastAPI 路由：

```python
"""我的应用 API 路由"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.core.db import get_db
from . import models          # 推荐相对导入

router = APIRouter()


@router.get("/items", response_model=dict)
async def list_items(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("my_app:item:read")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """获取列表"""
    # 你的业务逻辑
    return {"items": [], "total": 0}


@router.post("/items", status_code=201)
async def create_item(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("my_app:item:write")),
):
    """创建"""
    # 你的业务逻辑
    return {"id": 1}
```

### 4.2 自动挂载规则（必读）

平台在启动时扫描 `apps/` 自动挂载路由，规则不直观：

- 扫描**不以 `_` 开头**的目录
- **只识别 `router.py`**，其余文件一律不管
- 挂载前缀 `/api/v1/{目录名}`，并统一加三道守卫：
  1. `get_current_user` —— **必须登录**（默认就不允许匿名）
  2. `app_enabled_dependency(key)` —— 应用被停用则拒绝
  3. 你在路由里自己写的 `require_permission(...)`

所以 `router.py` 里的路径**不要**再带一次前缀：

```python
@router.get("/items")      # ✅ 实际地址 /api/v1/my_app/items
@router.get("/my_app/items")  # ❌ 变成 /api/v1/my_app/my_app/items
```

### 4.3 `public_router.py` 不会自动挂载

**这是最容易误判的一条。** 放在 `apps/{key}/public_router.py` 里的路由**不会出现**
在 API 上 —— 自动发现只找 `router.py`。

要提供免鉴权接口，只能由主程序手工 include（平台内置 App 的做法，属形态 B）：

```python
# backend/src/cenkor_admin/api/v1/__init__.py
from cenkor_admin.apps.my_app.public_router import router as my_app_public
api_v1_router.include_router(my_app_public, prefix="/public", tags=["my_app"])
```

> `manifest.public_routes_prefix` **只是元数据**（写进 App 注册信息供商店展示），
> **不参与任何路由挂载**。填了它，接口不会自动暴露。

### 4.4 权限命名规范

平台实际使用**三段式** `{app}:{resource}:{action}`，应用级管理用两段式：

```
{app}:{resource}:read      # 读取      my_app:item:read
{app}:{resource}:write     # 写入      my_app:item:write
{app}:{resource}:delete    # 删除      my_app:item:delete
{app}:{resource}:export    # 导出      my_app:item:export
{app}:admin                # 应用级管理 my_app:admin
```

参照线上既有取值：`crm:customer:read` / `crm:customer:export` / `crm:admin`。

两段式写法（`my_app:read`）功能上能跑，但与全平台既有权限码风格不一致，
RBAC 授权页会显得混乱。**跟着三段式走。**

### 4.5 前端插件

应用的前端**不是**往 `frontend/admin-web/src/views/` 里加页面（那是改主程序，
会被平台升级覆盖），而是产出 `frontend/dist/plugin.js`，由平台运行时动态加载：

```
后台启动 → GET /api/v1/system/apps/plugins → 注入
<script src="/.app-assets/{key}/plugin.js?v={mtime}">
plugin.js 执行 → window.__registerPlugin({ id, routes, menus, locales })
→ 合并进 admin-web 路由表 / 侧边栏 / i18n
```

最小入口：

```js
// frontend/src/main.js
import 'vue'        // 共享宿主的 window.Vue，不要 inline 一份
import ItemListView from './pages/ItemListView.vue'

window.__registerPlugin({
  id: 'my_app',                    // 必须等于 manifest 的 key
  version: '1.0.0',
  name: '我的应用',
  routes: [
    { path: 'my_app/items', name: 'my-app-items', component: ItemListView,
      meta: { permission: 'my_app:item:read' } },   // 与后端权限码一致
  ],
  menus: [
    { key: 'my_app:item', title: '数据列表', path: '/my_app/items', icon: 'menu', sort: 71 },
  ],
  locales: { 'zh-CN': { my_app: { title: '我的应用' } } },
})
```

构建必须把 `vue` 设为 external，否则插件内会 inline 一份 Vue，响应式失效：

```js
// frontend/vite.config.js
build: {
  lib: { entry: 'src/main.js', formats: ['iife'], name: 'MyAppPlugin', fileName: () => 'plugin.js' },
  rollupOptions: { external: ['vue'], output: { globals: { vue: 'Vue' }, inlineDynamicImports: true } },
}
```

调接口用平台注入的 `window.__PLUGIN_API__(method, path, body)`（自带 401 自动刷新
token），不要自己 `new fetch` 拼 token。

产物部署到：

```
backend/src/cenkor_admin/static/apps/{key}/plugin.js
```

由后端 `app.mount("/.app-assets", StaticFiles(...))` 暴露。改完前端**不用重启后端**，
浏览器强刷即可（脚本按 `?v=<mtime>` 拉取）。

> 完整链路（含 `__PLUGIN_NAV__`、兜底 token、菜单/路由对齐三要素）见
> [../dev_guide.md](../dev_guide.md) 的「前端：插件机制」。

## 五、数据模型

### 5.1 模型文件

在 `models.py` 中定义 SQLAlchemy 模型：

```python
"""我的应用模型"""
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from cenkor_admin.core.db import Base


class MyItem(Base):
    __tablename__ = "my_app_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    creator_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

### 5.2 命名规范

| 项目 | 规范 | 示例 |
|------|------|------|
| 表名 | `{app_key}_{plural}` | `my_app_items` |
| 模型名 | `{Singular}` | `MyItem` |
| 字段名 | `snake_case` | `created_at` |
| 索引 | `ix_{table}_{column}` | `ix_my_app_items_creator_id` |

## 六、数据库迁移

> 迁移图分公开链与商业应用闭源链，靠挂载点串联。**会进开源仓库的迁移必须插在
> 挂载点 `gen_inventory` 之前**；`alembic revision --autogenerate` 生成的
> `down_revision` 默认是当前 head（闭源部署里是闭源 head），必须手工改成公开 revision。
> 完整规则与执行顺序见 [migrations.md](../migrations.md)。

### 6.1 创建迁移文件

迁移目录**按来源分层**（`alembic.ini` 的 `version_locations` 逐条列出：
`core` / `erp` / `crm` / `mes` / `commerce` / `ext`），新建时用 `--version-path`
显式指定落点，别放到扁平路径下：

```bash
cd backend
PYTHONPATH=src alembic revision --autogenerate -m "create my_app tables" \
  --version-path alembic/versions/ext

alembic upgrade heads
bash ../scripts/check-migration-graph.py     # 断链 / 重复 / 多 head 自检
```

> 用代码生成器（`scripts/gen-app.py`）建应用时，迁移会自动生成并接好
> `down_revision`，不需要手工走这一步。

### 6.2 迁移文件模板

```python
"""create my_app tables

Revision ID: 20260611_1500_my_app
Revises: <上一个迁移ID>
Create Date: 2026-06-11 15:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "20260611_1500_my_app"
down_revision = "<上一个迁移ID>"


def upgrade():
    op.create_table(
        "my_app_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(200), nullable=False, index=True),
        # ... 其他字段
    )


def downgrade():
    op.drop_table("my_app_items")
```

## 七、打包规范

### 7.1 ZIP 包结构

用 `bash scripts/package-app.sh <key> [version]` 打包，产物在
`apps/<key>/release/<key>-<version>.zip`：

```
my_app-1.0.0.zip
├── manifest.py
├── __init__.py
├── models.py
├── router.py
├── schemas.py
├── service.py
├── alembic/versions/          # 本应用的迁移（package 模式）
├── frontend/dist/plugin.js    # 前端插件产物
└── requirements.txt           # 可选：额外依赖
```

打包时自动排除 `node_modules`、`release`、`__pycache__`、`.git`。
前端若定义了 `build` 脚本，打包前会先构建，保证 `dist` 与源码一致。

### 7.2 打包要求

1. **文件编码**：UTF-8
2. **Python 版本**：3.11+
3. **依赖管理**：如需额外依赖，在 `requirements.txt` 中声明
4. **无恶意代码**：禁止执行系统命令、访问敏感文件
5. **manifest 完整**：所有必需字段必须填写

### 7.3 用户手册（上架必带）

**每个应用都必须配一份面向使用者的操作手册**，放在：

```
docs/05-用户手册/<应用 key>_操作手册.md
```

例如工作流应用的就是 `docs/05-用户手册/workflow_操作手册.md`。

**为什么必须放这个目录**：文档站的侧栏对 `NN-中文名/` 这种**数字前缀目录**是
**原样列出、不做任何过滤**的；而放在 `docs/` 根级的散文档，必须命中技术分组关键词才显示，
文件名里带「教程」「使用指南」之类还会被**主动排除、静默消失**（不报错）。
所以用户手册只能放 `05-用户手册/`，不要放根级。

**写什么** —— 按「用户在界面上实际点的位置」写，不是按代码结构写：

1. **这个应用解决什么问题** —— 一两句 + 几个典型场景；
2. **从哪儿进** —— 左侧菜单名与子菜单，标明哪个角色用得到；
3. **跑通一次的最短路径** —— 编号步骤，每步说清「点哪里 → 看到什么 → 填什么」；
4. **日常操作速查** —— 每个按钮/动作干什么；
5. **进阶用法** —— 条件、分支、并发之类的能力边界；
6. **权限对照** —— 哪个功能需要什么权限码；
7. **常见问题** —— 用户真正会踩的坑（如「为什么提交了对方却没收到待办」）。

**命名约定**：`<key>_操作手册.md`，`key` 与 `manifest.py` 里的 `key` 一致 ——
同步脚本据此检查覆盖度。

**显示名**：侧栏标题取自去掉 `.md` 的文件名，所以还要在知识库站点的
`config.mts` 的 `TITLE_MAP` 里补一条映射（如 `workflow_操作手册` → `工作流审批 · 操作手册`），
否则侧栏会显示成带下划线的原始文件名。

> 同步脚本 `scripts/sync-docs-to-knowledge.sh` **每次构建前都会列出还没有手册的应用**。
> 目前只警告、不阻断构建（手册是逐步补齐的），等覆盖齐了可改成硬性关卡。

## 八、安装流程

1. 开发者上传 ZIP 包
2. 系统解压并校验 `manifest.py`
3. 检查 `key` 唯一性
4. 检查 `version` 格式
5. 检查依赖是否满足
6. 将应用代码放入 `apps/{key}/`
7. 前端产物放入 `static/apps/{key}/`（`plugin.js` 由 `/.app-assets` 暴露）
8. 执行数据库迁移（如有新表）
9. 注册权限和菜单（启动流程自动完成，无需手工 install）
10. 应用状态变为 `installed`

> 装完后前端插件会在下次打开后台时自动加载，**不需要重新构建 admin-web**。

## 九、安全规范

### 9.1 禁止事项

- 禁止 `os.system()`、`subprocess` 等系统调用
- 禁止 `open()` 访问 `apps/` 目录外的文件
- 禁止导入 `cenkor_admin.core.config` 以外的配置
- 禁止修改其他应用的数据
- 禁止在 manifest 中声明过高的权限

### 9.2 沙箱限制

- 应用代码运行在主进程内（非独立进程）
- 数据库操作通过 SQLAlchemy ORM
- 文件操作限制在 `apps/{key}/` 目录
- 网络请求仅允许 HTTPS

### 9.3 仓库边界与商业源码保护

平台仓库是**公开仓库**，因此「文件放在哪」直接决定它会不会被公开。

#### 两条落点

| 落点 | 忽略机制 | 用途 |
|---|---|---|
| `backend/src/apps/<key>/`（**外置**） | `.gitignore` 目录级整体忽略 | **商业闭源应用一律放这里** |
| `backend/src/cenkor_admin/apps/<key>/`（**内置**） | 默认进公开仓库，闭源须逐条登记 | 开源应用 |

放外置目录时，前端产物与数据库迁移仍落在被跟踪的目录里，故仍需单独登记 ——
写法参照 `.gitignore` 中 `commerce` / `payment` 两段。

#### 放内置目录时的登记清单（三条，缺一不可）

```bash
backend/src/cenkor_admin/apps/<key>/           # 后端源码
backend/src/cenkor_admin/static/apps/<key>/    # 前端产物（plugin.js 常有 MB 级）
backend/alembic/versions/<目录>/*_<key>*.py     # 数据库迁移
```

> ⚠️ 迁移已**按来源分目录**（`core` / `erp` / `crm` / `mes` / `commerce` / `ext`），
> 登记时写具体目录（如 `backend/alembic/versions/ext/*_<key>*.py`），
> **不要沿用老的扁平路径 `backend/alembic/versions/2026*_<key>*.py`** ——
> 升到分层布局后那条 glob 匹配不到任何文件，等于没登记（源码会被推到公开仓库）。

#### ⚠️ 新增 ignore 规则后，必须回头查历史

`.gitignore` 与 `git rm` **只管未来**。文件从工作区删掉 ≠ 从历史消失 ——
`git clone` 会拉取全部历史对象。

三条命令，缺一不可：

```bash
git ls-tree -r HEAD --name-only | grep <path>        # ① 当前快照
git rev-list --objects --all | grep <path>           # ② 历史对象 ← 关键
git rev-list --objects origin/main | grep <path>     # ③ 是否已推到远端
```

⚠️ **不要用 `git log --all -- <路径>` 下结论**：它只列出触碰过该路径的提交，
**看不到仍被引用的旧 blob**。曾据此误判「文件移除了就干净了」。

若 ② 有命中且 ③ 也有命中，说明源码**已进入公开仓库历史**：

- **只 `force push` 清不掉** —— GitHub 要求 commit 完全无引用后才由 Support 执行 GC，
  dangling commit 可保留数年；旧快照仍可经
  `codeload.github.com/<owner>/<repo>/tar.gz/<旧SHA>` 下载。
- 可选处置：① **删除仓库重建**（旧 commit 立即 404，实测有效）；
  ② 联系 GitHub Support 请求 GC。
  删库前先看仓库资产（stars / forks / issues），**零资产可直接重建**。

#### 提交前自检

仓库已装 pre-commit hook：扫出「既没被 git 跟踪、也没被 .gitignore 忽略」的应用目录，
并**阻断提交**。

```bash
bash scripts/check-app-tracking.sh      # 手动运行，有问题时退出码 1
git config core.hooksPath .githooks     # ⚠️ 新 clone 后必须执行一次，否则 hook 不生效
```

## 十、示例应用

带 `manifest.py` 的完整参考实现（从简单到复杂）：

| 应用 | 适合看什么 |
|---|---|
| `apps/links/` | 最简单的 CRUD 起步 |
| `apps/announcements/` | 公告：内容 + 发布状态 |
| `apps/tickets/` | 工单：状态流转、分派 |
| `apps/quick_notes/` / `apps/my_todo/` | 轻量工具类、前端插件写法 |
| `apps/cloud_storage/` | 文件上传 + 外部存储对接 |
| `apps/crm/` | 多实体 + 权限细分 + 前端插件（`plugin.js` 在产线跑） |
| `apps/erp/` / `apps/mes/` | 大型业务模块，迁移分目录的样板 |
| `apps/cms/` | 内容引擎与模板工作台本体，扩展字段前先读它 |

> 想快速起一个带 CRUD 的新应用，直接用 `scripts/gen-app.py`，
> 产出的代码即是按上述规范生成的（见 [../dev_guide.md](../dev_guide.md)
> 的「五分钟起一个 App」）。

## 十一、产品类型与开发方式（product / dev_method）

统一门户 / 商店 / 审核 / manifest 四处必须对以下两个维度取值一致，真相源是后端
`store_router.ALLOWED_PRODUCTS` 与 `store_router.DEV_METHODS`，前端各 app 收敛到 `src/lib/products.ts`。

### 11.1 产品类型 product（归属哪个产品 / 分发隔离）
允许值（slug 全链路必须完全一致）：

| slug | 含义 |
|---|---|
| `cenkor-admin` | Cenkor 平台（自营） |
| `cenkormes` | CenkorMES 离散制造 |
| `lightmes` | LightMES |
| `cenkor-process` | CenkorProcess 食品/流程制造（food.mes.cenkor.cn） |

### 11.2 应用开发方式 dev_method（交付安装目标，取代旧的 `product != cenkor-admin` 隐式判定）

| 取值 | 交付安装目标 | 包内必需 | 安装去向 |
|---|---|---|---|
| `platform` | 平台内置应用 | `manifest.py` + `__init__.py` | 装进 cenkor-admin 自身，审核通过后可直接「安装」 |
| `extension` | 产品扩展插件 | `manifest.json`（`key` 与提交一致） | 热挂载到对应 MES 实例；审核端不显示安装按钮，提示「需在 {产品} 实例安装」 |
| `standalone` | 独立应用 | `manifest.json` 或 `README` | 私有化整包，仅门户展示 / 售卖，不做安装向强校验 |

### 11.3 扩展包 manifest.json 字段规范
产品扩展（`dev_method=extension`）的 `manifest.json` 除 `key/name/version/permissions/menus` 外，
应携带：

```json
{
  "product": "cenkor-process",
  "dev_method": "extension"
}
```

后端 `submit_app` 会校验：
- `product ∈ ALLOWED_PRODUCTS`、`dev_method ∈ DEV_METHODS`，否则 400；
- 扩展包若 `manifest.json` 声明了 `product`，必须等于提交时所选 `product`，否则 400
  （避免「提交归 A 产品、包内写 B 产品」的漂移）。

> MES 宿主（cenkor-process / cenkormes）的 `extension_host/manifest.py load_manifest()`
> 为白名单解析、忽略未知键，因此新增 `product`/`dev_method` 不影响宿主加载。
