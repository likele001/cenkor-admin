"""应用商店 API"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.portal import models as portal_models
from cenkor_admin.apps.system import store_models
from cenkor_admin.apps.system.models import InstalledApp
from cenkor_admin.core.db import get_db
from cenkor_admin.core.security import decode_token
from cenkor_admin.apps.portal.auth import decode_portal_token, is_portal_token, PORTAL_JWT_ISSUER

log = structlog.get_logger()
router = APIRouter()
security = HTTPBearer(auto_error=False)

APPS_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent.parent / "uploads" / "apps"
# 前端静态资源目录（与 main.py 中的挂载点一致）
FRONTEND_STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "apps"


async def require_portal_or_admin(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """支持 portal token 或 admin token 的鉴权"""
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    security_bearer = HTTPBearer(auto_error=False)

    if not creds or not creds.credentials:
        raise HTTPException(401, "未提供认证信息")

    # 尝试 admin token
    try:
        payload = decode_token(creds.credentials)
        if payload.get("type") == "access" and not is_portal_token(payload):
            user_id = int(payload["sub"])
            user = await db.get(auth_models.User, user_id)
            if user and user.status == "active":
                return {"user_type": "admin", "user_id": user_id, "user": user}
    except Exception:
        pass

    # 尝试 portal token
    try:
        portal_payload = decode_portal_token(creds.credentials)
        if portal_payload.get("iss") == PORTAL_JWT_ISSUER and portal_payload.get("type") == "access":
            user_id = int(portal_payload["sub"])
            user = await db.get(portal_models.PortalUser, user_id)
            if user and user.status == "active" and not user.deleted_at:
                return {"user_type": "portal", "user_id": user_id, "user": user}
    except Exception:
        pass

    raise HTTPException(401, "Token 无效")


# ============================================================
# 开发者管理
# ============================================================

@router.get("/developers", response_model=dict[str, Any])
async def list_developers(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:read")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    stmt = select(store_models.Developer).order_by(store_models.Developer.id.desc())
    count = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return {
        "items": [
            {"id": d.id, "user_id": d.user_id, "display_name": d.display_name,
             "description": d.description, "website": d.website, "status": d.status,
             "created_at": d.created_at.isoformat() if d.created_at else None}
            for d in items
        ],
        "total": count,
    }


@router.post("/developers", status_code=201)
async def register_developer(
    body: dict,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_portal_or_admin),
):
    user_id = auth["user_id"]

    existing = (await db.execute(
        select(store_models.Developer).where(store_models.Developer.user_id == user_id)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "已注册为开发者")

    user = auth["user"]
    dev = store_models.Developer(
        user_id=user_id,
        display_name=body.get("display_name") or getattr(user, "nickname", None) or getattr(user, "username", ""),
        description=body.get("description"),
        website=body.get("website"),
    )
    db.add(dev)
    await db.commit()
    await db.refresh(dev)
    return {"id": dev.id, "display_name": dev.display_name}


# ============================================================
# 应用提交
# ============================================================

@router.get("/submissions", response_model=dict[str, Any])
async def list_submissions(
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_portal_or_admin),
    status: str | None = None,
    developer_id: int | None = None,
    only_active: bool = Query(False, description="仅返回每个 app_key 当前活跃的那条（installed/approved 各自最新一条）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """查看应用提交列表。管理员看全部，普通开发者只看自己的。"""
    # only_active：每个 app_key 在指定 status 下，只保留最新一条；
    #              且 platform_apps.status 必须为 installed（避免出现"已卸载却还在已安装列表"）。
    if only_active:
        from sqlalchemy import func as sa_func
        from cenkor_admin.apps.system.models import InstalledApp as _IA
        # 1) 找出当前 platform_apps 里 status=installed 的 app_key 集合
        active_keys_rows = (await db.execute(
            select(_IA.key).where(_IA.status == "installed")
        )).scalars().all()
        active_keys = set(active_keys_rows)

        # 2) 找出每个 app_key 的最新（按 id 最大）submission
        inner = (
            select(
                store_models.AppSubmission.app_key,
                sa_func.max(store_models.AppSubmission.id).label("max_id"),
            )
            .group_by(store_models.AppSubmission.app_key)
        )
        if status:
            inner = inner.where(store_models.AppSubmission.status == status)
        if developer_id is not None:
            inner = inner.where(store_models.AppSubmission.developer_id == developer_id)
        inner = inner.subquery()
        active_ids_subq = select(inner.c.max_id)
        all_ids = (await db.execute(active_ids_subq)).scalars().all()

        # 3) 过滤：只保留 app_key 仍处于 installed 状态的
        # 需要再次查询拿到 app_key 然后过滤
        rows_with_key = (await db.execute(
            select(store_models.AppSubmission.id, store_models.AppSubmission.app_key)
            .where(store_models.AppSubmission.id.in_(all_ids))
        )).all()
        only_active_ids = {r[0] for r in rows_with_key if r[1] in active_keys}
    else:
        only_active_ids = None
    stmt = (
        select(store_models.AppSubmission, store_models.Developer.display_name)
        .join(store_models.Developer, store_models.AppSubmission.developer_id == store_models.Developer.id)
        .order_by(store_models.AppSubmission.created_at.desc())
    )

    # 如果是 portal 用户，自动限制只看自己的提交
    if auth["user_type"] == "portal":
        dev = (await db.execute(
            select(store_models.Developer).where(
                store_models.Developer.user_id == auth["user_id"]
            )
        )).scalar_one_or_none()
        if not dev:
            developer_id = -1  # 无开发者身份，返回空
        else:
            developer_id = dev.id

    if status:
        stmt = stmt.where(store_models.AppSubmission.status == status)
    if developer_id is not None:
        stmt = stmt.where(store_models.AppSubmission.developer_id == developer_id)
    if only_active_ids is not None:
        if not only_active_ids:
            return {"items": [], "total": 0}
        stmt = stmt.where(store_models.AppSubmission.id.in_(only_active_ids))

    count = (await db.execute(select(func.count()).select_from(
        select(store_models.AppSubmission).where(stmt.whereclause).subquery()
    ))).scalar() or 0
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).all()

    return {
        "items": [
            {"id": s.id, "app_key": s.app_key, "name": s.name, "version": s.version,
             "description": s.description, "icon": s.icon, "category": s.category,
             "status": s.status, "review_note": s.review_note,
             "author": author,
             "download_count": s.download_count,
             "created_at": s.created_at.isoformat() if s.created_at else None,
             "reviewed_at": s.reviewed_at.isoformat() if s.reviewed_at else None}
            for s, author in rows
        ],
        "total": count,
    }


@router.post("/submissions", status_code=201)
async def submit_app(
    file: UploadFile = File(...),
    app_key: str = Form(...),
    name: str = Form(...),
    version: str = Form(...),
    description: str = Form(""),
    category: str = Form("system"),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_portal_or_admin),
):
    """开发者上传应用 ZIP 包"""
    user_id = auth["user_id"]

    # 检查开发者身份
    dev = (await db.execute(
        select(store_models.Developer).where(store_models.Developer.user_id == user_id)
    )).scalar_one_or_none()
    if not dev:
        raise HTTPException(403, "请先注册为开发者")

    # 校验文件
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(400, "请上传 ZIP 文件")

    # 校验 app_key 格式
    import re
    if not re.fullmatch(r"[a-z][a-z0-9\-_]{1,49}", app_key):
        raise HTTPException(400, "app_key 格式错误：小写字母开头，只含小写字母/数字/下划线/连字符，2-50位")

    # 保存文件并校验
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = UPLOAD_DIR / f"{app_key}-{version}.zip"
    content = await file.read()
    zip_path.write_bytes(content)

    file_hash = hashlib.sha256(content).hexdigest()

    # 解压校验 manifest
    manifest_data = None
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # 检查必要文件
            names = zf.namelist()
            if "manifest.py" not in names:
                raise HTTPException(400, "ZIP 包缺少 manifest.py")
            if "__init__.py" not in names:
                raise HTTPException(400, "ZIP 包缺少 __init__.py")

            # 读取并解析 manifest
            manifest_content = zf.read("manifest.py").decode("utf-8")
            manifest_data = _parse_manifest(manifest_content)
            if not manifest_data:
                raise HTTPException(400, "manifest.py 解析失败")

            # 校验 key 一致性
            if manifest_data.get("key") != app_key:
                raise HTTPException(400, f"manifest 中的 key ({manifest_data.get('key')}) 与提交的 app_key ({app_key}) 不一致")

            # 校验 router.py import 路径（常见错误：from apps.xxx）
            router_names = [n for n in names if n.endswith("router.py")]
            for rn in router_names:
                router_content = zf.read(rn).decode("utf-8", errors="ignore")
                if "from apps." in router_content or "import apps." in router_content:
                    raise HTTPException(
                        400,
                        "router.py 中使用了错误的 import 路径 `apps.*`，"
                        f"请改为 `from cenkor_admin.apps.{app_key} import models` 或 `from . import models`",
                    )
    except zipfile.BadZipFile:
        raise HTTPException(400, "ZIP 文件损坏")
    finally:
        if not manifest_data:
            zip_path.unlink(missing_ok=True)

    # 检查版本唯一性
    existing = (await db.execute(
        select(store_models.AppSubmission).where(
            store_models.AppSubmission.app_key == app_key,
            store_models.AppSubmission.version == version,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(409, f"版本 {version} 已存在")

    # 校验版本号：同一 app_key 的新版本必须严格大于已安装版本
    from cenkor_admin.apps.system.models import InstalledApp as _InstalledApp
    from packaging.version import Version as _Version, InvalidVersion as _InvalidVersion
    try:
        new_v = _Version(version)
    except _InvalidVersion:
        raise HTTPException(400, f"version 格式非法，应为 semver（如 1.0.0）：{version}")
    installed_row = (await db.execute(
        select(_InstalledApp).where(_InstalledApp.key == app_key)
    )).scalar_one_or_none()
    if installed_row and installed_row.status == "installed":
        try:
            current_v = _Version(installed_row.version)
            if new_v <= current_v:
                raise HTTPException(
                    400,
                    f"新版本 {version} 必须严格大于已安装版本 {installed_row.version}",
                )
        except _InvalidVersion:
            pass  # 已安装版本号解析失败时不阻塞新版本

    submission = store_models.AppSubmission(
        developer_id=dev.id,
        app_key=app_key,
        name=name or manifest_data.get("name", app_key),
        version=version,
        description=description or manifest_data.get("description", ""),
        icon=manifest_data.get("icon", "📦"),
        category=category,
        manifest_data=manifest_data,
        file_path=str(zip_path),
        file_hash=file_hash,
        status="pending",
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)

    # 通知所有有审核权限的管理员
    try:
        from cenkor_admin.apps.rbac.models import RolePermission, UserRole, Permission
        from cenkor_admin.apps.notification.models import Notification
        _pid = (await db.execute(
            select(Permission.id).where(Permission.code == "rbac:role:write")
        )).scalar_one_or_none()
        if _pid:
            _role_ids = (await db.execute(
                select(RolePermission.role_id).where(RolePermission.permission_id == _pid)
            )).scalars().all()
            _user_ids = (await db.execute(
                select(UserRole.user_id).where(UserRole.role_id.in_(_role_ids)).distinct()
            )).scalars().all()
            for _uid in _user_ids:
                db.add(Notification(
                    user_id=_uid, type="system",
                    title=f"新应用待审核：{name}",
                    body=f"开发者 {dev.display_name} 提交了「{name}」v{version}，请前往应用商店审核。",
                    link="/system/apps",
                    payload={"submission_id": submission.id, "app_key": app_key},
                ))
            await db.commit()
    except Exception as _ne:
        log.warning("store.submit_notification_fail", error=str(_ne))

    return {"id": submission.id, "app_key": submission.app_key, "status": submission.status}


@router.post("/submissions/{submission_id}/review")
async def review_submission(
    submission_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """管理员审核应用"""
    sub = await db.get(store_models.AppSubmission, submission_id)
    if not sub:
        raise HTTPException(404, "提交记录不存在")

    action = body.get("action")  # approve / reject
    note = body.get("note", "")

    if action == "approve":
        sub.status = "approved"
    elif action == "reject":
        sub.status = "rejected"
    else:
        raise HTTPException(400, "action 必须是 approve 或 reject")

    sub.review_note = note
    sub.reviewed_by = _.id
    sub.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"id": sub.id, "status": sub.status}


@router.delete("/submissions/{submission_id}", status_code=204)
async def withdraw_submission(
    submission_id: int,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_portal_or_admin),
):
    """开发者撤回自己的提交（pending / approved / rejected 状态可撤回；installed 不可撤回）。"""
    sub = await db.get(store_models.AppSubmission, submission_id)
    if not sub:
        raise HTTPException(404, "提交记录不存在")

    # 权限检查：管理员可撤回任何；portal 只能撤回自己的
    if auth["user_type"] == "portal":
        dev = (await db.execute(
            select(store_models.Developer).where(
                store_models.Developer.user_id == auth["user_id"]
            )
        )).scalar_one_or_none()
        if not dev or dev.id != sub.developer_id:
            raise HTTPException(403, "无权操作此提交")

    if sub.status == "installed":
        raise HTTPException(400, "已安装的应用无法撤回，请联系管理员卸载")

    # 清理 ZIP 文件
    if sub.file_path and os.path.exists(sub.file_path):
        try:
            os.remove(sub.file_path)
        except Exception:
            pass

    await db.delete(sub)
    await db.commit()
    return None


@router.post("/submissions/{submission_id}/install")
async def install_submission(
    submission_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """安装已审核通过的应用"""
    sub = await db.get(store_models.AppSubmission, submission_id)
    if not sub or sub.status != "approved":
        raise HTTPException(400, "应用未审核通过")

    # 检查 ZIP 文件存在
    if not sub.file_path or not os.path.exists(sub.file_path):
        raise HTTPException(400, "ZIP 文件不存在，请重新上传")

    # 解压到 apps 目录（兼容 ZIP 根目录或单层子目录打包）
    app_dir = APPS_DIR / sub.app_key
    try:
        with zipfile.ZipFile(sub.file_path, "r") as zf:
            _extract_app_zip(zf, app_dir)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"解压失败: {e}")

    # 处理前端资源：复制 frontend/dist/ → static/apps/{key}/
    has_frontend = False
    frontend_src = app_dir / "frontend" / "dist"
    if frontend_src.exists():
        target_dir = FRONTEND_STATIC_DIR / sub.app_key
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(frontend_src, target_dir)
        has_frontend = True
        log.info("store.frontend_copied", key=sub.app_key, target=str(target_dir))

    # 处理数据库迁移文件：拷贝 ZIP 中的 alembic/versions/*.py
    _copy_migration_files(app_dir, sub.app_key)

    # 立即执行数据库迁移（安装时建表，无需重启）
    try:
        from alembic.config import Config
        from alembic import command
        _alembic_cfg = Config(
            str(Path(__file__).resolve().parent.parent.parent.parent.parent / "alembic.ini")
        )
        command.upgrade(_alembic_cfg, "head")
        log.info("store.migration_upgrade_ok", app_key=sub.app_key)
    except Exception as e:
        log.warning("store.migration_upgrade_fail", app_key=sub.app_key, error=str(e))

    # 更新状态
    sub.status = "installed"

    # 自动安装（注册权限/菜单）
    warnings: list[str] = []
    try:
        from cenkor_admin.apps.system.app_registry import install_app
        await install_app(db, sub.app_key)
    except Exception as e:
        log.warning("store.install.auto_failed", app_key=sub.app_key, error=str(e))
        raise HTTPException(500, f"应用注册失败: {e}")

    # 动态注册 API 路由（无需重启后端）
    route_registered = False
    try:
        from cenkor_admin.api.v1 import register_app_router
        route_registered = register_app_router(sub.app_key)
        if not route_registered and (app_dir / "router.py").exists():
            warnings.append("API 路由注册失败，请检查 router.py 中的 import 路径")
    except Exception as e:
        log.warning("store.route_register_failed", app_key=sub.app_key, error=str(e))
        warnings.append(f"API 路由注册异常: {e}")

    # 更新 has_frontend 标记
    installed_row = (await db.execute(
        select(InstalledApp).where(InstalledApp.key == sub.app_key)
    )).scalar_one_or_none()
    if installed_row:
        installed_row.has_frontend = has_frontend

    await db.commit()
    return {
        "ok": True,
        "app_key": sub.app_key,
        "has_frontend": has_frontend,
        "route_registered": route_registered,
        "warnings": warnings,
    }


# ============================================================
# 工具函数
# ============================================================

# alembic 迁移文件目录
ALEMBIC_VERSIONS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "alembic" / "versions"


def _extract_app_zip(zf: zipfile.ZipFile, app_dir: Path) -> None:
    """解压 App ZIP，自动剥离单层根目录（如 my_todo/manifest.py）。"""
    names = [n for n in zf.namelist() if n and not n.endswith("/")]
    if not names:
        raise HTTPException(400, "ZIP 包为空")

    if "manifest.py" in names:
        prefix = ""
    else:
        manifest_paths = [n for n in names if n.endswith("manifest.py")]
        if not manifest_paths:
            raise HTTPException(400, "ZIP 包缺少 manifest.py")
        manifest_path = min(manifest_paths, key=len)
        prefix = manifest_path[: -len("manifest.py")]

    if app_dir.exists():
        shutil.rmtree(app_dir)
    app_dir.mkdir(parents=True)

    for name in names:
        if prefix and not name.startswith(prefix):
            continue
        rel = name[len(prefix):] if prefix else name
        if not rel:
            continue
        target = app_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(name) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)


def _migration_revision_exists(revision_id: str) -> bool:
    """检查 revision ID 是否已存在于平台迁移目录。"""
    import re
    pattern = re.compile(
        rf"""revision(?:\s*:\s*str)?\s*=\s*['\"]{re.escape(revision_id)}['\"]"""
    )
    for f in ALEMBIC_VERSIONS_DIR.glob("*.py"):
        try:
            if pattern.search(f.read_text(encoding="utf-8")):
                return True
        except OSError:
            continue
    return False


def _read_migration_revision(path: Path) -> str | None:
    import re
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"""revision(?:\s*:\s*str)?\s*=\s*['\"]([^'\"]+)['\"]""", content)
    return m.group(1) if m else None


def _copy_migration_files(app_dir: Path, app_key: str) -> None:
    """将 ZIP 中 alembic/versions/*.py 拷贝到平台的迁移目录（跳过已存在的 revision）。"""
    migration_src = app_dir / "alembic" / "versions"
    if not migration_src.exists():
        return
    for f in sorted(migration_src.iterdir()):
        if f.suffix != ".py" or f.name.startswith("_"):
            continue
        revision_id = _read_migration_revision(f)
        if revision_id and _migration_revision_exists(revision_id):
            log.info("store.migration_skipped", revision=revision_id, app_key=app_key)
            continue
        dst = ALEMBIC_VERSIONS_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{app_key}_{f.name}"
        shutil.copy2(f, dst)
        log.info("store.migration_copied", src=f.name, dst=dst.name)


def _parse_manifest(content: str) -> dict | None:
    """安全解析 manifest.py 内容"""
    try:
        # 提取 MANIFEST 关键字段（正则提取，不执行代码）
        import re
        result = {}

        # 提取 key
        m = re.search(r'key\s*=\s*["\']([^"\']+)["\']', content)
        if m: result["key"] = m.group(1)

        # 提取 name
        m = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
        if m: result["name"] = m.group(1)

        # 提取 version
        m = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
        if m: result["version"] = m.group(1)

        # 提取 author
        m = re.search(r'author\s*=\s*["\']([^"\']+)["\']', content)
        if m: result["author"] = m.group(1)

        # 提取 description
        m = re.search(r'description\s*=\s*["\']([^"\']+)["\']', content)
        if m: result["description"] = m.group(1)

        # 提取 icon
        m = re.search(r'icon\s*=\s*["\']([^"\']+)["\']', content)
        if m: result["icon"] = m.group(1)

        # 提取 category
        m = re.search(r'category\s*=\s*["\']([^"\']+)["\']', content)
        if m: result["category"] = m.group(1)

        # 提取 permissions_required 列表
        m = re.search(r'permissions_required\s*=\s*\[(.*?)\]', content, re.DOTALL)
        if m:
            perms = re.findall(r'["\']([^"\']+)["\']', m.group(1))
            result["permissions_required"] = perms

        # 提取 menus（简化提取）
        menus_match = re.search(r'menus\s*=\s*\[(.*?)\]\s*\)', content, re.DOTALL)
        if menus_match:
            result["menus_raw"] = menus_match.group(0)[:500]  # 保留原始内容

        return result if result.get("key") else None
    except Exception:
        return None
