from cenkor_admin.apps.base import AppManifest

MANIFEST = AppManifest(
    key="cloud_storage",
    name="云存储",
    version="1.0.0",
    description="替换 S3 后端。支持腾讯云 COS / 阿里云 OSS / 七牛云 Kodo / 又拍云。",
    icon="cloud",
    category="system",
    author="Cenkor Team",
    permissions_required=[
        "cloud_storage:read",
        "cloud_storage:write",
        "cloud_storage:admin",
    ],
    menus=[
        {
            "key": "cloud_storage",
            "title": "云存储",
            "path": "/cloud_storage",
            "icon": "cloud",
            "sort": 95,
        }
    ],
    public_routes_prefix="/cloud_storage",
)
