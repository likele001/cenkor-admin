"""S3 协议通用基类（腾讯 COS / 阿里 OSS / 七牛 Kodo 共享）"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import aiobotocore.session
from aiobotocore.config import AioConfig


class S3CompatDriver:
    name = "s3compat"
    _endpoint: str | None = None
    _access_key: str | None = None
    _secret_key: str | None = None
    _region: str = "auto"
    _cdn_domain: str | None = None
    _addressing_style: str = "virtual"  # virtual | path
    _session = aiobotocore.session.AioSession()

    def configure(self, creds: dict) -> None:
        self._access_key = creds.get("access_key", "")
        self._secret_key = creds.get("secret_key", "")
        self._endpoint = creds.get("endpoint")
        self._region = creds.get("region", "auto")
        self._cdn_domain = creds.get("cdn_domain")
        self._addressing_style = creds.get("addressing_style", "virtual")

    def public_endpoint(self) -> str | None:
        return self._cdn_domain or self._endpoint

    @asynccontextmanager
    async def _client(self) -> AsyncIterator:
        async with self._session.create_client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
            config=AioConfig(signature_version="s3v4", s3={"addressing_style": self._addressing_style}),
        ) as c:
            yield c

    async def health_check(self) -> dict:
        if not self._access_key or not self._endpoint:
            return {"ok": False, "error": "未配置 access_key / endpoint"}
        try:
            async with self._client() as c:
                await c.list_buckets()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def ensure_bucket(self, bucket: str) -> None:
        async with self._client() as c:
            try:
                await c.head_bucket(Bucket=bucket)
                return
            except Exception:
                pass
            params = {"Bucket": bucket}
            if self._region and self._region not in ("auto",):
                params["CreateBucketConfiguration"] = {"LocationConstraint": self._region}
            await c.create_bucket(**params)

    async def upload_fileobj(self, bucket: str, key: str, fileobj, content_type: str) -> None:
        async with self._client() as c:
            await c.put_object(
                Bucket=bucket, Key=key, Body=fileobj.read(),
                ContentType=content_type,
            )

    async def delete(self, bucket: str, key: str) -> None:
        async with self._client() as c:
            await c.delete_object(Bucket=bucket, Key=key)

    async def presigned_put_url(self, bucket: str, key: str, expires: int = 600) -> str:
        async with self._client() as c:
            return await c.generate_presigned_url(
                "put_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires,
            )

    async def presigned_get_url(self, bucket: str, key: str, expires: int = 3600) -> str:
        async with self._client() as c:
            return await c.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires,
            )

    async def list_objects(self, bucket: str, prefix: str = "", max_keys: int = 1000) -> list[dict]:
        async with self._client() as c:
            paginator = c.get_paginator("list_objects_v2")
            items: list[dict] = []
            async for page in paginator.paginate(Bucket=bucket, Prefix=prefix, PaginationConfig={"MaxItems": max_keys}):
                for obj in page.get("Contents", []):
                    items.append({
                        "key": obj["Key"],
                        "size": obj.get("Size", 0),
                        "last_modified": obj["LastModified"].isoformat() if obj.get("LastModified") else None,
                        "etag": obj.get("ETag"),
                    })
                    if len(items) >= max_keys:
                        return items
            return items

    async def copy_object(self, src_bucket: str, src_key: str, dst_bucket: str, dst_key: str) -> None:
        async with self._client() as c:
            await c.copy_object(
                Bucket=dst_bucket, Key=dst_key,
                CopySource={"Bucket": src_bucket, "Key": src_key},
            )

    async def head_object(self, bucket: str, key: str) -> dict | None:
        try:
            async with self._client() as c:
                r = await c.head_object(Bucket=bucket, Key=key)
                return {
                    "size": r.get("ContentLength", 0),
                    "content_type": r.get("ContentType"),
                    "etag": r.get("ETag"),
                }
        except Exception:
            return None
