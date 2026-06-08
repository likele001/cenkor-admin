"""RBAC · Pydantic schemas"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---- 角色 ----
class RoleBase(BaseModel):
    code: str = Field(..., min_length=2, max_length=50)
    name: str
    description: str | None = None


class RoleCreate(RoleBase):
    permission_ids: list[int] = []
    menu_ids: list[int] = []


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    permission_ids: list[int] | None = None
    menu_ids: list[int] | None = None


class RoleOut(RoleBase):
    id: int
    is_system: bool
    created_at: datetime
    permission_ids: list[int] = []
    menu_ids: list[int] = []
    model_config = ConfigDict(from_attributes=True)


# ---- 权限 ----
class PermissionOut(BaseModel):
    id: int
    code: str
    type: str
    name: str
    description: str | None = None
    model_config = ConfigDict(from_attributes=True)


# ---- 菜单 ----
class MenuOut(BaseModel):
    id: int
    key: str
    parent_id: int | None
    title: str
    icon: str | None
    path: str | None
    sort: int
    status: str
    children: list["MenuOut"] = []
    model_config = ConfigDict(from_attributes=True)


MenuOut.model_rebuild()
