"""阿里云 OSS — S3 协议"""
from ._s3_base import S3CompatDriver


class AliyunOSSDriver(S3CompatDriver):
    name = "aliyun"
    # endpoint 例子：https://oss-cn-hangzhou.aliyuncs.com
    # addressing_style=virtual


driver = AliyunOSSDriver()
