"""Notification App · 站内信/系统通知"""
from cenkor_admin.apps.base import AppManifest

MANIFEST = AppManifest(
    key="notification",
    builtin=True,          # 底座：站内信铃铛，多模块发通知依赖
    name="通知",
    version="0.1.0",
    description="站内信、系统通知（铃铛）",
)

# 兼容旧引用：应用扫描器只认大写的 MANIFEST
manifest = MANIFEST
