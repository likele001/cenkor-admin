"""S3 / MinIO 客户端（异步）"""
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


class S3Client:
    """异步 S3 客户端（兼容 AWS S3 / MinIO）"""

    def __init__(self) -> None:
        self._session: aiobotocore.session.AioSession = get_session()
        self._endpoint = settings.S3_ENDPOINT
        self._access_key = settings.S3_ACCESS_KEY
        self._secret_key = settings.S3_SECRET_KEY
        self._region = settings.S3_REGION

    @asynccontextmanager
    async def client(self) -> AsyncIterator:
        async with self._session.create_client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
            config=AioConfig(signature_version="s3v4"),
        ) as client:
            yield client

    async def ensure_bucket(self, bucket: str) -> None:
        """确保 bucket 存在（不存在则创建）"""
        async with self.client() as c:
            try:
                await c.head_bucket(Bucket=bucket)
            except Exception:
                await c.create_bucket(Bucket=bucket)
                log.info("s3.bucket.created", bucket=bucket)

    async def presigned_put_url(
        self, bucket: str, key: str, expires: int = 600
    ) -> str:
        """生成预签名上传 URL（前端直传）"""
        async with self.client() as c:
            return await c.generate_presigned_url(
                "put_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires,
            )

    async def presigned_get_url(
        self, bucket: str, key: str, expires: int = 3600
    ) -> str:
        """生成预签名下载 URL"""
        async with self.client() as c:
            return await c.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires,
            )

    async def upload_fileobj(
        self, bucket: str, key: str, fileobj, content_type: str
    ) -> None:
        """服务端上传（小文件）"""
        async with self.client() as c:
            await c.put_object(
                Bucket=bucket, Key=key, Body=fileobj.read(),
                ContentType=content_type,
            )

    async def delete(self, bucket: str, key: str) -> None:
        async with self.client() as c:
            await c.delete_object(Bucket=bucket, Key=key)


s3 = S3Client()
