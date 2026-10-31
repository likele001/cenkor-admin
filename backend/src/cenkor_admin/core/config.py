"""Cenkor Admin · 配置层（从 .env 加载，跨 DB 兼容）"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

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

    # ---- 核心升级资源库（后台「在线升级 > 资源库」下拉用）----
    # 远程 releases.json 清单（结构 [{version, channel, released_at, pkg_url, size, notes}, ...]）
    CORE_RELEASES_URL: str = "https://cenkor.cn/api/releases.json"
    # 远程清单鉴权 token（走 Authorization: Bearer <token>）；空 = 不带鉴权
    CORE_RELEASES_TOKEN: str = ""
    # 远程清单缓存时长（秒），避免每次进升级页都打远程
    CORE_RELEASES_TTL_SECONDS: int = 300
    # 「下载到本地」的目标目录
    CORE_RELEASES_DOWNLOAD_DIR: str = "/www/wwwroot/cenkor-admin/release"

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
    DATABASE_URL: str = "postgresql+asyncpg://cenkor:change-me-in-env@localhost:5432/cenkor"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://cenkor:change-me-in-env@localhost:5432/cenkor"
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
    # ---- 官方应用市场（开源层：目录浏览 + 授权码安装）----
    # 留空则回退 PORTAL_PUBLIC_URL（默认 https://portal.cenkor.cn）
    # 与 CENKOR_CLOUD_URL 解耦：后者决定本机是授权中心还是客户实例，
    # 而市场目录是公开数据，两种角色都应能浏览。
    MARKET_HUB_URL: str = ""
    CENKOR_CLOUD_URL: str = ""
    # 授权中心不可达时的离线宽限天数（超期后收费应用停止放行）
    LICENSE_OFFLINE_GRACE_DAYS: int = 15
    # 心跳间隔（小时）
    LICENSE_HEARTBEAT_HOURS: int = 24

    # ---- AI（OpenAI 兼容协议，可指向 DeepSeek / 通义 / Moonshot / vLLM 等）----
    # 总开关：关闭时 AI 相关路由不注册，前端也拿不到入口。
    # 真正的可用条件 = AI_ENABLED 且 AI_API_KEY 非空（见 core.llm.ai_enabled）
    AI_ENABLED: bool = False
    # 仅用于溯源标注，不影响协议（协议永远是 OpenAI 兼容）
    AI_PROVIDER: str = "openai"
    AI_BASE_URL: str = "https://api.openai.com/v1"
    # 密钥一律从 .env 注入，禁止写进代码或默认值
    AI_API_KEY: str = ""
    AI_CHAT_MODEL: str = "gpt-4o-mini"
    AI_EMBED_MODEL: str = "text-embedding-3-small"
    # embedding 单独走另一家服务商（常见：chat 用 DeepSeek 省钱，embedding 用通义）。
    # 两个都留空 = 与 chat 共用同一服务商。
    AI_EMBED_BASE_URL: str = ""
    AI_EMBED_API_KEY: str = ""
    # 期望维度，仅作参考；实际维度以接口返回为准（会写入 cms_embeddings.dim）
    AI_EMBED_DIM: int = 1536
    AI_TIMEOUT_SECONDS: int = 60
    AI_MAX_RETRIES: int = 2
    AI_TEMPERATURE: float = 0.3
    # 单次向量化批大小（embedding 接口通常有批量上限，过大易 400）
    AI_EMBED_BATCH: int = 32
    # 视觉模型：留空 = 该能力未启用。通道与密钥继承上面的 chat 配置
    # （绝大多数 OpenAI 兼容站 chat 与 vision 同 base_url）。
    AI_VISION_MODEL: str = ""
    # 图片生成：同上，留空则不具备出图能力。部分站点图片走独立 base_url。
    AI_IMAGE_BASE_URL: str = ""
    AI_IMAGE_API_KEY: str = ""
    AI_IMAGE_MODEL: str = ""

    # 后台可视化配置说明：
    # 以上 AI_* 是「环境变量兜底」路径。正式用法是在后台 AI 设置里添加服务商
    # 并按能力绑定模型，配置来源见 apps/cms/ai/registry.py（DB 优先，.env 兜底）。

    # ---- MCP（Agent 接入）----
    # MCP 端点鉴权密钥；留空则拒绝外部调用（后台调试用 /mcp/tools）
    MCP_API_KEY: str = ""
    MCP_ENABLED: bool = True
    # 写权限总闸门：false 时 Agent 只能读，create/update/publish 一律拒绝。
    # 必须在这里定义字段 —— 只在代码里 getattr 默认值的话，.env 怎么设都不生效。
    MCP_ALLOW_WRITE: bool = True
    # 内容引擎端点的细分权限校验（apps/cms/rbac_guard.py）。
    # 默认开启；出问题置 false 可退回「登录即可」。
    CMS_RBAC_ENFORCE: bool = True

    # ---- CMS 公开页静态缓存（模板系统 P2）----
    # 后端渲染详情页后把 HTML 落盘，nginx try_files 命中就不回源。
    # 关掉 = 全部 miss = 自动回落动态渲染，等于没开过，可随时应急。
    # 注意字段必须声明在这里：只在代码里 os.environ 读取的话，.env 怎么配都不生效。
    CMS_STATIC_CACHE: bool = False
    # 落盘根目录，留空用 backend/var/htmlcache
    CMS_STATIC_CACHE_ROOT: str = ""

    @property
    def ai_ready(self) -> bool:
        """AI 是否真正可用（开关 + 密钥双检）"""
        return bool(self.AI_ENABLED and self.AI_API_KEY)

    @property
    def ai_embed_ready(self) -> bool:
        """语义检索是否可用（需要 embed 模型名 + 对应密钥）"""
        if not self.ai_ready:
            return False
        if not self.AI_EMBED_MODEL:
            return False
        return bool(self.AI_EMBED_API_KEY or self.AI_API_KEY)

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
