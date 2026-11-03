"""payment 应用：可插拔的统一支付中心。

- 驱动层在 drivers/（每个第三方通道一个文件，通过 @register_driver 注册）
- 业务编排在 service.py
- 管理接口在 router.py（自动挂载到 /api/v1/payment）
- 公开接口在 public_router.py（回调 + 收银台，挂 /api/v1/public/payment）
"""
