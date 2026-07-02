"""链接收集 App manifest"""
from __future__ import annotations

from cenkor_admin.apps.base import AppManifest

MANIFEST = AppManifest(
    key="links",
    name="链接收藏",
    version="1.0.0",
    author="Cenkor",
    description="书签与外部链接收集管理，支持分类、标签、收藏夹",
    icon="🔗",
    category="productivity",
    min_platform_version="0.1.0",
    dependencies=[],
    permissions_required=[
        "links:read",
        "links:write",
    ],
    menus=[
        {
            "key": "links",
            "title": "链接收藏",
            "icon": "link",
            "sort": 62,
            "children": [
                {"key": "links:list", "title": "链接列表", "path": "/links"},
            ],
        },
    ],
)
