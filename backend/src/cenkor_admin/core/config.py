"""Cenkor Admin · 配置层（从 .env 加载，跨 DB 兼容）"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from cenkor_admin import __version__ as _PKG_VERSION


def _find_env_file() -> str | None:
    """按优先级查找 .env 文件（兼容宝塔 / Docker / 手动启动等各种 CWD）"""
    candidates = [
        Path.cwd() / ".env",
        Path.cwd().parent / ".env",
        Path(__file__).resolve().parent.parent.parent.parent / ".env",
        Path(os.environ.get("HOME", "/tmp")) / ".env",
    ]
    for p in candidates:
        if p.exists():
            return str(p.resolve())
    return ".env"


class Settings(BaseSettings):
    """应用配置 - 全部从环境变量读取，缺省值只用于 dev。"""

    model_config = SettingsConfigDict(
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- 应用 ----
    APP_NAME: str = "Cenkor Admin"
    APP_VERSION: str = _PKG_VERSION
    APP_ENV: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True

    # ---- 核心版本检查（升级提示）----
    # 是否启用「发现新版本」检查（spoke 向官方云查询核心最新版本）
    RELEASE_CHECK_ENABLED: bool = True
    # 查询地址；留空则回退到 CENKOR_CLOUD_URL。两者都为空 = 本机即中心，不联网检查
    RELEASE_CHECK_URL: str = ""
    # 检查结果缓存时长（小时），避免每次进工作台都打中心
    RELEASE_CHECK_TTL_HOURS: int = 6

    # ---- 安全 ----
    SECRET_KEY: str = "dev-secret-change-me-32-bytes-min"
    # 历史 SECRET_KEY 列表（用于轮换：旧 token 仍可解码，但新 token 用新 key）
    SECRET_KEY_OLD: str = ""  # 逗号分隔
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # Cookie Secure（生产应为 True）
    COOKIE_SECURE: bool = False
    # 限流（API 调用频率）
    RATE_LIMIT_PER_MINUTE: int = 300

    @property
    def secret_keys(self) -> list[str]:
        """所有有效的 SECRET_KEY（包含历史的）"""
        keys = [self.SECRET_KEY]
        if self.SECRET_KEY_OLD:
            for k in self.SECRET_KEY_OLD.split(","):
                k = k.strip()
                if k and k not in keys:
                    keys.append(k)
        return keys

    # ---- 数据库 ----
    DATABASE_URL: str = "postgresql+asyncpg://cenkor:li123456@localhost:5432/cenkor"
    DATABASE_URL_SYNC: str = "postgresql://cenkor:li123456@localhost:5432/cenkor"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False

    # ---- Redis ----
    REDIS_URL: str = "redis://localhost:6379/0"

    # ---- S3 / MinIO ----
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_API_PORT: int = 9000  # 公网访问的端口（Docker 映射后的端口）
    S3_ACCESS_KEY: str = "minio"
    S3_SECRET_KEY: str = "minio12345"
    S3_BUCKET_PUBLIC: str = "cenkor-public"
    S3_BUCKET_PRIVATE: str = "cenkor-private"
    S3_REGION: str = "us-east-1"

    # ---- 飞书 OAuth ----
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""
    FEISHU_REDIRECT_URI: str = "http://localhost:5173/auth/feishu/callback"

    # ---- CORS ----
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:8000"

    # ---- SMTP（忘记密码 / 通知邮件；本期 P1 接入）----
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@cenkor.cn"
    SMTP_USE_TLS: bool = True

    # ---- 公网 ----
    PUBLIC_BASE_URL: str = "http://localhost:8000"

    # ---- 门户官网（应用市场绑定确认页）----
    # 仅用于生成「去门户确认绑定」的链接；授权中心与客户实例都读它
    PORTAL_PUBLIC_URL: str = "https://portal.cenkor.cn"

    # ---- 应用授权中心（生态收费）----
    # 留空 = 本机即授权中心（自营部署：签发与校验同库）
    # 填 https://portal.cenkor.cn = 客户实例，向该地址激活 / 心跳 / 拉包
    CENKOR_CLOUD_URL: str = ""
    # 授权中心不可达时的离线宽限天数（超期后收费应用停止放行）
    LICENSE_OFFLINE_GRACE_DAYS: int = 15
    # 心跳间隔（小时）
    LICENSE_HEARTBEAT_HOURS: int = 24

    @property
    def db_dialect(self) -> str:
        """返回当前数据库方言（postgresql | mysql | sqlite | unknown）"""
        url = self.DATABASE_URL.lower()
        if "postgresql" in url or "postgres" in url:
            return "postgresql"
        if "mysql" in url:
            return "mysql"
        if "sqlite" in url:
            return "sqlite"
        return "unknown"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_postgres(self) -> bool:
        return self.db_dialect == "postgresql"

    @property
    def is_mysql(self) -> bool:
        return self.db_dialect == "mysql"

    @property
    def is_sqlite(self) -> bool:
        return self.db_dialect == "sqlite"


@lru_cache
def get_settings() -> Settings:
    # 强制从 .env 加载，覆盖可能继承的旧环境变量
    env_path = _find_env_file()
    if env_path and os.path.exists(env_path):
        try:
            from dotenv import dotenv_values
            overrides = {k: v for k, v in dotenv_values(env_path).items() if v is not None}
            return Settings(**overrides)
        except ImportError:
            pass
    return Settings()
