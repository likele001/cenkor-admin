"""公告管理 App manifest"""
from __future__ import annotations

from cenkor_admin.apps.base import AppManifest

MANIFEST = AppManifest(
    key="announcements",
    name="公告管理",
    version="1.0.0",
    author="Cenkor",
    description="企业内部公告发布与管理，支持置顶、分类、定时发布",
    icon="📢",
    category="productivity",
    min_platform_version="0.1.0",
    dependencies=[],
    permissions_required=[
        "announcements:read",
        "announcements:write",
    ],
    menus=[
        {
            "key": "announcements",
            "title": "公告管理",
            "icon": "megaphone",
            "sort": 60,
            "children": [
                {"key": "announcements:list", "title": "公告列表", "path": "/announcements"},
            ],
        },
    ],
)
