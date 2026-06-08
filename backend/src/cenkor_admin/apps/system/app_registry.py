"""应用中心：扫描 manifest + 安装状态"""
from __future__ import annotations

import importlib
import pkgutil
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.base import AppManifest
from cenkor_admin.apps.system.models import InstalledApp


def scan_app_manifests() -> dict[str, AppManifest]:
    """扫描 apps 包下各 App 的 manifest。"""
    manifests: dict[str, AppManifest] = {}
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
    return manifests


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
    await db.commit()
    await db.refresh(row)
    return row


async def uninstall_app(db: AsyncSession, key: str) -> None:
    result = await db.execute(select(InstalledApp).where(InstalledApp.key == key))
    row = result.scalar_one_or_none()
    if not row:
        raise ValueError(f"App 未安装: {key}")
    row.status = "uninstalled"
    row.uninstalled_at = datetime.now(timezone.utc)
    await db.commit()
