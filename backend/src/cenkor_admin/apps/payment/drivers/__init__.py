"""驱动注册入口：导入本包即完成所有通道注册。

新增通道只需在此追加一行 import。
"""
from cenkor_admin.apps.payment.drivers.base import (  # noqa: F401
    NotifyResult,
    PayError,
    PaymentDriver,
    PayRequest,
    PayResult,
    get_driver_class,
    list_providers,
    register_driver,
)
from cenkor_admin.apps.payment.drivers import alipay  # noqa: F401,E402
from cenkor_admin.apps.payment.drivers import wechat  # noqa: F401,E402
from cenkor_admin.apps.payment.drivers import xunhupay  # noqa: F401,E402

__all__ = [
    "NotifyResult",
    "PayError",
    "PaymentDriver",
    "PayRequest",
    "PayResult",
    "get_driver_class",
    "list_providers",
    "register_driver",
]
