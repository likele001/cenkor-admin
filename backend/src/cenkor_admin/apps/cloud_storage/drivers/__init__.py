"""统一 StorageDriver 接口

- 腾讯 COS / 阿里 OSS / 七牛 Kodo 走 S3 协议
- 又拍云走 REST API（自己的 driver）
"""
from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class StorageDriver(Protocol):
    name: str

    def configure(self, creds: dict) -> None: ...
    def public_endpoint(self) -> str | None: ...
    async def health_check(self) -> dict: ...
    async def ensure_bucket(self, bucket: str) -> None: ...
    async def upload_fileobj(self, bucket: str, key: str, fileobj, content_type: str) -> None: ...
    async def delete(self, bucket: str, key: str) -> None: ...
    async def presigned_put_url(self, bucket: str, key: str, expires: int = 600) -> str: ...
    async def presigned_get_url(self, bucket: str, key: str, expires: int = 3600) -> str: ...
    async def list_objects(self, bucket: str, prefix: str = "", max_keys: int = 1000) -> list[dict]: ...
    async def copy_object(self, src_bucket: str, src_key: str, dst_bucket: str, dst_key: str) -> None: ...
    async def head_object(self, bucket: str, key: str) -> dict | None: ...


def get_driver(name: str) -> StorageDriver:
    if name == "tencent":
        from .tencent import driver
        return driver
    if name == "aliyun":
        from .aliyun import driver
        return driver
    if name == "qiniu":
        from .qiniu import driver
        return driver
    if name == "upyun":
        from .upyun import driver
        return driver
    if name == "minio":
        from .minio import driver
        return driver
    raise ValueError(f"未知 provider: {name}")


SUPPORTED_PROVIDERS = ["tencent", "aliyun", "qiniu", "upyun"]
