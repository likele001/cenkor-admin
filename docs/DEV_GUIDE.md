# Cenkor Platform V2 — 开发者指南

> 本指南面向 **新接入 Cenkor Platform V2 的开发者**。
> 涵盖：如何创建自定义 App、如何添加内容类型/字段、如何扩展模板引擎。

---

## 目录

- [快速开始](#快速开始)
- [创建第一个 App](#创建第一个-app)
- [内容类型与字段定义](#内容类型与字段定义)
- [Liquid 模板开发](#liquid-模板开发)
- [API 鉴权与跨域](#api-鉴权与跨域)
- [部署与运维](#部署与运维)
- [常见问题](#常见问题)

---

## 快速开始

### 环境要求

| 工具 | 版本 |
|------|------|
| Python | 3.11+ |
| Node.js | 18+ |
| PostgreSQL | 16+ |
| Redis | 7+ |
| MinIO | 最新 |

### 克隆与启动

```bash
git clone https://github.com/cenkor/cenkor-admin.git
cd cenkor-admin

# 后端
cd backend
pip install -r requirements.txt
cp ../.env.example .env
# 编辑 .env 填入 DB/Redis/MinIO 等配置
alembic upgrade head
python -m cenkor_admin.scripts.seed
uvicorn cenkor_admin.main:app --host 0.0.0.0 --port 8000

# 前端（后台）
cd ../frontend/admin-web
npm install
npm run dev  # http://localhost:5173

# 前端（前台）
cd ../frontend/portal-web
npm install
npm run dev  # http://localhost:5175
```

### 默认账号

- 后台: `admin@cenkor.cn` / `admin123`（**生产请立即修改！**）
- 前台: 注册即可

---

## 创建第一个 App

### 步骤 1: 目录结构

```bash
backend/src/cenkor_admin/apps/
└── my_app/                  # ← 你的新 App
    ├── __init__.py
    ├── manifest.py          # ← 必须：App 元数据
    ├── models.py            # 可选：你的业务模型
    ├── router.py            # 可选：后台 API
    ├── public_router.py     # 可选：前台 API
    └── schemas.py           # 可选：Pydantic schemas
```

### 步骤 2: 定义 manifest.py

```python
"""My App · 元数据"""
from cenkor_admin.apps.base import AppManifest

MANIFEST = AppManifest(
    key="my_app",                                  # 唯一标识
    name="我的应用",
    version="0.1.0",
    description="这是一个示例 App",
    icon="🧪",
    permissions_required=[
        "my_app:item:read",
        "my_app:item:write",
    ],
    menus=[
        {
            "key": "my_app",
            "title": "我的应用",
            "icon": "package",
            "sort": 60,
            "children": [
                {"key": "my_app:items", "title": "条目管理", "path": "/my_app/items"},
            ],
        }
    ],

    # V2: 声明内容类型
    content_types=[
        {
            "key": "myitem",
            "name": "条目",
            "icon": "📄",
            "supports_category": True,
            "supports_tags": True,
        }
    ],

    # V2: 字段分组（tabs）
    field_groups=[
        {"content_type": "myitem", "key": "basic", "label": "基础信息", "sort": 0},
        {"content_type": "myitem", "key": "advanced", "label": "高级", "sort": 1},
    ],

    # V2: 字段定义
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

    # V2: 初始分类
    categories_seed=[
        {"content_type": "myitem", "slug": "general", "name": "通用"},
        {"content_type": "myitem", "slug": "important", "name": "重要"},
    ],

    public_routes_prefix="/api/v1/public/my_app",
)
```

### 步骤 3: 启动时自动注册

启动后端时，会自动：
1. 扫描 `apps/*/manifest.py` 找到你的 MANIFEST
2. 写入 `platform_apps` 表
3. 通过 `FieldRegistry` 注册 content_types / field_groups / field_definitions / categories_seed

**无需手动执行 install！**

### 步骤 4: 添加自定义业务模型

```python
# my_app/models.py
from cenkor_admin.core.db import Base
from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

class MyItem(Base):
    __tablename__ = "my_app_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    entry_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cms_entries.id", ondelete="CASCADE"), unique=True
    )
    # ...
```

```python
# my_app/router.py
from fastapi import APIRouter, Depends
from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.cms import models as cms_models

router = APIRouter()

@router.get("/items")
async def list_items(db = Depends(get_db), _ = Depends(get_current_user)):
    """列出我的条目（关联 cms_entries）"""
    items = await db.execute(
        select(cms_models.Entry)
        .where(cms_models.Entry.content_type_id == MY_ITEM_CT_ID)
    )
    return items.scalars().all()
```

### 步骤 5: 前端页面

```bash
# admin-web
mkdir -p frontend/admin-web/src/views/my_app
# 创建 ItemsListView.vue + ItemsEditView.vue

# 注册路由
# 在 router/index.ts 添加
{
  path: 'my_app/items',
  name: 'my-app-items',
  component: ItemsListView,
  meta: { permission: 'my_app:item:read' }
}
```

---

## 内容类型与字段定义

### 21 种字段类型

详见 [`apps/cms/field_types.py`](../backend/src/cenkor_admin/apps/cms/field_types.py)。

### 添加自定义字段

**方法 1：通过后台 UI**
- 登录后台 → 内容管理 → 内容类型 → 选择类型 → 「+ 字段」
- 21 种类型可选，配置 label/group/options/validation

**方法 2：通过 API**

```bash
# 1. 获取内容类型 ID
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/cms/content-types

# 2. 创建字段定义
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "field_key": "score",
    "label": "评分",
    "field_type": "number",
    "required": false,
    "validation": {"min": 0, "max": 100}
  }' \
  http://localhost:8000/api/v1/cms/content-types/1/field-definitions
```

**方法 3：在 manifest.py 中声明**

（推荐用于「启动即需要的核心字段」）

### 字段值过滤查询

```bash
# 查询 license=Apache-2.0 的产品
curl "http://localhost:8000/api/v1/cms/entries?content_type_key=product&custom.license=Apache-2.0"
```

**注意**: JSONB 字段过滤需要 GIN 索引（已自动创建）。

---

## Liquid 模板开发

### 基础语法

```liquid
{# 变量 #}
{{ product.title }}
{{ product.custom_fields.price | format_price }}

{# 流程控制 #}
{% if product.is_flagship %}
  🏆 旗舰产品
{% elsif product.is_open_source %}
  🌟 开源
{% else %}
  商业产品
{% endif %}

{# 循环 #}
{% for item in products %}
  <div>{{ item.title }} - {{ item.custom_fields.price | format_price }}</div>
{% endfor %}
```

### 内置 Filters

| Filter | 用法 | 说明 |
|--------|------|------|
| `upcase` | `{{ str \| upcase }}` | 大写 |
| `downcase` | `{{ str \| downcase }}` | 小写 |
| `truncate` | `{{ str \| truncate: 100 }}` | 截断 |
| `date` | `{{ date \| date: "%Y-%m-%d" }}` | 日期格式化 |
| `currency` | `{{ num \| currency }}` | 货币格式 |
| `format_price` | `{{ num \| format_price }}` | ¥1,234.00 |
| `markdown` | `{{ md \| markdown }}` | MD → HTML |
| `strip_html` | `{{ html \| strip_html }}` | 去标签 |
| `json` | `{{ obj \| json }}` | 序列化 |
| `join` | `{{ arr \| join: ", " }}` | 数组→字符串 |
| `size` | `{{ arr \| size }}` | 长度 |
| `default` | `{{ var \| default: "N/A" }}` | 默认值 |
| `where` | `{{ arr \| where: "status", "published" }}` | 过滤 |
| `sort` | `{{ arr \| sort: "name" }}` | 排序 |
| `map` | `{{ arr \| map: "name" }}` | 提取属性 |

### 业务 Filters

| Filter | 用途 | 示例 |
|--------|------|------|
| `t` | i18n 翻译 | `{{ product.line \| t }}` |
| `asset_url` | 资源 URL | `{{ path \| asset_url }}` |
| `thumb` | 缩略图 | `{{ url \| thumb: "300x200" }}` |
| `reading_time` | 阅读时长 | `{{ content \| reading_time }}` 分钟 |

### 全局变量

```javascript
cmsRender(template, data, {
  now: new Date().toISOString(),
  site: { name: '辰科', logo: '...' },
  theme: { primary_color: '#3b82f6' },
  current_user: { id, username, nickname, avatar },
  request: { path, params, query }
})
```

### 前端使用

```typescript
import { cmsRender } from '@/lib/cms-render'

const html = cmsRender(
  'Hello {{ name | upcase }}, price: {{ price | format_price }}',
  { name: 'world', price: 99.99 }
)
```

### 后端预览

```bash
# 通过 API 渲染（调试用）
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "template": "{{ name | upcase }} - {{ price | format_price }}",
    "data": {"name": "test", "price": 99.99}
  }' \
  http://localhost:8000/api/v1/cms/templates/render
```

---

## API 鉴权与跨域

### 鉴权方式

**后台 API（需 admin JWT）**

```bash
# 1. 登录获取 token
curl -X POST -H "Content-Type: application/json" \
  -d '{
    "username": "admin@cenkor.cn",
    "password": "admin123",
    "captcha_token": "任意16+hex"
  }' \
  http://localhost:8000/api/v1/auth/login

# 2. 使用 token
curl -H "Authorization: Bearer <access_token>" \
  http://localhost:8000/api/v1/cms/content-types
```

**前台 API（portal JWT，路由前缀 `/api/v1/public/portal/*`）**

```bash
# 注册
curl -X POST -H "Content-Type: application/json" \
  -d '{
    "username": "user1",
    "email": "u@example.com",
    "password": "test123456",
    "captcha_token": "任意16+hex"
  }' \
  http://localhost:8000/api/v1/public/portal/auth/register

# 登录获取 token（issuer=cenkor-portal）
curl -X POST -H "Content-Type: application/json" \
  -d '{
    "username": "user1",
    "password": "test123456",
    "captcha_token": "任意16+hex"
  }' \
  http://localhost:8000/api/v1/public/portal/auth/login
```

**公共 API（无需鉴权）**

```bash
# 公共内容
curl http://localhost:8000/api/v1/public/site/product

# 公共分类
curl http://localhost:8000/api/v1/public/categories?content_type_key=product
```

### 跨域（CORS）

`CORS_ORIGINS` 配置（`.env`）：

```bash
# 开发
CORS_ORIGINS=http://localhost:5173,http://localhost:5175,http://localhost:8000

# 生产
CORS_ORIGINS=https://admin.example.com,https://portal.example.com
```

**安全规则**：
- ❌ 禁止设置 `*`（生产）
- ✅ 明确列出每个允许的源
- ✅ 启用 `allow_credentials=True`

---

## 部署与运维

### 环境变量

```bash
# 应用
APP_NAME="Cenkor Admin"
APP_ENV="production"      # development | staging | production
DEBUG=False               # 生产必须 False

# 安全
SECRET_KEY="<强随机字符串>"
SECRET_KEY_OLD=""          # 轮换用，逗号分隔
COOKIE_SECURE=True

# 数据库
DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/db"
DATABASE_URL_SYNC="postgresql://user:pass@host:5432/db"  # Alembic 用

# Redis
REDIS_URL="redis://host:6379/0"

# S3 / MinIO
S3_ENDPOINT="https://minio.example.com"
S3_ACCESS_KEY="..."
S3_SECRET_KEY="..."
S3_BUCKET_PUBLIC="..."
S3_BUCKET_PRIVATE="..."

# 飞书 OAuth（可选）
FEISHU_APP_ID="..."
FEISHU_APP_SECRET="..."

# SMTP
SMTP_HOST="smtp.example.com"
SMTP_PORT=587
SMTP_USER="..."
SMTP_PASSWORD="..."
```

### 数据库迁移

```bash
# 升级
alembic upgrade head

# 降级一步
alembic downgrade -1

# 查看当前版本
alembic current

# 查看历史
alembic history
```

### 数据迁移（旧 → 新）

```bash
# cms_products/cases/news → cms_entries（幂等）
python -m cenkor_admin.scripts.migrate_to_entries
```

### 启动顺序

1. PostgreSQL
2. Redis
3. MinIO
4. 后端（先启动，自动执行 App 中心扫描 + FieldRegistry 注册）
5. 前端

### 监控

- 健康检查: `GET /api/health`
- 审计日志: `GET /api/v1/system/audit`（需 system:audit:read 权限）
- 审计统计: `GET /api/v1/system/audit/stats`

### 备份

```bash
# 数据库
pg_dump -U cenkor cenkor > /backup/cenkor_$(date +%Y%m%d).sql

# MinIO（使用 mc 客户端）
mc mirror cenkor-public /backup/minio/public/

# 上传文件（不推荐备份 MinIO 数据）— 通过应用层冗余
```

### SECRET_KEY 轮换

```bash
# 1. 生成新 key
NEW_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# 2. 部署：SECRET_KEY 新，SECRET_KEY_OLD 旧
# 3. 观察几天后所有 token 都是用新 key 签发
# 4. 清除 SECRET_KEY_OLD
```

---

## 常见问题

### Q1: 新增字段后旧数据如何处理？

新字段加入 manifest 后：
1. 启动时自动注册（新建字段）— 默认值
2. 旧数据该字段为 `null` / `{}`，通过 `default_value` 兜底
3. 可通过 `custom_fields JSONB` GIN 索引查询

### Q2: 如何修改字段类型？

**不推荐直接改** `field_type`，会导致历史数据格式不兼容。

**推荐做法**：
1. 创建新字段（不同 key）
2. 数据迁移脚本
3. 删除旧字段

### Q3: App 卸载后数据怎么办？

- content_types **软删**（`deleted_at`）
- field_groups/definitions 级联软删
- categories/tags/entries 保留（不影响前端展示）

如需彻底清理，手动执行 SQL：

```sql
DELETE FROM cms_content_types WHERE key = 'my_app';
```

### Q4: portal token 能不能访问后台？

❌ **不能**。访问后台会被中间件拦截，返回 403：

```json
{
  "detail": "前台用户无法访问后台管理接口"
}
```

这是 V2 设计的核心安全特性，不可关闭。

### Q5: 字段类型不在 21 种之内？

新增字段类型需要修改 `apps/cms/field_types.py`，并配套修改：
- `FIELD_TYPES` 列表
- `FIELD_DEFAULTS` 默认值
- `VALIDATION_RULES` 校验规则
- `validate_field_value()` 校验函数
- 前端 `DynamicFieldRenderer.vue` 渲染控件

### Q6: Liquid 模板如何处理转义？

```liquid
{{ str | escape }}    {# HTML 转义 #}
{{ str | raw }}       {# 不转义（Shopify 风格，本项目未实现 raw 关键字）#}
{{ str | strip_html }} {# 去除 HTML 标签 #}
```

### Q7: 如何调试 liquid 模板？

- 后端：`POST /api/v1/cms/templates/render`（实时渲染）
- 后端：`POST /api/v1/cms/templates/validate`（语法校验）
- 前端：`window.cmsRender()` 控制台输出错误

### Q8: 模板引擎能调用 Python 函数吗？

❌ **不能**（沙箱模式）。Liquid 仅允许白名单的 filters。

如需业务逻辑：
1. 写一个 Python function 包装成 filter
2. 注册到 `core/template_engine.py` 的 `_register_filters`
3. 重启后端

### Q9: 多租户怎么实现？

V1 已有 `tenant_id` 字段（软隔离）。
V2 暂未实现**硬隔离**（每个租户独立 DB schema）。

V3 路线图：基于 tenant_id 的 schema 隔离。

### Q10: 性能调优建议？

- **JSONB 字段**: 已自动创建 GIN 索引，避免全表扫
- **分类/标签**: 已建复合索引 `(content_type_id, parent_id)`
- **JWT decode**: 单 token 解码 < 1ms，无需缓存
- **N+1 查询**: 使用 `selectinload` 预加载关系（已在 content_engine_router.py 使用）

---

## 附录

### A. 完整字段类型参考

```python
# apps/cms/field_types.py
FIELD_TYPES = [
    'text', 'longtext', 'richtext', 'markdown',    # 文本
    'number', 'boolean', 'date', 'datetime',         # 数字/布尔/日期
    'url', 'email', 'phone',                        # 联系
    'image', 'images', 'file', 'files',            # 媒体
    'select', 'multiselect',                        # 选择
    'color', 'json', 'repeater', 'relation',         # 高级
]
```

### B. 完整 API 文档

- Swagger UI: `http://localhost:8000/api/docs`
- ReDoc: `http://localhost:8000/api/redoc`
- OpenAPI JSON: `http://localhost:8000/api/openapi.json`

### C. 项目结构

```
cenkor-admin/
├── backend/
│   ├── src/cenkor_admin/
│   │   ├── apps/                    # App 中心
│   │   │   ├── auth/                # 后台用户鉴权
│   │   │   ├── cms/                 # 内容引擎
│   │   │   │   ├── field_types.py   # 字段类型枚举
│   │   │   │   ├── field_registry.py# 字段注册器
│   │   │   │   ├── models.py        # ORM 模型
│   │   │   │   ├── router.py        # 后台 CRUD
│   │   │   │   ├── public_router.py # 公共 API
│   │   │   │   ├── template_router.py # 模板渲染
│   │   │   │   └── content_engine_router.py # 内容引擎 API
│   │   │   ├── notification/         # 通知
│   │   │   ├── portal/              # 前台用户
│   │   │   │   ├── models.py
│   │   │   │   ├── auth.py          # Portal JWT
│   │   │   │   ├── router.py
│   │   │   │   └── schemas.py
│   │   │   ├── rbac/                 # 权限
│   │   │   ├── system/               # 系统
│   │   │   └── base.py               # AppManifest
│   │   ├── core/                     # 核心
│   │   │   ├── config.py             # 配置
│   │   │   ├── db.py                 # 数据库
│   │   │   ├── security.py           # JWT + 密码
│   │   │   ├── template_engine.py    # Liquid 引擎
│   │   │   └── ...
│   │   ├── api/                      # API 路由
│   │   └── main.py
│   └── tests/                        # 测试
│       ├── test_field_types.py       # 单元测试
│       ├── test_content_engine.py    # E2E 测试
│       └── ...
├── frontend/
│   ├── admin-web/                    # 后台
│   │   ├── src/views/cms/             # CMS 页面
│   │   ├── src/components/cms/        # CMS 组件
│   │   └── ...
│   └── portal-web/                   # 前台
│       ├── src/views/
│       ├── src/lib/cms-render.ts      # Liquid 渲染
│       └── ...
├── docs/
│   ├── PLATFORM_V2_ROADMAP.md         # V2 路线图
│   ├── DEV_GUIDE.md                  # ← 本文档
│   ├── CORE_PLATFORM.md
│   └── ...
└── ARCHITECTURE.md                  # 架构文档
```
