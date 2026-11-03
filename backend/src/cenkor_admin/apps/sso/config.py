"""SSO 配置读写。

**为什么配置存数据库而不是 .env**：OAuth 配置错的概率极高（回调地址少个斜杠、
secret 复制时带了空格、APPID 和 APPSECRET 填反），而改 .env 要登服务器、
改完要重启。放在 ``system_settings`` 里，后台页面改完立即生效。

存储结构（``system_settings.key = sso.provider.{渠道key}``）::

    {
      "enabled": true,
      "client_id": "wx1234567890",
      "client_secret_enc": "enc:v1:gAAAAA...",   # 走 core.secrets 加密
      "realms": ["portal"],                       # 允许在哪端登录
      "extra": {"mode": "qrconnect"}
    }

``sso.callback_base_url`` 单独一条：这是你绑的备案域名。
配了它，五个渠道的回调地址自动都是
``{base}/api/v1/public/sso/{渠道}/callback``，不用一个个填。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.core.config import get_settings
from cenkor_admin.core.secrets import decrypt_secret, encrypt_secret

from .providers.base import ProviderConfig

PREFIX = "sso.provider."
BASE_URL_KEY = "sso.callback_base_url"
GROUP = "sso"

# 前端地址（回调完成后往哪跳）。前后台是两个独立站点，必须分开配。
FRONTEND_KEY_PREFIX = "sso.frontend_url."

# 哪些渠道允许在后台（admin）登录。白名单而不是黑名单：
# 微信/抖音是 C 端账号体系，当管理入口既不合规也没必要，加新渠道默认只给前台。
ADMIN_ALLOWED = frozenset({"feishu", "github", "google"})

REALMS = ("portal", "admin")


async def get_raw(db: AsyncSession, provider_key: str) -> dict[str, Any]:
    row = await db.get(auth_models.SystemSetting, PREFIX + provider_key)
    if row is None or not isinstance(row.value, dict):
        return {}
    return row.value


async def get_provider_config(db: AsyncSession, provider_key: str) -> ProviderConfig:
    """读渠道配置，secret 已解密。"""
    raw = await get_raw(db, provider_key)
    return ProviderConfig(
        enabled=bool(raw.get("enabled")),
        client_id=str(raw.get("client_id") or "").strip(),
        # 解不开返回空串：SECRET_KEY 轮换过，视为未配置，让用户重填
        client_secret=decrypt_secret(raw.get("client_secret_enc")) or "",
        extra=raw.get("extra") or {},
    )


async def save_provider_config(
    db: AsyncSession,
    provider_key: str,
    *,
    enabled: bool | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    realms: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """保存渠道配置。传 None 的字段保持不变（便于后台只改一项）。

    ``client_secret`` 传空串表示「清空」，传 None 表示「不改」——这两者
    在 UI 上语义不同：清空是明确的删除动作，不改是「我这次只动开关」。
    """
    key = PREFIX + provider_key
    row = await db.get(auth_models.SystemSetting, key)
    value: dict[str, Any] = dict(row.value) if row and isinstance(row.value, dict) else {}

    if enabled is not None:
        value["enabled"] = enabled
    if client_id is not None:
        value["client_id"] = client_id.strip()
    if client_secret is not None:
        value["client_secret_enc"] = encrypt_secret(client_secret.strip()) if client_secret.strip() else ""
    if realms is not None:
        # 白名单校验：微信/抖音写进 admin 一律剥掉，防止配置层绕过安全约束
        normalized = [r for r in realms if r in REALMS]
        if provider_key not in ADMIN_ALLOWED and "admin" in normalized:
            normalized = [r for r in normalized if r != "admin"]
        value["realms"] = normalized or ["portal"]
    if extra is not None:
        value["extra"] = extra

    value.setdefault("realms", ["portal"])

    if row is None:
        db.add(auth_models.SystemSetting(
            key=key, value=value, group=GROUP, description=f"SSO 渠道配置：{provider_key}"
        ))
    else:
        row.value = value
    await db.commit()
    return value


async def get_base_url(db: AsyncSession) -> str:
    """回调地址的域名前缀。配了就用配的，没配退回 PUBLIC_BASE_URL。"""
    row = await db.get(auth_models.SystemSetting, BASE_URL_KEY)
    if row and isinstance(row.value, str) and row.value.strip():
        return row.value.strip().rstrip("/")
    return get_settings().PUBLIC_BASE_URL.rstrip("/")


async def set_base_url(db: AsyncSession, url: str) -> None:
    url = url.strip().rstrip("/")
    row = await db.get(auth_models.SystemSetting, BASE_URL_KEY)
    if row is None:
        db.add(auth_models.SystemSetting(
            key=BASE_URL_KEY, value=url, group=GROUP, description="SSO 回调基础域名"
        ))
    else:
        row.value = url
    await db.commit()


def redirect_uri_for(base_url: str, provider_key: str) -> str:
    """统一回调地址。五个渠道同一个规则，避免手工填错。"""
    return f"{base_url}/api/v1/public/sso/{provider_key}/callback"


async def get_frontend_url(db: AsyncSession, realm: str) -> str:
    """回调完成后跳转到哪个前端站点。

    前台和后台是两个独立构建（portal-web / admin-web），开发期端口也不同
    （5175 / 5173）。没单独配就退回 PUBLIC_BASE_URL —— 生产环境通常
    是同一个域名下不同路径，这个默认值能直接用。
    """
    row = await db.get(auth_models.SystemSetting, FRONTEND_KEY_PREFIX + realm)
    if row and isinstance(row.value, str) and row.value.strip():
        return row.value.strip().rstrip("/")
    return get_settings().PUBLIC_BASE_URL.rstrip("/")


async def set_frontend_url(db: AsyncSession, realm: str, url: str) -> None:
    key = FRONTEND_KEY_PREFIX + realm
    url = url.strip().rstrip("/")
    row = await db.get(auth_models.SystemSetting, key)
    if row is None:
        db.add(auth_models.SystemSetting(
            key=key, value=url, group=GROUP, description=f"{realm} 端站点地址"
        ))
    else:
        row.value = url
    await db.commit()


async def public_provider_list(db: AsyncSession, realm: str = "portal") -> list[dict[str, Any]]:
    """登录页该显示哪些按钮。

    只返回「已启用 + 已配凭证 + 允许该端」的渠道，且**绝不回传 secret 或
    client_id** —— 前端只需要知道渠道名和跳转路径。
    """
    from .providers import all_providers

    items: list[dict[str, Any]] = []
    for key, provider in all_providers().items():
        raw = await get_raw(db, key)
        if not raw.get("enabled"):
            continue
        cfg = await get_provider_config(db, key)
        if not cfg.configured:
            continue
        realms = raw.get("realms") or ["portal"]
        if realm not in realms:
            continue
        items.append({
            "key": key,
            "name": provider.name,
            "icon": provider.icon,
            "note": provider.note,
            "authorize_url": f"/api/v1/public/sso/{key}/authorize?realm={realm}",
        })
    return items


__all__ = [
    "ADMIN_ALLOWED",
    "BASE_URL_KEY",
    "FRONTEND_KEY_PREFIX",
    "GROUP",
    "PREFIX",
    "REALMS",
    "get_base_url",
    "get_frontend_url",
    "get_provider_config",
    "get_raw",
    "public_provider_list",
    "redirect_uri_for",
    "save_provider_config",
    "set_base_url",
    "set_frontend_url",
]
