"""Cenkor SSO · 应用清单。

设计定位：**统一登录是一个可插拔的 App**，可以在应用中心装/卸/停。

停用后会发生什么（由平台底座保证，不需要本 App 自己实现）：
``register_app_router`` 给 ``/api/v1/sso/*`` 挂的 ``app_enabled_dependency``
会返回 403，后台配置页打不开。但 ``/api/v1/public/sso/*`` 是手工挂载的
匿名路由，不受该门禁约束 —— 这是刻意的：登录入口如果因为「App 停用」而
整个挂掉，用户连账号密码都进不去后台去把它启用回来。

菜单不在这里声明：本 App 只加一个「系统 → 登录方式」入口，而系统分组没有
manifest.py（它是核心平台的），走 ``scripts/seed.py`` 的 DEFAULT_MENUS，
由启动时的 RBAC 自动对齐补上。
"""

from __future__ import annotations

from cenkor_admin.apps.base import AppManifest

MANIFEST = AppManifest(
    key="sso",
    name="统一登录",
    version="1.0.0",
    author="Cenkor Team",
    description=(
        "可插拔的第三方登录：微信扫码、抖音、飞书、Google、GitHub。"
        "每个渠道一个适配器文件，丢进 providers/ 目录即生效。"
        "前台支持自动注册，后台只给已有账号开免密通道。"
    ),
    icon="🔐",
    category="system",
    min_platform_version="0.4.2",
    dependencies=[],
    permissions_required=[
        "sso:config:read",
        "sso:config:write",
    ],
    menus=[],
)
