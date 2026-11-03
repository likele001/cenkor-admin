from cenkor_admin.apps.base import AppManifest

MANIFEST = AppManifest(
    key="payment",
    builtin=True,          # 底座：支付底座，删了商店 / 套餐 / 订单付不了账
    name="支付中心",
    version="1.0.0",
    author="Cenkor",
    description="可插拔的统一支付应用：支付宝官方 / 微信支付官方 / 虎皮椒聚合，按业务应用（scene）隔离配置",
    icon="💳",
    category="system",
    permissions_required=["payment:read", "payment:write"],
    menus=[{
        "key": "payment",
        "title": "支付中心",
        "icon": "credit-card",
        "sort": 30,
        "children": [
            {"key": "payment:channels", "title": "支付通道", "path": "/payment/channels"},
            {"key": "payment:orders", "title": "支付订单", "path": "/payment/orders"},
        ],
    }],
)
