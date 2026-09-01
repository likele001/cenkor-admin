"""Auth App · 鉴权 API"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import structlog
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from cenkor_admin.api.deps import get_current_user, require_permission
from cenkor_admin.apps.auth import models, schemas
from cenkor_admin.apps.auth.oauth import feishu
from cenkor_admin.core.hooks import dispatch
from cenkor_admin.apps.notification.models import PasswordReset
from cenkor_admin.apps.rbac.models import (
    Role,
    UserRole,
    Permission,
    RolePermission,
    Menu,
    RoleMenu,
)
from cenkor_admin.core.config import get_settings
from cenkor_admin.core.db import get_db
from cenkor_admin.core.mail import send_email
from cenkor_admin.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

log = structlog.get_logger()
router = APIRouter()
settings = get_settings()


# ---- 工具 ----
async def _load_user_with_perms(db: AsyncSession, user_id: int) -> models.User:
    """加载用户 + 角色 + 权限 + 菜单（带 selectinload 预加载）"""
    stmt = (
        select(models.User)
        .options(
            # User → UserRole → Role → RolePermission → Permission
            selectinload(models.User.roles)  # type: ignore[arg-type]
            .selectinload(UserRole.role)
            .selectinload(Role.permissions)
            .selectinload(RolePermission.permission),
            # User → UserRole → Role → RoleMenu → Menu
            selectinload(models.User.roles)  # type: ignore[arg-type]
            .selectinload(UserRole.role)
            .selectinload(Role.menus)
            .selectinload(RoleMenu.menu),
        )
        .where(models.User.id == user_id, models.User.deleted_at.is_(None))
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _build_user_brief(user: models.User) -> schemas.UserBrief:
    """把 User 实体转成 UserBrief（展开权限 + 菜单）"""
    permissions: set[str] = set()
    menus: list[dict] = []
    seen_menus: set[int] = set()
    for user_role in user.roles:  # type: ignore[attr-defined]  # UserRole list
        role = user_role.role
        # 权限：role.permissions 是 RolePermission list；每项有 .permission
        for rp in role.permissions:  # type: ignore[attr-defined]
            perm = rp.permission  # 真正的 Permission 对象
            if perm.code in permissions:
                continue
            permissions.add(perm.code)
        # 菜单：role.menus 是 RoleMenu list；每项有 .menu
        for rm in role.menus:  # type: ignore[attr-defined]
            menu = rm.menu
            if menu.id in seen_menus:
                continue
            seen_menus.add(menu.id)
            menus.append({
                "id": menu.id,
                "key": menu.key,
                "title": menu.title,
                "icon": menu.icon,
                "path": menu.path,
                "parent_id": menu.parent_id,
                "sort": menu.sort,
            })
    menus.sort(key=lambda x: (x["parent_id"] or 0, x["sort"]))
    return schemas.UserBrief(
        id=user.id,
        username=user.username,
        email=user.email,
        nickname=user.nickname,
        avatar=user.avatar,
        is_superuser=user.is_superuser,
        permissions=sorted(permissions),
        menus=menus,
    )


async def _is_captcha_required(db: AsyncSession) -> bool:
    """读取 system_settings.security.captcha_required；默认开启（向后兼容）。"""
    s = await db.get(models.SystemSetting, "security.captcha_required")
    if not s:
        return True
    v = s.value
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


# ---- 注册（portal 用户中心） ----
def _verify_slider_captcha(token: str | None) -> None:
    """轻量校验：token 必须存在且为合法 32 位 hex 字符串。

    真正的安全强度依赖 HTTPS + 限流；这里主要挡住纯脚本自动注册/登录。
    """
    if not token or not isinstance(token, str):
        raise HTTPException(400, "请先完成滑动验证")
    import re
    if not re.fullmatch(r"[0-9a-f]{16,128}", token):
        raise HTTPException(400, "滑动验证无效，请刷新重试")


@router.post("/register", response_model=schemas.TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    """注册后台用户（已废弃 — V2 已分离前后台用户体系）

    前台用户请使用 `/api/v1/public/portal/auth/register`
    后台用户由管理员通过 `/api/v1/auth/users` 创建

    本接口保留以保证向后兼容，但仅创建后台 User 实体。
    """
    _verify_slider_captcha(body.captcha_token)
    existing = await db.execute(
        select(models.User).where(
            (models.User.email == body.email) | (models.User.username == body.username),
            models.User.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "用户名或邮箱已存在")

    user = models.User(
        username=body.username,
        email=body.email,
        nickname=body.nickname or body.username,
        phone=body.phone,
        password_hash=hash_password(body.password),
        is_superuser=False,
        status="active",
    )
    db.add(user)
    await db.flush()

    role_ids = body.role_ids
    if not role_ids:
        viewer = (await db.execute(select(Role).where(Role.code == "viewer"))).scalar_one_or_none()
        if viewer:
            role_ids = [viewer.id]
    for rid in role_ids:
        db.add(UserRole(user_id=user.id, role_id=rid))

    await db.commit()
    user = await _load_user_with_perms(db, user.id)
    brief = _build_user_brief(user)
    return schemas.TokenResponse(
        access_token=create_access_token(user.id, {"is_superuser": user.is_superuser}),
        refresh_token=create_refresh_token(user.id, user.token_version),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=brief,
    )


@router.patch("/profile", response_model=schemas.UserBrief)
async def update_profile(
    body: schemas.UserUpdate,
    db: AsyncSession = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    """当前用户更新资料"""
    for k, v in body.model_dump(exclude_unset=True, exclude={"role_ids", "status"}).items():
        setattr(current, k, v)
    await db.commit()
    user = await _load_user_with_perms(db, current.id)
    return _build_user_brief(user)


@router.post("/change-password", status_code=204)
async def change_own_password(
    body: schemas.ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    """当前用户修改密码"""
    if not verify_password(body.old_password, current.password_hash):
        raise HTTPException(400, "原密码错误")
    current.password_hash = hash_password(body.new_password)
    current.token_version += 1
    await db.commit()


# ---- 登录 ----
@router.post("/login", response_model=schemas.TokenResponse)
async def login(body: schemas.LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """账号密码登录。username 可以是邮箱、用户名或手机号。"""
    if await _is_captcha_required(db):
        _verify_slider_captcha(body.captcha_token)
    # 查找用户
    stmt = select(models.User).where(
        models.User.deleted_at.is_(None),
        (models.User.email == body.username)
        | (models.User.username == body.username)
        | (models.User.phone == body.username),
    )
    user = (await db.execute(stmt)).scalar_one_or_none()

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent", "")[:500]

    if not user or not verify_password(body.password, user.password_hash):
        log.warning("auth.login.failed", username=body.username, ip=ip)
        # 记录失败日志（user_id 可能是 0 / None）
        if user is not None:
            db.add(models.LoginLog(
                user_id=user.id, ip=ip, user_agent=ua,
                success=False, reason="wrong_password", provider="local",
            ))
            await db.commit()
        raise HTTPException(status_code=401, detail="账号或密码错误")

    if user.status != "active":
        db.add(models.LoginLog(
            user_id=user.id, ip=ip, user_agent=ua,
            success=False, reason=f"status_{user.status}", provider="local",
        ))
        await db.commit()
        raise HTTPException(status_code=403, detail=f"账号已{user.status}")

    # 更新最后登录
    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = ip
    # 成功登录日志
    db.add(models.LoginLog(
        user_id=user.id, ip=ip, user_agent=ua, success=True, provider="local",
    ))
    await db.commit()

    log.info("auth.login.ok", user_id=user.id, username=user.username)

    # 插件框架：触发登录成功事件
    try:
        await dispatch("user.login", user=user, db=db, request=request)
    except Exception as e:
        log.warning("hook.dispatch_failed", hook="user.login", error=str(e))

    # 重新加载（含权限）
    user = await _load_user_with_perms(db, user.id)
    brief = _build_user_brief(user)

    return schemas.TokenResponse(
        access_token=create_access_token(user.id, {"is_superuser": user.is_superuser}),
        refresh_token=create_refresh_token(user.id, user.token_version),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=brief,
    )


@router.get("/login-config", summary="登录页配置（公开，无需认证）")
async def login_config(db: AsyncSession = Depends(get_db)):
    return {"captcha_required": await _is_captcha_required(db)}


@router.post("/refresh", response_model=schemas.TokenResponse)
async def refresh(body: schemas.RefreshRequest, db: AsyncSession = Depends(get_db)):
    """刷新 access token（旋转 refresh token）"""
    try:
        payload = decode_token(body.refresh_token)
    except JWTError as e:
        raise HTTPException(401, f"Refresh token 无效: {e}")

    if payload.get("type") != "refresh":
        raise HTTPException(401, "不是 refresh token")

    user_id = int(payload["sub"])
    tv = payload.get("tv", 0)

    user = await _load_user_with_perms(db, user_id)
    if not user or user.token_version != tv:
        raise HTTPException(401, "Token 已被撤销")
    if user.status != "active":
        raise HTTPException(403, f"账号已{user.status}")

    return schemas.TokenResponse(
        access_token=create_access_token(user.id, {"is_superuser": user.is_superuser}),
        refresh_token=create_refresh_token(user.id, user.token_version),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=_build_user_brief(user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """登出：bump token_version（旧 token 全部失效）"""
    user.token_version = (user.token_version or 0) + 1
    await db.commit()
    log.info("auth.logout", user_id=user.id)


# ===== 忘记密码 =====
@router.post("/forgot-password", status_code=200)
async def forgot_password(body: dict, request: Request, db: AsyncSession = Depends(get_db)):
    """请求重置密码：发邮件。

    body: { email, frontend_base? }
    为防止枚举账户，无论邮箱是否存在都返回成功。
    """
    email = (body.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(400, "请输入邮箱")
    frontend_base = body.get("frontend_base") or settings.PUBLIC_BASE_URL

    # 查用户
    user = (await db.execute(
        select(models.User).where(
            models.User.email == email, models.User.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

    # 始终返回 200，避免邮箱枚举
    if not user:
        log.info("auth.forgot.unknown_email", email=email)
        return {"ok": True, "message": "如果该邮箱已注册，重置链接已发送"}

    # 生成 token + 失效时间
    token = secrets.token_urlsafe(48)[:64]
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    db.add(PasswordReset(
        user_id=user.id, token=token, expires_at=expires,
        ip=request.client.host if request.client else None,
    ))
    await db.commit()

    # 构造重置链接
    reset_link = f"{frontend_base.rstrip('/')}/reset-password?token={token}"
    subject = "【Cenkor Admin】重置您的密码"
    body_text = (
        f"您好，\n\n"
        f"我们收到了重置 {email} 账户密码的请求。\n"
        f"请点击下方链接在 1 小时内重置密码：\n\n"
        f"  {reset_link}\n\n"
        f"如果这不是您本人的操作，请忽略此邮件。\n\n"
        f"—— Cenkor Admin"
    )
    body_html = (
        f"<p>您好，</p>"
        f"<p>我们收到了重置 <b>{email}</b> 账户密码的请求。</p>"
        f"<p><a href=\"{reset_link}\" "
        f"style=\"display:inline-block;padding:10px 18px;background:#0f172a;color:white;"
        f"border-radius:8px;text-decoration:none;font-weight:500;\">重置密码</a></p>"
        f"<p style=\"color:#64748b;font-size:13px;\">链接 1 小时内有效。如果不是您本人的操作，请忽略此邮件。</p>"
        f"<hr><p style=\"color:#94a3b8;font-size:11px;\">Cenkor Admin</p>"
    )
    try:
        result = send_email(email, subject, body_text)
        if not result.get("ok"):
            log.warning("auth.forgot.email_failed", email=email, reason=result.get("reason"))
    except Exception as e:
        log.error("auth.forgot.email_exception", error=str(e), email=email)

    return {"ok": True, "message": "如果该邮箱已注册，重置链接已发送"}


@router.post("/reset-password", status_code=200)
async def reset_password(body: dict, db: AsyncSession = Depends(get_db)):
    """使用 token 重置密码。

    body: { token, new_password }
    """
    token = (body.get("token") or "").strip()
    new_password = body.get("new_password") or ""
    if not token or len(new_password) < 8:
        raise HTTPException(400, "参数错误：token 必填，新密码 ≥8 位")

    reset = (await db.execute(
        select(PasswordReset).where(PasswordReset.token == token)
    )).scalar_one_or_none()
    if not reset:
        raise HTTPException(400, "重置链接无效或已过期")
    if reset.used_at is not None:
        raise HTTPException(400, "重置链接已被使用")
    expires_at = reset.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(400, "重置链接已过期")

    user = await db.get(models.User, reset.user_id)
    if not user or user.deleted_at is not None:
        raise HTTPException(400, "用户不存在")

    user.password_hash = hash_password(new_password)
    user.token_version = (user.token_version or 0) + 1  # 旧 token 全部失效
    reset.used_at = datetime.now(timezone.utc)
    await db.commit()
    log.info("auth.reset.ok", user_id=user.id)
    return {"ok": True}


# /me 路由在 api/v1/__init__.py 中定义（避免循环引用）


# ===== 飞书 OAuth =====
@router.get("/feishu/authorize", summary="飞书登录 - 跳转授权页")
async def feishu_authorize():
    """前端跳转到此端点，后端 302 重定向到飞书授权页"""
    if not feishu.enabled:
        raise HTTPException(503, "飞书登录未配置（需要 FEISHU_APP_ID / FEISHU_APP_SECRET）")
    state = feishu.new_state()
    await feishu.store_state(state)
    url = feishu.build_authorize_url(state)
    return RedirectResponse(url=url)


@router.get("/feishu/callback", summary="飞书登录 - OAuth 回调")
async def feishu_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """飞书授权后回调，code 换 token，查找/创建用户"""
    if not feishu.enabled:
        raise HTTPException(503, "飞书登录未配置")

    if not await feishu.consume_state(state):
        raise HTTPException(400, "无效或已过期的 OAuth state")

    try:
        fs_user = await feishu.exchange_code(code)
    except Exception as e:
        log.error("feishu.exchange.failed", error=str(e))
        raise HTTPException(400, f"飞书登录失败: {e}")

    # 查找已有绑定
    oauth_result = await db.execute(
        select(models.UserOAuth).where(
            models.UserOAuth.provider == "feishu",
            models.UserOAuth.open_id == fs_user["open_id"],
        )
    )
    oauth = oauth_result.scalar_one_or_none()

    if oauth:
        user = await _load_user_with_perms(db, oauth.user_id)
    else:
        # 创建新用户
        from python_slugify import slugify
        username = f"fs_{fs_user['open_id'][:12]}"
        user = models.User(
            username=username,
            email=fs_user.get("email") or f"{username}@feishu.local",
            nickname=fs_user.get("name", "飞书用户"),
            avatar=fs_user.get("avatar_url"),
            password_hash=hash_password(secrets.token_urlsafe(32)),  # 不可登录的随机密码
        )
        db.add(user)
        await db.flush()
        db.add(models.UserOAuth(
            user_id=user.id, provider="feishu", open_id=fs_user["open_id"],
            union_id=fs_user.get("union_id"),
            access_token_enc=fs_user["access_token"],  # MVP：明文存，生产要加密
            refresh_token_enc=fs_user.get("refresh_token"),
            expires_at=None,
        ))
        await db.commit()
        user = await _load_user_with_perms(db, user.id)

    if not user:
        raise HTTPException(500, "用户创建失败")

    brief = _build_user_brief(user)
    return {
        "access_token": create_access_token(user.id, {"is_superuser": user.is_superuser}),
        "refresh_token": create_refresh_token(user.id, user.token_version),
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": brief.model_dump() if hasattr(brief, "model_dump") else brief,
    }


import secrets  # noqa: E402


# ===== Users 管理 =====
@router.get("/users", response_model=dict[str, Any])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: models.User = Depends(require_permission("rbac:user:read")),
    search: str | None = Query(None, description="按 username / email / nickname 模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """用户列表（含角色 ID）"""
    from cenkor_admin.core.repository import apply_filters, paginate
    from sqlalchemy import and_

    base_filters = apply_filters(
        models.User,
        search=search,
        search_fields=["username", "email", "nickname"],
    )
    stmt = (
        select(models.User, UserRole.role_id)
        .outerjoin(UserRole, UserRole.user_id == models.User.id)
        .where(and_(*base_filters))
    )
    # paginate 直接用会丢失 UserRole 的 role_id 字段；这里手工 count + 切片
    from sqlalchemy import func
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(models.User.id).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).all()

    # 收集 role_id
    user_dict: dict[int, dict] = {}
    for user, role_id in rows:
        if user.id not in user_dict:
            user_dict[user.id] = {
                "id": user.id, "username": user.username, "email": user.email,
                "nickname": user.nickname, "avatar": user.avatar,
                "status": user.status, "is_superuser": user.is_superuser,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
                "last_login_ip": user.last_login_ip,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "role_ids": [],
            }
        if role_id and role_id not in user_dict[user.id]["role_ids"]:
            user_dict[user.id]["role_ids"].append(role_id)

    return {"items": list(user_dict.values()), "total": total, "page": page, "page_size": page_size}


@router.get("/users/export")
async def export_users_csv(
    db: AsyncSession = Depends(get_db),
    _: models.User = Depends(require_permission("rbac:user:read")),
    search: str | None = None,
):
    """导出用户 CSV（流式分块）"""
    from cenkor_admin.core.repository import apply_filters, stream_for_csv
    from datetime import datetime as _dt
    from fastapi.responses import StreamingResponse

    base_filters = apply_filters(
        models.User,
        search=search,
        search_fields=["username", "email", "nickname"],
    )
    base_stmt = select(models.User).where(*base_filters)

    header = "id,username,email,nickname,status,is_superuser,last_login_at,created_at\r\n"

    async def gen():
        yield "\ufeff" + header
        async for u in stream_for_csv(db, base_stmt, id_column=models.User.id, batch_size=500):
            cells = [
                u.id, u.username, u.email, u.nickname or "",
                u.status, "1" if u.is_superuser else "0",
                u.last_login_at.isoformat() if u.last_login_at else "",
                u.created_at.isoformat() if u.created_at else "",
            ]
            line = ",".join(
                f'"{str(c).replace(chr(34), chr(34)*2)}"' if c and any(ch in str(c) for ch in [",", '"', "\n"]) else str(c)
                for c in cells
            )
            yield line + "\r\n"

    return StreamingResponse(
        gen(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="users_{_dt.now().strftime("%Y%m%d_%H%M%S")}.csv"',
        },
    )


@router.get("/users/{user_id}/login-history", response_model=dict[str, Any])
async def get_user_login_history(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: models.User = Depends(require_permission("rbac:user:read")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """用户登录历史（最近 90 天）"""
    from datetime import timedelta
    from cenkor_admin.core.repository import paginate
    since = datetime.now(timezone.utc) - timedelta(days=90)
    stmt = (
        select(models.LoginLog)
        .where(models.LoginLog.user_id == user_id, models.LoginLog.created_at >= since)
        .order_by(models.LoginLog.created_at.desc(), models.LoginLog.id.desc())
    )
    data = await paginate(db, stmt, page=page, page_size=page_size)
    return {
        "items": [
            {
                "id": l.id,
                "ip": l.ip,
                "user_agent": l.user_agent,
                "success": l.success,
                "reason": l.reason,
                "provider": l.provider,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in data["items"]
        ],
        "total": data["total"],
        "page": data["page"],
        "page_size": data["page_size"],
    }


@router.post("/users", status_code=201)
async def create_user(
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: models.User = Depends(require_permission("rbac:user:write")),
):
    """创建用户（管理端）"""
    username = body.get("username", "").strip()
    email = body.get("email", "").strip()
    password = body.get("password", "")
    if not username or not email or len(password) < 8:
        raise HTTPException(400, "username / email / password 必填且密码 ≥8 字符")

    # 重名检查
    existing = await db.execute(select(models.User).where(
        (models.User.username == username) | (models.User.email == email)
    ))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "用户名或邮箱已存在")

    user = models.User(
        username=username, email=email,
        nickname=body.get("nickname", ""),
        phone=body.get("phone"),
        password_hash=hash_password(password),
        is_superuser=bool(body.get("is_superuser", False)),
    )
    db.add(user)
    await db.flush()
    # 角色
    for rid in body.get("role_ids", []):
        db.add(UserRole(user_id=user.id, role_id=rid))
    await db.commit()
    await db.refresh(user)
    return {"id": user.id, "username": user.username, "email": user.email}


@router.patch("/users/{user_id}")
async def update_user(
    user_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: models.User = Depends(require_permission("rbac:user:write")),
):
    """更新用户（昵称/邮箱/状态/角色）"""
    user = await db.get(models.User, user_id)
    if not user or user.deleted_at:
        raise HTTPException(404, "User not found")

    if "nickname" in body: user.nickname = body["nickname"]
    if "email" in body:    user.email = body["email"]
    if "phone" in body:    user.phone = body["phone"]
    if "avatar" in body:   user.avatar = body["avatar"]
    if "status" in body:   user.status = body["status"]
    if "is_superuser" in body: user.is_superuser = bool(body["is_superuser"])

    # 角色：先删旧再加新
    if "role_ids" in body:
        from sqlalchemy import delete as sql_delete
        await db.execute(sql_delete(UserRole).where(UserRole.user_id == user_id))
        for rid in body["role_ids"]:
            db.add(UserRole(user_id=user_id, role_id=rid))

    await db.commit()
    return {"id": user.id}


@router.post("/users/{user_id}/change-password")
async def change_password(
    user_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: models.User = Depends(require_permission("rbac:user:write")),
):
    """管理端强制重置密码"""
    new_pwd = body.get("new_password", "")
    if len(new_pwd) < 8:
        raise HTTPException(400, "新密码至少 8 字符")
    user = await db.get(models.User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    user.password_hash = hash_password(new_pwd)
    user.token_version = (user.token_version or 0) + 1  # 强制旧 token 失效
    await db.commit()
    log.info("auth.password_reset", user_id=user_id)
    return {"ok": True}


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current: models.User = Depends(get_current_user),
    _: models.User = Depends(require_permission("rbac:user:write")),
):
    """软删（不能删自己）"""
    if user_id == current.id:
        raise HTTPException(400, "不能删除自己")
    user = await db.get(models.User, user_id)
    if not user or user.deleted_at:
        raise HTTPException(404, "User not found")
    user.deleted_at = datetime.now(timezone.utc)
    user.token_version = (user.token_version or 0) + 1
    await db.commit()
