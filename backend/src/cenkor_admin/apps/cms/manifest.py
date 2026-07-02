"""CMS App manifest — 应用中心注册信息（V2 内容引擎）"""
from __future__ import annotations

from cenkor_admin.apps.base import AppManifest

MANIFEST = AppManifest(
    key="cms",
    name="辰科官网 CMS",
    version="0.3.0",
    author="Cenkor",
    description="通用内容管理：内容类型 / 字段定义 / 分类标签 / Liquid 模板 / 公共 API",
    icon="📰",
    category="content",
    min_platform_version="0.1.0",
    dependencies=[],
    permissions_required=[
        "cms:content_types:read",
        "cms:content_types:write",
        "cms:field_definitions:read",
        "cms:field_definitions:write",
        "cms:categories:read",
        "cms:categories:write",
        "cms:tags:read",
        "cms:tags:write",
        "cms:entries:read",
        "cms:entries:write",
        "cms:product:read",
        "cms:product:write",
        "cms:case:read",
        "cms:case:write",
        "cms:news:read",
        "cms:news:write",
        "cms:site:read",
        "cms:site:write",
        "media:upload",
    ],
    # V2: 声明本 App 注册的内容类型
    content_types=[
        {"key": "product", "name": "产品", "icon": "📦", "supports_category": True, "supports_tags": True},
        {"key": "case", "name": "案例", "icon": "📋", "supports_category": True, "supports_tags": False},
        {"key": "news", "name": "新闻", "icon": "📰", "supports_category": True, "supports_tags": True},
    ],
    # V2: 字段分组模板
    field_groups=[
        {"content_type": "product", "key": "basic", "label": "基础信息", "sort": 0},
        {"content_type": "product", "key": "specs", "label": "技术规格", "sort": 1},
        {"content_type": "case", "key": "basic", "label": "基础信息", "sort": 0},
        {"content_type": "news", "key": "basic", "label": "基础信息", "sort": 0},
    ],
    # V2: 字段定义
    field_definitions=[
        {"content_type": "product", "key": "price", "label": "价格", "type": "number",
         "group": "specs", "validation": {"min": 0, "step": 0.01}},
        {"content_type": "product", "key": "screenshots", "label": "产品截图", "type": "images", "group": "specs"},
        {"content_type": "product", "key": "docs_url", "label": "文档地址", "type": "url", "group": "specs"},
        {"content_type": "product", "key": "license", "label": "许可证", "type": "select", "group": "specs",
         "options": [
             {"value": "MIT", "label": "MIT", "color": "#22c55e"},
             {"value": "Apache-2.0", "label": "Apache 2.0", "color": "#3b82f6"},
             {"value": "GPL-3.0", "label": "GPL 3.0", "color": "#f59e0b"},
             {"value": "Commercial", "label": "商业", "color": "#ef4444"},
         ]},
        {"content_type": "case", "key": "client_name", "label": "客户名称", "type": "text", "group": "basic"},
        {"content_type": "case", "key": "project_scale", "label": "项目规模", "type": "select", "group": "basic",
         "options": [
             {"value": "small", "label": "小型 (< 100万)", "color": "#84cc16"},
             {"value": "medium", "label": "中型 (100-1000万)", "color": "#f59e0b"},
             {"value": "large", "label": "大型 (> 1000万)", "color": "#ef4444"},
         ]},
        {"content_type": "news", "key": "source", "label": "来源", "type": "text", "group": "basic"},
        {"content_type": "news", "key": "cover", "label": "封面图", "type": "image", "group": "basic"},
    ],
    # V2: 初始分类
    categories_seed=[
        {"content_type": "product", "slug": "mes", "name": "MES 系统",
         "children": [
             {"slug": "flow", "name": "流程管理"},
             {"slug": "quality", "name": "质量管理"},
         ]},
        {"content_type": "product", "slug": "ai", "name": "AI 应用",
         "children": [
             {"slug": "agent", "name": "智能体"},
             {"slug": "rag", "name": "知识库"},
         ]},
        {"content_type": "case", "slug": "manufacturing", "name": "制造业"},
        {"content_type": "case", "slug": "finance", "name": "金融业"},
        {"content_type": "news", "slug": "product", "name": "产品动态"},
        {"content_type": "news", "slug": "industry", "name": "行业洞察"},
    ],
    public_routes_prefix="/api/v1/public",
    menus=[
        {
            "key": "cms",
            "title": "内容管理",
            "icon": "newspaper",
            "sort": 50,
            "children": [
                {"key": "cms:content-types", "title": "内容类型", "path": "/cms/content-types"},
                {"key": "cms:categories", "title": "分类管理", "path": "/cms/categories"},
                {"key": "cms:tags", "title": "标签管理", "path": "/cms/tags"},
                {"key": "cms:entries", "title": "通用内容", "path": "/cms/entries"},
                {"key": "cms:templates", "title": "模板预览", "path": "/cms/templates"},
                {"key": "cms:products", "title": "产品", "path": "/cms/entries?ct=product"},
                {"key": "cms:cases",    "title": "案例", "path": "/cms/cases"},
                {"key": "cms:news",     "title": "新闻", "path": "/cms/news"},
                {"key": "cms:site",     "title": "站点配置", "path": "/cms/site"},
                {"key": "cms:media",    "title": "媒体库", "path": "/cms/media"},
            ],
        },
    ],
)
