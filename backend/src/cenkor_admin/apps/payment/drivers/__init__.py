"""驱动注册入口：导入本包即完成所有通道注册。

新增通道只需在此追加一行 import。
"""
from cenkor_admin.apps.payment.drivers import (
    alipay,  # noqa: F401
    wechat,  # noqa: F401
    xunhupay,  # noqa: F401
)
from cenkor_admin.apps.payment.drivers.base import (
    NotifyResult,
    PayError,
    PaymentDriver,
    PayRequest,
    PayResult,
    get_driver_class,
    list_providers,
    register_driver,
)

__all__ = [
    "NotifyResult",
    "PayError",
    "PayRequest",
    "PayResult",
    "PaymentDriver",
    "get_driver_class",
    "list_providers",
    "register_driver",
]
