"""生态交易层：应用定价 / 订单 / 授权签发 / 云端绑定。

随平台以 MIT 开源（v0.5.11 起）。

授权体系的安全防线是**私钥**，不是本模块的源码：私钥由
``license_authority.get_or_create_keypair`` 运行时生成、以密文存进
``system_settings.license.signing_key``；开源侧 ``core/licensing.py``
只内置公钥做验签。因此公开签发逻辑不会削弱授权安全性 ——
拿到全部源码但没有私钥，依然伪造不出有效授权。
"""
