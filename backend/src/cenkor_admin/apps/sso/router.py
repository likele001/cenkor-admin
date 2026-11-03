"""SSO 路由。

分两组，**挂载方式不同**，这是本 App 唯一需要特殊处理的地方：

- ``public_router``：授权跳转和回调必须匿名可访问。而平台的 App 自动注册
  （``api/v1/__init__.py::register_app_router``）会给所有 App 路由强制加
  ``Depends(get_current_user)`` —— 要是走自动注册，用户点「微信登录」会先被
  要求登录，死循环。所以这组路由在 ``api/v1/__init__.py`` 里手工挂到
  ``/public/sso``，和 portal 的 public 路由同级。
- ``router``：配置管理、绑定管理，走正常自动注册到 ``/sso``，享受登录门禁和
  App 启用门禁（应用停用后这些接口一律 403）。
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.portal import models as portal_models
from cenkor_admin.core.config import get_settings
from cenkor_admin.core.db import get_db
from cenkor_admin.core.secrets import decrypt_secret, secret_hint

from . import config as sso_config
from . import state as sso_state
from .providers import all_providers, get_provider
from .providers.base import OAuthError, OAuthUser
from .store import AccountStore, SsoLoginError, get_store

log = structlog.get_logger()
settings = get_settings()

public_router = APIRouter()
router = APIRouter()

_CFG_READ = require_permission("sso:config:read")
_CFG_WRITE = require_permission("sso:config:write")


# =====================================================================
# 匿名路由
# =====================================================================


@public_router.get("/login-config", summary="登录页可用的第三方渠道（匿名）")
async def login_config(
    realm: str = Query("portal"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """前端登录页据此渲染按钮。没有可用渠道时返回空数组，按钮区自动隐藏。"""
    if realm not in sso_config.REALMS:
        raise HTTPException(400, "未知的登录端")
    return {
        "realm": realm,
        "providers": await sso_config.public_provider_list(db, realm),
        "frontend": await sso_config.get_frontend_url(db, realm),
    }


@public_router.get("/{provider_key}/authorize", summary="跳转第三方授权页")
async def authorize(
    provider_key: str,
    realm: str = Query("portal"),
    redirect: str | None = Query(None, description="登录成功后回跳的站内路径"),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """发起登录。**只做登录，不做绑定** —— 绑定走 /api/v1/sso/bind/{provider}，
    因为绑定需要知道「我现在是谁」，而浏览器整页跳转带不了 Authorization 头。"""
    provider = get_provider(provider_key)
    if provider is None:
        raise HTTPException(404, f"不支持的登录渠道：{provider_key}")
    if realm not in sso_config.REALMS:
        raise HTTPException(400, "未知的登录端")

    raw = await sso_config.get_raw(db, provider_key)
    cfg = await sso_config.get_provider_config(db, provider_key)
    if not raw.get("enabled"):
        raise HTTPException(400, f"{provider.name} 登录未启用")
    if not cfg.configured:
        raise HTTPException(400, f"{provider.name} 登录未配置凭证")
    if realm not in (raw.get("realms") or ["portal"]):
        raise HTTPException(400, f"{provider.name} 未在本端开放")

    base = await sso_config.get_base_url(db)
    redirect_uri = sso_config.redirect_uri_for(base, provider_key)

    state = sso_state.new_state()
    verifier: str | None = None
    challenge: str | None = None
    if provider.supports_pkce:
        verifier, challenge = sso_state.new_pkce_pair()

    await sso_state.put_state(
        state,
        provider=provider_key,
        realm=realm,
        code_verifier=verifier,
        redirect_after=redirect,
    )

    url = provider.authorize_url(cfg, redirect_uri, state, challenge)
    log.info("sso.authorize.redirect", provider=provider_key, realm=realm)
    return RedirectResponse(url=url, status_code=302)


@public_router.get("/{provider_key}/callback", summary="第三方授权回调")
async def callback(
    provider_key: str,
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """OAuth 回调。无论成功失败都 302 回前端，错误以 query 参数带过去。

    为什么不返回 JSON：用户是在浏览器里整页跳转过来的，看到一坨 JSON 会懵。
    """
    provider = get_provider(provider_key)

    # 先解析 state 拿到 realm，才能知道该跳到哪个前端站点。
    # state 缺失时只能按 portal 处理——这种情况下用户本来也就在前台。
    saved = await sso_state.take_state(state) if state else None
    realm = (saved or {}).get("realm") or "portal"
    frontend = await sso_config.get_frontend_url(db, realm)

    def fail(message: str, code_: str = "sso_failed") -> RedirectResponse:
        q = urlencode({"error": code_, "message": message, "realm": realm})
        return RedirectResponse(f"{frontend}/auth/sso/callback?{q}", status_code=302)

    if provider is None:
        return fail("不支持的登录渠道", "bad_provider")
    if error:
        return fail(f"授权被拒绝（{error}）", "access_denied")
    if not code or not state:
        # 微信用户点「取消」时不会带 code
        return fail("未获取到授权码，可能取消了授权", "no_code")
    if saved is None:
        # 三种可能：超过 10 分钟过期、伪造、已经用过一次
        return fail("登录会话已过期，请重新发起登录", "state_expired")

    cfg = await sso_config.get_provider_config(db, provider_key)
    if not cfg.configured:
        return fail("该渠道配置已失效，请联系管理员", "not_configured")

    base = await sso_config.get_base_url(db)
    redirect_uri = sso_config.redirect_uri_for(base, provider_key)

    try:
        user_info: OAuthUser = await provider.exchange(
            cfg, code, redirect_uri, saved.get("code_verifier")
        )
    except OAuthError as exc:
        log.warning("sso.exchange.failed", provider=provider_key, error=str(exc))
        return fail(str(exc), "exchange_failed")
    except Exception as exc:
        log.error("sso.exchange.crashed", provider=provider_key, error=str(exc))
        return fail("登录服务暂时不可用，请稍后再试", "exchange_error")

    store = get_store(realm)

    # ---- 绑定模式：已登录用户把新渠道绑到自己的账号 ----
    link_user_id = saved.get("link_user_id")
    if link_user_id:
        try:
            await _do_bind(db, store, int(link_user_id), provider_key, user_info)
            await db.commit()
        except SsoLoginError as exc:
            await db.rollback()
            return fail(exc.message, exc.code)
        except Exception as exc:
            await db.rollback()
            log.error("sso.bind.failed", provider=provider_key, error=str(exc))
            return fail("绑定失败，请稍后重试", "bind_failed")
        q = urlencode({"bound": provider_key, "provider_name": provider.name, "realm": realm})
        return RedirectResponse(
            f"{await sso_config.get_frontend_url(db, realm)}/auth/sso/callback?{q}",
            status_code=302,
        )

    # ---- 登录模式 ----
    try:
        user_id, is_new = await store.login_or_register(db, provider_key, user_info)
        user = await store.get_active_user(db, user_id)
        if user is None:
            raise SsoLoginError("账号不存在或已删除", code="user_missing")
        await store.log_login(db, user_id=user_id, provider=provider_key, success=True)
        await db.commit()
    except SsoLoginError as exc:
        await db.rollback()
        log.info("sso.login.denied", provider=provider_key, realm=realm, code=exc.code)
        return fail(exc.message, exc.code)
    except Exception as exc:
        await db.rollback()
        log.error("sso.login.failed", provider=provider_key, realm=realm, error=str(exc))
        return fail("登录失败，请稍后重试或改用账号密码登录", "login_failed")

    # 关键：不把 token 放 URL，只发一个 2 分钟一次性票据
    ticket = sso_state.new_ticket()
    await sso_state.put_ticket(
        ticket, realm=realm, user_id=user_id, provider=provider_key, is_new_user=is_new
    )

    params: dict[str, str] = {"ticket": ticket, "realm": realm, "provider": provider_key}
    if is_new:
        params["new"] = "1"
    after = saved.get("redirect_after")
    if after:
        params["redirect"] = after
    log.info("sso.login.ok", provider=provider_key, realm=realm, user_id=user_id, new=is_new)
    return RedirectResponse(
        f"{await sso_config.get_frontend_url(db, realm)}/auth/sso/callback?{urlencode(params)}",
        status_code=302,
    )


async def _do_bind(
    db: AsyncSession, store: AccountStore, user_id: int, provider_key: str, user_info: OAuthUser
) -> None:
    """把渠道身份绑到指定账号。

    该身份已绑到别人身上时**明确拒绝**，不静默改绑：静默改绑等于谁先抢到
    这个微信账号谁就能把它从原主人身上抢走。
    """
    owner = await store.find_user_by_identity(db, provider_key, user_info.subject)
    if owner is not None and owner != user_id:
        raise SsoLoginError(
            "该第三方账号已绑定到其他账号，请先在原账号里解绑", code="already_bound"
        )
    await store.bind(db, user_id, provider_key, user_info)


@public_router.post("/exchange", summary="用一次性票据换取登录凭证")
async def exchange(
    ticket: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """前端回调页调这个接口拿 token。

    票据一次性：换过一次立即失效。即便票据被截获，攻击窗口也只有 2 分钟且
    只能用一次（正常用户几乎同时就换掉了）。
    """
    saved = await sso_state.take_ticket(ticket)
    if saved is None:
        raise HTTPException(400, "登录票据无效或已过期，请重新登录")

    realm = saved.get("realm") or "portal"
    store = get_store(realm)
    try:
        user = await store.get_active_user(db, int(saved["user_id"]))
    except SsoLoginError as exc:
        raise HTTPException(403, exc.message) from exc
    if user is None:
        raise HTTPException(403, "账号不存在或已停用")

    tokens = store.issue_tokens(user)
    tokens.update({
        "realm": realm,
        "provider": saved.get("provider"),
        "is_new_user": bool(saved.get("is_new_user")),
    })
    return tokens


# =====================================================================
# 管理路由（自动注册到 /api/v1/sso，带登录 + App 启用门禁）
# =====================================================================


def _mask_secret(enc: str | None) -> str:
    """后台展示用：只暴露末四位，够确认「填的是哪把 key」就够了。"""
    plain = decrypt_secret(enc)
    if plain is None:
        return "（密钥无法解密，请重新填写）"
    return secret_hint(plain)


@router.get("/providers", summary="全部渠道配置")
async def list_providers(
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(_CFG_READ),
) -> dict[str, Any]:
    base = await sso_config.get_base_url(db)
    items: list[dict[str, Any]] = []
    for key, provider in all_providers().items():
        raw = await sso_config.get_raw(db, key)
        cfg = await sso_config.get_provider_config(db, key)
        items.append({
            "key": key,
            "name": provider.name,
            "icon": provider.icon,
            "note": provider.note,
            "supports_pkce": provider.supports_pkce,
            # 后台能不能开这个渠道。微信/抖音是 C 端账号体系，不适合当管理入口
            "admin_allowed": key in sso_config.ADMIN_ALLOWED,
            "enabled": bool(raw.get("enabled")),
            "configured": cfg.configured,
            "client_id": raw.get("client_id") or "",
            "client_secret_hint": _mask_secret(raw.get("client_secret_enc")),
            "realms": raw.get("realms") or ["portal"],
            "extra": raw.get("extra") or {},
            "extra_fields": provider.extra_fields(),
            "callback_url": sso_config.redirect_uri_for(base, key),
        })
    return {
        "base_url": base,
        "portal_frontend": await sso_config.get_frontend_url(db, "portal"),
        "admin_frontend": await sso_config.get_frontend_url(db, "admin"),
        "providers": items,
    }


@router.put("/providers/{provider_key}", summary="保存渠道配置")
async def save_provider(
    provider_key: str,
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(_CFG_WRITE),
) -> dict[str, Any]:
    if get_provider(provider_key) is None:
        raise HTTPException(404, f"不支持的渠道：{provider_key}")
    await sso_config.save_provider_config(
        db,
        provider_key,
        enabled=payload.get("enabled"),
        client_id=payload.get("client_id"),
        # 不传 = 不改；传空串 = 清空。两者语义不同，见 save_provider_config 文档
        client_secret=payload.get("client_secret"),
        realms=payload.get("realms"),
        extra=payload.get("extra"),
    )
    return {"ok": True}


@router.put("/settings", summary="保存回调域名与前端地址")
async def save_settings(
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(_CFG_WRITE),
) -> dict[str, Any]:
    base = (payload.get("base_url") or "").strip()
    if base:
        if not base.startswith(("http://", "https://")):
            raise HTTPException(400, "回调域名必须以 http:// 或 https:// 开头")
        await sso_config.set_base_url(db, base)
    for realm in sso_config.REALMS:
        url = (payload.get(f"{realm}_frontend") or "").strip()
        if url:
            if not url.startswith(("http://", "https://")):
                raise HTTPException(400, "前端地址必须以 http:// 或 https:// 开头")
            await sso_config.set_frontend_url(db, realm, url)
    return {"ok": True}


# ---- 绑定管理（当前登录用户） ----


@router.post("/bind/{provider_key}", summary="发起绑定第三方渠道")
async def start_bind(
    provider_key: str,
    realm: str = Query("portal"),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(_CFG_READ),
) -> dict[str, str]:
    """返回第三方授权地址，由前端 window.location 跳过去。

    绑定走这个接口而不是匿名 authorize，是因为这里能拿到当前登录用户；
    `link_user_id` 存进 state，回调时据此绑到该账号。
    """
    provider = get_provider(provider_key)
    if provider is None:
        raise HTTPException(404, f"不支持的渠道：{provider_key}")
    raw = await sso_config.get_raw(db, provider_key)
    cfg = await sso_config.get_provider_config(db, provider_key)
    if not raw.get("enabled") or not cfg.configured:
        raise HTTPException(400, f"{provider.name} 未启用或未配置")

    base = await sso_config.get_base_url(db)
    redirect_uri = sso_config.redirect_uri_for(base, provider_key)

    state = sso_state.new_state()
    verifier: str | None = None
    challenge: str | None = None
    if provider.supports_pkce:
        verifier, challenge = sso_state.new_pkce_pair()

    await sso_state.put_state(
        state,
        provider=provider_key,
        realm=realm,
        code_verifier=verifier,
        link_user_id=user.id,
    )
    return {"authorize_url": provider.authorize_url(cfg, redirect_uri, state, challenge)}


@router.get("/bindings", summary="当前账号已绑定的渠道")
async def my_bindings(
    realm: str = Query("portal"),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(_CFG_READ),
) -> list[dict[str, Any]]:
    if realm == "admin":
        rows = (await db.execute(
            select(auth_models.UserOAuth).where(auth_models.UserOAuth.user_id == user.id)
        )).scalars().all()
    else:
        rows = (await db.execute(
            select(portal_models.PortalUserOAuth).where(
                portal_models.PortalUserOAuth.user_id == user.id
            )
        )).scalars().all()

    result: list[dict[str, Any]] = []
    for r in rows:
        raw = getattr(r, "raw_profile", None) or {}
        result.append({
            "id": r.id,
            "provider": r.provider,
            "nickname": raw.get("nickname") or raw.get("name") or "",
            "avatar": raw.get("avatar_url") or raw.get("avatar") or "",
            "last_login_at": r.last_login_at.isoformat()
            if getattr(r, "last_login_at", None) else None,
        })
    return result


@router.delete("/bindings/{binding_id}", summary="解绑渠道")
async def remove_binding(
    binding_id: int,
    realm: str = Query("portal"),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(_CFG_WRITE),
) -> dict[str, bool]:
    """只能解绑自己的。带上 user_id 条件而不是先查再判断，避免 TOCTOU。"""
    if realm == "admin":
        stmt = delete(auth_models.UserOAuth).where(
            auth_models.UserOAuth.id == binding_id,
            auth_models.UserOAuth.user_id == user.id,
        )
    else:
        stmt = delete(portal_models.PortalUserOAuth).where(
            portal_models.PortalUserOAuth.id == binding_id,
            portal_models.PortalUserOAuth.user_id == user.id,
        )
    result = await db.execute(stmt)
    await db.commit()
    if not result.rowcount:
        raise HTTPException(404, "绑定不存在或不属于当前账号")
    return {"ok": True}
