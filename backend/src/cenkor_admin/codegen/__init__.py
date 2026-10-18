"""cenkor_admin.codegen — CRUD 代码生成器

包含：
    builder.py       生成核心（纯 stdlib + PyYAML，不依赖 fastapi/sqlalchemy）
    templates/app/   App 模板（后端 + 前端源码）
    assets/          构建好的前端运行时插件 plugin_head.js（每个生成的 App 复用这一份）
    runtime_plugin/  运行时插件源码（构建 plugin_head.js 用，不随生成的 App 分发）

入口：
    · CLI：scripts/gen-app.py（薄封装）
    · HTTP：apps/system/codegen_router.py（/api/v1/system/codegen）
"""

__all__ = ["builder"]
