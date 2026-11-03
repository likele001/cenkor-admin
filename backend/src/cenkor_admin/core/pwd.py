"""口令哈希统一入口（bcrypt）。

全站只允许从这里取 ``pwd_context``，不要在别处新建 ``CryptContext``。原因有两条：

1. **兼容垫片只能装一次、且必须早于 backend 加载。**
   passlib 1.7.4 的 bcrypt backend 在首次 hash/verify 才惰性加载，加载时要读
   ``bcrypt.__about__.__version__``；而 bcrypt 4.1 起删掉了 ``__about__``。
   垫片放在这里，任何模块导入本文件就会先装好，避免各自为战时漏装。
2. **参数分叉会直接变成登录事故。**
   多份 ``CryptContext`` 一旦 schemes / rounds 不一致，同一条口令在不同入口的
   行为就会分叉，典型症状是「改完密码登录不了」。

哈希输出格式为 bcrypt 的 ``$2b$``，与 bcrypt 3.x / 4.x 全互通，已有口令无需迁移。
"""
from __future__ import annotations

import types

import bcrypt
from passlib.context import CryptContext

# --- bcrypt >= 4.1 兼容垫片 ---------------------------------------------------
# 补回 passlib 版本探测所需的 __about__。仅影响版本读取，不参与哈希计算，
# 因此不会改变哈希结果，也不会让历史口令失效。
if not hasattr(bcrypt, "__about__"):
    bcrypt.__about__ = types.SimpleNamespace(__version__=bcrypt.__version__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
