"""七牛云 Kodo — S3 协议（兼容 S3v4）"""
from ._s3_base import S3CompatDriver


class QiniuKodoDriver(S3CompatDriver):
    name = "qiniu"
    # endpoint 例子：https://s3-<region>.qiniucs.com
    # 七牛 S3 兼容接口必须使用 path-style。
    _addressing_style = "path"

    def configure(self, creds: dict) -> None:
        super().configure(creds)
        self._addressing_style = "path"

    async def ensure_bucket(self, bucket: str) -> None:
        """七牛空间需在控制台预先创建，仅校验可访问性。"""
        async with self.client() as c:
            await c.head_bucket(Bucket=bucket)


driver = QiniuKodoDriver()
