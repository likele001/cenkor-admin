"""AI 配置解析层 · 后台可视化配置与运行时之间的唯一桥梁。

职责只有一件：把「数据库里的服务商 + 能力绑定」解析成「某个能力该用哪套
endpoint」，供 ``core.llm`` 构造客户端。

四条设计原则：

1. **DB 优先，.env 兜底**
   后台配置了就用后台的；没配就回退环境变量。这样老部署升级后立刻可用，
   不会因为「还没去界面点一遍」而全线不可用。

2. **同步读取，异步刷新**
   ``get_llm_for()`` 是同步调用（被大量既有代码直接调），不能在里面查库。
   所以缓存常驻内存，由 startup 预热 + 写操作后立即刷新 + TTL 到期后台补刷。

3. **密钥只在内存解密**
   缓存里的 ``api_key`` 是明文，但不上日志（dataclass repr=False）、
   不出接口（接口只给掩码）。密文解不开时不算崩，标记为 key_error 降级。

4. **参数白名单**
   用户在界面上填的 params 不直接透传给服务商，按能力过滤+裁剪，
   避免「温度填了 500」这种把请求打成 400 的低级故障。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.core.config import get_settings
from cenkor_admin.core.secrets import decrypt_secret

# ---------------------------------------------------------------- 能力定义


@dataclass(frozen=True)
class CapabilitySpec:
    key: str
    label: str
    hint: str
    # 该能力是否已经真实接入调用链；未接入的在界面上标注「仅配置」
    wired: bool = True


CAPABILITIES: tuple[CapabilitySpec, ...] = (
    CapabilitySpec("chat", "对话补全", "建模、起草、翻译、SEO 等文本生成"),
    CapabilitySpec("embedding", "向量化", "语义检索与相似度计算"),
    CapabilitySpec("vision", "视觉理解", "看图说话、图文审校、截图转结构化数据"),
    CapabilitySpec("image", "图片生成", "封面图、配图、示意图"),
    CapabilitySpec("rerank", "重排序", "检索结果精排，提升召回质量", wired=False),
    CapabilitySpec("asr", "语音识别", "音视频转文字", wired=False),
    CapabilitySpec("tts", "语音合成", "文案转语音", wired=False),
)

CAPABILITY_KEYS: tuple[str, ...] = tuple(c.key for c in CAPABILITIES)
CAPABILITY_MAP: dict[str, CapabilitySpec] = {c.key: c for c in CAPABILITIES}


# ---------------------------------------------------------------- 参数白名单


@dataclass(frozen=True)
class ParamSpec:
    """单个参数的约束。type 决定裁剪方式，enum 非空时只接受枚举值。"""

    type: str  # float | int | str | bool
    lo: float | None = None
    hi: float | None = None
    enum: tuple[str, ...] = ()


PARAM_SPECS: dict[str, dict[str, ParamSpec]] = {
    "chat": {
        "temperature": ParamSpec("float", 0.0, 2.0),
        "max_tokens": ParamSpec("int", 1, 32000),
        "top_p": ParamSpec("float", 0.0, 1.0),
        "frequency_penalty": ParamSpec("float", -2.0, 2.0),
    },
    "embedding": {
        "dim": ParamSpec("int", 1, 8192),
        "batch": ParamSpec("int", 1, 128),
    },
    "vision": {
        "max_tokens": ParamSpec("int", 1, 32000),
        "detail": ParamSpec("str", enum=("low", "high", "auto")),
    },
    "image": {
        "size": ParamSpec("str"),
        "quality": ParamSpec("str", enum=("standard", "hd", "low", "medium", "high", "auto")),
        "n": ParamSpec("int", 1, 4),
        "style": ParamSpec("str", enum=("vivid", "natural")),
    },
    "rerank": {"top_n": ParamSpec("int", 1, 100)},
    "asr": {"language": ParamSpec("str")},
    "tts": {"speed": ParamSpec("float", 0.25, 4.0)},
}


def sanitize_params(capability: str, raw: dict[str, Any] | None) -> dict[str, Any]:
    """按白名单过滤并裁剪参数。未知键直接丢弃，越界值夹到边界。"""
    if not raw:
        return {}
    specs = PARAM_SPECS.get(capability) or {}
    out: dict[str, Any] = {}
    for key, value in raw.items():
        spec = specs.get(key)
        if spec is None or value is None or value == "":
            continue
        if spec.type == "float":
            try:
                num = float(value)
            except (TypeError, ValueError):
                continue
            if spec.lo is not None:
                num = max(spec.lo, num)
            if spec.hi is not None:
                num = min(spec.hi, num)
            out[key] = num
        elif spec.type == "int":
            try:
                num_i = int(value)
            except (TypeError, ValueError):
                continue
            if spec.lo is not None:
                num_i = max(int(spec.lo), num_i)
            if spec.hi is not None:
                num_i = min(int(spec.hi), num_i)
            out[key] = num_i
        elif spec.type == "bool":
            out[key] = bool(value)
        else:
            text = str(value).strip()
            if spec.enum and text not in spec.enum:
                continue
            if text:
                out[key] = text
    return out


# ---------------------------------------------------------------- 端点


@dataclass(frozen=True)
class Endpoint:
    """某类能力解析后的最终调用目标。"""

    capability: str
    base_url: str
    model: str
    # repr=False：这个对象可能被塞进异常信息或日志，密钥绝不能跟着走
    api_key: str = field(default="", repr=False)
    kind: str = "openai"
    provider_id: int | None = None
    provider_slug: str = ""
    provider_name: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    timeout: float = 60.0
    max_retries: int = 2
    extra_headers: dict[str, str] = field(default_factory=dict)
    # db = 后台配置；env = 环境变量兜底
    source: str = "env"

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model)


@dataclass
class ProviderView:
    """服务商在内存里的可调用形态。key_error 非空表示密文解不开。"""

    id: int
    slug: str
    name: str
    kind: str
    base_url: str
    api_key: str = field(default="", repr=False)
    key_error: str = ""
    enabled: bool = True
    timeout: float = 60.0
    max_retries: int = 2
    extra_headers: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------- 缓存


class Registry:
    def __init__(self) -> None:
        self.providers: dict[int, ProviderView] = {}
        self.endpoints: dict[str, Endpoint] = {}
        self.loaded_at: float = 0.0
        self.ttl: float = 30.0
        self.last_error: str = ""
        self._refreshing = False

    @property
    def stale(self) -> bool:
        return (time.monotonic() - self.loaded_at) > self.ttl

    def endpoint(self, capability: str) -> Endpoint | None:
        ep = self.endpoints.get(capability)
        return ep if ep and ep.configured else None


_REGISTRY = Registry()


def current() -> Registry:
    """只读当前缓存，永不阻塞、永不查库。"""
    return _REGISTRY


def invalidate() -> None:
    """标记过期。下次异步调用点会重新加载。"""
    _REGISTRY.loaded_at = 0.0


# ---------------------------------------------------------------- 加载


def _env_endpoints() -> dict[str, Endpoint]:
    """从环境变量构造兜底端点。

    只取仍走 .env 的部署形态：单服务商、chat 与 embedding 可分离。
    vision / image 默认继承 chat 的通道与密钥（绝大多数 OpenAI 兼容站
    三者在同一 base_url 下），只单独指定模型名。
    """
    s = get_settings()
    if not (getattr(s, "AI_ENABLED", False) and getattr(s, "AI_API_KEY", "")):
        return {}

    base = (getattr(s, "AI_BASE_URL", "") or "").rstrip("/")
    key = getattr(s, "AI_API_KEY", "") or ""
    timeout = float(getattr(s, "AI_TIMEOUT_SECONDS", 60) or 60)
    retries = int(getattr(s, "AI_MAX_RETRIES", 2) or 0)
    kind = getattr(s, "AI_PROVIDER", "openai") or "openai"

    out: dict[str, Endpoint] = {}

    chat_model = getattr(s, "AI_CHAT_MODEL", "") or ""
    if chat_model:
        out["chat"] = Endpoint(
            capability="chat",
            base_url=base,
            model=chat_model,
            api_key=key,
            kind=kind,
            provider_slug="env",
            provider_name="环境变量",
            params=sanitize_params("chat", {"temperature": getattr(s, "AI_TEMPERATURE", 0.3)}),
            timeout=timeout,
            max_retries=retries,
            source="env",
        )

    # embedding 可以单独一家（DeepSeek 没有 embedding 接口）
    eb = (getattr(s, "AI_EMBED_BASE_URL", "") or "").rstrip("/") or base
    ek = getattr(s, "AI_EMBED_API_KEY", "") or key
    em = getattr(s, "AI_EMBED_MODEL", "") or ""
    if em and eb:
        dim = getattr(s, "AI_EMBED_DIM", 0) or 0
        out["embedding"] = Endpoint(
            capability="embedding",
            base_url=eb,
            model=em,
            api_key=ek,
            kind=kind,
            provider_slug="env",
            provider_name="环境变量",
            params=sanitize_params(
                "embedding",
                {
                    "dim": dim or None,
                    "batch": getattr(s, "AI_EMBED_BATCH", 32),
                },
            ),
            timeout=timeout,
            max_retries=retries,
            source="env",
        )

    vm = getattr(s, "AI_VISION_MODEL", "") or ""
    if vm:
        out["vision"] = Endpoint(
            capability="vision",
            base_url=base,
            model=vm,
            api_key=key,
            kind=kind,
            provider_slug="env",
            provider_name="环境变量",
            timeout=timeout,
            max_retries=retries,
            source="env",
        )

    ib = (getattr(s, "AI_IMAGE_BASE_URL", "") or "").rstrip("/") or base
    ik = getattr(s, "AI_IMAGE_API_KEY", "") or key
    im = getattr(s, "AI_IMAGE_MODEL", "") or ""
    if im and ib:
        out["image"] = Endpoint(
            capability="image",
            base_url=ib,
            model=im,
            api_key=ik,
            kind=kind,
            provider_slug="env",
            provider_name="环境变量",
            timeout=max(timeout, 120.0),
            max_retries=retries,
            source="env",
        )

    return out


async def load(db: AsyncSession, *, force: bool = False) -> Registry:
    """从数据库重建缓存。失败时保留旧缓存（宁可旧一点，不能突然不可用）。"""
    if not force and not _REGISTRY.stale:
        return _REGISTRY

    # 延迟导入，避免 models 与 registry 循环引用
    from cenkor_admin.apps.cms.ai.models import CmsAiCapability, CmsAiProvider

    try:
        rows = (await db.execute(select(CmsAiProvider))).scalars().all()
        caps = (await db.execute(select(CmsAiCapability))).scalars().all()
    except Exception as exc:  # 表还没建好时不要让整个服务起不来
        _REGISTRY.last_error = f"{type(exc).__name__}: {exc}"
        logger.warning("ai_registry.load_failed", error=_REGISTRY.last_error)
        return _REGISTRY

    providers: dict[int, ProviderView] = {}
    for row in rows:
        key = decrypt_secret(row.api_key_enc)
        providers[row.id] = ProviderView(
            id=row.id,
            slug=row.slug,
            name=row.name,
            kind=row.kind or "openai",
            base_url=(row.base_url or "").rstrip("/"),
            api_key=key or "",
            key_error=""
            if key is not None
            else "密钥无法解密（SECRET_KEY 可能已变更，请重新填写）",
            enabled=bool(row.enabled),
            timeout=float(row.timeout_seconds or 60),
            max_retries=int(row.max_retries or 0),
            extra_headers=dict(row.extra_headers or {}),
        )

    endpoints: dict[str, Endpoint] = {}
    for cap in caps:
        if not cap.enabled:
            continue
        prov = providers.get(cap.provider_id) if cap.provider_id else None
        if prov is None or not prov.enabled or not cap.model:
            continue
        if prov.key_error:
            # 密钥解不开：跳过，让 env 兜底或标记未配置，而不是拿空 key 去撞 401
            continue
        endpoints[cap.capability] = Endpoint(
            capability=cap.capability,
            base_url=prov.base_url,
            model=cap.model,
            api_key=prov.api_key,
            kind=prov.kind,
            provider_id=prov.id,
            provider_slug=prov.slug,
            provider_name=prov.name,
            params=sanitize_params(cap.capability, cap.params),
            timeout=prov.timeout,
            max_retries=prov.max_retries,
            extra_headers=prov.extra_headers,
            source="db",
        )

    # 后台没配的能力用环境变量补上——不覆盖后台已配的
    for cap_key, ep in _env_endpoints().items():
        endpoints.setdefault(cap_key, ep)

    _REGISTRY.providers = providers
    _REGISTRY.endpoints = endpoints
    _REGISTRY.loaded_at = time.monotonic()
    _REGISTRY.last_error = ""
    logger.debug("ai_registry.loaded", providers=len(providers), endpoints=sorted(endpoints))
    return _REGISTRY


def schedule_refresh() -> None:
    """在异步上下文里投递一次后台刷新，不阻塞当前请求。

    同步环境（脚本、CLI）没有事件循环，直接跳过——调用方拿到的仍是缓存。
    """
    if _REGISTRY._refreshing:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _run() -> None:
        from cenkor_admin.core.db import AsyncSessionLocal

        _REGISTRY._refreshing = True
        try:
            async with AsyncSessionLocal() as session:
                await load(session, force=True)
        except Exception as exc:  # pragma: no cover
            logger.warning("ai_registry.refresh_failed", error=str(exc))
        finally:
            _REGISTRY._refreshing = False

    loop.create_task(_run())


def get_endpoint(capability: str) -> Endpoint | None:
    """取端点。缓存过期时顺手投递后台刷新，本次仍用旧值。"""
    if _REGISTRY.stale:
        schedule_refresh()
    return _REGISTRY.endpoint(capability)


def available_capabilities() -> list[str]:
    return [k for k in CAPABILITY_KEYS if _REGISTRY.endpoint(k)]
