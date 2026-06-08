"""Auth App · Pydantic schemas"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---- 登录 ----
class LoginRequest(BaseModel):
    """账号密码登录"""
    username: str = Field(..., description="邮箱 / 用户名 / 手机号")
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # 秒
    user: "UserBrief"


class RefreshRequest(BaseModel):
    refresh_token: str


# ---- 用户 ----
class UserBrief(BaseModel):
    id: int
    username: str
    email: EmailStr
    nickname: str = ""
    avatar: str | None = None
    is_superuser: bool = False
    permissions: list[str] = []   # 展开后的权限码
    menus: list[dict[str, Any]] = []

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=80)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    nickname: str = ""
    phone: str | None = None
    is_superuser: bool = False
    role_ids: list[int] = []


class UserUpdate(BaseModel):
    nickname: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    avatar: str | None = None
    status: str | None = None
    role_ids: list[int] | None = None


class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    nickname: str
    avatar: str | None
    status: str
    is_superuser: bool
    last_login_at: datetime | None
    created_at: datetime
    role_ids: list[int] = []

    model_config = ConfigDict(from_attributes=True)


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


# 解决前向引用
TokenResponse.model_rebuild()
