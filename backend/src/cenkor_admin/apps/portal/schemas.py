"""Portal App · Pydantic schemas（前台用户）"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class PortalLoginRequest(BaseModel):
    username: str = Field(..., description="用户名 / 邮箱 / 手机号")
    password: str
    captcha_token: str | None = Field(None, description="滑动验证 token")


class PortalRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=80)
    email: EmailStr | None = None
    password: str = Field(..., min_length=8, max_length=128)
    nickname: str = ""
    phone: str | None = None
    captcha_token: str | None = Field(None, description="滑动验证 token")


class PortalTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "PortalUserBrief"


class PortalRefreshRequest(BaseModel):
    refresh_token: str


class PortalUserBrief(BaseModel):
    id: int
    username: str
    email: str | None = None
    nickname: str = ""
    avatar: str | None = None
    model_config = ConfigDict(from_attributes=True)


class PortalUserUpdate(BaseModel):
    nickname: str | None = None
    email: str | None = None
    phone: str | None = None
    avatar: str | None = None


class PortalChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


class PortalForgotPasswordRequest(BaseModel):
    email: str
    frontend_base: str | None = None


class PortalResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)


class PortalOAuthBindRequest(BaseModel):
    """用户自行绑定 OAuth（移动端使用）"""
    provider: str = Field(..., description="feishu / wechat / github")
    open_id: str = Field(..., min_length=1, max_length=200)
    union_id: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None


class PortalOAuthBindingOut(BaseModel):
    id: int
    provider: str
    open_id: str
    union_id: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


PortalTokenResponse.model_rebuild()
