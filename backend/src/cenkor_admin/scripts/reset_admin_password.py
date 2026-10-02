"""重置管理员口令 —— 忘记初始口令时的官方恢复路径。

管理员口令在库里只存 bcrypt hash（不可逆），明文只在 seed 首次创建时打印一次。
一旦容器被重建（docker compose down 再 up），日志里那行就没了，而且 seed 因为
"管理员已存在"会直接跳过 —— 所以"忘记口令"必须有独立入口，不能靠重跑 seed。

用法：
    # Docker 部署（推荐走包装脚本）
    bash scripts/reset-admin-password.sh
    bash scripts/reset-admin-password.sh --password 'NewPass123'

    # 裸机 / 宿主机部署
    cd backend && PYTHONPATH=src python -m cenkor_admin.scripts.reset_admin_password

不传 --password 时随机生成一个强口令并在终端打印。
"""
from __future__ import annotations

import argparse
import asyncio
import secrets
import string

import structlog
from sqlalchemy import select

from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.core.db import AsyncSessionLocal, async_engine
from cenkor_admin.core.security import hash_password

log = structlog.get_logger()

DEFAULT_EMAIL = "admin@cenkor.cn"
PASSWORD_LENGTH = 16
# ⚠️ 必须与 seed._generate_admin_password 的字符集保持一致（两处改动要同步）
PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*"


def generate_password(length: int = PASSWORD_LENGTH) -> str:
    """生成随机强口令（与 seed 同策略）。"""
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))


async def reset(email: str, password: str | None) -> int:
    """把指定账号的口令重置为 password（None 则随机生成）。返回进程退出码。"""
    generated = password is None
    new_password = password or generate_password()

    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(auth_models.User).where(auth_models.User.email == email))
        ).scalar_one_or_none()
        if user is None:
            print(f"\n  ✗ 未找到账号 {email}，未做任何修改。\n")
            log.error("reset_admin.user_not_found", email=email)
            await async_engine.dispose()
            return 1

        user.password_hash = hash_password(new_password)
        # 口令变更后让所有已签发的 access/refresh token 立即失效
        user.token_version = (user.token_version or 0) + 1
        await db.commit()

        username, token_version = user.username, user.token_version

        print("\n" + "=" * 68)
        print(f"  账号      ：{email}（用户名 {username}）")
        print(f"  新口令    ：{new_password}")
        print(f"  来源      ：{'本次随机生成' if generated else '命令行指定'}")
        print("  ⚠️ 口令只显示这一次，且旧会话已全部失效，请立即保存")
        print("=" * 68 + "\n")

    log.info("reset_admin.done", email=email, token_version=token_version)
    await async_engine.dispose()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="重置 Cenkor Admin 管理员口令",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="不传 --password 时随机生成一个强口令并打印。",
    )
    parser.add_argument("--email", default=DEFAULT_EMAIL, help=f"账号邮箱（默认 {DEFAULT_EMAIL}）")
    parser.add_argument("--password", default=None, help="新口令；不传则随机生成")
    args = parser.parse_args()
    return asyncio.run(reset(args.email, args.password))


if __name__ == "__main__":
    raise SystemExit(main())
