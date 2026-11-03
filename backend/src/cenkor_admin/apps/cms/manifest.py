"""CMS App manifest — 应用中心注册信息（V2 内容引擎）"""
from __future__ import annotations

from cenkor_admin.apps.base import AppManifest

MANIFEST = AppManifest(
    key="cms",
    builtin=True,          # 底座：产品核心：内容类型 / 字段 / 模板 / AI 能力全在这里
    name="辰科官网 CMS",
    version="0.4.0",
    author="Cenkor",
    description="通用内容管理：内容类型 / 字段定义 / 分类标签 / Liquid 模板 / AI 能力 / 公共 API",
    icon="📰",
    category="content",
    min_platform_version="0.1.0",
    dependencies=[],
    # 权限点必须在这里声明：install_app() 会按此清单建 rbac_permissions，
    # 角色页的权限树只渲染库里存在的码。漏声明 = 该权限永远无法授予非超管，
    # 页面前端守卫 meta.permission 也就永远拦死（只能靠 is_superuser 兜底）。
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
        "cms:entry:review",    # 审核动作独立于编辑：编辑能提交，审核才能通过
        "cms:ai:read",         # AI 配置/用量查看
        "cms:ai:manage",       # AI 服务商密钥、能力绑定（高危，只给管理员）
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
                # AI 三项排组首，按「建模 → 生产 → 配置」的使用顺序。
                # 藏在深层等于没上线：用户根本不会去翻。
                {"key": "cms:ai-builder", "title": "AI 建模向导", "icon": "🤖",
                 "path": "/cms/ai-builder", "sort": 44},
                {"key": "cms:ai-workbench", "title": "AI 内容工作台", "icon": "🪄",
                 "path": "/cms/ai-workbench", "sort": 45},
                {"key": "cms:ai-settings", "title": "AI 能力配置", "icon": "✨",
                 "path": "/cms/ai-settings", "sort": 46},
                {"key": "cms:search", "title": "内容搜索", "icon": "🔍",
                 "path": "/cms/search", "sort": 47},
                {"key": "cms:content-types", "title": "内容类型", "path": "/cms/content-types", "sort": 48},
                {"key": "cms:languages", "title": "语言管理", "path": "/cms/languages", "sort": 49},
                {"key": "cms:categories", "title": "分类管理", "path": "/cms/categories", "sort": 50},
                {"key": "cms:tags", "title": "标签管理", "path": "/cms/tags", "sort": 51},
                {"key": "cms:entries", "title": "通用内容", "path": "/cms/entries", "sort": 52},
                {"key": "cms:templates", "title": "模板预览", "path": "/cms/templates", "sort": 53},
                {"key": "cms:products", "title": "产品", "path": "/cms/products", "sort": 54},
                {"key": "cms:cases",    "title": "案例", "path": "/cms/cases", "sort": 55},
                {"key": "cms:news",     "title": "新闻", "path": "/cms/news", "sort": 56},
                {"key": "cms:site",     "title": "站点配置", "path": "/cms/site", "sort": 57},
                {"key": "cms:media",    "title": "媒体库", "path": "/cms/media", "sort": 58},
                {"key": "cms:url-rules", "title": "URL 规则", "icon": "link",
                 "path": "/cms/url-rules", "sort": 57},
                {"key": "builder", "title": "页面构建", "icon": "🧩",
                 "path": "/builder/pages", "sort": 90},
            ],
        },
        # AI 内容中心：低频但必备的 AI 能力集中在此，避免散落各处点不到。
        # 高频三项（建模向导 / 内容工作台 / 能力配置）仍挂在「内容管理」组首，
        # 菜单 key 全局唯一，因此不会重复出现。
        {
            "key": "cms-ai-center",
            "title": "AI 内容中心",
            "icon": "🧠",
            "sort": 40,
            "children": [
                {"key": "cms:ai-home", "title": "AI 驾驶舱", "path": "/cms/ai", "sort": 40},
                {"key": "cms:ai-batch", "title": "批量生产", "path": "/cms/ai-batch", "sort": 41},
                {"key": "cms:ai-knowledge", "title": "知识库", "path": "/cms/ai-knowledge", "sort": 42},
                {"key": "cms:ai-landing", "title": "落地页工坊", "path": "/cms/ai-landing", "sort": 43},
                {"key": "cms:ai-workflow", "title": "工作流编排", "path": "/cms/ai-workflow", "sort": 44},
                {"key": "cms:ai-prompts", "title": "提示词管理", "path": "/cms/ai-prompts", "sort": 45},
                {"key": "cms:ai-health", "title": "内容体检", "path": "/cms/ai-health", "sort": 46},
                {"key": "cms:ai-quality", "title": "AI 质量台", "path": "/cms/ai-quality", "sort": 47},
                {"key": "cms:ai-ask", "title": "问答自测", "path": "/cms/ai-ask", "sort": 48},
                {"key": "cms:ai-gaps", "title": "选题缺口", "path": "/cms/ai-gaps", "sort": 49},
                {"key": "cms:content-analytics", "title": "内容效果", "path": "/cms/analytics", "sort": 50},
                {"key": "cms:publish-channels", "title": "分发渠道", "path": "/cms/publish-channels", "sort": 51},
                {"key": "cms:ai-usage", "title": "AI 用量", "path": "/cms/ai-usage", "sort": 52},
                {"key": "cms:ai-memory", "title": "AI 记忆", "path": "/cms/ai-memory", "sort": 53},
            ],
        },
    ],
)
