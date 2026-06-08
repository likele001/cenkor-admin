"""RBAC · API"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.rbac import models, schemas
from cenkor_admin.core.db import get_db

router = APIRouter()


# ---- 角色 ----
@router.get("/roles", response_model=dict[str, Any])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:read")),
):
    result = await db.execute(select(models.Role).order_by(models.Role.id))
    roles = result.scalars().all()
    return {
        "items": [
            {
                "id": r.id,
                "code": r.code,
                "name": r.name,
                "description": r.description,
                "is_system": r.is_system,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in roles
        ]
    }


@router.post("/roles", response_model=schemas.RoleOut, status_code=201)
async def create_role(
    body: schemas.RoleCreate,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    role = models.Role(**body.model_dump(exclude={"permission_ids", "menu_ids"}))
    db.add(role)
    await db.flush()  # 拿 id

    for pid in body.permission_ids:
        db.add(models.RolePermission(role_id=role.id, permission_id=pid))
    for mid in body.menu_ids:
        db.add(models.RoleMenu(role_id=role.id, menu_id=mid))

    await db.commit()
    await db.refresh(role)
    return role


@router.get("/roles/{role_id}", response_model=dict[str, Any])
async def get_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:read")),
):
    role = await db.get(models.Role, role_id)
    if not role:
        raise HTTPException(404, "Role not found")
    perm_result = await db.execute(
        select(models.RolePermission.permission_id).where(models.RolePermission.role_id == role_id)
    )
    menu_result = await db.execute(
        select(models.RoleMenu.menu_id).where(models.RoleMenu.role_id == role_id)
    )
    return {
        "id": role.id,
        "code": role.code,
        "name": role.name,
        "description": role.description,
        "is_system": role.is_system,
        "permission_ids": list(perm_result.scalars().all()),
        "menu_ids": list(menu_result.scalars().all()),
        "created_at": role.created_at.isoformat() if role.created_at else None,
    }


@router.patch("/roles/{role_id}", response_model=schemas.RoleOut)
async def update_role(
    role_id: int,
    body: schemas.RoleUpdate,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    role = await db.get(models.Role, role_id)
    if not role:
        raise HTTPException(404, "Role not found")
    if role.is_system and body.name is not None:
        pass  # 允许改描述，code 不可改
    for k, v in body.model_dump(exclude_unset=True, exclude={"permission_ids", "menu_ids"}).items():
        setattr(role, k, v)
    if body.permission_ids is not None:
        await db.execute(delete(models.RolePermission).where(models.RolePermission.role_id == role_id))
        for pid in body.permission_ids:
            db.add(models.RolePermission(role_id=role_id, permission_id=pid))
    if body.menu_ids is not None:
        await db.execute(delete(models.RoleMenu).where(models.RoleMenu.role_id == role_id))
        for mid in body.menu_ids:
            db.add(models.RoleMenu(role_id=role_id, menu_id=mid))
    await db.commit()
    await db.refresh(role)
    return role


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    role = await db.get(models.Role, role_id)
    if not role:
        raise HTTPException(404, "Role not found")
    if role.is_system:
        raise HTTPException(400, "系统内置角色不可删除")
    await db.delete(role)
    await db.commit()


# ---- 权限 ----
@router.get("/permissions", response_model=list[schemas.PermissionOut])
async def list_permissions(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:permission:read")),
):
    result = await db.execute(select(models.Permission).order_by(models.Permission.code))
    return result.scalars().all()


# ---- 菜单 ----
@router.get("/menus", response_model=list[schemas.MenuOut])
async def list_menus(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:menu:read")),
):
    result = await db.execute(
        select(models.Menu).where(models.Menu.status == "active").order_by(models.Menu.sort, models.Menu.id)
    )
    menus = result.scalars().all()
    return _build_tree(menus)


def _menu_node(menu: models.Menu) -> dict:
    return {
        "id": menu.id,
        "key": menu.key,
        "parent_id": menu.parent_id,
        "title": menu.title,
        "icon": menu.icon,
        "path": menu.path,
        "component": menu.component,
        "sort": menu.sort,
        "status": menu.status,
        "children": [],
    }


def _build_tree(menus: list[models.Menu]) -> list[dict]:
    """扁平菜单 → 树"""
    by_id = {m.id: _menu_node(m) for m in menus}
    roots: list[dict] = []
    for m in menus:
        node = by_id[m.id]
        if m.parent_id and m.parent_id in by_id:
            by_id[m.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


# ===== 菜单 CRUD（之前只有 list） =====
@router.post("/menus", status_code=201)
async def create_menu(
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:menu:write")),
):
    """创建菜单"""
    parent_id = body.get("parent_id")
    if parent_id:
        parent = await db.get(models.Menu, parent_id)
        if not parent:
            raise HTTPException(400, f"父菜单不存在: {parent_id}")
    menu = models.Menu(
        key=body["key"],
        parent_id=parent_id,
        title=body["title"],
        icon=body.get("icon"),
        path=body.get("path"),
        component=body.get("component"),
        sort=body.get("sort", 0),
        status=body.get("status", "active"),
    )
    db.add(menu)
    await db.commit()
    await db.refresh(menu)
    return {"id": menu.id, "key": menu.key, "title": menu.title}


@router.patch("/menus/{menu_id}")
async def update_menu(
    menu_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:menu:write")),
):
    """更新菜单"""
    menu = await db.get(models.Menu, menu_id)
    if not menu:
        raise HTTPException(404, "Menu not found")
    for f in ("title", "icon", "path", "component", "sort", "status", "parent_id"):
        if f in body:
            setattr(menu, f, body[f])
    await db.commit()
    return {"id": menu.id, "title": menu.title}


@router.delete("/menus/{menu_id}", status_code=204)
async def delete_menu(
    menu_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:menu:write")),
):
    """删除菜单（级联）"""
    menu = await db.get(models.Menu, menu_id)
    if not menu:
        raise HTTPException(404, "Menu not found")
    await db.delete(menu)  # FK ondelete=CASCADE 自动级联
    await db.commit()


@router.post("/menus/reorder")
async def reorder_menus(
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:menu:write")),
):
    """批量重排（接收 [{"id":1,"sort":0,"parent_id":null}, ...]）"""
    items = body.get("items", [])
    for item in items:
        menu = await db.get(models.Menu, item["id"])
        if not menu:
            continue
        if "sort" in item:
            menu.sort = item["sort"]
        if "parent_id" in item:
            menu.parent_id = item["parent_id"]
    await db.commit()
    return {"ok": True, "count": len(items)}
