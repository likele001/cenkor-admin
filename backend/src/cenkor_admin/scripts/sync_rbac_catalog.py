"""按 App manifest 同步权限点与菜单到 RBAC 表（幂等，可反复执行）。

## 为什么需要这个脚本

`install_app()` 只在「安装 App」那一次把 manifest 里的 `permissions_required`
和 `menus` 写进 RBAC 表。已经上线的实例再改 manifest（新增页面、新增 AI 能力），
库里不会回填，于是出现三种「功能做了但摸不到」的症状：

1. 角色页的权限树只渲染库里存在的权限码 → 新权限根本勾不到，非超管一律进不去
2. 侧边栏由 `/auth/me` 的 menus 驱动 → 没有菜单行 = 没有入口
3. super_admin 在角色页显示的权限数与实际能力不符（靠 is_superuser 兜底掩盖了）

本脚本按 manifest 重放一次 RBAC 登记，只做「补」，不删不改已有数据：
- 不覆盖已存在权限的名称
- 不覆盖已存在菜单的 title / path / sort / parent（运营在菜单管理里调过的顺序要保留）

## 用法

    cd backend
    PYTHONPATH=src python -m cenkor_admin.scripts.sync_rbac_catalog --dry-run
    PYTHONPATH=src python -m cenkor_admin.scripts.sync_rbac_catalog

    --no-bind-super   不把全部权限绑给 super_admin（默认会绑，让角色页显示与真实能力一致）
    --only cms        只同步指定 App（可多次传）
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

import structlog
from sqlalchemy import select

from cenkor_admin.apps.rbac import models as rbac_models
from cenkor_admin.apps.system.app_registry import scan_app_manifests
from cenkor_admin.apps.system.models import InstalledApp
from cenkor_admin.core.db import AsyncSessionLocal

log = structlog.get_logger()

# 权限码 → 展示名。未列出的沿用权限码本身（与 install_app 的行为保持一致）。
# 角色页直接把 name 显示给运营看，所以这里给的必须是中文人话。
PERMISSION_LABELS: dict[str, str] = {
    "cms:content_types:read": "查看内容类型",
    "cms:content_types:write": "编辑内容类型",
    "cms:field_definitions:read": "查看字段定义",
    "cms:field_definitions:write": "编辑字段定义",
    "cms:categories:read": "查看分类",
    "cms:categories:write": "编辑分类",
    "cms:tags:read": "查看标签",
    "cms:tags:write": "编辑标签",
    "cms:entries:read": "查看通用内容",
    "cms:entries:write": "编辑通用内容",
    "cms:entry:review": "审核通用内容（发布/驳回）",
    "cms:ai:read": "查看 AI 能力配置",
    "cms:ai:manage": "管理 AI 服务商与密钥",
    "cms:product:read": "查看产品",
    "cms:product:write": "编辑产品",
    "cms:case:read": "查看案例",
    "cms:case:write": "编辑案例",
    "cms:news:read": "查看新闻",
    "cms:news:write": "编辑新闻",
    "cms:site:read": "查看站点配置",
    "cms:site:write": "编辑站点配置",
    "media:upload": "上传媒体",
}


async def _ensure_permission(
    db: Any, code: str, dry_run: bool, created: list[str]
) -> rbac_models.Permission | None:
    """补一个权限点，返回实体（dry_run 时可能返回 None）。"""
    row = (
        await db.execute(select(rbac_models.Permission).where(rbac_models.Permission.code == code))
    ).scalar_one_or_none()
    if row:
        return row
    created.append(code)
    if dry_run:
        return None
    obj = rbac_models.Permission(
        code=code, type="API", name=PERMISSION_LABELS.get(code, code)
    )
    db.add(obj)
    await db.flush()
    return obj


async def _ensure_menu_tree(
    db: Any,
    menu_def: dict[str, Any],
    parent: rbac_models.Menu | None,
    dry_run: bool,
    created: list[str],
    sort_offset: int = 0,
) -> rbac_models.Menu | None:
    """递归补菜单。已存在的菜单一律不动（保留运营调过的顺序与标题）。"""
    key = menu_def.get("key", "")
    if not key:
        return None

    row = (
        await db.execute(select(rbac_models.Menu).where(rbac_models.Menu.key == key))
    ).scalar_one_or_none()

    if row is None:
        created.append(key)
        if not dry_run:
            declared_sort = menu_def.get("sort")
            row = rbac_models.Menu(
                key=key,
                title=menu_def.get("title", key),
                icon=menu_def.get("icon"),
                path=menu_def.get("path"),
                parent_id=parent.id if parent else None,
                sort=declared_sort if declared_sort is not None else 50 + sort_offset,
            )
            db.add(row)
            await db.flush()

    for i, child in enumerate(menu_def.get("children", []) or []):
        await _ensure_menu_tree(
            db, child, row, dry_run, created, sort_offset=i
        )
    return row


async def sync(dry_run: bool, bind_super: bool, only: set[str] | None) -> dict[str, Any]:
    manifests = scan_app_manifests()
    stats: dict[str, Any] = {
        "apps": [],
        "permissions_created": [],
        "menus_created": [],
        "super_bound": 0,
        "dry_run": dry_run,
    }

    async with AsyncSessionLocal() as db:
        installed_keys = {
            row[0]
            for row in (await db.execute(select(InstalledApp.key))).all()
        }

        targets = [
            m for k, m in manifests.items()
            if k in installed_keys and (only is None or k in only)
        ]
        stats["apps"] = [m.key for m in targets]
        if not targets:
            log.warning("sync_rbac.no_target_app")

        for manifest in targets:
            for code in manifest.permissions_required or []:
                await _ensure_permission(db, code, dry_run, stats["permissions_created"])
            for menu_def in manifest.menus or []:
                await _ensure_menu_tree(
                    db, menu_def, None, dry_run, stats["menus_created"]
                )

        # super_admin 绑全部权限：角色页显示的授权清单要和「实际能做什么」一致，
        # 否则运营会以为超管缺权限而重复授权。
        if bind_super:
            sa_role = (
                await db.execute(
                    select(rbac_models.Role).where(rbac_models.Role.code == "super_admin")
                )
            ).scalar_one_or_none()
            if sa_role:
                all_perms = (await db.execute(select(rbac_models.Permission))).scalars().all()
                have = {
                    row[0]
                    for row in (
                        await db.execute(
                            select(rbac_models.RolePermission.permission_id).where(
                                rbac_models.RolePermission.role_id == sa_role.id
                            )
                        )
                    ).all()
                }
                for p in all_perms:
                    if p.id in have:
                        continue
                    stats["super_bound"] += 1
                    if not dry_run:
                        db.add(
                            rbac_models.RolePermission(
                                role_id=sa_role.id, permission_id=p.id
                            )
                        )

                # 超管也要能看到全部菜单（新菜单默认只挂超管，这里兜一次）
                all_menus = (await db.execute(select(rbac_models.Menu))).scalars().all()
                have_m = {
                    row[0]
                    for row in (
                        await db.execute(
                            select(rbac_models.RoleMenu.menu_id).where(
                                rbac_models.RoleMenu.role_id == sa_role.id
                            )
                        )
                    ).all()
                }
                for m in all_menus:
                    if m.id in have_m:
                        continue
                    if not dry_run:
                        db.add(rbac_models.RoleMenu(role_id=sa_role.id, menu_id=m.id))

        if dry_run:
            await db.rollback()
        else:
            await db.commit()

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="按 App manifest 同步 RBAC 权限点与菜单")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要创建的内容，不落库")
    parser.add_argument(
        "--no-bind-super", action="store_true", help="不把全部权限绑定给 super_admin"
    )
    parser.add_argument(
        "--only", action="append", default=None, metavar="APP_KEY",
        help="只同步指定 App（可多次传，如 --only cms）",
    )
    args = parser.parse_args()

    stats = asyncio.run(
        sync(
            dry_run=args.dry_run,
            bind_super=not args.no_bind_super,
            only=set(args.only) if args.only else None,
        )
    )

    tag = "[dry-run] " if stats["dry_run"] else ""
    print(f"{tag}apps: {', '.join(stats['apps']) or '(none)'}")
    print(f"{tag}权限新建 {len(stats['permissions_created'])} 个")
    for code in stats["permissions_created"]:
        print(f"    + {code}  ({PERMISSION_LABELS.get(code, code)})")
    print(f"{tag}菜单新建 {len(stats['menus_created'])} 个")
    for key in stats["menus_created"]:
        print(f"    + {key}")
    print(f"{tag}super_admin 补绑权限 {stats['super_bound']} 条")


if __name__ == "__main__":
    main()
