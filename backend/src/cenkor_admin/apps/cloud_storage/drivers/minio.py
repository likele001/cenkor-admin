"""内置 MinIO / S3 驱动（迁移源）"""
from ._s3_base import S3CompatDriver


class MinIODriver(S3CompatDriver):
    name = "minio"
    # MinIO 在本机或IP/非通配域名下，必须使用 path-style，
    # 否则 boto3 会把 bucket 拼成子域（scanwork1.localhost:9002）导致连不上。
    _addressing_style = "path"

    def configure(self, creds: dict) -> None:
        super().configure(creds)
        self._addressing_style = "path"

    async def ensure_bucket(self, bucket: str) -> None:
        """MinIO 不支持 AWS LocationConstraint，直接 create_bucket。"""
        async with self.client() as c:
            try:
                await c.head_bucket(Bucket=bucket)
            except Exception:
                await c.create_bucket(Bucket=bucket)


driver = MinIODriver()
