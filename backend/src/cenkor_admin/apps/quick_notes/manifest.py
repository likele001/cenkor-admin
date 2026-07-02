from cenkor_admin.apps.base import AppManifest

MANIFEST = AppManifest(
    key="quick_notes",
    name="Quick Notes",
    version="1.0.0",
    description="简易备忘录工具，支持增删改查、颜色标记、搜索",
    icon="📝",
    category="productivity",
    author="Cenkor Team",
    permissions_required=[
        "quick_notes:read",
        "quick_notes:write",
    ],
    menus=[
        {
            "key": "quick_notes",
            "title": "Quick Notes",
            "path": "/quick_notes",
            "icon": "sticky-note",
            "sort": 60,
        }
    ],
    public_routes_prefix="/quick_notes",
)
