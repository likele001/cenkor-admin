"""统一存储客户端：根据 cloud_storage App 配置动态选择 driver。

启动时尝试加载 cloud_storage app 配置；若未配置则 fallback 到 .env 里的 MinIO/S3 配置，
保证旧的代码路径不破坏。
"""
from __future__ import annotations

import structlog
from contextlib import asynccontextmanager
from typing import AsyncIterator

import aiobotocore.session
from aiobotocore.config import AioConfig
from aiobotocore.session import get_session

from cenkor_admin.core.config import get_settings

settings = get_settings()
log = structlog.get_logger()


class _S3Fallback:
    """旧路径 fallback：直接走 .env 里的 MinIO/S3 配置"""
    name = "minio"
    _session = get_session()
    _endpoint = settings.S3_ENDPOINT
    _access_key = settings.S3_ACCESS_KEY
    _secret_key = settings.S3_SECRET_KEY
    _region = settings.S3_REGION or "auto"

    @asynccontextmanager
    async def client(self) -> AsyncIterator:
        async with self._session.create_client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
            config=AioConfig(signature_version="s3v4"),
        ) as c:
            yield c

    async def ensure_bucket(self, bucket: str) -> None:
        async with self.client() as c:
            try:
                await c.head_bucket(Bucket=bucket)
            except Exception:
                await c.create_bucket(Bucket=bucket)
                log.info("s3.bucket.created", bucket=bucket)

    async def presigned_put_url(self, bucket: str, key: str, expires: int = 600) -> str:
        async with self.client() as c:
            return await c.generate_presigned_url(
                "put_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires,
            )

    async def presigned_get_url(self, bucket: str, key: str, expires: int = 3600) -> str:
        async with self.client() as c:
            return await c.generate_presigned_url(
                "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires,
            )

    async def upload_fileobj(self, bucket: str, key: str, fileobj, content_type: str) -> None:
        async with self.client() as c:
            await c.put_object(
                Bucket=bucket, Key=key, Body=fileobj.read(), ContentType=content_type,
            )

    async def delete(self, bucket: str, key: str) -> None:
        async with self.client() as c:
            await c.delete_object(Bucket=bucket, Key=key)


class _Dispatch:
    """运行时按配置切换 driver。

    旧的 `s3.presigned_put_url(...)` 调用方式不变；底层在第一次调用时根据 cloud_storage app
    的 active_provider 加载 driver。如果没装 cloud_storage app，则用旧 .env 配置。
    """
    _driver = None

    async def _resolve(self):
        if self._driver is not None:
            return self._driver
        try:
            import json
            from cenkor_admin.core.db import AsyncSessionLocal
            from cenkor_admin.apps.cloud_storage import crypto as _crypto
            from cenkor_admin.apps.cloud_storage.drivers import get_driver
            from cenkor_admin.apps.cloud_storage.models import CloudStorageConfig
            from cenkor_admin.apps.system.models import InstalledApp
            from sqlalchemy import select
            async with AsyncSessionLocal() as db:
                installed = (await db.execute(
                    select(InstalledApp).where(
                        InstalledApp.key == "cloud_storage",
                        InstalledApp.status == "installed",
                    )
                )).scalar_one_or_none()
                if not installed:
                    raise RuntimeError("cloud_storage not installed")
                cfg = (await db.execute(
                    select(CloudStorageConfig).where(CloudStorageConfig.id == 1)
                )).scalar_one_or_none()
                if not cfg:
                    raise RuntimeError("cloud_storage config missing")
                token = getattr(cfg, f"creds_{cfg.active_provider}", None)
                if not token:
                    raise RuntimeError(f"creds for {cfg.active_provider} missing")
                plain = json.loads(_crypto.decrypt(token))
            d = get_driver(cfg.active_provider)
            d.configure(plain)
            self._driver = d
            return d
        except Exception as e:
            log.debug("storage.fallback_to_minio", error=str(e))
            self._driver = _S3Fallback()
            return self._driver

    async def ensure_bucket(self, bucket: str) -> None:
        d = await self._resolve()
        await d.ensure_bucket(bucket)

    async def presigned_put_url(self, bucket: str, key: str, expires: int = 600) -> str:
        d = await self._resolve()
        return await d.presigned_put_url(bucket, key, expires)

    async def presigned_get_url(self, bucket: str, key: str, expires: int = 3600) -> str:
        d = await self._resolve()
        return await d.presigned_get_url(bucket, key, expires)

    async def upload_fileobj(self, bucket: str, key: str, fileobj, content_type: str) -> None:
        d = await self._resolve()
        await d.upload_fileobj(bucket, key, fileobj, content_type)

    async def delete(self, bucket: str, key: str) -> None:
        d = await self._resolve()
        await d.delete(bucket, key)


s3 = _Dispatch()
