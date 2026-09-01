<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
const activeTab = ref<'overview' | 'backend' | 'frontend' | 'publish'>('overview')
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200 sticky top-0 z-30">
      <div class="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <router-link to="/" class="flex items-center gap-2">
            <img src="/logo.svg" class="w-7 h-7 rounded-lg" width="28" height="28">
            <span class="font-semibold text-sm">Cenkor Developer</span>
          </router-link>
          <span class="text-ink-300">/</span>
          <span class="text-sm text-ink-500">开发文档</span>
        </div>
        <div class="flex items-center gap-4">
          <router-link to="/" class="text-sm text-ink-600 hover:text-ink-900">首页</router-link>
          <router-link to="/store" class="text-sm text-ink-600 hover:text-ink-900">商店</router-link>
          <router-link to="/login" class="btn-ghost text-sm">登录</router-link>
          <router-link to="/register" class="btn-primary text-sm">注册</router-link>
        </div>
      </div>
    </header>

    <main class="max-w-5xl mx-auto px-6 py-10">
      <div class="bg-white border border-ink-200 rounded-2xl p-8 md:p-12">
        <div class="mb-8">
          <h1 class="text-3xl font-bold tracking-tight mb-3">应用开发规范</h1>
          <p class="text-ink-500">了解如何为 Cenkor Admin 开发真正可插拔的应用（后端 + 前端）</p>
        </div>

        <div class="flex gap-1 mb-8 p-1 bg-ink-100 rounded-lg w-fit flex-wrap">
          <button
            class="px-4 py-2 rounded-md text-sm font-medium transition-colors"
            :class="activeTab === 'overview' ? 'bg-white text-ink-900 shadow-sm' : 'text-ink-500 hover:text-ink-700'"
            @click="activeTab = 'overview'"
          >概述</button>
          <button
            class="px-4 py-2 rounded-md text-sm font-medium transition-colors"
            :class="activeTab === 'backend' ? 'bg-white text-ink-900 shadow-sm' : 'text-ink-500 hover:text-ink-700'"
            @click="activeTab = 'backend'"
          >后端开发</button>
          <button
            class="px-4 py-2 rounded-md text-sm font-medium transition-colors"
            :class="activeTab === 'frontend' ? 'bg-white text-ink-900 shadow-sm' : 'text-ink-500 hover:text-ink-700'"
            @click="activeTab = 'frontend'"
          >前端开发</button>
          <button
            class="px-4 py-2 rounded-md text-sm font-medium transition-colors"
            :class="activeTab === 'publish' ? 'bg-white text-ink-900 shadow-sm' : 'text-ink-500 hover:text-ink-700'"
            @click="activeTab = 'publish'"
          >打包与发布</button>
        </div>

        <!-- ==================== 概述 ==================== -->
        <div v-if="activeTab === 'overview'">
          <nav class="mb-10 p-4 bg-ink-50 rounded-xl">
            <h3 class="text-sm font-semibold text-ink-700 mb-2">目录</h3>
            <ul class="text-sm space-y-1 text-ink-600">
              <li><a href="#arch" class="hover:text-ink-900 hover:underline">1. 架构</a></li>
              <li><a href="#lifecycle" class="hover:text-ink-900 hover:underline">2. 应用生命周期</a></li>
              <li><a href="#zip-structure" class="hover:text-ink-900 hover:underline">3. 提交包结构</a></li>
            </ul>
          </nav>

          <section id="arch" class="mb-10">
            <h2 class="text-xl font-semibold mb-4 pb-2 border-b">1. 架构</h2>
            <p class="text-ink-600 mb-4">
              Cenkor Admin 的应用是<strong>真正可插拔的</strong> —— 安装时无需修改平台源码，所有功能动态注册。
            </p>
            <div class="grid md:grid-cols-2 gap-6 mb-6">
              <div class="bg-blue-50 rounded-xl p-5">
                <h3 class="font-medium text-blue-800 mb-2">后端 Python 包</h3>
                <ul class="text-sm text-blue-700 space-y-1">
                  <li>• 独立目录在 <code>apps/&lt;key&gt;/</code></li>
                  <li>• 安装后路由 <strong>自动注册</strong>到 <code>/api/v1/</code></li>
                  <li>• 权限 / 菜单 / 内容类型自动注册</li>
                  <li>• 无需修改 <code>api/v1/__init__.py</code></li>
                </ul>
              </div>
              <div class="bg-green-50 rounded-xl p-5">
                <h3 class="font-medium text-green-800 mb-2">前端 plugin.js 包</h3>
                <ul class="text-sm text-green-700 space-y-1">
                  <li>• Vite library mode 构建产物</li>
                  <li>• 运行时通过 <code>window.__registerPlugin()</code> 注册</li>
                  <li>• 自动添加路由 / i18n / 菜单到 admin-web</li>
                  <li>• 无需修改 admin-web 源码或重新构建</li>
                </ul>
              </div>
            </div>
            <p class="text-ink-600 mb-4">关键机制：</p>
            <div class="bg-ink-900 text-ink-100 p-5 rounded-xl text-sm font-mono leading-relaxed">
              后端：apps/&lt;key&gt;/router.py ──→ api/v1 自动 include_router<br>
              前端：plugin.js ──→ __registerPlugin() ──→ PluginManager 动态注入<br>
              部署：安装 ZIP 时 backend + frontend/dist 分别部署
            </div>
          </section>

          <section id="lifecycle" class="mb-10">
            <h2 class="text-xl font-semibold mb-4 pb-2 border-b">2. 应用生命周期</h2>
            <div class="space-y-3 text-sm">
              <div class="flex gap-3 items-start">
                <span class="w-7 h-7 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center shrink-0 font-semibold text-xs">1</span>
                <div><strong>开发</strong> — 创建后端 Python 包 + 前端 Vite library 项目</div>
              </div>
              <div class="flex gap-3 items-start">
                <span class="w-7 h-7 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center shrink-0 font-semibold text-xs">2</span>
                <div><strong>打包</strong> — 将两个部分合并为 ZIP（含 <code>frontend/dist/</code>）</div>
              </div>
              <div class="flex gap-3 items-start">
                <span class="w-7 h-7 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center shrink-0 font-semibold text-xs">3</span>
                <div><strong>提交</strong> — 在 dev.cenkor.cn 上传 ZIP 到商店</div>
              </div>
              <div class="flex gap-3 items-start">
                <span class="w-7 h-7 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center shrink-0 font-semibold text-xs">4</span>
                <div><strong>审核</strong> — 管理员审核通过后标记为 <code>approved</code></div>
              </div>
              <div class="flex gap-3 items-start">
                <span class="w-7 h-7 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center shrink-0 font-semibold text-xs">5</span>
                <div><strong>安装</strong> — 管理员在后台安装：<br>
                  后端 → 复制到 <code>src/apps/&lt;key&gt;/</code>，自动注册<br>
                  前端 → 复制到 <code>static/apps/&lt;key&gt;/</code>，admin-web 动态加载</div>
              </div>
            </div>
          </section>

          <section id="zip-structure" class="mb-10">
            <h2 class="text-xl font-semibold mb-4 pb-2 border-b">3. 提交包结构</h2>
            <p class="text-ink-600 mb-4">一个完整的应用 ZIP 包含后端和前端两部分：</p>
            <pre class="bg-ink-900 text-ink-100 p-5 rounded-xl text-sm overflow-x-auto font-mono leading-relaxed">my-app-1.0.0.zip
├── __init__.py               # 必需：Python 包标识
├── manifest.py               # 必需：应用清单
├── router.py                 # 必需：API 路由（应用必须有至少一个）
├── models.py / models/       # 可选：数据模型（单文件或 models/ 分包均可）
├── schemas.py                # 可选：请求/响应模型
├── service.py                # 可选：业务逻辑
├── requirements.txt          # 可选：额外依赖
│
├── alembic/                  # 可选：数据库迁移目录
│   └── versions/             #   安装时自动拷贝到平台迁移目录并执行 upgrade
│       └── *.py
│
├── frontend/                 # 可选：前端资源目录
│   └── dist/
│       ├── plugin.js         # 必需前端入口（Vite library mode 构建产物）
│       └── ...               # 其他静态资源（CSS、字体等）</pre>
            <p class="text-sm text-ink-500 mt-2">
              不含前端则只需提交 <code>__init__.py + manifest.py</code> 两个必需文件；
              不含迁移则无需 <code>alembic/</code>。安装后 <code>hasFrontend</code> 自动标记为 true；
              若 ZIP 含 <code>alembic/versions/*.py</code>，安装时会自动 <code>upgrade head</code> 建表。
            </p>
          </section>
        </div>

        <!-- ==================== 后端开发 ==================== -->
        <div v-if="activeTab === 'backend'">
          <nav class="mb-10 p-4 bg-ink-50 rounded-xl">
            <h3 class="text-sm font-semibold text-ink-700 mb-2">目录</h3>
            <ul class="text-sm space-y-1 text-ink-600">
              <li><a href="#bk-manifest" class="hover:text-ink-900 hover:underline">1. manifest.py 详解</a></li>
              <li><a href="#bk-model" class="hover:text-ink-900 hover:underline">2. 数据模型</a></li>
              <li><a href="#bk-api" class="hover:text-ink-900 hover:underline">3. API 路由</a></li>
              <li><a href="#bk-content-engine" class="hover:text-ink-900 hover:underline">4. 内容引擎集成</a></li>
              <li><a href="#bk-migration" class="hover:text-ink-900 hover:underline">5. 数据库迁移</a></li>
              <li><a href="#bk-security" class="hover:text-ink-900 hover:underline">6. 安全规范</a></li>
            </ul>
          </nav>

          <section id="bk-manifest" class="mb-10">
            <h2 class="text-xl font-semibold mb-4 pb-2 border-b">1. manifest.py 详解</h2>
            <p class="text-ink-600 mb-4">每个 App 必须在根目录定义 <code>manifest.py</code>，导出 <code>MANIFEST</code> 实例：</p>
            <pre class="bg-ink-900 text-ink-100 p-5 rounded-xl text-sm overflow-x-auto font-mono leading-relaxed">from cenkor_admin.apps.base import AppManifest

MANIFEST = AppManifest(
    # === 基础信息 ===
    key="my_app",                    # 唯一标识：小写字母+下划线，2-50位（Python 模块名要求，禁用连字符）
    name="我的应用",                  # 显示名称
    version="1.0.0",                 # 语义化版本号
    author="开发者名称",              # 作者
    description="应用描述",           # 简短描述
    icon="📦",
    category="productivity",         # 分类：content / productivity / system / ai
    min_platform_version="0.1.0",
    dependencies=[],

    # === 权限 ===
    permissions_required=["my-app:read", "my-app:write"],

    # === 菜单（安装后自动注册到侧边栏） ===
    menus=[{
        "key": "my-app",
        "title": "我的应用",
        "icon": "box",
        "sort": 70,
        "children": [
            {"key": "my-app:list", "title": "数据列表", "path": "/my-app"},
        ],
    }],

    # === 内容引擎声明（可选） ===
    content_types=[],
    field_groups=[],
    field_definitions=[],
    categories_seed=[],

    # === 公共 API 前缀 ===
    public_routes_prefix="/api/v1/public/my-app",
)</pre>
            <p class="text-sm text-ink-500 mt-2">
              <code>menus</code> 中的 <code>path</code> 对应前端路由地址（如 <code>/my-app</code>），
              安装后自动绑定到超级管理员角色。
            </p>
          </section>

          <section id="bk-model" class="mb-10">
            <h2 class="text-xl font-semibold mb-4 pb-2 border-b">2. 数据模型</h2>
            <p class="text-ink-600 mb-4">使用 SQLAlchemy 2.0 声明式映射 + async：</p>
            <div class="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-4">
              <p class="text-sm text-blue-800">
                💡 <strong>模型可以封装为 <code>models/</code> 目录</strong>（复杂应用推荐）：包内放 <code>models/__init__.py</code> 作统一导出，
                其余模型按模块拆分（如 <code>models/sales.py</code>、<code>models/product.py</code>）。
                安装时整目录原样复制，功能与单文件 <code>models.py</code> 完全一致。
              </p>
            </div>
            <pre class="bg-ink-900 text-ink-100 p-5 rounded-xl text-sm overflow-x-auto font-mono leading-relaxed">from datetime import datetime
from sqlalchemy import String, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from cenkor_admin.core.db import Base

class MyItem(Base):
    __tablename__ = "my_app_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
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
    )</pre>

            <h3 class="font-medium mt-6 mb-2">命名规范</h3>
            <table class="w-full text-sm border border-ink-200 rounded-xl">
              <thead class="bg-ink-50"><tr><th class="px-4 py-2.5 text-left font-medium">项目</th><th class="px-4 py-2.5 text-left font-medium">规范</th><th class="px-4 py-2.5 text-left font-medium">示例</th></tr></thead>
              <tbody class="divide-y divide-ink-100">
                <tr><td class="px-4 py-2">表名</td><td><code>{app_key}_{plural}</code></td><td><code>my_app_items</code></td></tr>
                <tr><td class="px-4 py-2">模型名</td><td>PascalCase 单数</td><td><code>MyItem</code></td></tr>
                <tr><td class="px-4 py-2">模型文件</td><td><code>models.py</code> 或 <code>models/</code> 目录（含 <code>__init__.py</code>）</td><td><code>models.py</code> / <code>models/sales.py</code></td></tr>
                <tr><td class="px-4 py-2">删除</td><td>软删 <code>deleted_at</code></td><td>不要物理删除</td></tr>
                <tr><td class="px-4 py-2">创建人</td><td><code>creator_id</code></td><td>关联操作者 ID</td></tr>
              </tbody>
            </table>
          </section>

          <section id="bk-api" class="mb-10">
            <h2 class="text-xl font-semibold mb-4 pb-2 border-b">3. API 路由</h2>
            <p class="text-ink-600 mb-2">
              创建 <code>router.py</code>，使用 FastAPI <code>APIRouter</code>。
              <strong>路由会自动注册到 <code>/api/v1/&lt;app-key&gt;/</code></strong>。
            </p>
            <div class="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-4">
              <p class="text-sm text-blue-800">
                💡 <strong>多模块拆分可用多个子路由文件</strong>（复杂应用推荐）：如 <code>sp_router.py</code>、<code>so_router.py</code>。
                在根 <code>router.py</code> 顶部把它们 <code>include_router</code> 汇入主路由。平台只自动注册 <code>router.py</code>，子路由不会单独注册。
                注意避免子路由之间互相 <code>from . import xxx</code>（会造成循环导入），跨模块复用直接 <code>from .models.xxx import ...</code>。
              </p>
            </div>
            <pre class="bg-ink-900 text-ink-100 p-5 rounded-xl text-sm overflow-x-auto font-mono leading-relaxed">from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.my_app import models  # 或 from . import models
from cenkor_admin.core.db import get_db

router = APIRouter()

@router.get("")
async def list_items(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("my-app:read")),
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    stmt = select(models.MyItem).where(models.MyItem.deleted_at.is_(None))
    if search:
        stmt = stmt.where(models.MyItem.title.ilike(f"%{search}%"))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    stmt = stmt.order_by(models.MyItem.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return {"items": [item_to_dict(i) for i in items], "total": total}

@router.post("", status_code=201)
async def create_item(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("my-app:write")),
):
    obj = models.MyItem(**body, creator_id=current.id)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id}

@router.patch("/{item_id}")
async def update_item(
    item_id: int, body: dict,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("my-app:write")),
):
    obj = await db.get(models.MyItem, item_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "不存在")
    for k, v in body.items():
        if hasattr(obj, k):
            setattr(obj, k, v)
    await db.commit()
    return {"id": obj.id}

@router.delete("/{item_id}", status_code=204)
async def delete_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("my-app:write")),
):
    obj = await db.get(models.MyItem, item_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "不存在")
    obj.deleted_at = datetime.now()
    await db.commit()</pre>

            <div class="bg-green-50 border border-green-200 rounded-xl p-4 mt-4">
              <p class="text-sm text-green-800">
                ✅ <strong>无需手动注册路由</strong>。系统启动时会自动扫描 <code>apps/*/router.py</code>，
                将 <code>router</code> 变量注册到 <code>/api/v1/&lt;app-key&gt;/</code> 前缀下。
                无需修改 <code>api/v1/__init__.py</code>。
              </p>
            </div>

            <div class="bg-amber-50 border border-amber-200 rounded-xl p-4 mt-4">
              <p class="text-sm text-amber-800">
                ⚠️ <strong>导入规范</strong>：<code>router.py</code> 中引用自己的 models 必须使用
                <code>from cenkor_admin.apps.&lt;app_key&gt; import models</code>
                或 <code>from . import models</code>。
                <strong>禁止</strong>使用 <code>from apps.xxx import ...</code>，
                因为安装后应用位于 <code>cenkor_admin/apps/</code> 下，<code>apps.xxx</code> 路径不存在。
              </p>
            </div>

            <h3 class="font-medium mt-6 mb-2">权限命名规范</h3>
            <table class="w-full text-sm border border-ink-200 rounded-xl">
              <thead class="bg-ink-50"><tr><th class="px-4 py-2.5 text-left font-medium">权限名</th><th class="px-4 py-2.5 text-left font-medium">用法</th></tr></thead>
              <tbody class="divide-y divide-ink-100">
                <tr><td><code>{app-key}:read</code></td><td>列表和详情查看</td></tr>
                <tr><td><code>{app-key}:write</code></td><td>创建、更新、删除</td></tr>
              </tbody>
            </table>
          </section>

          <section id="bk-content-engine" class="mb-10">
            <h2 class="text-xl font-semibold mb-4 pb-2 border-b">4. 内容引擎集成</h2>
            <p class="text-ink-600 mb-4">
              支持 App 声明自定义内容类型、字段定义和分类。安装时自动注册到 <code>cms_*</code> 表。
            </p>
            <pre class="bg-ink-900 text-ink-100 p-5 rounded-xl text-sm overflow-x-auto font-mono leading-relaxed"># manifest.py 中声明
MANIFEST = AppManifest(
    content_types=[
        {"key": "project", "name": "项目", "icon": "📊",
         "supports_category": True, "supports_tags": True},
    ],
    field_groups=[
        {"content_type": "project", "key": "basic", "label": "基础信息", "sort": 0},
        {"content_type": "project", "key": "dates", "label": "时间周期", "sort": 1},
    ],
    field_definitions=[
        {"content_type": "project", "key": "budget", "label": "预算",
         "type": "number", "group": "dates", "validation": {"min": 0}},
    ],
    categories_seed=[
        {"content_type": "project", "slug": "internal", "name": "内部项目"},
    ],
)</pre>
          </section>

          <section id="bk-migration" class="mb-10">
            <h2 class="text-xl font-semibold mb-4 pb-2 border-b">5. 数据库迁移</h2>
            <p class="text-ink-600 mb-4">使用 Alembic 管理表结构。迁移文件放在应用源码的 <code>alembic/versions/</code> 目录，随 ZIP 一起提交。</p>
            <pre class="bg-ink-900 text-ink-100 p-5 rounded-xl text-sm overflow-x-auto font-mono leading-relaxed">cd backend
PYTHONPATH=src alembic revision --autogenerate -m "create my_app tables"
PYTHONPATH=src alembic upgrade head
PYTHONPATH=src alembic downgrade -1  # 回滚</pre>
            <div class="bg-blue-50 border border-blue-200 rounded-xl p-4 mt-4">
              <p class="text-sm text-blue-800">
                📦 <strong>随包提交</strong>：把迁移文件放进应用的 <code>alembic/versions/</code>，打包时带上 <code>alembic/</code> 目录。
                安装时系统会自动把它们拷贝到平台迁移目录并根据文件内的 <code>revision</code> 去重（已存在的跳过），随后执行 <code>alembic upgrade head</code> 完成建表——无需手工干预。
              </p>
            </div>
            <div class="bg-amber-50 border border-amber-200 rounded-xl p-4 mt-3">
              <p class="text-sm text-amber-800">
                ⚠️ <strong>规范要求</strong>：迁移脚本需<strong>幂等</strong>（用 <code>table existence</code> 判断后再创建表），避免对既有库重复执行报错。
                建议迁移文件内含 <code>branch_labels</code> 以与应用包区分，且 <code>revision</code> 长度 ≤ 32 字符。
              </p>
            </div>
          </section>

          <section id="bk-security" class="mb-10">
            <h2 class="text-xl font-semibold mb-4 pb-2 border-b">6. 安全规范</h2>
            <div class="bg-red-50 border border-red-200 rounded-xl p-5 mb-4">
              <h3 class="font-medium text-red-800 mb-2">禁止</h3>
              <ul class="text-sm text-red-700 space-y-1">
                <li>• <code>os.system()</code>、<code>subprocess</code> 等系统调用</li>
                <li>• 访问 <code>apps/</code> 目录外的文件</li>
                <li>• 修改其他应用的数据</li>
              </ul>
            </div>
            <div class="bg-blue-50 border border-blue-200 rounded-xl p-5">
              <h3 class="font-medium text-blue-800 mb-2">规范</h3>
              <ul class="text-sm text-blue-700 space-y-1">
                <li>• 所有 API 使用 <code>require_permission()</code> 鉴权</li>
                <li>• 删除使用软删 <code>deleted_at</code></li>
                <li>• 记录 <code>creator_id</code></li>
                <li>• 用户输入先校验再入库</li>
              </ul>
            </div>
          </section>
        </div>

        <!-- ==================== 前端开发 ==================== -->
        <div v-if="activeTab === 'frontend'">
          <nav class="mb-10 p-4 bg-ink-50 rounded-xl">
            <h3 class="text-sm font-semibold text-ink-700 mb-2">目录</h3>
            <ul class="text-sm space-y-1 text-ink-600">
              <li><a href="#fe-overview" class="hover:text-ink-900 hover:underline">1. 插件前端概述</a></li>
              <li><a href="#fe-quickstart" class="hover:text-ink-900 hover:underline">2. 快速开始：Vite Library</a></li>
              <li><a href="#fe-plugin-def" class="hover:text-ink-900 hover:underline">3. PluginDefinition 合约</a></li>
              <li><a href="#fe-api" class="hover:text-ink-900 hover:underline">4. API 调用</a></li>
              <li><a href="#fe-i18n" class="hover:text-ink-900 hover:underline">5. 国际化</a></li>
              <li><a href="#fe-menu" class="hover:text-ink-900 hover:underline">6. 菜单注册</a></li>
              <li><a href="#fe-build" class="hover:text-ink-900 hover:underline">7. 构建</a></li>
            </ul>
          </nav>

          <section id="fe-overview" class="mb-10">
            <h2 class="text-xl font-semibold mb-4 pb-2 border-b">1. 插件前端概述</h2>
            <p class="text-ink-600 mb-4">
              App 前端作为 <strong>Vite Library 项目</strong>独立开发，打包为 <code>plugin.js</code>，
              随 ZIP 包提交。安装后在 admin-web 中<strong>运行时动态加载</strong>，无需重新构建 admin-web。
            </p>
            <div class="bg-amber-50 border border-amber-200 rounded-xl p-4">
              <p class="text-sm text-amber-800">
                ⚠️ <strong>无需修改 admin-web 源码</strong>。
                不需要在 <code>router/index.ts</code> 加路由，不需要在 <code>views/system/</code> 创建文件。
                所有功能通过 <code>plugin.js</code> 声明，PluginManager 自动处理。
              </p>
            </div>
          </section>

          <section id="fe-quickstart" class="mb-10">
            <h2 class="text-xl font-semibold mb-4 pb-2 border-b">2. 快速开始：Vite Library</h2>
            <p class="text-ink-600 mb-4">在 App 源码目录下创建 <code>frontend/</code> 子项目：</p>

            <h3 class="font-medium mb-2">初始化</h3>
            <pre class="bg-ink-900 text-ink-100 p-5 rounded-xl text-sm overflow-x-auto font-mono leading-relaxed">mkdir -p my-app/frontend
cd my-app/frontend

# 用 Vite + Vue 3 + TypeScript 模板创建
npm create vite@latest . -- --template vue-ts</pre>

            <h3 class="font-medium mb-2 mt-6">配置 vite.config.ts</h3>
            <pre class="bg-ink-900 text-ink-100 p-5 rounded-xl text-sm overflow-x-auto font-mono leading-relaxed">import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  build: {
    lib: {
      entry: 'src/main.ts',
      name: 'MyAppPlugin',
      formats: ['iife'],
      fileName: () => 'plugin.js',
    },
    outDir: 'dist',
    emptyOutDir: true,
    cssCodeSplit: false,
  },
})</pre>

            <h3 class="font-medium mb-2 mt-6">创建入口 main.ts</h3>
            <pre class="bg-ink-900 text-ink-100 p-5 rounded-xl text-sm overflow-x-auto font-mono leading-relaxed">import { createApp, defineComponent, h } from 'vue'

// 定义页面组件
const TodoView = defineComponent({
  name: 'TodoView',
  setup() {
    return () => h('div', [
      h('h1', { class: 'text-2xl font-semibold mb-4' }, 'Todo 待办'),
    ])
  },
})

// 注册插件
const plugin = {
  id: 'todo',
  version: '1.0.0',
  name: 'Todo 待办',
  routes: [
    {
      path: 'todo',
      name: 'todo',
      component: TodoView,
      meta: { permission: 'todo:read' },
    },
  ],
  menus: [
    {
      key: 'todo',
      title: 'Todo',
      path: '/todo',
      icon: 'list-todo',
      sort: 65,
    },
  ],
  locales: {
    'zh-CN': { todo: { title: '待办事项' } },
    'en-US': { todo: { title: 'Todo List' } },
  },
}

window.__registerPlugin(plugin)</pre>

            <h3 class="font-medium mb-2 mt-6">构建</h3>
            <pre class="bg-ink-900 text-ink-100 p-5 rounded-xl text-sm overflow-x-auto font-mono leading-relaxed">cd my-app/frontend
npm install
npm run build

# 产物
ls dist/
# plugin.js   ← 这就是需要打包进 ZIP 的文件</pre>

            <h3 class="font-medium mb-2 mt-6">打包到 ZIP</h3>
            <pre class="bg-ink-900 text-ink-100 p-5 rounded-xl text-sm overflow-x-auto font-mono leading-relaxed">cd my-app
# 确保 frontend/dist/plugin.js 存在
# 然后打包整个目录
zip -r my-app-1.0.0.zip . -x "frontend/src" "frontend/node_modules" "frontend/public"</pre>
          </section>

          <section id="fe-plugin-def" class="mb-10">
            <h2 class="text-xl font-semibold mb-4 pb-2 border-b">3. PluginDefinition 合约</h2>
            <p class="text-ink-600 mb-2">plugin.js 必须调用 <code>window.__registerPlugin()</code>，传入对象结构如下：</p>
            <pre class="bg-ink-900 text-ink-100 p-5 rounded-xl text-sm overflow-x-auto font-mono leading-relaxed">interface PluginDefinition {
  id: string       // 应用 key，必须和 manifest.py 一致
  version: string
  name: string

  // 路由（Vue Router 子路由，path 相对 /admin/）
  routes?: Array<{
    path: string
    name: string
    component: any       // Vue 组件
    meta?: Record&lt;string, any&gt;
  }>

  // 菜单项（直接显示在侧边栏）
  menus?: Array<{
    key: string
    title: string
    path: string           // 对应 route path
    icon?: string          // Lucide 图标名
    sort?: number          // 排序（默认 90）
    parentId?: string      // 父菜单 key，支持二级
  }>

  // 国际化（merge 到 vue-i18n messages）
  locales?: Record&lt;string, Record&lt;string, any&gt;&gt;
}</pre>
            <p class="text-sm text-ink-500 mt-2">
              PluginManager 收到注册后：<br>
              1. 通过 <code>router.addRoute()</code> 添加路由<br>
              2. 通过 <code>i18n.global.mergeLocaleMessage()</code> 合并翻译<br>
              3. 将 <code>menus</code> 追加到 <code>window.__pluginMenus</code> 供 AppLayout 渲染
            </p>
          </section>

          <section id="fe-api" class="mb-10">
            <h2 class="text-xl font-semibold mb-4 pb-2 border-b">4. API 调用</h2>
            <p class="text-ink-600 mb-4">
              在页面组件中使用 <code>api</code> 实例（admin-web 全局提供）：</p>
            <pre class="bg-ink-900 text-ink-100 p-5 rounded-xl text-sm overflow-x-auto font-mono leading-relaxed" v-pre>// 前端插件页面中
import { api } from '@/lib/api'

// 注意：因为插件在 admin-web 环境运行，@/lib/api 会从宿主获取

// GET 列表
const { data } = await api.get('/api/v1/todo', {
  params: { page: 1, page_size: 20 }
})

// POST 创建
await api.post('/api/v1/todo', { title: '新待办' })

// PATCH 更新
await api.patch('/api/v1/todo/1', { done: true })

// DELETE 删除
await api.delete('/api/v1/todo/1')</pre>
          </section>

          <section id="fe-i18n" class="mb-10">
            <h2 class="text-xl font-semibold mb-4 pb-2 border-b">5. 国际化</h2>
            <p class="text-ink-600 mb-4">
              在 PluginDefinition 的 <code>locales</code> 字段声明，PluginManager 自动合并：</p>
            <pre class="bg-ink-900 text-ink-100 p-5 rounded-xl text-sm overflow-x-auto font-mono leading-relaxed" v-pre>// plugin.js
window.__registerPlugin({
  id: 'todo',
  locales: {
    'zh-CN': {
      todo: { title: '待办事项', desc: '管理你的待办' }
    },
    'en-US': {
      todo: { title: 'Todos', desc: 'Manage your todos' }
    },
  },
})

// 页面组件中使用
const { t } = useI18n()
console.log(t('todo.title'))   // → "待办事项"</pre>
          </section>

          <section id="fe-menu" class="mb-10">
            <h2 class="text-xl font-semibold mb-4 pb-2 border-b">6. 菜单</h2>
            <p class="text-ink-600 mb-4">
              在 PluginDefinition 的 <code>menus</code> 字段声明，自动显示在后台侧边栏：</p>
            <pre class="bg-ink-900 text-ink-100 p-5 rounded-xl text-sm overflow-x-auto font-mono leading-relaxed">window.__registerPlugin({
  id: 'todo',
  menus: [
    {
      key: 'todo',
      title: 'Todo',
      path: '/todo',
      icon: 'list-todo',    // Lucide 图标
      sort: 65,             // 数值越小越靠前
    },
    {
      key: 'todo:stats',
      title: '统计',
      path: '/todo/stats',
      parentId: 'todo',      // 二级菜单
      sort: 10,
    },
  ],
})</pre>
            <p class="text-sm text-ink-500 mt-2">
              图标名参考 <a href="https://lucide.dev/icons" target="_blank" class="text-blue-600 hover:underline">Lucide Icons</a>。
              支持二级菜单（通过 <code>parentId</code> 关联）。
            </p>
          </section>

          <section id="fe-build" class="mb-10">
            <h2 class="text-xl font-semibold mb-4 pb-2 border-b">7. 构建</h2>
            <p class="text-ink-600 mb-2">前端项目构建命令：</p>
            <pre class="bg-ink-900 text-ink-100 p-5 rounded-xl text-sm overflow-x-auto font-mono leading-relaxed">cd my-app/frontend
npm run build

# 产物
dist/
├── plugin.js          # ← 打包进 ZIP
└── style.css          # ← 如有 CSS，同样打包进 ZIP（放在 frontend/dist/ 下）</pre>
            <p class="text-ink-600 mt-4">
              构建后确保 <code>frontend/dist/plugin.js</code> 在 ZIP 包内存在。
              然后参照「打包与发布」章节提交流程。
            </p>
          </section>
        </div>

        <!-- ==================== 打包与发布 ==================== -->
        <div v-if="activeTab === 'publish'">
          <nav class="mb-10 p-4 bg-ink-50 rounded-xl">
            <h3 class="text-sm font-semibold text-ink-700 mb-2">目录</h3>
            <ul class="text-sm space-y-1 text-ink-600">
              <li><a href="#pub-prepare" class="hover:text-ink-900 hover:underline">1. 准备 ZIP</a></li>
              <li><a href="#pub-check" class="hover:text-ink-900 hover:underline">2. 自检清单</a></li>
              <li><a href="#pub-store" class="hover:text-ink-900 hover:underline">3. 提交到商店</a></li>
              <li><a href="#pub-install" class="hover:text-ink-900 hover:underline">4. 安装流程</a></li>
              <li><a href="#pub-version" class="hover:text-ink-900 hover:underline">5. 版本更新</a></li>
            </ul>
          </nav>

          <section id="pub-prepare" class="mb-10">
            <h2 class="text-xl font-semibold mb-4 pb-2 border-b">1. 准备 ZIP</h2>
            <p class="text-ink-600 mb-4">确保你的 App 根目录结构如下：</p>
            <pre class="bg-ink-900 text-ink-100 p-5 rounded-xl text-sm overflow-x-auto font-mono leading-relaxed">my-app/
├── __init__.py               # 必需
├── manifest.py               # 必需
├── router.py                 # API 路由（含 include 的子路由）
├── models.py 或 models/      # 数据模型（单文件或分包）
├── alembic/
│   └── versions/             # 数据库迁移（可选，安装时自动 upgrade head）
├── frontend/                 # 可选
│   └── dist/
│       └── plugin.js         # 前端插件
└── requirements.txt          # 可选</pre>
            <p class="text-ink-600 mt-4">打包命令（白名单式，排除一切无关文件）：</p>
            <pre class="bg-ink-900 text-ink-100 p-5 rounded-xl text-sm overflow-x-auto font-mono leading-relaxed">cd my-app
zip -r my-app-1.0.0.zip \
  __init__.py manifest.py router.py \
  models.py \
  alembic/ \
  frontend/dist/ \
  -x "*/__pycache__/*" "*.pyc" "*/.git/*" "*/node_modules/*" "*/dist/.vite/*"</pre>
            <p class="text-sm text-ink-500 mt-2">
              使用<strong>白名单</strong>（只列要打包的文件/目录）而不是 <code>zip -r .</code> 整目录打包，
              可避免把 <code>node_modules/</code>、<code>.git/</code>、<code>__pycache__/</code> 等无关文件带进包内。
            </p>
          </section>

          <section id="pub-check" class="mb-10">
            <h2 class="text-xl font-semibold mb-4 pb-2 border-b">2. 自检清单</h2>
            <div class="space-y-2">
              <label class="flex items-start gap-3 p-3 bg-green-50 rounded-xl">
                <span class="text-green-600 mt-0.5">☑</span>
                <span class="text-sm text-green-800"><code>__init__.py</code> 和 <code>manifest.py</code> 在 ZIP 根目录</span>
              </label>
              <label class="flex items-start gap-3 p-3 bg-green-50 rounded-xl">
                <span class="text-green-600 mt-0.5">☑</span>
                <span class="text-sm text-green-800"><code>router.py</code> 使用 <code>from cenkor_admin.apps.&lt;key&gt; import models</code> 或 <code>from . import models</code>，不使用 <code>from apps.xxx</code></span>
              </label>
              <label class="flex items-start gap-3 p-3 bg-green-50 rounded-xl">
                <span class="text-green-600 mt-0.5">☑</span>
                <span class="text-sm text-green-800"><code>manifest.py</code> 中 <code>key</code> 与文件名一致，全局唯一</span>
              </label>
              <label class="flex items-start gap-3 p-3 bg-green-50 rounded-xl">
                <span class="text-green-600 mt-0.5">☑</span>
                <span class="text-sm text-green-800">若拆分子路由（<code>*_router.py</code>），已在根 <code>router.py</code> 中 <code>include_router</code> 汇入</span>
              </label>
              <label class="flex items-start gap-3 p-3 bg-green-50 rounded-xl">
                <span class="text-green-600 mt-0.5">☑</span>
                <span class="text-sm text-green-800">若携迁移文件，已放在 <code>alembic/versions/</code> 且脚本幂等、<code>revision</code> 唯一</span>
              </label>
              <label class="flex items-start gap-3 p-3 bg-green-50 rounded-xl">
                <span class="text-green-600 mt-0.5">☑</span>
                <span class="text-sm text-green-800">版本号遵循 <code>semver</code>（<code>major.minor.patch</code>）</span>
              </label>
              <label class="flex items-start gap-3 p-3 bg-green-50 rounded-xl">
                <span class="text-green-600 mt-0.5">☑</span>
                <span class="text-sm text-green-800">所有 API 路由使用了 <code>require_permission()</code></span>
              </label>
              <label class="flex items-start gap-3 p-3 bg-green-50 rounded-xl">
                <span class="text-green-600 mt-0.5">☑</span>
                <span class="text-sm text-green-800">有前端的：<code>frontend/dist/plugin.js</code> 存在且调用了 <code>window.__registerPlugin()</code></span>
              </label>
              <label class="flex items-start gap-3 p-3 bg-green-50 rounded-xl">
                <span class="text-green-600 mt-0.5">☑</span>
                <span class="text-sm text-green-800">ZIP 不含 <code>node_modules/</code>、<code>.git/</code> 等无关文件</span>
              </label>
            </div>
          </section>

          <section id="pub-store" class="mb-10">
            <h2 class="text-xl font-semibold mb-4 pb-2 border-b">3. 提交到商店</h2>
            <div class="space-y-3 text-sm">
              <div class="flex gap-3 items-start">
                <span class="w-7 h-7 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center shrink-0 font-semibold text-xs">1</span>
                <div><strong>注册开发者</strong> — 在 dev.cenkor.cn 注册，填写开发者信息</div>
              </div>
              <div class="flex gap-3 items-start">
                <span class="w-7 h-7 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center shrink-0 font-semibold text-xs">2</span>
                <div><strong>提交应用</strong> — 在「提交应用」页面上传 ZIP，填写 App Key / 名称 / 版本 / 分类</div>
              </div>
              <div class="flex gap-3 items-start">
                <span class="w-7 h-7 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center shrink-0 font-semibold text-xs">3</span>
                <div><strong>等待审核</strong> — 管理员审核后状态变为 <code>approved</code></div>
              </div>
            </div>
          </section>

          <section id="pub-install" class="mb-10">
            <h2 class="text-xl font-semibold mb-4 pb-2 border-b">4. 安装流程</h2>
            <p class="text-ink-600 mb-4">
              管理员在 admin.cenkor.cn → 应用中心 → 商店中找到 App 并安装。安装时系统自动执行：
            </p>
            <div class="bg-ink-900 text-ink-100 p-5 rounded-xl text-sm font-mono leading-relaxed">
              1. 解压 ZIP<br>
              2. 后端文件 → 复制到 <code>cenkor_admin/apps/&lt;key&gt;/</code><br>
              3. 前端文件 → 复制到 <code>cenkor_admin/static/apps/&lt;key&gt;/</code><br>
              4. 迁移文件 → 复制到 <code>alembic/versions/</code>，自动执行 <code>alembic upgrade head</code><br>
              5. 注册权限、菜单、内容类型到数据库<br>
              6. 标记 <code>has_frontend = True</code>（如有 frontend/dist）
            </div>
            <div class="bg-amber-50 border border-amber-200 rounded-xl p-4 mt-4">
              <p class="text-sm text-amber-800">
                ⚠️ <strong>安装后需刷新管理后台页面</strong>。
                PluginManager 在页面启动时加载 <code>plugin.js</code>，
                安装新应用后需要刷新浏览器才能加载新插件的前端路由和菜单。
              </p>
            </div>
            <p class="text-sm text-ink-500 mt-2">
              后端路由在安装时自动注册（无需重启），前端 PluginManager 下次加载 admin-web 时通过 <code>GET /system/apps/plugins</code>
              获取已安装的前端插件列表，并动态加载 <code>/.app-assets/&lt;key&gt;/plugin.js</code>。
            </p>
          </section>

          <section id="pub-version" class="mb-10">
            <h2 class="text-xl font-semibold mb-4 pb-2 border-b">5. 版本更新</h2>
            <div class="space-y-3 text-sm">
              <div class="flex gap-3 items-start">
                <span class="w-7 h-7 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center shrink-0 font-semibold text-xs">1</span>
                <div><strong>修改代码</strong> — 更新 Python 和/或前端代码</div>
              </div>
              <div class="flex gap-3 items-start">
                <span class="w-7 h-7 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center shrink-0 font-semibold text-xs">2</span>
                <div><strong>修改 manifest 版本号</strong> — 更新 <code>version</code> 字段</div>
              </div>
              <div class="flex gap-3 items-start">
                <span class="w-7 h-7 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center shrink-0 font-semibold text-xs">3</span>
                <div><strong>重新打包</strong> — 运行 <code>zip</code> 命令</div>
              </div>
              <div class="flex gap-3 items-start">
                <span class="w-7 h-7 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center shrink-0 font-semibold text-xs">4</span>
                <div><strong>提交新版本</strong> — 应用商店会自动检测版本升级</div>
              </div>
              <div class="flex gap-3 items-start">
                <span class="w-7 h-7 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center shrink-0 font-semibold text-xs">5</span>
                <div><strong>重新安装</strong> — 管理员安装新版，覆盖旧文件，保留数据</div>
              </div>
            </div>
          </section>
        </div>

        <div class="text-center pt-8 border-t mt-10">
          <p class="text-ink-500 mb-4">准备好了吗？</p>
          <router-link to="/register" class="btn-primary text-base px-8 py-3">开始开发</router-link>
        </div>
      </div>
    </main>

    <footer class="border-t border-ink-200 py-8 text-center text-sm text-ink-400">
      © 2026 Cenkor. All rights reserved.
    </footer>
  </div>
</template>
