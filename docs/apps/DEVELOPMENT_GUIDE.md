# Cenkor Admin 应用开发规范

> 版本：1.0.0  
> 更新日期：2026-06-11

## 一、概述

Cenkor Admin 支持通过应用（App）扩展平台功能。每个应用是一个独立的模块，可以：

- 注册新的内容类型和字段
- 添加后台管理页面
- 注册 API 路由
- 添加菜单和权限
- 提供公共 API

## 二、应用结构

### 2.1 目录结构

```
my-app/
├── manifest.py          # 必需：应用清单
├── __init__.py          # 必需：Python 包标识
├── models.py            # 可选：数据库模型
├── router.py            # 可选：API 路由
├── schemas.py           # 可选：Pydantic 模型
├── service.py           # 可选：业务逻辑
└── static/              # 可选：前端资源
    └── index.html       # 可选：应用管理页面
```

### 2.2 manifest.py（必需）

每个应用必须在根目录定义 `manifest.py`，导出 `MANIFEST` 对象：

```python
"""我的应用 manifest"""
from cenkor_admin.apps.base import AppManifest

MANIFEST = AppManifest(
    # ---- 基础信息 ----
    key="my-app",                    # 唯一标识（小写英文+连字符）
    name="我的应用",                  # 显示名称
    version="1.0.0",                 # 语义化版本号
    author="开发者名称",              # 作者
    description="应用描述",           # 简短描述
    icon="📦",                       # Emoji 图标
    category="productivity",         # 分类：content / productivity / system / ai

    # ---- 依赖 ----
    min_platform_version="0.1.0",    # 最低平台版本
    dependencies=[],                 # 依赖的其他 App key

    # ---- 权限 ----
    permissions_required=[
        "my-app:read",               # 读取权限
        "my-app:write",              # 写入权限
    ],

    # ---- 菜单 ----
    menus=[
        {
            "key": "my-app",
            "title": "我的应用",
            "icon": "box",           # 图标名称
            "sort": 70,              # 排序（数字越小越靠前）
            "children": [
                {"key": "my-app:list", "title": "数据列表", "path": "/my-app"},
            ],
        },
    ],

    # ---- 内容引擎（可选）----
    content_types=[
        {"key": "my-item", "name": "我的项目", "icon": "📋",
         "supports_category": True, "supports_tags": True},
    ],
    field_groups=[
        {"content_type": "my-item", "key": "basic", "label": "基础信息", "sort": 0},
    ],
    field_definitions=[
        {"content_type": "my-item", "key": "name", "label": "名称",
         "type": "text", "group": "basic", "required": True},
        {"content_type": "my-item", "key": "description", "label": "描述",
         "type": "richtext", "group": "basic"},
    ],
    categories_seed=[
        {"content_type": "my-item", "slug": "general", "name": "通用"},
    ],

    # ---- 公共 API ----
    public_routes_prefix="/api/v1/public/my-app",
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
from cenkor_admin.apps.my_app import models  # 推荐相对导入：from . import models
from cenkor_admin.core.db import get_db

router = APIRouter()


@router.get("", response_model=dict)
async def list_items(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("my-app:read")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """获取列表"""
    # 你的业务逻辑
    return {"items": [], "total": 0}


@router.post("", status_code=201)
async def create_item(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("my-app:write")),
):
    """创建"""
    # 你的业务逻辑
    return {"id": 1}
```

### 4.2 权限命名规范

```
{app-key}:read     # 读取权限
{app-key}:write    # 写入权限
{app-key}:delete   # 删除权限（可选）
{app-key}:admin    # 管理权限（可选）
```

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

### 6.1 创建迁移文件

```bash
cd backend
PYTHONPATH=src alembic revision --autogenerate -m "create my_app tables"
```

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

```
my-app-1.0.0.zip
├── manifest.py
├── __init__.py
├── models.py
├── router.py
├── schemas.py
├── service.py
└── requirements.txt    # 可选：额外依赖
```

### 7.2 打包要求

1. **文件编码**：UTF-8
2. **Python 版本**：3.11+
3. **依赖管理**：如需额外依赖，在 `requirements.txt` 中声明
4. **无恶意代码**：禁止执行系统命令、访问敏感文件
5. **manifest 完整**：所有必需字段必须填写

## 八、安装流程

1. 开发者上传 ZIP 包
2. 系统解压并校验 `manifest.py`
3. 检查 `key` 唯一性
4. 检查 `version` 格式
5. 检查依赖是否满足
6. 将应用代码放入 `apps/{key}/` 目录
7. 执行数据库迁移（如有新表）
8. 注册权限和菜单
9. 应用状态变为 `installed`

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

## 十、示例应用

参考内置应用：
- `apps/cms/` — 内容管理系统
- `apps/announcements/` — 公告管理
- `apps/tickets/` — 工单系统
- `apps/links/` — 链接收藏
