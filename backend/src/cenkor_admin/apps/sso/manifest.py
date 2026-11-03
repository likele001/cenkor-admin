"""Cenkor SSO · 应用清单。

设计定位：**统一登录是底座能力（``builtin=True``），不是可售卖、可装卸的应用。**

它留在 ``apps/`` 目录，只是为了复用 manifest 的自动注册能力（路由门禁、
权限码、hook 扫描）—— ``builtin`` 这一位才是它真正的身份：启动强制启用、
应用中心归入「内置功能」且不渲染卸载 / 停用入口、API 层拒绝这两个动作。

为什么不能可卸载：登录是系统的入口。一旦停用，``/api/v1/sso/*`` 会 403
（后台配置页打不开），而 ``/api/v1/public/sso/*`` 是手工挂载的匿名路由、
不受门禁约束（这是刻意的，否则停用后没人能登进去把它启用回来）—— 两者
叠加就是「前台还能扫码登录、后台配置页却消失」的半死状态。所以直接从
语义上禁止卸载 / 停用，而不是靠注释提醒运营别点。

菜单不在这里声明：本 App 只加一个「系统 → 登录方式」入口，而系统分组没有
manifest.py（它是核心平台的），走 ``scripts/seed.py`` 的 DEFAULT_MENUS，
由启动时的 RBAC 自动对齐补上。
"""

from __future__ import annotations

from cenkor_admin.apps.base import AppManifest

MANIFEST = AppManifest(
    key="sso",
    builtin=True,          # 底座能力：不可卸载 / 不可停用
    name="统一登录",
    version="1.0.0",
    author="Cenkor Team",
    description=(
        "内置的第三方登录：微信扫码、抖音、飞书、Google、GitHub。"
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
