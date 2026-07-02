"""工单系统 App manifest"""
from __future__ import annotations

from cenkor_admin.apps.base import AppManifest

MANIFEST = AppManifest(
    key="tickets",
    name="工单系统",
    version="1.0.0",
    author="Cenkor",
    description="内部工单与任务追踪，支持分配、状态流转、优先级管理",
    icon="🎫",
    category="productivity",
    min_platform_version="0.1.0",
    dependencies=[],
    permissions_required=[
        "tickets:read",
        "tickets:write",
        "tickets:assign",
    ],
    menus=[
        {
            "key": "tickets",
            "title": "工单管理",
            "icon": "ticket",
            "sort": 61,
            "children": [
                {"key": "tickets:list", "title": "工单列表", "path": "/tickets"},
            ],
        },
    ],
)
