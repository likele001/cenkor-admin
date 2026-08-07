"""云存储 App 路由：凭据 CRUD / 文件浏览 / 迁移"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from cenkor_admin.api.deps import get_current_user, require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.core.db import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from . import models, crypto
from .drivers import get_driver, SUPPORTED_PROVIDERS

router = APIRouter()


# ============================================================
# 凭据管理
# ============================================================

class CredsIn(BaseModel):
    access_key: str
    secret_key: str
    bucket: str
    region: str | None = None
    endpoint: str | None = None
    cdn_domain: str | None = None
    addressing_style: str = "virtual"
    prefix: str | None = None
    extra: dict[str, Any] | None = None


class ActivateIn(BaseModel):
    provider: str


class CredsOut(BaseModel):
    has_secret: bool
    access_key_masked: str | None = None
    secret_key_masked: str | None = None
    bucket: str | None = None
    region: str | None = None
    endpoint: str | None = None
    cdn_domain: str | None = None
    addressing_style: str | None = None
    prefix: str | None = None
    extra: dict[str, Any] | None = None


def _mask_payload(plain: dict) -> dict:
    out = {}
    if "access_key" in plain:
        out["access_key_masked"] = crypto.mask(plain["access_key"])
        out["has_secret"] = True
    if "secret_key" in plain:
        out["secret_key_masked"] = crypto.mask(plain["secret_key"])
    for k in ("bucket", "region", "endpoint", "cdn_domain", "addressing_style", "prefix", "extra"):
        if k in plain:
            out[k] = plain[k]
    return out


async def _get_config(db: AsyncSession) -> models.CloudStorageConfig:
    row = (await db.execute(select(models.CloudStorageConfig).where(models.CloudStorageConfig.id == 1))).scalar_one_or_none()
    if not row:
        row = models.CloudStorageConfig(id=1, active_provider="tencent")
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


def _creds_for(row: models.CloudStorageConfig, provider: str) -> dict | None:
    field = f"creds_{provider}"
    token = getattr(row, field, None)
    if not token:
        return None
    try:
        return json.loads(crypto.decrypt(token))
    except Exception:
        return None


@router.get("/config")
async def get_config(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("cloud_storage:read")),
):
    row = await _get_config(db)
    out: dict[str, Any] = {
        "active_provider": row.active_provider,
        "keep_local_backup": bool(row.keep_local_backup),
        "providers": {},
    }
    for p in SUPPORTED_PROVIDERS:
        plain = _creds_for(row, p)
        if plain:
            out["providers"][p] = _mask_payload(plain)
        else:
            out["providers"][p] = {"has_secret": False}
    return out


@router.put("/config/{provider}/creds")
async def save_creds(
    provider: str,
    body: CredsIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("cloud_storage:admin")),
):
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(400, f"未知 provider: {provider}")
    row = await _get_config(db)
    payload = body.model_dump(exclude_none=True)
    field = f"creds_{provider}"
    setattr(row, field, crypto.encrypt(json.dumps(payload, ensure_ascii=False)))
    row.updated_by = user.id
    await db.commit()
    return {"ok": True}


@router.delete("/config/{provider}/creds")
async def delete_creds(
    provider: str,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("cloud_storage:admin")),
):
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(400, f"未知 provider: {provider}")
    row = await _get_config(db)
    setattr(row, f"creds_{provider}", None)
    if row.active_provider == provider:
        row.active_provider = SUPPORTED_PROVIDERS[0]
    await db.commit()
    return {"ok": True}


@router.post("/config/activate")
async def activate(
    body: ActivateIn,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("cloud_storage:admin")),
):
    if body.provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(400, f"未知 provider: {body.provider}")
    row = await _get_config(db)
    if not _creds_for(row, body.provider):
        raise HTTPException(400, f"该 provider 尚未配置凭据")
    row.active_provider = body.provider
    await db.commit()
    return {"ok": True, "active_provider": body.provider}


class ConfigSettings(BaseModel):
    keep_local_backup: bool


@router.put("/config", response_model=dict)
async def save_settings(
    body: ConfigSettings,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("cloud_storage:admin")),
):
    """保存云存储全局设置（如「保留本地备份」开关）。"""
    row = await _get_config(db)
    row.keep_local_backup = body.keep_local_backup
    row.updated_by = user.id
    await db.commit()
    return {"ok": True, "keep_local_backup": row.keep_local_backup}


# ============================================================
# 健康检查 / 文件浏览
# ============================================================

@router.get("/health")
async def health(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("cloud_storage:read")),
):
    row = await _get_config(db)
    results = {}
    for p in SUPPORTED_PROVIDERS:
        plain = _creds_for(row, p)
        if not plain:
            results[p] = {"ok": False, "error": "未配置凭据"}
            continue
        try:
            d = get_driver(p)
            d.configure(plain)
            results[p] = await d.health_check()
        except Exception as e:
            results[p] = {"ok": False, "error": str(e)[:200]}
    return {"active_provider": row.active_provider, "results": results}


async def _active_driver(db: AsyncSession):
    row = await _get_config(db)
    plain = _creds_for(row, row.active_provider)
    if not plain:
        raise HTTPException(400, "请先在「云存储 → 凭据」配置当前激活 provider")
    d = get_driver(row.active_provider)
    d.configure(plain)
    return d, plain


@router.get("/files")
async def list_files(
    bucket: str = Query(...),
    prefix: str = Query(""),
    max_keys: int = Query(100, le=1000),
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("cloud_storage:read")),
):
    driver, _ = await _active_driver(db)
    items = await driver.list_objects(bucket=bucket, prefix=prefix, max_keys=max_keys)
    return {"items": items, "count": len(items)}


@router.delete("/files")
async def delete_file(
    bucket: str = Query(...),
    key: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("cloud_storage:write")),
):
    driver, _ = await _active_driver(db)
    await driver.delete(bucket=bucket, key=key)
    return {"ok": True}


class PresignIn(BaseModel):
    bucket: str
    key: str
    method: str = "put"  # put | get
    expires: int = 600


@router.post("/presign")
async def presign(
    body: PresignIn,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("cloud_storage:write")),
):
    driver, _ = await _active_driver(db)
    try:
        if body.method == "get":
            url = await driver.presigned_get_url(body.bucket, body.key, body.expires)
        else:
            url = await driver.presigned_put_url(body.bucket, body.key, body.expires)
    except NotImplementedError as e:
        raise HTTPException(501, str(e))
    return {"url": url}


# ============================================================
# 迁移：MinIO → 当前激活 provider
# ============================================================

@router.post("/migrate")
async def start_migration(
    bucket: str = Query(...),
    prefix: str = Query(""),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("cloud_storage:admin")),
):
    """同步启动迁移（异步任务，写表记录进度）"""
    row = await _get_config(db)
    plain = _creds_for(row, row.active_provider)
    if not plain:
        raise HTTPException(400, "请先配置目标 provider 凭据")
    driver = get_driver(row.active_provider)
    driver.configure(plain)
    src_driver = get_driver("minio")  # 固定走旧 S3/MinIO
    from cenkor_admin.core.config import get_settings
    s = get_settings()
    src_driver.configure({
        "access_key": s.S3_ACCESS_KEY,
        "secret_key": s.S3_SECRET_KEY,
        "endpoint": s.S3_ENDPOINT,
        "region": s.S3_REGION or "auto",
    })

    job = models.CloudStorageMigrationJob(
        source="minio", target=row.active_provider, status="running", started_at=datetime.now(timezone.utc)
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # 异步执行
    asyncio.get_event_loop().create_task(
        _run_migration(job.id, src_driver, driver, bucket, prefix)
    )
    return {"ok": True, "job_id": job.id}


import asyncio  # noqa: E402


async def _run_migration(job_id: int, src, dst, bucket: str, prefix: str) -> None:
    """在后台跑迁移，每 50 个对象更新一次进度"""
    from cenkor_admin.core.db import AsyncSessionLocal
    from cenkor_admin.core.config import get_settings
    s = get_settings()
    src_bucket = bucket or s.S3_BUCKET_PRIVATE

    try:
        items = await src.list_objects(src_bucket, prefix=prefix, max_keys=100000)
        async with AsyncSessionLocal() as db:
            job = await db.get(models.CloudStorageMigrationJob, job_id)
            if not job:
                return
            job.total = len(items)
            await db.commit()

        done = 0
        failed = 0
        for it in items:
            try:
                # 读源 → 写目标。注意：必须用 src（MinIO 源 driver）读对象，
                # 不能复用 core.storage.s3，因为 active_provider 已切到目标 provider，
                # 它会从目标 driver 读源 bucket，导致失败。
                async with src.client() as c:
                    r = await c.get_object(Bucket=src_bucket, Key=it["key"])
                    body = await r["Body"].read()
                from io import BytesIO
                await dst.upload_fileobj(
                    bucket=src_bucket, key=it["key"],
                    fileobj=BytesIO(body),
                    content_type="application/octet-stream",
                )
                done += 1
            except Exception as e:
                failed += 1
                # 记录但不中断
            if (done + failed) % 50 == 0:
                async with AsyncSessionLocal() as db:
                    job = await db.get(models.CloudStorageMigrationJob, job_id)
                    if job:
                        job.done = done
                        job.failed = failed
                        await db.commit()
        async with AsyncSessionLocal() as db:
            job = await db.get(models.CloudStorageMigrationJob, job_id)
            if job:
                job.done = done
                job.failed = failed
                job.status = "done" if failed == 0 else "partial"
                job.finished_at = datetime.now(timezone.utc)
                await db.commit()
    except Exception as e:
        async with AsyncSessionLocal() as db:
            job = await db.get(models.CloudStorageMigrationJob, job_id)
            if job:
                job.status = "failed"
                job.error = str(e)[:500]
                job.finished_at = datetime.now(timezone.utc)
                await db.commit()


@router.get("/migrate/{job_id}")
async def get_migration(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("cloud_storage:read")),
):
    job = await db.get(models.CloudStorageMigrationJob, job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    return {
        "id": job.id,
        "source": job.source, "target": job.target, "status": job.status,
        "total": job.total, "done": job.done, "failed": job.failed,
        "error": job.error, "started_at": job.started_at, "finished_at": job.finished_at,
    }
