"""账号存储（realm 维度）。

provider 拿到 ``OAuthUser`` 之后交给这里，由它决定落到哪套用户表、发哪种 JWT。
这样渠道层完全不需要知道「我是给前台还是后台用的」。

两个 realm 的行为差异是**安全边界**，不是配置项：

===================  ==============================  ============================
                     portal（前台客户）               admin（后台管理角色）
===================  ==============================  ============================
首次登录             自动建号，注册即用                **拒绝**，只按已有绑定找账号
理由                 客户端产品，降低注册摩擦          后台是权限入口，能自助进等于绕过
                                                       权限审批
发什么 token         portal 专用 JWT（iss 隔离）       admin JWT（core.security）
成功去哪             建号或登录                       仅登录
===================  ==============================  ============================

后台这条约束在代码里写死（``auto_register = False`` 且找不到就抛异常），
不做成开关 —— 一个能被配置打开的「后门」本身就是风险。
"""

from __future__ import annotations

import hashlib
import secrets
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.portal import models as portal_models
from cenkor_admin.apps.portal.auth import (
    create_portal_access_token,
    create_portal_refresh_token,
    hash_password,
)
from cenkor_admin.core.config import get_settings
from cenkor_admin.core.secrets import encrypt_secret

from .providers.base import OAuthUser

settings = get_settings()


class SsoLoginError(Exception):
    """登录被业务规则拒绝（账号不存在 / 已停用 / 已绑定他人）。

    ``payload`` 会作为结构化信息传给前端，前端据此展示可操作提示，
    比如「账号未绑定，请联系管理员」而不是笼统的「登录失败」。
    """

    def __init__(self, message: str, code: str = "denied") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def _token_expiry(expires_in: int | None) -> datetime | None:
    if not expires_in:
        return None
    return datetime.now(UTC) + timedelta(seconds=int(expires_in))


class AccountStore(ABC):
    """账号存储抽象。子类实现「查绑定 / 建号 / 发 token」。"""

    realm: str = ""
    # 首次登录是否自动建号。后台恒为 False，见模块文档。
    auto_register: bool = False
    # 该端登录成功后，前端应跳回的默认路径
    default_redirect: str = "/"

    # ---------- 绑定查询与写入 ----------

    @abstractmethod
    async def find_user_by_identity(
        self, db: AsyncSession, provider: str, subject: str
    ) -> int | None:
        """按 (provider, subject) 查已绑定的本端 user_id。"""

    @abstractmethod
    async def bind(
        self, db: AsyncSession, user_id: int, provider: str, user: OAuthUser
    ) -> None:
        """建立绑定关系。已存在则不重复插入。"""

    @abstractmethod
    async def create_user(self, db: AsyncSession, provider: str, user: OAuthUser) -> int:
        """按第三方信息建本端账号，返回 user_id。"""

    @abstractmethod
    async def get_active_user(self, db: AsyncSession, user_id: int) -> Any | None:
        """取用户并校验状态。不存在 / 已停用返回 None。"""

    @abstractmethod
    async def log_login(
        self,
        db: AsyncSession,
        *,
        user_id: int | None,
        provider: str,
        success: bool,
        reason: str | None = None,
    ) -> None:
        """记录登录历史。"""

    # ---------- 主流程 ----------

    async def login_or_register(
        self, db: AsyncSession, provider: str, user: OAuthUser
    ) -> tuple[int, bool]:
        """返回 (user_id, 是否新建)。"""
        existing = await self.find_user_by_identity(db, provider, user.subject)
        if existing is not None:
            await self.bind(db, existing, provider, user)  # 刷新 token / 昵称
            return existing, False

        if not self.auto_register:
            raise SsoLoginError(
                "该账号未绑定本站，请联系管理员在用户管理里绑定后再用第三方登录",
                code="not_bound",
            )

        user_id = await self.create_user(db, provider, user)
        return user_id, True

    def issue_tokens(self, user: Any) -> dict[str, Any]:
        """签发本端 token。"""
        raise NotImplementedError

    # ---------- 工具 ----------

    @staticmethod
    async def _unique_username(
        db: AsyncSession, model: Any, base: str, *, max_len: int = 60
    ) -> str:
        """生成不冲突的用户名。

        第三方账号批量导入时重名是常态（微信昵称会重、subject 前 12 位可能也重），
        靠 UNIQUE 约束报错再重试的写法会在并发下打架，这里一次性算出可用名。
        """
        base = base.strip()[:max_len] or "user"
        candidate = base
        for i in range(2, 50):
            exists = await db.execute(select(model.id).where(model.username == candidate))
            if exists.scalar_one_or_none() is None:
                return candidate
            suffix = f"_{i}"
            candidate = f"{base[: max_len - len(suffix)]}{suffix}"
        # 兜底：随机后缀。走到这里说明同名账号已经 50 个，正常业务不会发生。
        return f"{base[:max_len - 8]}_{secrets.token_hex(4)}"

    @staticmethod
    async def _free_email(db: AsyncSession, model: Any, email: str | None) -> str | None:
        """邮箱被占用时降级为 None。

        第三方给的邮箱可能和本站已有账号撞（用户拿同一个邮箱注册过本站）。
        后端不能因此报 500 —— 但也**绝不能**把两个账号合并：那等于任何人只要
        能控制一个邮箱就能接管别人账号。所以这里只做「留空」，绑定关系交给
        用户登录后手动操作。
        """
        if not email:
            return None
        exists = await db.execute(select(model.id).where(model.email == email))
        return None if exists.scalar_one_or_none() is not None else email


class PortalAccountStore(AccountStore):
    """前台客户账号。"""

    realm = "portal"
    auto_register = True
    default_redirect = "/"

    async def find_user_by_identity(
        self, db: AsyncSession, provider: str, subject: str
    ) -> int | None:
        row = await db.execute(
            select(portal_models.PortalUserOAuth.user_id).where(
                portal_models.PortalUserOAuth.provider == provider,
                portal_models.PortalUserOAuth.open_id == subject,
            )
        )
        return row.scalar_one_or_none()

    async def bind(
        self, db: AsyncSession, user_id: int, provider: str, user: OAuthUser
    ) -> None:
        row = await db.execute(
            select(portal_models.PortalUserOAuth).where(
                portal_models.PortalUserOAuth.provider == provider,
                portal_models.PortalUserOAuth.open_id == user.subject,
            )
        )
        existing = row.scalar_one_or_none()
        now = datetime.now(UTC)
        if existing is None:
            db.add(portal_models.PortalUserOAuth(
                user_id=user_id,
                provider=provider,
                open_id=user.subject,
                union_id=user.union_id,
                access_token_enc=encrypt_secret(user.access_token),
                refresh_token_enc=encrypt_secret(user.refresh_token),
                expires_at=_token_expiry(user.expires_in),
                raw_profile=user.raw,
                last_login_at=now,
            ))
        else:
            # 每次登录都刷新 token：第三方可能轮换了 access_token，
            # 旧的一旦失效，后续想调渠道 API（比如拉头像、发消息）就会失败
            existing.union_id = user.union_id or existing.union_id
            existing.access_token_enc = encrypt_secret(user.access_token) or existing.access_token_enc
            existing.refresh_token_enc = encrypt_secret(user.refresh_token) or existing.refresh_token_enc
            existing.expires_at = _token_expiry(user.expires_in) or existing.expires_at
            existing.raw_profile = user.raw
            existing.last_login_at = now
        await db.flush()

    async def create_user(self, db: AsyncSession, provider: str, user: OAuthUser) -> int:
        # 用户名取「渠道_前12位」：比纯随机可读，排障时一眼能看出是从哪来的。
        # subject 可能含特殊字符（飞书 open_id 是 ou_xxx，微信是 oXxx），只留安全字符。
        digest = hashlib.sha256(user.subject.encode("utf-8")).hexdigest()[:8]
        safe = "".join(c for c in user.subject[:12] if c.isalnum()) or digest
        username = await self._unique_username(
            db, portal_models.PortalUser, f"{provider}_{safe}"
        )
        email = await self._free_email(db, portal_models.PortalUser, user.email)

        row = portal_models.PortalUser(
            username=username,
            email=email,
            nickname=(user.nickname or provider)[:80],
            avatar=user.avatar,
            # 密码字段 NOT NULL，第三方用户没有密码。给一个随机串，
            # 这样「忘记密码」流程永远走不通（没人知道这个串），
            # 也就不会出现「第三方账号被猜出密码登录」的漏洞。
            password_hash=hash_password(secrets.token_urlsafe(32)),
            register_ip=None,
            last_login_at=datetime.now(UTC),
        )
        db.add(row)
        await db.flush()
        await self.bind(db, row.id, provider, user)
        return row.id

    async def get_active_user(
        self, db: AsyncSession, user_id: int
    ) -> portal_models.PortalUser | None:
        user = await db.get(portal_models.PortalUser, user_id)
        if user is None or user.deleted_at is not None:
            return None
        if user.status != "active":
            raise SsoLoginError(f"账号状态为 {user.status}，无法登录", code="inactive")
        return user

    async def log_login(
        self,
        db: AsyncSession,
        *,
        user_id: int | None,
        provider: str,
        success: bool,
        reason: str | None = None,
    ) -> None:
        db.add(portal_models.PortalLoginLog(
            user_id=user_id or 0,
            provider=provider,
            success=success,
            reason=reason,
        ))
        await db.flush()

    def issue_tokens(self, user: portal_models.PortalUser) -> dict[str, Any]:
        return {
            "access_token": create_portal_access_token(user.id),
            "refresh_token": create_portal_refresh_token(user.id, user.token_version),
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "nickname": user.nickname,
                "avatar": user.avatar,
            },
        }


class AdminAccountStore(AccountStore):
    """后台管理角色账号。

    **不自动建号**：扫码进来的人如果本地没有绑定关系，一律拒绝。
    后台账号必须由超管在「用户管理」里创建并分配角色，第三方登录只是
    给已有账号开一条免密通道，不是注册入口。
    """

    realm = "admin"
    auto_register = False
    default_redirect = "/dashboard"

    async def find_user_by_identity(
        self, db: AsyncSession, provider: str, subject: str
    ) -> int | None:
        row = await db.execute(
            select(auth_models.UserOAuth.user_id).where(
                auth_models.UserOAuth.provider == provider,
                auth_models.UserOAuth.open_id == subject,
            )
        )
        return row.scalar_one_or_none()

    async def bind(
        self, db: AsyncSession, user_id: int, provider: str, user: OAuthUser
    ) -> None:
        row = await db.execute(
            select(auth_models.UserOAuth).where(
                auth_models.UserOAuth.provider == provider,
                auth_models.UserOAuth.open_id == user.subject,
            )
        )
        existing = row.scalar_one_or_none()
        if existing is None:
            # 同一用户重复绑同一渠道时，先解掉旧绑定再插新的，
            # 否则会撞 UNIQUE(provider, open_id)
            db.add(auth_models.UserOAuth(
                user_id=user_id,
                provider=provider,
                open_id=user.subject,
                union_id=user.union_id,
                access_token_enc=encrypt_secret(user.access_token),
                refresh_token_enc=encrypt_secret(user.refresh_token),
                expires_at=_token_expiry(user.expires_in),
                raw_profile=user.raw,
                last_login_at=datetime.now(UTC),
            ))
        else:
            existing.union_id = user.union_id or existing.union_id
            existing.access_token_enc = encrypt_secret(user.access_token) or existing.access_token_enc
            existing.last_login_at = datetime.now(UTC)
        await db.flush()

    async def create_user(self, db: AsyncSession, provider: str, user: OAuthUser) -> int:
        # 理论不可达（auto_register=False 时 login_or_register 会提前抛异常），
        # 保留是为了让抽象完整；真被调用说明有人改了 auto_register，
        # 直接抛错比默默建号安全。
        raise SsoLoginError(
            "后台不支持第三方自助注册，请用账号密码登录", code="no_register"
        )

    async def get_active_user(
        self, db: AsyncSession, user_id: int
    ) -> auth_models.User | None:
        user = await db.get(auth_models.User, user_id)
        if user is None or user.deleted_at is not None:
            return None
        if user.status != "active":
            raise SsoLoginError(f"账号状态为 {user.status}，无法登录", code="inactive")
        return user

    async def log_login(
        self,
        db: AsyncSession,
        *,
        user_id: int | None,
        provider: str,
        success: bool,
        reason: str | None = None,
    ) -> None:
        db.add(auth_models.LoginLog(
            user_id=user_id or 0,
            provider=provider,
            success=success,
            reason=reason,
        ))
        await db.flush()

    def issue_tokens(self, user: auth_models.User) -> dict[str, Any]:
        # 与账号密码登录走同一套签发逻辑，保证权限、token_version 语义一致。
        # 延迟导入避免 sso 与 core.security 的循环依赖。
        from cenkor_admin.core.security import create_access_token, create_refresh_token

        return {
            "access_token": create_access_token(user.id, extra={"username": user.username}),
            "refresh_token": create_refresh_token(user.id, user.token_version),
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "nickname": user.nickname,
                "avatar": user.avatar,
            },
        }


_STORES: dict[str, AccountStore] = {
    "portal": PortalAccountStore(),
    "admin": AdminAccountStore(),
}


def get_store(realm: str) -> AccountStore:
    store = _STORES.get(realm)
    if store is None:
        raise SsoLoginError(f"未知的登录端：{realm}", code="bad_realm")
    return store


__all__ = [
    "AccountStore",
    "AdminAccountStore",
    "PortalAccountStore",
    "SsoLoginError",
    "get_store",
]
