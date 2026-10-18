"""库存管理 — AppManifest（由 scripts/gen-app.py 生成）"""
from __future__ import annotations

from cenkor_admin.apps.base import AppManifest


MANIFEST = AppManifest(
    key="inventory",
    name="库存管理",
    version="1.0.0",
    author='Cenkor Team',
    description='库存基础资料：仓库 / 库位',
    icon="📦",
    category="business",
    permissions_required=[
        "inventory:warehouse:read",
        "inventory:warehouse:write",
        "inventory:warehouse:delete",
        "inventory:warehouse:export",
        "inventory:location:read",
        "inventory:location:write",
        "inventory:location:delete",
        "inventory:location:export",
        "inventory:admin",
    ],
    menus=[
        {
            "key": "inventory",
            "title": "库存管理",
            "icon": "appstore",
            "sort": 80,
            "children": [
                {
                    "key": "inventory:warehouse",
                    "title": "仓库",
                    "path": "/inventory/warehouse",
                    "icon": "menu",
                    "sort": 81,
                },
                {
                    "key": "inventory:location",
                    "title": "库位",
                    "path": "/inventory/location",
                    "icon": "menu",
                    "sort": 82,
                },
            ],
        },
    ],
    public_routes_prefix="/api/v1/inventory",
)
