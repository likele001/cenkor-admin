"""应用中心：扫描 manifest + 安装状态"""
from __future__ import annotations

import importlib
import importlib.util
import pkgutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.base import AppManifest
from cenkor_admin.apps.system.models import InstalledApp
from cenkor_admin.core.hooks import registry, register_app_hooks


def scan_app_manifests() -> dict[str, AppManifest]:
    """扫描所有 App 目录下的 manifest，包括内置和商店安装的。"""
    manifests: dict[str, AppManifest] = {}

    # 1. 扫描内置 App (cenkor_admin.apps.*)
    import cenkor_admin.apps as apps_pkg
    for mod in pkgutil.iter_modules(apps_pkg.__path__):
        if mod.name.startswith("_"):
            continue
        try:
            m = importlib.import_module(f"cenkor_admin.apps.{mod.name}.manifest")
            manifest: AppManifest = getattr(m, "MANIFEST", None)
            if manifest:
                manifests[manifest.key] = manifest
        except (ImportError, AttributeError):
            continue

    # 2. 扫描外部 App 目录 (src/apps/*)  — 商店安装的 app 可能在此
    _scan_external_apps(manifests)

    return manifests


def _scan_external_apps(manifests: dict[str, AppManifest]) -> None:
    """扫描 backend/src/apps/ 下的外部 App manifest"""
    import sys
    external_apps_dir = Path(__file__).resolve().parent.parent.parent.parent / "apps"
    if not external_apps_dir.exists():
        return
    if str(external_apps_dir.parent) not in sys.path:
        sys.path.insert(0, str(external_apps_dir.parent))
    for item in external_apps_dir.iterdir():
        if item.name.startswith("_") or not item.is_dir():
            continue
        manifest_path = item / "manifest.py"
        if not manifest_path.exists():
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                f"external_apps.{item.name}.manifest", manifest_path
            )
            if not spec or not spec.loader:
                continue
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            manifest: AppManifest = getattr(m, "MANIFEST", None)
            if manifest:
                manifests[manifest.key] = manifest
        except Exception:
            continue


def _detect_app_has_frontend(key: str) -> bool:
    """检测 App 是否包含可供 admin-web 动态加载的前端资源。"""
    static_app_dir = Path(__file__).resolve().parent.parent.parent / "static" / "apps" / key
    return (static_app_dir / "plugin.js").exists()


async def _get_counts(db: AsyncSession, manifest) -> dict[str, int]:
    """统计 app 注册的内容/字段/分类数量"""
    from cenkor_admin.apps.cms import models as cms_models

    counts = {"content_types": 0, "field_definitions": 0, "categories": 0, "tags": 0, "entries": 0}

    ct_keys = [ct["key"] for ct in manifest.content_types]
    if not ct_keys:
        return counts

    # content_types
    cts = (await db.execute(
        select(cms_models.ContentType)
        .where(cms_models.ContentType.key.in_(ct_keys))
    )).scalars().all()
    counts["content_types"] = len(cts)
    ct_ids = [ct.id for ct in cts]

    if ct_ids:
        # field_definitions
        fds = (await db.execute(
            select(cms_models.FieldDefinition.id)
            .where(cms_models.FieldDefinition.content_type_id.in_(ct_ids))
        )).scalars().all()
        counts["field_definitions"] = len(fds)

        # categories
        cats = (await db.execute(
            select(cms_models.Category.id)
            .where(cms_models.Category.content_type_id.in_(ct_ids))
        )).scalars().all()
        counts["categories"] = len(cats)

        # tags
        tags = (await db.execute(
            select(cms_models.Tag.id)
            .where(cms_models.Tag.content_type_id.in_(ct_ids))
        )).scalars().all()
        counts["tags"] = len(tags)

        # entries
        entries = (await db.execute(
            select(cms_models.Entry.id)
            .where(cms_models.Entry.content_type_id.in_(ct_ids))
        )).scalars().all()
        counts["entries"] = len(entries)

    return counts


async def list_apps_with_status(db: AsyncSession) -> list[dict[str, Any]]:
    """对比代码 manifest 与 DB 安装状态。"""
    code_manifests = scan_app_manifests()
    result = await db.execute(select(InstalledApp))
    installed = {a.key: a for a in result.scalars().all()}

    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    for key, manifest in code_manifests.items():
        seen.add(key)
        row = installed.get(key)
        if not row or row.status != "installed":
            status = "not_installed"
        elif row.version != manifest.version:
            status = "needs_upgrade"
        else:
            status = "installed"

        counts = await _get_counts(db, manifest) if status in ("installed", "needs_upgrade") else {}

        items.append({
            "key": key,
            "name": manifest.name,
            "version": manifest.version,
            "code_version": manifest.version,
            "db_version": row.version if row else None,
            "status": status,
            "description": manifest.description,
            "icon": manifest.icon,
            "permissions_required": manifest.permissions_required,
            "content_types": manifest.content_types,
            "field_groups": manifest.field_groups,
            "field_definitions": manifest.field_definitions,
            "categories_seed": manifest.categories_seed,
            "public_routes_prefix": manifest.public_routes_prefix,
            "permissions_grants": row.permissions_grants if row else {},
            "has_frontend": row.has_frontend if row else False,
            "registered_counts": counts,
        })

    for key, row in installed.items():
        if key not in seen and row.status == "installed":
            items.append({
                "key": key,
                "name": row.name,
                "version": row.version,
                "code_version": None,
                "db_version": row.version,
                "status": "missing",
                "description": "代码中缺失",
                "icon": "⚠️",
                "permissions_required": [],
                "content_types": [],
                "field_groups": [],
                "field_definitions": [],
                "categories_seed": [],
                "public_routes_prefix": "",
                "permissions_grants": row.permissions_grants or {},
                "has_frontend": row.has_frontend or False,
                "registered_counts": {},
            })

    return items


async def install_app(db: AsyncSession, key: str) -> InstalledApp:
    manifests = scan_app_manifests()
    if key not in manifests:
        raise ValueError(f"App 不存在: {key}")
    manifest = manifests[key]
    result = await db.execute(select(InstalledApp).where(InstalledApp.key == key))
    row = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if row:
        row.name = manifest.name
        row.version = manifest.version
        row.status = "installed"
        row.installed_at = now
        row.uninstalled_at = None
    else:
        row = InstalledApp(
            key=key,
            name=manifest.name,
            version=manifest.version,
            status="installed",
            installed_at=now,
        )
        db.add(row)
    # 标记是否包含前端资源
    row.has_frontend = _detect_app_has_frontend(key)
    await db.flush()

    # 自动注册权限
    if manifest.permissions_required:
        from cenkor_admin.apps.rbac import models as rbac_models
        for perm_code in manifest.permissions_required:
            existing = await db.execute(
                select(rbac_models.Permission).where(rbac_models.Permission.code == perm_code)
            )
            if not existing.scalar_one_or_none():
                db.add(rbac_models.Permission(code=perm_code, type="api", name=perm_code))
        await db.flush()

    # 自动注册菜单
    if manifest.menus:
        from cenkor_admin.apps.rbac import models as rbac_models
        # 找到超级管理员角色
        sa_role = (await db.execute(
            select(rbac_models.Role).where(rbac_models.Role.code == "super_admin")
        )).scalar_one_or_none()

        for menu_def in manifest.menus:
            await _register_menu_tree(db, menu_def, parent=None, role_id=sa_role.id if sa_role else None)
        await db.flush()

    # 自动注册 manifest 中声明的 content_types / field_groups / field_definitions
    if manifest.content_types or manifest.field_groups or manifest.field_definitions or manifest.categories_seed:
        try:
            from cenkor_admin.apps.cms.field_registry import register_app
            await register_app(db, manifest)
        except Exception as e:
            await db.rollback()
            raise RuntimeError(f"自动注册 App 数据失败: {e}")

    await db.commit()
    await db.refresh(row)

    # 注册 App 声明的钩子处理器（插件框架 M1·P0）
    try:
        registered = register_app_hooks(key, list(manifest.hooks or []))
        if registered:
            log.info("app.hooks_registered", key=key, modules=registered)
    except Exception as e:
        log.warning("app.hooks_register_failed", key=key, error=str(e))

    return row


async def _register_menu_tree(
    db: AsyncSession, menu_def: dict, parent=None, role_id: int | None = None, sort_offset: int = 0
) -> None:
    """递归注册菜单树"""
    from cenkor_admin.apps.rbac import models as rbac_models
    from sqlalchemy import select as sa_select

    key = menu_def.get("key", "")
    # 检查是否已存在
    existing = await db.execute(
        sa_select(rbac_models.Menu).where(rbac_models.Menu.key == key)
    )
    existing_menu = existing.scalar_one_or_none()

    if not existing_menu:
        menu = rbac_models.Menu(
            key=key,
            title=menu_def.get("title", key),
            icon=menu_def.get("icon"),
            path=menu_def.get("path"),
            parent_id=parent.id if parent else None,
            sort=menu_def.get("sort", 50) + sort_offset,
        )
        db.add(menu)
        await db.flush()
    else:
        menu = existing_menu

    # 关联超级管理员角色
    if role_id:
        existing_rm = await db.execute(
            sa_select(rbac_models.RoleMenu).where(
                rbac_models.RoleMenu.role_id == role_id,
                rbac_models.RoleMenu.menu_id == menu.id,
            )
        )
        if not existing_rm.scalar_one_or_none():
            db.add(rbac_models.RoleMenu(role_id=role_id, menu_id=menu.id))

    # 递归处理子菜单
    for i, child_def in enumerate(menu_def.get("children", [])):
        await _register_menu_tree(db, child_def, parent=menu, role_id=role_id, sort_offset=i)


async def uninstall_app(db: AsyncSession, key: str) -> None:
    manifests = scan_app_manifests()
    manifest = manifests.get(key)
    result = await db.execute(select(InstalledApp).where(InstalledApp.key == key))
    row = result.scalar_one_or_none()
    if not row:
        raise ValueError(f"App 未安装: {key}")

    # 清理 app 注册的钩子处理器（插件框架 M1·P0）
    try:
        registry.clear_app(key)
    except Exception:
        pass

    # 清理 app 注册的内容数据
    if manifest:
        try:
            from cenkor_admin.apps.cms.field_registry import get_registry
            await get_registry().uninstall_app_data(db, manifest)
        except Exception:
            pass  # 即使清理失败也继续卸载

    # 清理 app 注册的菜单（递归删除子菜单 + 角色关联）
    await _uninstall_app_menus(db, key)

    # 清理 app 注册的权限点 + 角色授权
    await _uninstall_app_permissions(db, manifest)

    row.status = "uninstalled"
    row.uninstalled_at = datetime.now(timezone.utc)
    await db.commit()


async def update_permissions_grants(
    db: AsyncSession, key: str, grants: dict[str, list[str]]
) -> InstalledApp:
    """更新 App 的权限委派配置"""
    row = (await db.execute(
        select(InstalledApp).where(InstalledApp.key == key)
    )).scalar_one_or_none()
    if not row:
        raise ValueError(f"App 未安装: {key}")
    row.permissions_grants = grants or {}
    await db.commit()
    await db.refresh(row)
    return row


async def _uninstall_app_menus(db: AsyncSession, key: str) -> None:
    """卸载 app 时清理其注册的菜单（含子菜单与角色关联）。

    识别规则：menu.key 以 '<key>:' 或 '<key>' 开头（即与该 app 关联）。
    顶级菜单（parent_id 为 None）也会被删除。
    """
    from cenkor_admin.apps.rbac import models as rbac_models
    from sqlalchemy import delete as sa_delete

    # 找出所有属于该 app 的菜单 key（manifest.menus 中的 key）
    # 因为 _register_menu_tree 直接用 menu_def['key']，没加 app key 前缀，
    # 所以这里按"path 或 key 指向 /<app_key>"的菜单来识别
    matching_menus = (await db.execute(
        select(rbac_models.Menu).where(
            (rbac_models.Menu.key == key) | (rbac_models.Menu.path == f"/{key}")
        )
    )).scalars().all()

    # 收集这些菜单的 id（包括它们的孩子一并清掉）
    to_delete_ids: set[int] = set()
    stack = [m.id for m in matching_menus]
    while stack:
        mid = stack.pop()
        if mid in to_delete_ids:
            continue
        to_delete_ids.add(mid)
        # 找直接子菜单
        children = (await db.execute(
            select(rbac_models.Menu.id).where(rbac_models.Menu.parent_id == mid)
        )).scalars().all()
        stack.extend(children)

    if not to_delete_ids:
        return

    # 先删角色-菜单关联
    await db.execute(
        sa_delete(rbac_models.RoleMenu).where(
            rbac_models.RoleMenu.menu_id.in_(to_delete_ids)
        )
    )
    # 再删菜单
    await db.execute(
        sa_delete(rbac_models.Menu).where(rbac_models.Menu.id.in_(to_delete_ids))
    )
    await db.flush()


async def _uninstall_app_permissions(db: AsyncSession, manifest) -> None:
    """卸载 app 时清理其声明的权限点（含角色授权）。"""
    if not manifest or not manifest.permissions_required:
        return
    from cenkor_admin.apps.rbac import models as rbac_models
    from sqlalchemy import delete as sa_delete

    perms = (await db.execute(
        select(rbac_models.Permission).where(
            rbac_models.Permission.code.in_(manifest.permissions_required)
        )
    )).scalars().all()
    perm_ids = {p.id for p in perms}
    if not perm_ids:
        return

    # 先删角色-权限关联
    await db.execute(
        sa_delete(rbac_models.RolePermission).where(
            rbac_models.RolePermission.permission_id.in_(perm_ids)
        )
    )
    # 再删权限
    await db.execute(
        sa_delete(rbac_models.Permission).where(
            rbac_models.Permission.id.in_(perm_ids)
        )
    )
    await db.flush()
