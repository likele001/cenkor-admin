"""支付驱动抽象层。

每个 provider 实现一个 PaymentDriver 子类并用 @register_driver 注册。
驱动职责单一：**只负责与第三方通信、签名、验签**，不碰数据库、不写业务状态。
这样新增一个通道 = 新增一个文件，commerce / 业务侧代码零改动。

统一约定：
- 金额内部一律用「分」（int），驱动自行换算成第三方要的单位
- 异步：全部 async，HTTP 走 httpx
- 驱动实例由 service 层按 channel 配置构造（已解密的明文配置）
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, ClassVar


class PayError(Exception):
    """支付网关交互失败。message 面向用户，detail 面向排查。"""

    def __init__(self, message: str, *, detail: str = "", code: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.code = code


@dataclass
class PayRequest:
    """下单入参。"""

    out_trade_no: str
    subject: str
    amount_cents: int
    scene_key: str = "default"
    description: str = ""
    client_ip: str = ""
    notify_url: str = ""
    return_url: str = ""
    openid: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class PayResult:
    """下单结果。

    mode 决定前端/收银台怎么渲染：
      qrcode   -> payload["code_url"] 生成二维码
      redirect -> payload["url"] 直接跳转
      jsapi    -> payload 是 JSAPI 调起参数
      manual   -> 线下转账，payload 里是收款信息
    """

    mode: str
    payload: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class NotifyResult:
    """回调解析结果。"""

    ok: bool
    out_trade_no: str = ""
    trade_no: str = ""
    amount_cents: int = 0
    paid: bool = False
    close: bool = False
    raw: dict[str, Any] = field(default_factory=dict)
    reply: str = ""
    content_type: str = "text/plain"
    error: str = ""


_REGISTRY: dict[str, type["PaymentDriver"]] = {}


def register_driver(cls: type["PaymentDriver"]) -> type["PaymentDriver"]:
    if not cls.provider:
        raise ValueError(f"{cls.__name__} 未声明 provider")
    _REGISTRY[cls.provider] = cls
    return cls


def get_driver_class(provider: str) -> type["PaymentDriver"]:
    cls = _REGISTRY.get(provider)
    if cls is None:
        raise PayError(f"不支持的支付通道：{provider}", code="unknown_provider")
    return cls


def list_providers() -> list[dict[str, Any]]:
    """给前端渲染「新增通道」下拉用。"""
    out = []
    for cls in _REGISTRY.values():
        out.append({
            "provider": cls.provider,
            "display_name": cls.display_name,
            "sub_types": [{"value": v, "label": lbl} for v, lbl in cls.sub_types],
            "supports_refund": cls.supports_refund,
            "fields": cls.config_fields,
        })
    return sorted(out, key=lambda x: x["provider"])


class PaymentDriver(abc.ABC):
    """通道驱动基类。"""

    provider: ClassVar[str] = ""
    display_name: ClassVar[str] = ""
    # 虎皮椒这种一个账号挂多个支付方式的通道用 sub_types 声明
    sub_types: ClassVar[list[tuple[str, str]]] = []
    supports_refund: ClassVar[bool] = True
    # 前端表单字段声明；secret=True 的项落库前加密
    config_fields: ClassVar[list[dict[str, Any]]] = []

    def __init__(
        self,
        config: dict[str, Any],
        *,
        mode: str = "live",
        scene_key: str = "default",
        sub_type: str = "",
    ):
        self.config = config or {}
        self.mode = mode or "live"
        self.scene_key = scene_key
        self.sub_type = sub_type or str((config or {}).get("sub_type") or "")

    @classmethod
    def secret_fields(cls) -> tuple[str, ...]:
        return tuple(f["key"] for f in cls.config_fields if f.get("secret"))

    @classmethod
    def validate_config(cls, config: dict[str, Any]) -> list[str]:
        """返回缺失的必填项 label 列表。"""
        missing = []
        for f in cls.config_fields:
            if f.get("required") and not (config or {}).get(f["key"]):
                # 已加密的回填值视为已填
                missing.append(f["label"])
        return missing

    def one(self, key: str, default: str = "") -> str:
        val = self.config.get(key)
        return str(val).strip() if val not in (None, "") else default

    @abc.abstractmethod
    async def create_pay(self, req: PayRequest) -> PayResult:
        """向第三方下单。"""

    @abc.abstractmethod
    async def query(self, out_trade_no: str) -> dict[str, Any]:
        """主动查单。返回至少 {paid: bool, trade_no: str, amount_cents: int, status: str}。"""

    @abc.abstractmethod
    async def refund(
        self,
        out_trade_no: str,
        amount_cents: int,
        out_refund_no: str,
        reason: str = "",
        total_cents: int = 0,
    ) -> dict[str, Any]:
        """退款。返回至少 {ok: bool, refund_trade_no: str, message: str}。"""

    @abc.abstractmethod
    async def verify_notify(self, headers: dict[str, str], body: bytes) -> NotifyResult:
        """解析并验签第三方异步回调。

        注意：返回 NotifyResult 而不是抛异常 —— 回调必须给第三方一个明确应答，
        否则会被反复重推。异常一律在驱动内部收敛进 NotifyResult.error。
        """
