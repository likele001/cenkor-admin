"""七牛云 Kodo —— 原生 HTTP API 实现。

放弃 S3 兼容网关（`s3-<region>.qiniucs.com`）：从海外节点访问该网关 TLS 握手需 3s+、
实测吞吐 ~40KB/s，2.7MB 对象上传 60s 超时；而原生表单上传同文件 1.8s。
故本 driver 的写入/删除/列举/下载全部走七牛原生 API，S3 client 仅保留给
`presigned_put_url`（七牛不支持 S3 预签名 PUT，只能退回 S3v4 签名）。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from urllib.parse import urlencode

import anyio

from ._s3_base import S3CompatDriver, _cdn_public_url

_UPLOAD_HOST = {
    "z0": "upload.qiniup.com",
    "z1": "upload-z1.qiniup.com",
    "z2": "upload-z2.qiniup.com",
    "na0": "upload-na0.qiniup.com",
    "as0": "upload-as0.qiniup.com",
}
_RS_HOST = "https://rs.qiniu.com"      # 元信息 / 删除
_RSF_HOST = "https://rsf.qiniu.com"    # 列举
_META_TIMEOUT = 30      # 元信息/删除/列举
_UPLOAD_TIMEOUT = 300   # 上传（跨境上行慢，给足时间）


def _urlsafe(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode()


def _entry_uri(bucket: str, key: str) -> str:
    return _urlsafe(f"{bucket}:{key}".encode())


class QiniuKodoDriver(S3CompatDriver):
    name = "qiniu"
    _ensured: set[str] = set()
    _bucket: str = ""

    def configure(self, creds: dict) -> None:
        super().configure(creds)
        self._addressing_style = "path"
        self._bucket = creds.get("bucket") or ""
        self._ensured = set()

    # ---------- 鉴权 ----------
    def _upload_token(self, bucket: str, key: str, expires: int = 3600) -> str:
        policy = {
            "scope": f"{bucket}:{key}",
            "deadline": int(time.time()) + expires,
            "insertOnly": 0,
        }
        enc = _urlsafe(json.dumps(policy, separators=(",", ":")).encode())
        sign = hmac.new(self._secret_key.encode(), enc.encode(), hashlib.sha1).digest()
        return f"{self._access_key}:{_urlsafe(sign)}:{enc}"

    def _mgmt_auth(self, path: str, body: str = "") -> str:
        """QBox 管理凭证。

        实测七牛要求 signingStr = path + "\\n" + body，body 为空时也必须保留换行，
        否则一律 401 BadToken。path 需包含 query 串。
        """
        data = f"{path}\n{body}"
        sign = hmac.new(self._secret_key.encode(), data.encode(), hashlib.sha1).digest()
        return f"QBox {self._access_key}:{_urlsafe(sign)}"

    # ---------- 同步 HTTP 原语（由 anyio 抛到线程池执行）----------
    @staticmethod
    def _request(url: str, body: bytes | None = None, headers: dict | None = None,
                 timeout: int = _META_TIMEOUT) -> bytes:
        req = urllib.request.Request(url, data=body, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read()[:300].decode(errors="replace")
            except Exception:
                pass
            raise RuntimeError(f"qiniu http {e.code} {url}: {detail}") from None

    def _put_form(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        host = _UPLOAD_HOST.get(self._region or "z2", "upload-z2.qiniup.com")
        boundary = f"----cenkor{int(time.time() * 1000)}"
        filename = key.rsplit("/", 1)[-1] or "blob"
        chunks: list[bytes] = []
        for name, value in (("token", self._upload_token(bucket, key)), ("key", key)):
            chunks.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
            )
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {content_type or 'application/octet-stream'}\r\n\r\n".encode()
        )
        chunks.append(data)
        chunks.append(f"\r\n--{boundary}--\r\n".encode())
        body = b"".join(chunks)
        # 跨境链路抖动明显（实测同一文件 8s~105s），失败重试 2 次
        last: Exception | None = None
        for attempt in range(3):
            try:
                self._request(
                    f"https://{host}/", body,
                    {"Content-Type": f"multipart/form-data; boundary={boundary}"},
                    timeout=_UPLOAD_TIMEOUT,
                )
                return
            except Exception as e:  # noqa: BLE001
                last = e
                if attempt < 2:
                    time.sleep(1 + attempt * 2)
        raise RuntimeError(f"qiniu upload failed after 3 attempts: {last}") from None

    def _rsf_list(self, bucket: str, prefix: str, limit: int) -> dict:
        path = f"/list?{urlencode({'bucket': bucket, 'prefix': prefix, 'limit': limit})}"
        raw = self._request(f"{_RSF_HOST}{path}", headers={"Authorization": self._mgmt_auth(path)})
        return json.loads(raw or b"{}")

    # ---------- 异步公开接口 ----------
    async def _run(self, fn: Callable, *args):
        return await anyio.to_thread.run_sync(lambda: fn(*args))

    async def ensure_bucket(self, bucket: str) -> None:
        """七牛空间需在控制台预建；这里只做一次可达性探针（结果缓存，避免每次上传多付 3s）。"""
        if bucket in self._ensured:
            return
        try:
            await self._run(self._rsf_list, bucket, "", 1)
        except Exception as e:
            raise RuntimeError(f"qiniu bucket {bucket} 不可访问: {e}") from None
        self._ensured.add(bucket)

    async def health_check(self) -> dict:
        if not self._access_key or not self._secret_key:
            return {"ok": False, "error": "未配置 access_key / secret_key"}
        if not self._bucket:
            return {"ok": False, "error": "未配置 bucket"}
        try:
            info = await self._run(self._rsf_list, self._bucket, "", 1)
            return {"ok": True, "bucket": self._bucket, "items": len(info.get("items", []))}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def upload_fileobj(self, bucket: str, key: str, fileobj, content_type: str) -> None:
        data = fileobj.read()
        await self.ensure_bucket(bucket)
        await self._run(self._put_form, bucket, key, data, content_type)

    async def delete(self, bucket: str, key: str) -> None:
        path = f"/delete/{_entry_uri(bucket, key)}"
        await self._run(self._request, f"{_RS_HOST}{path}", b"", {"Authorization": self._mgmt_auth(path)})

    async def stat(self, bucket: str, key: str) -> dict | None:
        path = f"/stat/{_entry_uri(bucket, key)}"
        try:
            raw = await self._run(self._request, f"{_RS_HOST}{path}", None, {"Authorization": self._mgmt_auth(path)})
        except Exception:
            return None
        return json.loads(raw or b"{}")

    async def download(self, bucket: str, key: str) -> bytes:
        url = _cdn_public_url(self._cdn_domain, bucket, key)
        if not url:
            url = self.public_url(bucket, key)
        return await self._run(self._request, url)

    async def list_objects(self, bucket: str, prefix: str = "", max_keys: int = 1000) -> list[dict]:
        info = await self._run(self._rsf_list, bucket, prefix, max_keys)
        out: list[dict] = []
        for it in info.get("items", [])[:max_keys]:
            out.append({
                "key": it.get("key"),
                "size": it.get("fsize", 0),
                "last_modified": str(it.get("putTime", "")),
                "etag": it.get("hash"),
            })
        return out

    async def presigned_put_url(self, bucket: str, key: str, expires: int = 600) -> str:
        """七牛无 S3 预签名 PUT，退化到 S3 网关签名（仅前端直传场景使用，速率受限）。"""
        return await super().presigned_put_url(bucket, key, expires)


driver = QiniuKodoDriver()
