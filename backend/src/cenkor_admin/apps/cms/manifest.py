"""CMS App manifest — 应用中心注册信息（MVP 代码级模块化）"""
from __future__ import annotations

from cenkor_admin.apps.base import AppManifest

MANIFEST = AppManifest(
    key="cms",
    name="辰科官网 CMS",
    version="0.1.0",
    author="Cenkor",
    description="官网内容管理：产品 / 案例 / 新闻 / 站点配置 / 媒体库",
    icon="📰",
    min_platform_version="0.1.0",
    dependencies=[],
    permissions_required=[
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
    menus=[
        {
            "key": "cms",
            "title": "内容管理",
            "icon": "newspaper",
            "sort": 50,
            "children": [
                {"key": "cms:products", "title": "产品", "path": "/cms/products"},
                {"key": "cms:cases",    "title": "案例", "path": "/cms/cases"},
                {"key": "cms:news",     "title": "新闻", "path": "/cms/news"},
                {"key": "cms:site",     "title": "站点配置", "path": "/cms/site"},
                {"key": "cms:media",    "title": "媒体库", "path": "/cms/media"},
            ],
        },
    ],
)
