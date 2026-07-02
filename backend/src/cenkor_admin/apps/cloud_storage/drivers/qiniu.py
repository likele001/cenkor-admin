"""七牛云 Kodo — S3 协议（兼容 S3v4）"""
from ._s3_base import S3CompatDriver


class QiniuKodoDriver(S3CompatDriver):
    name = "qiniu"
    # endpoint 例子：https://s3-<region>.qiniucs.com
    # 七牛 S3 endpoint 使用 path-style


driver = QiniuKodoDriver()
