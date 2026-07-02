from cenkor_admin.apps.base import AppManifest

MANIFEST = AppManifest(
    key="my_todo",
    name="My Todo",
    version="1.0.0",
    author="Demo Dev",
    description="A simple todo app for testing the store install flow",
    icon="✅",
    category="productivity",
    permissions_required=["my_todo:read", "my_todo:write"],
    menus=[{
        "key": "my_todo",
        "title": "My Todo",
        "icon": "list-todo",
        "sort": 65,
        "children": [
            {"key": "my_todo:list", "title": "Todo List", "path": "/my_todo"},
        ],
    }],
)
