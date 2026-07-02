"""腾讯云 COS — S3 协议"""
from ._s3_base import S3CompatDriver


class TencentCOSDriver(S3CompatDriver):
    name = "tencent"
    # endpoint 例子：https://cos.<region>.myqcloud.com
    # addressing_style=virtual


driver = TencentCOSDriver()
