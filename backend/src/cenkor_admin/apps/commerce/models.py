"""应用生态交易模型（P0）：定价 / 订单 / 授权 / 实例绑定

设计要点：
- 金额一律用「分」存整数，避免浮点误差；currency 默认 CNY。
- app_pricing 是商品（每个 app_key 一条），app_orders 是交易，
  app_licenses 是交付凭证，app_license_bindings 是授权实际落地的实例。
- license 与 order 解耦：order_id 可为空，支持运营手工签发（赠送 / 补偿 / 线下大客户）。
- token 字段保存云端私钥签名的授权凭证，客户实例用内置公钥验签，
  因此客户改本地缓存也无法伪造有效期 —— 这是「底座开源 + 应用收费」能成立的前提。
"""
from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from cenkor_admin.apps.system import pricing_rules
from cenkor_admin.core.compat import json_column
from cenkor_admin.core.db import Base

# 去掉易混淆字符（0/O/1/I），便于电话或微信里口述授权码
LICENSE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# 收费模式枚举由公开的字段规则模块定义（唯一真相源）
PRICING_MODELS = pricing_rules.PRICING_MODELS
ORDER_STATUSES = ("pending", "paid", "cancelled", "refunded", "expired")
LICENSE_STATUSES = ("issued", "active", "expired", "revoked", "suspended")


def _rand_block(n: int = 4) -> str:
    return "".join(secrets.choice(LICENSE_ALPHABET) for _ in range(n))


def generate_license_key() -> str:
    """CKA-XXXX-XXXX-XXXX-XXXX（19 位有效字符，约 94 bit 熵，不可爆破）"""
    return "CKA-" + "-".join(_rand_block() for _ in range(4))


def generate_order_no() -> str:
    ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"CK{ts}{''.join(secrets.choice('0123456789') for _ in range(4))}"


class AppPricing(Base):
    """应用定价（商品）。定位键是 (product, app_key)，每个轴各一条。

    没建行不等于免费 —— 下单端点缺行即拒单（commerce_router.create_order）。
    要白送就明确建一条 model=free，别靠"没配过价"这种沉默态。
    """

    __tablename__ = "app_pricing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 目标产品/宿主（多产品命名空间）：与 app_key 组合唯一
    product: Mapped[str] = mapped_column(String(32), default="cenkor-admin", nullable=False, index=True)
    app_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # 商品归属：app_developers.id。NULL 或 1(Cenkor 官方) = 平台自营，收入全额归平台
    developer_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # 单应用扣点覆盖（万分比，2000 = 20%）。NULL = 用平台全局默认
    platform_fee_bp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # free / one_time / seat（试用与订阅已下线，2026-09-23）
    model: Mapped[str] = mapped_column(String(20), default="free", nullable=False)
    # ---- 三个价（一律「分」）----
    # 原价（划线价）：仅用于展示，不参与结算。0 = 不显示划线价
    list_price_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 售价：常规成交价
    price_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 促销价：限时，促销期内取代售价成交，到期自动回落售价。0 = 无促销
    promo_price_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    promo_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promo_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promo_label: Mapped[str | None] = mapped_column(String(60), nullable=True)  # 活动名
    # 座位单价：对应「售价」档；原价与促销价按同比例换算
    seat_price_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="CNY", nullable=False)
    # 授权周期：仅「按席位」模式生效（席位制按周期授权）；买断为永久有效
    period_days: Mapped[int] = mapped_column(Integer, default=365, nullable=False)
    # 已下线：恒 0。列保留仅为兼容历史数据，不要再写入任何值
    trial_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    min_seats: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_seats: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0 = 不限
    # 购买是否需要人工审核
    require_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    intro: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[Any | None] = mapped_column(json_column(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("product", "app_key", name="uq_app_pricing_product_key"),
    )


class AppOrder(Base):
    """应用购买订单。"""

    __tablename__ = "app_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_no: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    product: Mapped[str] = mapped_column(String(32), default="cenkor-admin", nullable=False, index=True)
    app_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    app_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    # 买家：portal 前台用户或 admin 后台用户
    buyer_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    buyer_type: Mapped[str] = mapped_column(String(16), default="portal", nullable=False)
    buyer_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    buyer_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # 下单时的定价快照（定价改了不影响历史订单）
    model: Mapped[str] = mapped_column(String(20), default="one_time", nullable=False)
    seats: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # 实际成交单价（生效价：促销期内即促销价）
    unit_price_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 原价（划线价）快照，仅用于订单展示「原价 → 实付」。0 = 无划线
    list_unit_price_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 成交时的促销活动名（非促销期成交为 NULL）
    promo_label: Mapped[str | None] = mapped_column(String(60), nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="CNY", nullable=False)
    # ---- 分账快照：下单时定死，日后改扣点不影响历史订单 ----
    developer_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    platform_fee_bp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    platform_fee_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    developer_income_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # none(平台自营) / pending(结算期内) / settled(已转可提) / refunded(已冲正)
    settle_status: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # pending / paid / cancelled / refunded / expired
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    # manual(对公/线下) / wechat / alipay / offline
    channel: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    trade_no: Mapped[str | None] = mapped_column(String(128), nullable=True)  # 第三方支付单号
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[Any | None] = mapped_column(json_column(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AppLicense(Base):
    """授权凭证。签发后由客户实例激活 / 心跳。"""

    __tablename__ = "app_licenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    license_key: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    product: Mapped[str] = mapped_column(String(32), default="cenkor-admin", nullable=False, index=True)
    app_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    app_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    order_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("app_orders.id"), nullable=True, index=True
    )
    buyer_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    buyer_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    model: Mapped[str] = mapped_column(String(20), default="one_time", nullable=False)
    seats: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # issued / active / expired / revoked / suspended
    status: Mapped[str] = mapped_column(String(20), default="issued", nullable=False, index=True)
    # 绑定信息（首次激活时写入）
    bound_domain: Mapped[str | None] = mapped_column(String(200), nullable=True)
    instance_fp: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    max_instances: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_rebind: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    rebind_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # 云端私钥签名的授权凭证（客户实例用内置公钥验签）
    token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AppLicenseBinding(Base):
    """授权与实例的绑定关系。同一授权可绑多台（受 max_instances 限制）。"""

    __tablename__ = "app_license_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    license_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("app_licenses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instance_fp: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    domain: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    agent: Mapped[str | None] = mapped_column(String(200), nullable=True)
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[Any | None] = mapped_column(json_column(), nullable=True)

    __table_args__ = (
        UniqueConstraint("license_id", "instance_fp", name="uq_license_binding_fp"),
    )


class DevWallet(Base):
    """开发者钱包。三个资金池互不混用：

    - ``available_cents``：可提现余额
    - ``pending_cents``：已成交但仍在结算期内的净收入
    - ``frozen_cents``：已发起提现、等平台审核打款的金额

    三池之和即该开发者账面总额。任何变动都必须经 ``ledger.post()`` 落流水。
    """

    __tablename__ = "dev_wallets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    developer_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    available_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pending_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    frozen_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_income_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_withdrawn_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_refunded_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DevLedger(Base):
    """开发者资金流水。**只增不改** —— 钱包余额永远可由流水重算，这是对账依据。

    一条流水只记「一个池的一次变动」，``pool_after_cents`` 为该池变动后的余额。
    """

    __tablename__ = "dev_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    developer_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # sale / settle / refund / withdraw_apply / withdraw_paid / withdraw_reject / adjust
    type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    # available / pending / frozen
    pool: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    pool_after_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    order_no: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    withdrawal_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    app_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    available_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    settled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class DevWithdrawal(Base):
    """开发者提现申请。收款账户在申请时快照，避免开发者中途改账户影响在途单据。"""

    __tablename__ = "dev_withdrawals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    developer_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    fee_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    actual_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # alipay / bank / wechat
    account_type: Mapped[str] = mapped_column(String(20), default="alipay", nullable=False)
    account_no: Mapped[str | None] = mapped_column(String(200), nullable=True)
    account_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # pending / approved / rejected / paid
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pay_voucher: Mapped[str | None] = mapped_column(String(300), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DevPayoutAccount(Base):
    """开发者默认收款账户 —— 提现时作为收款信息快照的来源，避免重复填写。"""

    __tablename__ = "dev_payout_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    developer_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    # alipay / wechat / bank
    account_type: Mapped[str] = mapped_column(String(20), default="alipay", nullable=False)
    account_no: Mapped[str | None] = mapped_column(String(200), nullable=True)
    account_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ============================================================
# 云端绑定：客户实例 ↔ 官方账号
# ============================================================

class CloudDeviceCode(Base):
    """一次性绑定码（设备码流程的「官方云」侧）。

    客户实例申请 → 用户在门户输入 user_code 确认 → 实例轮询换发长期实例令牌。
    device_code 只在实例与云之间传递，user_code 才是给人看的；
    approve 后置 ``approved``，换发令牌后置 ``consumed``，防止同一个码被重复兑换。
    """

    __tablename__ = "cloud_device_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    user_code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    # pending / approved / denied / consumed / expired
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    instance_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    instance_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    instance_uid: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # 目标产品/宿主：绑定后写入实例，用于按产品过滤目录/已购
    product: Mapped[str] = mapped_column(String(32), default="cenkor-admin", nullable=False, index=True)
    portal_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CloudInstance(Base):
    """已绑定官方账号的客户实例（官方云侧）。

    ``token_hash`` 只存 sha256 —— 云端库即使泄露也无法反推出实例令牌。
    刻意不给 ``updated_at`` 加 onupdate：避免 commit 后序列化触发异步懒加载
    （``MissingGreenlet`` 的经典来源）。
    """

    __tablename__ = "cloud_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instance_uid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # 目标产品/宿主：cenkormes / lightmes / cenkor-admin ...
    product: Mapped[str] = mapped_column(String(32), default="cenkor-admin", nullable=False, index=True)
    portal_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    instance_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CloudClient(Base):
    """本机（客户实例）持有的云端凭证 —— 单行表，``id`` 恒为 1。

    只存实例令牌，**不存任何门户账号密码**；解绑即删行。
    """

    __tablename__ = "cloud_client"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hub_url: Mapped[str] = mapped_column(String(255), nullable=False)
    instance_uid: Mapped[str] = mapped_column(String(64), nullable=False)
    token: Mapped[str] = mapped_column(Text, nullable=False)
    account: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bound_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
