"""OpenAI 兼容 LLM 客户端。

设计目标：
- **零新增依赖**：只用项目已装的 httpx，不引 openai SDK，便于离线交付与打包瘦身
- **多 provider**：只要能说 OpenAI 协议就能接（OpenAI / DeepSeek / 通义 / Moonshot / 智谱 / vLLM / Ollama）
- **可降级**：未配置密钥时抛 LLMNotConfiguredError，调用方自行回退到人工流程，绝不阻塞主链路
- **可观测**：每次调用返回 token 用量与耗时，供 cms_ai_generations 表做溯源与成本核算

对外 API：
    llm = get_llm()
    r = await llm.chat([{"role": "user", "content": "..."}])
    data = await llm.chat_json(messages, hint="...")      # 强制 JSON 并容错解析
    vecs = await llm.embed(["文本1", "文本2"])
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger

from cenkor_admin.core.config import get_settings


class LLMError(RuntimeError):
    """LLM 调用失败（网络、鉴权、限流重试耗尽、响应不可解析）"""


class LLMNotConfiguredError(LLMError):
    """未配置 AI_API_KEY 等必要参数——调用方应降级而非报错给用户"""


@dataclass(slots=True)
class LLMUsage:
    tokens_in: int = 0
    tokens_out: int = 0
    total_tokens: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "total_tokens": self.total_tokens,
        }


@dataclass(slots=True)
class LLMResult:
    """一次补全的结果 + 可观测元数据"""

    text: str
    model: str
    provider: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    latency_ms: int = 0
    finish_reason: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def meta(self) -> dict[str, Any]:
        """落库用的溯源信息（不含正文，避免日志膨胀）"""
        return {
            "provider": self.provider,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "finish_reason": self.finish_reason,
            **self.usage.as_dict(),
        }


# --------------------------------------------------------------------------
# JSON 抽取：模型偶尔会在 JSON 外包 ```json 或加前言，这里做容错
# --------------------------------------------------------------------------
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> Any:
    """从模型输出里尽力抽出一个 JSON 值。

    依次尝试：整段解析 → 去代码围栏 → 定位首个 { 或 [ 到最后一个闭合符。
    全部失败抛 LLMError，调用方据此重试或降级。
    """
    if not text or not text.strip():
        raise LLMError("模型返回空响应")

    candidates: list[str] = [text.strip()]

    # 抽取 ```json ... ``` 块
    for m in _FENCE_RE.findall(text):
        candidates.append(m.strip())

    # 定位平衡括号区间（优先对象，其次数组）
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            candidates.append(text[start : end + 1])

    for cand in candidates:
        if not cand:
            continue
        try:
            return json.loads(cand)
        except (ValueError, TypeError):
            continue

    preview = text[:200].replace("\n", " ")
    raise LLMError(f"无法从模型输出解析 JSON（前 200 字符：{preview}）")


class LLMClient:
    """OpenAI 兼容协议的轻量异步客户端。

    生命周期：应用启动时首次 get_llm() 创建，进程内复用 httpx 连接池。
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        chat_model: str,
        embed_model: str,
        provider: str = "openai",
        timeout: float = 60.0,
        max_retries: int = 2,
        temperature: float = 0.3,
        embed_base_url: str = "",
        embed_api_key: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.provider = provider
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.temperature = temperature

        # embedding 可以走另一家服务商（常见：chat 用 DeepSeek 省钱，embedding 用通义）。
        # 留空则回退主配置——单服务商的用户完全感知不到这个参数的存在。
        self.embed_base_url = (embed_base_url or base_url).rstrip("/")
        self._embed_api_key = embed_api_key or api_key
        self._embed_is_separate = bool(
            embed_base_url and embed_base_url.rstrip("/") != self.base_url
        )

        self._client: httpx.AsyncClient | None = None
        self._embed_client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()
        # embedding 维度缓存：不同模型维度不同，首次调用后记录
        self.detected_dim: int | None = None

    # ---------------- 基础设施 ----------------

    @property
    def configured(self) -> bool:
        return bool(self._api_key and self.base_url)

    @property
    def embed_configured(self) -> bool:
        """语义检索是否可用（需要 embed 模型名 + 对应密钥）"""
        return bool(self.embed_model and self._embed_api_key and self.embed_base_url)

    def _build_client(self, base_url: str, api_key: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(self.timeout, connect=15.0),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            async with self._lock:
                if self._client is None or self._client.is_closed:
                    self._client = self._build_client(self.base_url, self._api_key)
        return self._client

    async def _get_embed_client(self) -> httpx.AsyncClient:
        # 未单独配置 embedding 服务商时，与 chat 共用同一个连接池
        if not self._embed_is_separate:
            return await self._get_client()
        if self._embed_client is None or self._embed_client.is_closed:
            async with self._lock:
                if self._embed_client is None or self._embed_client.is_closed:
                    self._embed_client = self._build_client(
                        self.embed_base_url, self._embed_api_key
                    )
        return self._embed_client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
        if self._embed_client is not None and not self._embed_client.is_closed:
            await self._embed_client.aclose()
        self._embed_client = None

    def _ensure_ready(self) -> None:
        if not self.configured:
            raise LLMNotConfiguredError(
                "AI 未配置：请在 .env 设置 AI_API_KEY（以及需要的 AI_BASE_URL / AI_CHAT_MODEL）"
            )

    async def _post(
        self, path: str, payload: dict[str, Any], *, client: httpx.AsyncClient | None = None
    ) -> dict[str, Any]:
        """带指数退避的 POST。只对可重试错误重试（429 / 5xx / 网络超时）。"""
        self._ensure_ready()
        http = client if client is not None else await self._get_client()
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = await http.post(path, json=payload)
                if resp.status_code in (429, 500, 502, 503, 504):
                    # 服务端限流或抖动：退避重试
                    raise _RetryableError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                if resp.status_code >= 400:
                    # 4xx（鉴权/参数错）重试无意义
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:500]}")
                return resp.json()
            except _RetryableError as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    break
                backoff = min(2**attempt * 1.0, 8.0)
                logger.warning("llm.retry", attempt=attempt + 1, wait=backoff, error=str(exc))
                await asyncio.sleep(backoff)
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    break
                backoff = min(2**attempt * 1.0, 8.0)
                logger.warning("llm.network_retry", attempt=attempt + 1, error=str(exc))
                await asyncio.sleep(backoff)

        raise LLMError(f"LLM 调用失败（已重试 {self.max_retries} 次）：{last_exc}")

    # ---------------- 补全 ----------------

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
        extra: dict[str, Any] | None = None,
    ) -> LLMResult:
        """单轮/多轮补全。json_mode=True 时尽量让服务端以 JSON 对象作答。"""
        payload: dict[str, Any] = {
            "model": model or self.chat_model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if json_mode:
            # 主流 OpenAI 兼容服务都支持；不支持的会忽略或报 400，
            # 那种情况下上层 chat_json 的容错解析仍然可用
            payload["response_format"] = {"type": "json_object"}
        if extra:
            payload.update(extra)

        started = time.monotonic()
        data = await self._post("/chat/completions", payload)
        latency_ms = int((time.monotonic() - started) * 1000)

        try:
            choice = data["choices"][0]
            text = choice["message"]["content"] or ""
            finish_reason = choice.get("finish_reason", "") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"响应结构异常：{str(data)[:300]}") from exc

        u = data.get("usage") or {}
        usage = LLMUsage(
            tokens_in=int(u.get("prompt_tokens") or 0),
            tokens_out=int(u.get("completion_tokens") or 0),
            total_tokens=int(u.get("total_tokens") or 0),
        )
        result = LLMResult(
            text=text,
            model=data.get("model") or payload["model"],
            provider=self.provider,
            usage=usage,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            raw={k: v for k, v in data.items() if k != "choices"},
        )
        logger.info(
            "llm.chat",
            model=result.model,
            tokens=usage.total_tokens,
            latency_ms=latency_ms,
        )
        return result

    async def chat_json(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        repair_attempts: int = 1,
    ) -> tuple[Any, LLMResult]:
        """要求模型输出 JSON，返回 (解析结果, 原始结果)。

        首次解析失败时把错误回灌给模型再试一次（repair_attempts 控制）。
        """
        result = await self.chat(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        try:
            return extract_json(result.text), result
        except LLMError as exc:
            if repair_attempts <= 0:
                raise
            logger.warning("llm.json_repair", error=str(exc))
            repair_messages = [
                *messages,
                {"role": "assistant", "content": result.text[:4000]},
                {
                    "role": "user",
                    "content": (
                        "上面的输出不是合法 JSON。请只输出一个合法 JSON，"
                        "不要任何解释文字、不要 markdown 代码围栏。"
                    ),
                },
            ]
            repaired = await self.chat(
                repair_messages,
                model=model,
                temperature=0,
                max_tokens=max_tokens,
                json_mode=True,
            )
            return extract_json(repaired.text), repaired

    # ---------------- 向量 ----------------

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        """批量取向量。空输入直接返回空列表，不发请求。"""
        cleaned = [t if isinstance(t, str) else str(t) for t in texts]
        if not cleaned:
            return []

        payload: dict[str, Any] = {
            "model": model or self.embed_model,
            "input": cleaned,
        }
        # embedding 可能走另一家服务商，用独立连接池
        http = await self._get_embed_client()
        data = await self._post("/embeddings", payload, client=http)

        try:
            items = data["data"]
            # 服务端不保证按输入顺序返回，必须按 index 排序
            items = sorted(items, key=lambda x: x.get("index", 0))
            vectors = [item["embedding"] for item in items]
        except (KeyError, TypeError) as exc:
            raise LLMError(f"embedding 响应结构异常：{str(data)[:300]}") from exc

        if vectors:
            self.detected_dim = len(vectors[0])
            if len(vectors) != len(cleaned):
                raise LLMError(f"embedding 数量不匹配：请求 {len(cleaned)}，返回 {len(vectors)}")
        return vectors

    async def embed_one(self, text: str, *, model: str | None = None) -> list[float]:
        vectors = await self.embed([text], model=model)
        if not vectors:
            raise LLMError("embedding 返回为空")
        return vectors[0]


class _RetryableError(Exception):
    """内部标记：该错误值得重试"""


# --------------------------------------------------------------------------
# 单例
# --------------------------------------------------------------------------
_llm: LLMClient | None = None


def get_llm() -> LLMClient:
    """按当前配置返回进程级单例。配置变更需重启进程生效。"""
    global _llm
    if _llm is None:
        s = get_settings()
        _llm = LLMClient(
            base_url=getattr(s, "AI_BASE_URL", "https://api.openai.com/v1"),
            api_key=getattr(s, "AI_API_KEY", ""),
            chat_model=getattr(s, "AI_CHAT_MODEL", "gpt-4o-mini"),
            embed_model=getattr(s, "AI_EMBED_MODEL", "text-embedding-3-small"),
            provider=getattr(s, "AI_PROVIDER", "openai"),
            timeout=float(getattr(s, "AI_TIMEOUT_SECONDS", 60)),
            max_retries=int(getattr(s, "AI_MAX_RETRIES", 2)),
            temperature=float(getattr(s, "AI_TEMPERATURE", 0.3)),
            # 留空则回退主配置
            embed_base_url=getattr(s, "AI_EMBED_BASE_URL", "") or "",
            embed_api_key=getattr(s, "AI_EMBED_API_KEY", "") or "",
        )
    return _llm


def ai_enabled() -> bool:
    """功能开关 + 密钥双检。路由层用它决定是否注册 AI 端点。"""
    s = get_settings()
    return bool(getattr(s, "AI_ENABLED", False)) and bool(getattr(s, "AI_API_KEY", ""))


async def close_llm() -> None:
    """应用关闭时释放连接池。"""
    global _llm
    if _llm is not None:
        await _llm.aclose()
        _llm = None
