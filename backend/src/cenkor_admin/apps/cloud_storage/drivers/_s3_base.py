"""S3 协议通用基类（腾讯 COS / 阿里 OSS / 七牛 Kodo 共享）"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator
from urllib.parse import urlparse, urlunparse

import aiobotocore.session
from aiobotocore.config import AioConfig

# 七牛 Kodo 区域码 → S3 LocationConstraint
_QINIU_REGION_MAP = {
    "z0": "cn-east-1",
    "z1": "cn-north-1",
    "z2": "cn-south-1",
    "na0": "us-north-1",
    "as0": "ap-southeast-1",
}


def _resolve_location_constraint(region: str) -> str | None:
    """将各厂商 region 规范化为 S3 CreateBucket 可接受的 LocationConstraint。"""
    if not region or region in ("auto",):
        return None
    if region == "us-east-1":
        # AWS 标准区域：不能传 LocationConstraint
        return None
    if region in _QINIU_REGION_MAP:
        return _QINIU_REGION_MAP[region]
    return region


def _cdn_public_url(cdn_domain: str | None, bucket: str, key: str) -> str | None:
    """配置了 CDN 域名时，公网 URL 通常不含 bucket 前缀。"""
    if not cdn_domain:
        return None
    base = cdn_domain.rstrip("/")
    return f"{base}/{key.lstrip('/')}"


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

    def public_url(self, bucket: str, key: str) -> str:
        """生成对象公网访问 URL（优先 CDN 域名）。"""
        cdn_url = _cdn_public_url(self._cdn_domain, bucket, key)
        if cdn_url:
            return cdn_url
        ep = (self._endpoint or "").rstrip("/")
        if not ep:
            return f"/{bucket}/{key}"
        # path-style：endpoint/bucket/key
        return f"{ep}/{bucket}/{key.lstrip('/')}"

    def _apply_cdn_domain(self, url: str) -> str:
        """若配置了 CDN 域名，将预签名 URL 的 host 替换为 CDN 域名，保持签名参数不变。"""
        if not self._cdn_domain:
            return url
        cdn = urlparse(self._cdn_domain)
        if not cdn.netloc:
            return url
        parsed = urlparse(url)
        return urlunparse(parsed._replace(netloc=cdn.netloc))

    @asynccontextmanager
    async def client(self) -> AsyncIterator:
        """公开返回 boto3 S3 client（用于迁移等需要直接调用 S3 API 的场景）。"""
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
            async with self.client() as c:
                await c.list_buckets()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def ensure_bucket(self, bucket: str) -> None:
        async with self.client() as c:
            try:
                await c.head_bucket(Bucket=bucket)
                return
            except Exception:
                pass
            params: dict = {"Bucket": bucket}
            loc = _resolve_location_constraint(self._region)
            if loc:
                params["CreateBucketConfiguration"] = {"LocationConstraint": loc}
            await c.create_bucket(**params)

    async def upload_fileobj(self, bucket: str, key: str, fileobj, content_type: str) -> None:
        async with self.client() as c:
            await c.put_object(
                Bucket=bucket, Key=key, Body=fileobj.read(),
                ContentType=content_type,
            )

    async def delete(self, bucket: str, key: str) -> None:
        async with self.client() as c:
            await c.delete_object(Bucket=bucket, Key=key)

    async def presigned_put_url(self, bucket: str, key: str, expires: int = 600) -> str:
        async with self.client() as c:
            url = await c.generate_presigned_url(
                "put_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires,
            )
            return self._apply_cdn_domain(url)

    async def presigned_get_url(self, bucket: str, key: str, expires: int = 3600) -> str:
        async with self.client() as c:
            url = await c.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires,
            )
            return self._apply_cdn_domain(url)

    async def list_objects(self, bucket: str, prefix: str = "", max_keys: int = 1000) -> list[dict]:
        async with self.client() as c:
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
        async with self.client() as c:
            await c.copy_object(
                Bucket=dst_bucket, Key=dst_key,
                CopySource={"Bucket": src_bucket, "Key": src_key},
            )

    async def head_object(self, bucket: str, key: str) -> dict | None:
        try:
            async with self.client() as c:
                r = await c.head_object(Bucket=bucket, Key=key)
                return {
                    "size": r.get("ContentLength", 0),
                    "content_type": r.get("ContentType"),
                    "etag": r.get("ETag"),
                }
        except Exception:
            return None
