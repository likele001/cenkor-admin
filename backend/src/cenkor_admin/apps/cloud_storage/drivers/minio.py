"""内置 MinIO / S3 驱动（迁移源）"""
from ._s3_base import S3CompatDriver


class MinIODriver(S3CompatDriver):
    name = "minio"
    # addressing_style=path 因为 MinIO endpoint 不带 bucket 子域


driver = MinIODriver()
