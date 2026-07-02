"""又拍云 — REST API 协议"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import quote

import aiohttp


class UpyunDriver:
    name = "upyun"

    def __init__(self) -> None:
        self._operator: str | None = None
        self._password: str | None = None
        self._bucket: str | None = None
        self._endpoint: str = "https://v0.api.upyun.com"
        self._cdn_domain: str | None = None

    def configure(self, creds: dict) -> None:
        self._operator = creds.get("access_key")  # 又拍把 operator 当用户名
        self._password = creds.get("secret_key")
        self._bucket = creds.get("bucket")
        self._endpoint = creds.get("endpoint", "https://v0.api.upyun.com")
        self._cdn_domain = creds.get("cdn_domain")

    def public_endpoint(self) -> str | None:
        return self._cdn_domain or self._endpoint

    def _sign(self, method: str, uri: str, length: int) -> dict:
        """又拍 REST 签名：Basic base64(operator:password)"""
        if not self._operator or not self._password:
            raise RuntimeError("未配置 operator / password")
        user_pass = f"{self._operator}:{self._password}".encode()
        token = base64.b64encode(user_pass).decode()
        return {
            "Authorization": f"Basic {token}",
            "Content-Length": str(length),
        }

    @property
    def _base(self) -> str:
        return f"{self._endpoint}/{$self._bucket}" if False else f"{self._endpoint}/{self._bucket}"

    async def health_check(self) -> dict:
        if not self._operator or not self._password or not self._bucket:
            return {"ok": False, "error": "未配置 operator / password / bucket"}
        try:
            uri = f"/{self._bucket}/"
            headers = self._sign("GET", uri, 0)
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{self._endpoint}{uri}", headers=headers) as r:
                    if r.status == 200:
                        return {"ok": True}
                    return {"ok": False, "error": f"HTTP {r.status}: {await r.text()}"[:200]}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def ensure_bucket(self, bucket: str) -> None:
        # 又拍 bucket 创建需控制台操作
        return

    async def upload_fileobj(self, bucket: str, key: str, fileobj, content_type: str) -> None:
        data = fileobj.read()
        # 又拍：PUT /<bucket>/<key>  Content-MD5 必填
        md5 = base64.b64encode(hashlib.md5(data).digest()).decode()
        uri = f"/{bucket}/{key}"
        sign = self._sign("PUT", uri, len(data))
        sign["Content-Type"] = content_type
        sign["Content-MD5"] = md5
        async with aiohttp.ClientSession() as s:
            async with s.put(f"{self._endpoint}{uri}", headers=sign, data=data) as r:
                if r.status not in (200, 201):
                    raise RuntimeError(f"又拍上传失败 HTTP {r.status}: {await r.text()}")

    async def delete(self, bucket: str, key: str) -> None:
        uri = f"/{bucket}/{key}"
        sign = self._sign("DELETE", uri, 0)
        async with aiohttp.ClientSession() as s:
            async with s.delete(f"{self._endpoint}{uri}", headers=sign) as r:
                if r.status not in (200, 204):
                    raise RuntimeError(f"又拍删除失败 HTTP {r.status}: {await r.text()}")

    async def presigned_put_url(self, bucket: str, key: str, expires: int = 600) -> str:
        # 又拍官方不推荐 presigned URL；前端走我们服务端中转
        raise NotImplementedError("又拍云请使用服务端中转上传")

    async def presigned_get_url(self, bucket: str, key: str, expires: int = 3600) -> str:
        # 拼接公开 URL（又拍通常用 CDN 域名）
        if self._cdn_domain:
            return f"https://{self._cdn_domain}/{key}"
        # 自签名 token URL（仅私有空间有效）
        token = self._make_download_token(bucket, key, expires)
        return f"{self._endpoint}/{bucket}/{key}?_upt={token}"

    def _make_download_token(self, bucket: str, key: str, expires: int) -> str:
        """又拍私有空间下载签名：HMAC-SHA1"""
        e = int(time.time()) + expires
        s = f"{key}&{e}&{hashlib.md5(self._password.encode()).hexdigest()}"
        h = hmac.new(self._password.encode(), s.encode(), hashlib.sha1).hexdigest()[:20]
        return f"{h}{e}"

    async def list_objects(self, bucket: str, prefix: str = "", max_keys: int = 1000) -> list[dict]:
        # 又拍：GET /<bucket>/?list
        items: list[dict] = []
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{self._endpoint}/{bucket}/",
                params={"list": "", "prefix": prefix} if prefix else {"list": ""},
                headers=self._sign("GET", f"/{bucket}/", 0),
            ) as r:
                if r.status != 200:
                    return []
                body = await r.json()
                for it in body.get("items", []):
                    items.append({
                        "key": it["name"],
                        "size": it.get("size", 0),
                        "last_modified": it.get("time"),
                        "type": it.get("type"),
                    })
                    if len(items) >= max_keys:
                        break
                return items

    async def copy_object(self, src_bucket: str, src_key: str, dst_bucket: str, dst_key: str) -> None:
        uri = f"/{dst_bucket}/{dst_key}"
        sign = self._sign("PUT", uri, 0)
        sign["X-Upyun-Source"] = f"/{src_bucket}/{src_key}"
        async with aiohttp.ClientSession() as s:
            async with s.put(f"{self._endpoint}{uri}", headers=sign) as r:
                if r.status not in (200, 201):
                    raise RuntimeError(f"又拍复制失败 HTTP {r.status}: {await r.text()}")

    async def head_object(self, bucket: str, key: str) -> dict | None:
        uri = f"/{bucket}/{key}"
        sign = self._sign("HEAD", uri, 0)
        async with aiohttp.ClientSession() as s:
            async with s.head(f"{self._endpoint}{uri}", headers=sign) as r:
                if r.status == 200:
                    return {
                        "size": int(r.headers.get("Content-Length", 0)),
                        "content_type": r.headers.get("Content-Type"),
                    }
                return None


driver = UpyunDriver()
