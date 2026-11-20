"""Auth App · 鉴权 API"""
from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from cenkor_admin.api.deps import get_current_user, require_permission
from cenkor_admin.apps.auth import models, schemas
from cenkor_admin.apps.auth.oauth import feishu
from cenkor_admin.apps.notification.models import PasswordReset
from cenkor_admin.apps.rbac.models import (
    Role,
    RoleMenu,
    RolePermission,
    UserRole,
)
from cenkor_admin.core.auth_guard import (
    check_login_rate,
    check_public_rate,
    consume_refresh_jti,
    record_login_failure,
    record_login_success,
    refresh_ttl_seconds,
)
from cenkor_admin.core.config import get_settings
from cenkor_admin.core.db import get_db
from cenkor_admin.core.hooks import dispatch
from cenkor_admin.core.mail import send_email
from cenkor_admin.core.secrets import encrypt_secret
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
def _safe_reset_base(candidate: str | None) -> str:
    """密码重置链接的域名白名单校验。

    candidate 来自请求体，不做校验就等于允许攻击者把重置链接指向钓鱼站
    （受害者邮箱收到的 token 直接送给攻击者）。只放行 PUBLIC_BASE_URL 与
    CORS 白名单里的前端源；其余一律回落服务端默认值。
    """
    default = settings.PUBLIC_BASE_URL.rstrip("/")
    allowed = {urlparse(default).netloc}
    for origin in settings.cors_origins_list:
        netloc = urlparse(origin).netloc
        if netloc:
            allowed.add(netloc)
    if candidate:
        parsed = urlparse(candidate)
        if parsed.scheme in ("http", "https") and parsed.netloc in allowed:
            return candidate.rstrip("/")
    return default


def _csv_cell(value: Any) -> str:
    """CSV 单元格公式注入防护：= + - @ 开头的串会被 Excel 当公式执行。"""
    s = "" if value is None else str(value)
    if s and s[0] in "=+-@\t\r":
        s = "'" + s
    return s


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
            # 停用应用的菜单不下发（app_registry.set_app_enabled 会置 status=disabled）。
            # 角色-菜单授权关系保留在库里，应用重新启用后菜单即刻恢复。
            if getattr(menu, "status", "active") != "active":
                continue
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
    """已下线（2026-11-11 安全修复）。

    历史上本接口公开创建后台 User 且接受请求体里的 role_ids，
    任何人可注册并指定管理员角色 → 提权。滑动验证码也仅是格式校验。
    保留路由壳子返回 410，让旧客户端拿到明确语义而不是静默成功。
    后台账号一律由管理员通过 /api/v1/auth/users 创建；
    前台用户走 /api/v1/public/portal/auth/register。
    """
    raise HTTPException(410, "后台注册接口已下线，请联系管理员创建账号")


@router.patch("/profile", response_model=schemas.UserBrief)
async def update_profile(
    body: schemas.UserUpdate,
    db: AsyncSession = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    """当前用户更新资料"""
    data = body.model_dump(exclude_unset=True, exclude={"role_ids", "status"})
    # 邮箱变更必须查唯一性：重复邮箱会让 forgot-password 的
    # scalar_one_or_none 抛 MultipleResultsFound，可被用来瘫痪他人重置流程
    new_email = data.get("email")
    if new_email and new_email != current.email:
        dup = await db.execute(
            select(models.User).where(
                models.User.email == new_email,
                models.User.id != current.id,
                models.User.deleted_at.is_(None),
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(409, "邮箱已被其他账号使用")
    for k, v in data.items():
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
    ip = request.client.host if request.client else "unknown"
    # 应用层限流 + 账号锁定（不依赖 nginx 边缘规则，见 core.auth_guard）
    await check_login_rate(ip, body.username)
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

    ua = request.headers.get("user-agent", "")[:500]

    if not user or not verify_password(body.password, user.password_hash):
        await record_login_failure(ip, body.username)
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
    await record_login_success(ip, body.username)
    user.last_login_at = datetime.now(UTC)
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
        access_token=create_access_token(
            user.id, {"is_superuser": user.is_superuser}, token_version=user.token_version,
        ),
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

    # 一次性旋转：jti 消费失败 = 旧 token 重放（可能已泄露），
    # bump token_version 撤销该用户全部会话，迫使重新登录。
    # 无 jti 的遗留 token（升级前签发）放行，7 天窗口后自然淘汰。
    jti = payload.get("jti")
    if jti and not await consume_refresh_jti(jti, refresh_ttl_seconds(payload)):
        user.token_version = (user.token_version or 0) + 1
        await db.commit()
        log.warning("auth.refresh.replay_detected", user_id=user.id)
        raise HTTPException(401, "Refresh token 已被使用，所有会话已失效，请重新登录")

    return schemas.TokenResponse(
        access_token=create_access_token(
            user.id, {"is_superuser": user.is_superuser}, token_version=user.token_version,
        ),
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
    # 防邮件轰炸 / 枚举探测：单 IP 每分钟最多 5 次
    await check_public_rate(
        request.client.host if request.client else "unknown", "forgot_password", limit=5,
    )
    # 重置链接域名走白名单，杜绝请求体投毒到钓鱼站
    frontend_base = _safe_reset_base(body.get("frontend_base"))

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
    # adm- 前缀：与前台重置令牌隔离（共用 password_resets 表，
    # 不带区分会让前台令牌重置同 id 的后台账号）
    token = "adm-" + secrets.token_urlsafe(48)[:60]
    expires = datetime.now(UTC) + timedelta(hours=1)
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
    # 拒绝前台体系签发的重置令牌（ptl- 前缀），防跨体系重置
    if token.startswith("ptl-"):
        raise HTTPException(400, "重置链接无效或已过期")

    reset = (await db.execute(
        select(PasswordReset).where(PasswordReset.token == token)
    )).scalar_one_or_none()
    if not reset:
        raise HTTPException(400, "重置链接无效或已过期")
    if reset.used_at is not None:
        raise HTTPException(400, "重置链接已被使用")
    expires_at = reset.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        raise HTTPException(400, "重置链接已过期")

    user = await db.get(models.User, reset.user_id)
    if not user or user.deleted_at is not None:
        raise HTTPException(400, "用户不存在")

    user.password_hash = hash_password(new_password)
    user.token_version = (user.token_version or 0) + 1  # 旧 token 全部失效
    reset.used_at = datetime.now(UTC)
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
            # 第三方 token 与 API Key 同等待遇：Fernet 加密落库，
            # 避免 pg_dump / 只读账号 / 运维 SELECT * 散落明文
            access_token_enc=encrypt_secret(fs_user["access_token"]),
            refresh_token_enc=encrypt_secret(fs_user.get("refresh_token")),
            expires_at=None,
        ))
        await db.commit()
        user = await _load_user_with_perms(db, user.id)

    if not user:
        raise HTTPException(500, "用户创建失败")

    brief = _build_user_brief(user)
    return {
        "access_token": create_access_token(
            user.id, {"is_superuser": user.is_superuser}, token_version=user.token_version,
        ),
        "refresh_token": create_refresh_token(user.id, user.token_version),
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": brief.model_dump() if hasattr(brief, "model_dump") else brief,
    }




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
    from sqlalchemy import and_

    from cenkor_admin.core.repository import apply_filters

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
    from datetime import datetime as _dt

    from fastapi.responses import StreamingResponse

    from cenkor_admin.core.repository import apply_filters, stream_for_csv

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
                f'"{c.replace(chr(34), chr(34)*2)}"' if c and any(ch in c for ch in [",", '"', "\n"]) else c
                for c in (_csv_cell(x) for x in cells)
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
    since = datetime.now(UTC) - timedelta(days=90)
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
    current: models.User = Depends(get_current_user),
    _: models.User = Depends(require_permission("rbac:user:write")),
):
    """创建用户（管理端）"""
    username = body.get("username", "").strip()
    email = body.get("email", "").strip()
    password = body.get("password", "")
    if not username or not email or len(password) < 8:
        raise HTTPException(400, "username / email / password 必填且密码 ≥8 字符")
    # 提权收口：只有超管能造超管。否则「管用户的人」可给自己造一个
    # is_superuser 账号，rbac:user:write 就成了事实上的最高权限
    if body.get("is_superuser") and not current.is_superuser:
        raise HTTPException(403, "只有超级管理员能创建超级管理员")

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
    current: models.User = Depends(get_current_user),
    _: models.User = Depends(require_permission("rbac:user:write")),
):
    """更新用户（昵称/邮箱/状态/角色）"""
    user = await db.get(models.User, user_id)
    if not user or user.deleted_at:
        raise HTTPException(404, "User not found")
    # 超管账号只能由超管修改；is_superuser 字段 likewise。
    # 堵住「改超管邮箱/角色」与「自我提权」两条路径
    if user.is_superuser and not current.is_superuser:
        raise HTTPException(403, "无权修改超级管理员账号")
    if "is_superuser" in body and not current.is_superuser:
        raise HTTPException(403, "只有超级管理员能授予/撤销超级管理员")

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
    current: models.User = Depends(get_current_user),
    _: models.User = Depends(require_permission("rbac:user:write")),
):
    """管理端强制重置密码"""
    new_pwd = body.get("new_password", "")
    if len(new_pwd) < 8:
        raise HTTPException(400, "新密码至少 8 字符")
    user = await db.get(models.User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.is_superuser and not current.is_superuser:
        raise HTTPException(403, "无权重置超级管理员密码")
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
    if user.is_superuser and not current.is_superuser:
        raise HTTPException(403, "无权删除超级管理员账号")
    user.deleted_at = datetime.now(UTC)
    user.token_version = (user.token_version or 0) + 1
    await db.commit()
