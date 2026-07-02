"""Portal App · 前台用户认证 API（/api/v1/public/portal/）"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import httpx
from cenkor_admin.apps.portal import models, schemas
from cenkor_admin.apps.portal.auth import (
    create_portal_access_token,
    create_portal_refresh_token,
    decode_portal_token,
    hash_password,
    verify_password,
    JWTError,
)
from cenkor_admin.core.config import get_settings
from cenkor_admin.core.db import get_db
from cenkor_admin.core.mail import send_email
from cenkor_admin.core.redis import redis_client

log = structlog.get_logger()
router = APIRouter()
settings = get_settings()

# ---- Portal OAuth 配置 ----
FEISHU_PORTAL_STATE_PREFIX = "oauth:portal:feishu:state:"
FEISHU_PORTAL_STATE_TTL = 300  # 5 分钟


class PortalFeishuOAuth:
    """Portal 用户飞书 OAuth 2.0"""

    AUTHORIZE_URL = "https://open.feishu.cn/open-apis/authen/v1/index"
    TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
    USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"

    def __init__(self) -> None:
        self.app_id = settings.FEISHU_APP_ID
        self.app_secret = settings.FEISHU_APP_SECRET
        self.redirect_uri = settings.FEISHU_REDIRECT_URI

    @property
    def enabled(self) -> bool:
        return bool(self.app_id and self.app_secret)

    def build_authorize_url(self, state: str) -> str:
        params = {
            "app_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "state": state,
            "scope": "contact:user.id:readonly contact:user.base:readonly",
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(self.TOKEN_URL, json={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.app_id,
                "client_secret": self.app_secret,
            })
            r.raise_for_status()
            data = r.json()
            if data.get("code") != 0:
                raise RuntimeError(f"Feishu token error: {data}")

            access_token = data["access_token"]

            r2 = await client.get(self.USER_INFO_URL, headers={
                "Authorization": f"Bearer {access_token}",
            })
            r2.raise_for_status()
            user_info = r2.json()
            if user_info.get("code") != 0:
                raise RuntimeError(f"Feishu user_info error: {user_info}")

            return {
                "access_token": access_token,
                "refresh_token": data.get("refresh_token"),
                "expires_in": data.get("expires_in", 7200),
                "open_id": user_info["data"]["open_id"],
                "union_id": user_info["data"].get("union_id"),
                "name": user_info["data"].get("name", ""),
                "email": user_info["data"].get("email", ""),
                "avatar_url": user_info["data"].get("avatar_url", ""),
            }

    def new_state(self) -> str:
        return secrets.token_urlsafe(32)

    async def store_state(self, state: str) -> None:
        await redis_client.setex(f"{FEISHU_PORTAL_STATE_PREFIX}{state}", FEISHU_PORTAL_STATE_TTL, "1")

    async def consume_state(self, state: str) -> bool:
        key = f"{FEISHU_PORTAL_STATE_PREFIX}{state}"
        if not await redis_client.get(key):
            return False
        await redis_client.delete(key)
        return True


portal_feishu = PortalFeishuOAuth()


def _verify_captcha(token: str | None) -> None:
    if not token or not isinstance(token, str):
        raise HTTPException(400, "请先完成滑动验证")
    import re
    if not re.fullmatch(r"[0-9a-f]{16,128}", token):
        raise HTTPException(400, "滑动验证无效，请刷新重试")


async def get_current_portal_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> models.PortalUser:
    """从 Bearer token 解析当前前台用户"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "未提供认证信息")
    token = auth_header[7:]

    try:
        payload = decode_portal_token(token)
    except JWTError as e:
        raise HTTPException(401, f"Token 无效: {e}")

    if payload.get("type") != "access":
        raise HTTPException(401, "不是 access token")

    user_id = int(payload["sub"])
    user = await db.get(models.PortalUser, user_id)
    if not user or user.deleted_at:
        raise HTTPException(401, "用户不存在")
    if user.status != "active":
        raise HTTPException(403, f"账号已{user.status}")
    return user


# ============================================================
# 注册
# ============================================================

@router.post("/auth/register", response_model=schemas.PortalTokenResponse, status_code=status.HTTP_201_CREATED)
async def portal_register(
    body: schemas.PortalRegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _verify_captcha(body.captcha_token)

    existing = await db.execute(
        select(models.PortalUser).where(
            (models.PortalUser.username == body.username)
            | (models.PortalUser.email == body.email if body.email else False),
            models.PortalUser.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "用户名或邮箱已存在")

    ip = request.client.host if request.client else None
    user = models.PortalUser(
        username=body.username,
        email=body.email,
        nickname=body.nickname or body.username,
        phone=body.phone,
        password_hash=hash_password(body.password),
        status="active",
        register_ip=ip,
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except Exception:
        await db.rollback()
        raise HTTPException(409, "用户名或邮箱已存在")

    return schemas.PortalTokenResponse(
        access_token=create_portal_access_token(user.id),
        refresh_token=create_portal_refresh_token(user.id, user.token_version),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=schemas.PortalUserBrief(
            id=user.id, username=user.username, email=user.email,
            nickname=user.nickname, avatar=user.avatar,
        ),
    )


# ============================================================
# 登录
# ============================================================

@router.post("/auth/login", response_model=schemas.PortalTokenResponse)
async def portal_login(
    body: schemas.PortalLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _verify_captcha(body.captcha_token)

    stmt = select(models.PortalUser).where(
        models.PortalUser.deleted_at.is_(None),
        (models.PortalUser.username == body.username)
        | (models.PortalUser.email == body.username)
        | (models.PortalUser.phone == body.username),
    )
    user = (await db.execute(stmt)).scalar_one_or_none()

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent", "")[:500]

    if not user or not verify_password(body.password, user.password_hash):
        if user:
            db.add(models.PortalLoginLog(
                user_id=user.id, ip=ip, user_agent=ua,
                success=False, reason="wrong_password", provider="local",
            ))
            await db.commit()
        raise HTTPException(401, "账号或密码错误")

    if user.status != "active":
        raise HTTPException(403, f"账号已{user.status}")

    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = ip
    db.add(models.PortalLoginLog(
        user_id=user.id, ip=ip, user_agent=ua, success=True, provider="local",
    ))
    await db.commit()
    await db.refresh(user)

    return schemas.PortalTokenResponse(
        access_token=create_portal_access_token(user.id),
        refresh_token=create_portal_refresh_token(user.id, user.token_version),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=schemas.PortalUserBrief(
            id=user.id, username=user.username, email=user.email,
            nickname=user.nickname, avatar=user.avatar,
        ),
    )


# ============================================================
# 刷新 Token
# ============================================================

@router.post("/auth/refresh", response_model=schemas.PortalTokenResponse)
async def portal_refresh(
    body: schemas.PortalRefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = decode_portal_token(body.refresh_token)
    except JWTError as e:
        raise HTTPException(401, f"Refresh token 无效: {e}")

    if payload.get("type") != "refresh":
        raise HTTPException(401, "不是 refresh token")

    user_id = int(payload["sub"])
    tv = payload.get("tv", 0)

    user = await db.get(models.PortalUser, user_id)
    if not user or user.deleted_at or user.token_version != tv:
        raise HTTPException(401, "Token 已被撤销")
    if user.status != "active":
        raise HTTPException(403, f"账号已{user.status}")

    return schemas.PortalTokenResponse(
        access_token=create_portal_access_token(user.id),
        refresh_token=create_portal_refresh_token(user.id, user.token_version),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=schemas.PortalUserBrief(
            id=user.id, username=user.username, email=user.email,
            nickname=user.nickname, avatar=user.avatar,
        ),
    )


# ============================================================
# 当前用户
# ============================================================

@router.get("/me", response_model=schemas.PortalUserBrief)
async def portal_me(user: models.PortalUser = Depends(get_current_portal_user)):
    return schemas.PortalUserBrief(
        id=user.id, username=user.username, email=user.email,
        nickname=user.nickname, avatar=user.avatar,
    )


@router.patch("/me/profile", response_model=schemas.PortalUserBrief)
async def portal_update_profile(
    body: schemas.PortalUserUpdate,
    db: AsyncSession = Depends(get_db),
    user: models.PortalUser = Depends(get_current_portal_user),
):
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(user, k, v)
    await db.commit()
    await db.refresh(user)
    return schemas.PortalUserBrief(
        id=user.id, username=user.username, email=user.email,
        nickname=user.nickname, avatar=user.avatar,
    )


@router.post("/me/change-password", status_code=204)
async def portal_change_password(
    body: schemas.PortalChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    user: models.PortalUser = Depends(get_current_portal_user),
):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(400, "原密码错误")
    user.password_hash = hash_password(body.new_password)
    user.token_version = (user.token_version or 0) + 1
    await db.commit()


# ============================================================
# OAuth 绑定（自服务）
# ============================================================

@router.post("/me/oauth/bind", response_model=schemas.PortalOAuthBindingOut, status_code=201)
async def portal_bind_oauth(
    body: schemas.PortalOAuthBindRequest,
    db: AsyncSession = Depends(get_db),
    user: models.PortalUser = Depends(get_current_portal_user),
):
    """用户自行绑定 OAuth"""
    # 检查 open_id 是否已被其他用户绑定
    existing = (await db.execute(
        select(models.PortalUserOAuth).where(
            models.PortalUserOAuth.provider == body.provider,
            models.PortalUserOAuth.open_id == body.open_id,
        )
    )).scalar_one_or_none()
    if existing:
        if existing.user_id == user.id:
            raise HTTPException(409, "该 OAuth 已绑定到当前账号")
        raise HTTPException(409, "该 OAuth 已绑定到其他账号")

    oauth = models.PortalUserOAuth(
        user_id=user.id,
        provider=body.provider,
        open_id=body.open_id,
        union_id=body.union_id,
        access_token_enc=body.access_token,
        refresh_token_enc=body.refresh_token,
    )
    db.add(oauth)
    await db.commit()
    await db.refresh(oauth)
    return oauth


@router.delete("/me/oauth/{oauth_id}", status_code=204)
async def portal_unbind_oauth(
    oauth_id: int,
    db: AsyncSession = Depends(get_db),
    user: models.PortalUser = Depends(get_current_portal_user),
):
    """用户自行解绑 OAuth"""
    oauth = await db.get(models.PortalUserOAuth, oauth_id)
    if not oauth or oauth.user_id != user.id:
        raise HTTPException(404, "OAuth binding not found")
    await db.delete(oauth)
    await db.commit()


@router.get("/me/oauth", response_model=list[schemas.PortalOAuthBindingOut])
async def portal_list_oauth(
    db: AsyncSession = Depends(get_db),
    user: models.PortalUser = Depends(get_current_portal_user),
):
    """列出当前用户的所有 OAuth 绑定"""
    result = await db.execute(
        select(models.PortalUserOAuth)
        .where(models.PortalUserOAuth.user_id == user.id)
        .order_by(models.PortalUserOAuth.created_at.desc())
    )
    return result.scalars().all()


# ============================================================
# 忘记密码
# ============================================================

@router.post("/auth/forgot-password", status_code=200)
async def portal_forgot_password(
    body: schemas.PortalForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    email = (body.email or "").strip().lower()
    if not email:
        raise HTTPException(400, "请输入邮箱")

    user = (await db.execute(
        select(models.PortalUser).where(
            models.PortalUser.email == email,
            models.PortalUser.deleted_at.is_(None),
        )
    )).scalar_one_or_none()

    if not user:
        return {"ok": True, "message": "如果该邮箱已注册，重置链接已发送"}

    token = secrets.token_urlsafe(48)[:64]
    from cenkor_admin.apps.notification.models import PasswordReset
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    db.add(PasswordReset(
        user_id=user.id, token=token, expires_at=expires,
        ip=request.client.host if request.client else None,
    ))
    await db.commit()

    frontend_base = body.frontend_base or settings.PUBLIC_BASE_URL
    reset_link = f"{frontend_base.rstrip('/')}/reset-password?token={token}"

    try:
        send_email(
            email,
            "【Cenkor】重置您的密码",
            f"您好，\n\n请点击下方链接在 1 小时内重置密码：\n\n  {reset_link}\n\n—— Cenkor",
        )
    except Exception:
        pass

    return {"ok": True, "message": "如果该邮箱已注册，重置链接已发送"}


@router.post("/auth/reset-password", status_code=200)
async def portal_reset_password(
    body: schemas.PortalResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    token = (body.token or "").strip()
    if not token:
        raise HTTPException(400, "参数错误")

    from cenkor_admin.apps.notification.models import PasswordReset
    reset = (await db.execute(
        select(PasswordReset).where(PasswordReset.token == token)
    )).scalar_one_or_none()
    if not reset or reset.used_at:
        raise HTTPException(400, "重置链接无效或已过期")
    expires_at = reset.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(400, "重置链接已过期")

    user = await db.get(models.PortalUser, reset.user_id)
    if not user or user.deleted_at:
        raise HTTPException(400, "用户不存在")

    user.password_hash = hash_password(body.new_password)
    user.token_version = (user.token_version or 0) + 1
    reset.used_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True}


# ============================================================
# Portal OAuth 登录（飞书）
# ============================================================

@router.get("/auth/feishu/authorize", summary="Portal 飞书登录 - 跳转授权页")
async def portal_feishu_authorize():
    """前台用户飞书登录授权跳转"""
    if not portal_feishu.enabled:
        raise HTTPException(503, "飞书登录未配置")
    state = portal_feishu.new_state()
    await portal_feishu.store_state(state)
    url = portal_feishu.build_authorize_url(state)
    return RedirectResponse(url=url)


@router.get("/auth/feishu/callback", summary="Portal 飞书登录 - OAuth 回调")
async def portal_feishu_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """前台用户飞书 OAuth 回调"""
    if not portal_feishu.enabled:
        raise HTTPException(503, "飞书登录未配置")

    if not await portal_feishu.consume_state(state):
        raise HTTPException(400, "无效或已过期的 OAuth state")

    try:
        fs_user = await portal_feishu.exchange_code(code)
    except Exception as e:
        log.error("portal.feishu.exchange.failed", error=str(e))
        raise HTTPException(400, f"飞书登录失败: {e}")

    # 查找已有绑定
    oauth_result = await db.execute(
        select(models.PortalUserOAuth).where(
            models.PortalUserOAuth.provider == "feishu",
            models.PortalUserOAuth.open_id == fs_user["open_id"],
        )
    )
    oauth = oauth_result.scalar_one_or_none()

    if oauth:
        user = await db.get(models.PortalUser, oauth.user_id)
        if not user or user.deleted_at:
            raise HTTPException(400, "绑定的用户不存在")
    else:
        # 创建新用户
        from python_slugify import slugify
        username = f"portal_fs_{fs_user['open_id'][:12]}"
        user = models.PortalUser(
            username=username,
            email=fs_user.get("email") or f"{username}@feishu.local",
            nickname=fs_user.get("name", "飞书用户"),
            avatar=fs_user.get("avatar_url"),
            password_hash=hash_password(secrets.token_urlsafe(32)),
        )
        db.add(user)
        await db.flush()
        db.add(models.PortalUserOAuth(
            user_id=user.id, provider="feishu", open_id=fs_user["open_id"],
            union_id=fs_user.get("union_id"),
            access_token_enc=fs_user["access_token"],
            refresh_token_enc=fs_user.get("refresh_token"),
            expires_at=None,
        ))
        await db.commit()
        await db.refresh(user)

    if user.status != "active":
        raise HTTPException(403, f"账号已{user.status}")

    return schemas.PortalTokenResponse(
        access_token=create_portal_access_token(user.id),
        refresh_token=create_portal_refresh_token(user.id, user.token_version),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=schemas.PortalUserBrief(
            id=user.id, username=user.username, email=user.email,
            nickname=user.nickname, avatar=user.avatar,
        ),
    )
