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
import base64
import hashlib
import json
import mimetypes
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from cenkor_admin.core.config import get_settings


class LLMError(RuntimeError):
    """LLM 调用失败（网络、鉴权、限流重试耗尽、响应不可解析）"""


class LLMNotConfiguredError(LLMError):
    """未配置 AI_API_KEY 等必要参数——调用方应降级而非报错给用户"""


class LLMUnsupportedError(LLMError):
    """服务商拒绝了请求本身（模型不支持、套餐不含该能力、参数非法）。

    为什么单独一类：这类错误重试一万次也是同样结果 —— 换模型或换套餐才行。
    上层看到它就知道「这是配置问题，去后台改绑定/充值」，而不是「服务抖动，
    稍后重试」。返回给运营的文案也完全不同：给一句「AI 服务调用失败：
    HTTP 404: {一大段 JSON}」等于没说话。
    """


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
        extra_headers: dict[str, str] | None = None,
        embed_params: dict[str, Any] | None = None,
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
        # 网关常要求额外鉴权头（如 X-Api-Version / api-key），一并带上
        self.extra_headers = {k: str(v) for k, v in (extra_headers or {}).items() if k and v}

        # embedding 厂商私有参数（如豆包 dimensions=1024 降维）。
        # 只有非 None 的键才透传，避免 None 把厂商默认值冲掉。
        self.embed_params: dict[str, Any] = {
            k: v for k, v in (embed_params or {}).items() if v is not None
        }

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
        # 最近一次 embed 的用量：embedding 接口也按 token 计费，
        # 调用方（向量化 / 用量记账）需要它才能把这块成本算进去。
        # 单实例共享，并发时会互相覆盖 —— 只影响记账精度，不影响功能。
        self.last_embed_usage: dict[str, int] = {}

    # ---------------- 基础设施 ----------------

    @property
    def configured(self) -> bool:
        return bool(self._api_key and self.base_url)

    @property
    def embed_configured(self) -> bool:
        """语义检索是否可用（需要 embed 模型名 + 对应密钥）"""
        return bool(self.embed_model and self._embed_api_key and self.embed_base_url)

    def _build_client(self, base_url: str, api_key: str) -> httpx.AsyncClient:
        headers: dict[str, str] = dict(self.extra_headers.items())
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(self.timeout, connect=15.0),
            headers={
                **headers,
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

    @staticmethod
    def _exc_text(exc: Exception) -> str:
        """异常的可读文本。

        `str(httpx.ReadTimeout())` 是空字符串 —— 直接塞进错误消息会得到
        「LLM 调用失败（已重试 2 次）：」，冒号后什么都没有，
        用户和日志都拿不到任何线索。类型名至少能区分超时 / 连接失败 / 协议错。
        """
        text = str(exc).strip()
        if text:
            return text
        name = type(exc).__name__
        if isinstance(exc, httpx.TimeoutException):
            return f"{name}（AI 服务未在超时时间内返回）"
        return name

    async def _post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> dict[str, Any]:
        """带指数退避的 POST。只对可重试错误重试（429 / 5xx / 网络超时）。

        `timeout` / `max_retries` 可按调用覆盖，原因：默认 60s 是给普通补全
        定的，长文改写（公众号 800~1500 字）单次就要 60s 以上，用默认值
        会稳定超时 —— 而重试只是把同一个超时再等一遍，最后报出来的还是一句
        没有信息的空错误。
        """
        self._ensure_ready()
        http = client if client is not None else await self._get_client()
        retries = self.max_retries if max_retries is None else max(0, max_retries)
        # 注意：不能写 timeout=timeout，httpx 里 None 表示「不超时」，
        # 必须整体省略这个参数才会沿用 client 的默认值
        req_kwargs: dict[str, Any] = (
            {} if timeout is None else {"timeout": httpx.Timeout(timeout, connect=15.0)}
        )
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = await http.post(path, json=payload, **req_kwargs)
                if resp.status_code in (429, 500, 502, 503, 504):
                    # 服务端限流或抖动：退避重试
                    raise _RetryableError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                if resp.status_code >= 400:
                    # 4xx（鉴权/参数错）重试无意义
                    if resp.status_code in (400, 404, 422):
                        # 这几个码的含义是「请求本身不被接受」，不是服务故障：
                        # 模型不支持、套餐不含该能力、参数非法。归成专门异常，
                        # 上层才能给出「去改绑定/充值」而不是「稍后重试」的提示。
                        raise LLMUnsupportedError(
                            f"HTTP {resp.status_code}: {resp.text[:500]}"
                        ) from None
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:500]}")
                return resp.json()
            except _RetryableError as exc:
                last_exc = exc
                if attempt >= retries:
                    break
                backoff = min(2**attempt * 1.0, 8.0)
                logger.warning(
                    "llm.retry", attempt=attempt + 1, wait=backoff, error=self._exc_text(exc)
                )
                await asyncio.sleep(backoff)
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt >= retries:
                    break
                backoff = min(2**attempt * 1.0, 8.0)
                logger.warning(
                    "llm.network_retry",
                    attempt=attempt + 1,
                    timeout=timeout or self.timeout,
                    error=self._exc_text(exc),
                )
                await asyncio.sleep(backoff)

        detail = self._exc_text(last_exc) if last_exc is not None else "未知错误"
        raise LLMError(f"LLM 调用失败（已重试 {retries} 次）：{detail}")

    async def _get(
        self,
        path: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> dict[str, Any]:
        """带指数退避的 GET。

        视频任务轮询用它：一次网络抖动不该让整个任务判定失败 —— 任务在
        服务商那边还在跑，我们这边报错只会让用户重提交、白花一次钱。
        所以这里的重试比 POST 更宽容（GET 无副作用，重试代价为零）。
        """
        self._ensure_ready()
        http = await self._get_client()
        retries = self.max_retries if max_retries is None else max(0, max_retries)
        req_kwargs: dict[str, Any] = (
            {} if timeout is None else {"timeout": httpx.Timeout(timeout, connect=15.0)}
        )
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = await http.get(path, **req_kwargs)
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise _RetryableError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                if resp.status_code >= 400:
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:500]}")
                return resp.json()
            except _RetryableError as exc:
                last_exc = exc
                if attempt >= retries:
                    break
                backoff = min(2**attempt * 1.0, 8.0)
                logger.warning(
                    "llm.get_retry", attempt=attempt + 1, wait=backoff, error=self._exc_text(exc)
                )
                await asyncio.sleep(backoff)
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt >= retries:
                    break
                backoff = min(2**attempt * 1.0, 8.0)
                logger.warning(
                    "llm.get_network_retry",
                    attempt=attempt + 1,
                    timeout=timeout or self.timeout,
                    error=self._exc_text(exc),
                )
                await asyncio.sleep(backoff)

        detail = self._exc_text(last_exc) if last_exc is not None else "未知错误"
        raise LLMError(f"LLM 请求失败（已重试 {retries} 次）：{detail}")

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
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> LLMResult:
        """单轮/多轮补全。json_mode=True 时尽量让服务端以 JSON 对象作答。

        `timeout` / `max_retries` 透传给 `_post`，供长文生成这类慢调用覆盖
        默认 60s —— 否则模型还在写、客户端已经放弃。
        """
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
        data = await self._post(
            "/chat/completions", payload, timeout=timeout, max_retries=max_retries
        )
        latency_ms = int((time.monotonic() - started) * 1000)

        try:
            choice = data["choices"][0]
            message = choice.get("message") or {}
            text = message.get("content") or ""
            finish_reason = choice.get("finish_reason", "") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"响应结构异常：{str(data)[:300]}") from exc

        # 推理模型（reasoner 类）被 max_tokens 截断时，message 里可能**只有**
        # reasoning_content、没有 content 键。这不是服务异常，是预算不够 ——
        # 报「响应结构异常」会让人去查网络和鉴权，方向完全错。
        if not text.strip():
            reasoning = str(message.get("reasoning_content") or "")
            if finish_reason == "length":
                raise LLMError(
                    "输出被 max_tokens 截断：推理模型的思考过程已占满预算"
                    f"（reasoning {len(reasoning)} 字符），请提高 max_tokens"
                )
            if reasoning.strip():
                raise LLMError(
                    "模型只返回了思考过程、没有正文：请提高 max_tokens 或改用非推理模型"
                )

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
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> tuple[Any, LLMResult]:
        """要求模型输出 JSON，返回 (解析结果, 原始结果)。

        首次解析失败时把错误回灌给模型再试一次（repair_attempts 控制）。
        `timeout` / `max_retries` 透传给底层请求，长文场景要显式放大。
        """
        result = await self.chat(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
            timeout=timeout,
            max_retries=max_retries,
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
                timeout=timeout,
                max_retries=max_retries,
            )
            return extract_json(repaired.text), repaired

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        extra: dict[str, Any] | None = None,
        meta_out: dict[str, Any] | None = None,
    ):
        """流式补全：逐段 yield 正文增量（OpenAI 兼容 SSE）。

        与 chat() 的差异：
        - 不做重试 —— 流式无法安全重放（客户端可能已收到一半），失败直接抛 LLMError
        - 结束后把 model/provider/usage/latency/finish_reason 写进 meta_out（若传入），
          供调用方落溯源；服务商流式不给 usage 时按字符长度粗估 tokens_out
        """
        self._ensure_ready()
        payload: dict[str, Any] = {
            "model": model or self.chat_model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if extra:
            payload.update(extra)

        http = await self._get_client()
        started = time.monotonic()
        parts: list[str] = []
        usage = LLMUsage()
        finish_reason = ""
        resp_model = ""
        try:
            async with http.stream("POST", "/chat/completions", json=payload) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    raise LLMError(f"HTTP {resp.status_code}: {body[:500]}")
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(data)
                    except ValueError:
                        continue
                    u = chunk.get("usage")
                    if isinstance(u, dict):
                        usage = LLMUsage(
                            tokens_in=int(u.get("prompt_tokens") or 0),
                            tokens_out=int(u.get("completion_tokens") or 0),
                            total_tokens=int(u.get("total_tokens") or 0),
                        )
                    if chunk.get("model"):
                        resp_model = str(chunk["model"])
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    if choices[0].get("finish_reason"):
                        finish_reason = choices[0]["finish_reason"]
                    delta = (choices[0].get("delta") or {}).get("content")
                    if delta:
                        parts.append(delta)
                        yield delta
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM 流式调用失败：{exc}") from exc

        latency_ms = int((time.monotonic() - started) * 1000)
        if meta_out is not None:
            text = "".join(parts)
            if usage.total_tokens == 0 and text:
                # 多数服务商流式分片不带 usage；按中文密度粗估（约 2 字符/token），误差换体验
                usage = LLMUsage(tokens_out=max(1, round(len(text) / 2)))
            meta_out.update(
                {
                    "model": resp_model or payload["model"],
                    "provider": self.provider,
                    "usage": usage.as_dict(),
                    "latency_ms": latency_ms,
                    "finish_reason": finish_reason,
                }
            )
        logger.info(
            "llm.chat_stream",
            model=resp_model or payload["model"],
            chars=len("".join(parts)),
            latency_ms=latency_ms,
        )

    # ---------------- 向量 ----------------

    async def embed_meta(
        self, texts: list[str], *, model: str | None = None
    ) -> tuple[list[list[float]], dict[str, int]]:
        """批量取向量，并把本次调用的计量信息一起返回。

        元数据**随返回值出去**，不依赖实例属性：`embed_one` 只是批量版的一层
        包装，若把 usage 记在 `self.last_embed_usage` 上，两个协程并发时后一个
        会覆盖前一个，A 的 token 就会被记到 B 头上。

        返回 `(vectors, {"prompt_tokens", "total_tokens", "latency_ms"})`。
        """
        cleaned = [t if isinstance(t, str) else str(t) for t in texts]
        if not cleaned:
            return [], {"prompt_tokens": 0, "total_tokens": 0, "latency_ms": 0}

        payload: dict[str, Any] = {
            "model": model or self.embed_model,
            "input": cleaned,
        }
        if self.embed_params:
            payload.update(self.embed_params)
        # embedding 可能走另一家服务商，用独立连接池
        http = await self._get_embed_client()
        started = time.perf_counter()
        data = await self._post("/embeddings", payload, client=http)
        latency_ms = int((time.perf_counter() - started) * 1000)

        try:
            items = data["data"]
            # 服务端不保证按输入顺序返回，必须按 index 排序
            items = sorted(items, key=lambda x: x.get("index", 0))
            vectors = [item["embedding"] for item in items]
        except (KeyError, TypeError) as exc:
            raise LLMError(f"embedding 响应结构异常：{str(data)[:300]}") from exc

        # 用量：不同服务商字段名不一，能拿到多少算多少，拿不到就留 0
        usage = data.get("usage") if isinstance(data, dict) else None
        meta = {"prompt_tokens": 0, "total_tokens": 0, "latency_ms": latency_ms}
        if isinstance(usage, dict):
            meta["prompt_tokens"] = int(
                usage.get("prompt_tokens") or usage.get("total_tokens") or 0
            )
            meta["total_tokens"] = int(
                usage.get("total_tokens") or usage.get("prompt_tokens") or 0
            )

        if vectors:
            self.detected_dim = len(vectors[0])
            if len(vectors) != len(cleaned):
                raise LLMError(f"embedding 数量不匹配：请求 {len(cleaned)}，返回 {len(vectors)}")
        return vectors, meta

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        """批量取向量。空输入直接返回空列表，不发请求。

        `last_embed_usage` 仅为兼容旧调用方保留；新代码请用 `embed_meta`，
        并发下实例属性会被别的请求覆盖。
        """
        vectors, meta = await self.embed_meta(texts, model=model)
        self.last_embed_usage = {
            "prompt_tokens": meta["prompt_tokens"],
            "total_tokens": meta["total_tokens"],
        }
        return vectors

    async def embed_one(self, text: str, *, model: str | None = None) -> list[float]:
        vectors = await self.embed([text], model=model)
        if not vectors:
            raise LLMError("embedding 返回为空")
        return vectors[0]

    async def embed_one_meta(
        self, text: str, *, model: str | None = None
    ) -> tuple[list[float], dict[str, int]]:
        """单条取向量 + 计量信息，并发安全。"""
        vectors, meta = await self.embed_meta([text], model=model)
        if not vectors:
            raise LLMError("embedding 返回为空")
        return vectors[0], meta

    # ---------------- 视觉与图片 ----------------

    async def vision_chat(
        self,
        prompt: str,
        images: list[str],
        *,
        system: str | None = None,
        model: str | None = None,
        detail: str = "auto",
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> LLMResult:
        """看图说话。images 里每项可为 URL、data: URI 或本地文件路径。

        走的是标准 chat/completions 多模态 messages，任何支持视觉的
        OpenAI 兼容服务（GPT-4o / Qwen-VL / GLM-4V / 本地 vLLM）都能用，
        不需要为视觉单独写一套协议。
        """
        if not images:
            raise LLMError("vision_chat 需要至少一张图片")
        if detail not in ("low", "high", "auto"):
            detail = "auto"

        parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for img in images:
            parts.append(
                {"type": "image_url", "image_url": {"url": _to_image_url(img), "detail": detail}}
            )

        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": parts})

        return await self.chat(messages, model=model, max_tokens=max_tokens, json_mode=json_mode)

    async def generate_image(
        self,
        prompt: str,
        *,
        model: str | None = None,
        size: str | None = None,
        quality: str | None = None,
        style: str | None = None,
        n: int = 1,
        response_format: str = "url",
        extra: dict[str, Any] | None = None,
    ) -> ImageResult:
        """文生图（/images/generations）。

        size / quality 是各家差异最大的地方：OpenAI 用 1024x1024 与 hd，
        国内服务常见 1024*1024 与 low/medium/high。所以这两个值不写死，
        由能力参数下发，服务商不认时会返回明确报错，界面上一眼能看出来。
        """
        payload: dict[str, Any] = {
            "model": model or self.chat_model,
            "prompt": prompt,
            "n": max(1, min(int(n or 1), 4)),
        }
        if size:
            payload["size"] = size
        if quality:
            payload["quality"] = quality
        if style:
            payload["style"] = style
        if response_format:
            payload["response_format"] = response_format
        if extra:
            payload.update(extra)

        started = time.monotonic()
        data = await self._post("/images/generations", payload)
        latency_ms = int((time.monotonic() - started) * 1000)

        items = data.get("data") or []
        if not isinstance(items, list) or not items:
            raise LLMError(f"图片生成响应缺少 data：{str(data)[:300]}")

        urls = [str(it["url"]) for it in items if isinstance(it, dict) and it.get("url")]
        b64 = [str(it["b64_json"]) for it in items if isinstance(it, dict) and it.get("b64_json")]
        revised = ""
        if isinstance(items[0], dict):
            revised = str(items[0].get("revised_prompt") or "")

        logger.info("llm.image", model=payload["model"], count=len(items), latency_ms=latency_ms)
        return ImageResult(
            urls=urls,
            b64=b64,
            revised_prompt=revised,
            model=str(data.get("model") or payload["model"]),
            latency_ms=latency_ms,
            raw={k: v for k, v in data.items() if k != "data"},
        )

    async def create_video_task(
        self,
        prompt: str,
        *,
        image: str | None = None,
        model: str | None = None,
        ratio: str | None = "16:9",
        duration: int | None = 5,
        resolution: str | None = None,
        watermark: bool | None = False,
        camera_fixed: bool | None = None,
        extra: dict[str, Any] | None = None,
    ) -> VideoTask:
        """提交视频生成任务，立刻返回任务 id（不等产物）。

        带 `image` 就是图生视频（首帧即该图），不带就是文生视频 —— 两种模式
        在服务商侧是同一个端点、同一个参数结构，差别只在 content 里多不多
        一个 image_url 块。所以这里合成一个方法，不拆两份。

        **不能在这里等结果**：一次生成 60~300 秒，uvicorn 前面还有 nginx
        `proxy_read_timeout 60s`，同步等必然 504，而且会把 worker 占死。
        """
        text = _fmt_video_prompt(
            prompt,
            ratio=ratio,
            duration=duration,
            resolution=resolution,
            watermark=watermark,
            camera_fixed=camera_fixed,
        )
        content: list[dict[str, Any]] = [{"type": "text", "text": text}]
        if image:
            content.append({"type": "image_url", "image_url": {"url": _to_image_url(image)}})

        payload: dict[str, Any] = {
            "model": model or self.chat_model,
            "content": content,
        }
        if extra:
            payload.update(extra)

        started = time.monotonic()
        data = await self._post("/contents/generations/tasks", payload, timeout=60.0)
        latency_ms = int((time.monotonic() - started) * 1000)

        task = _video_task_from(data)
        if not task.task_id:
            raise LLMError(f"视频任务提交后没有返回任务 id：{str(data)[:300]}")
        logger.info(
            "llm.video.submitted",
            model=payload["model"],
            task=task.task_id,
            i2v=bool(image),
            latency_ms=latency_ms,
        )
        return task

    async def query_video_task(self, task_id: str) -> VideoTask:
        """查询视频任务状态。

        轮询期间单次失败不该判定任务失败 —— 服务商那边还在跑，我们报错
        只会让运营重新提交、白花一次钱。所以给足重试（4 次），超时也给宽。
        """
        if not task_id:
            raise LLMError("查询视频任务需要 task_id")
        data = await self._get(
            f"/contents/generations/tasks/{task_id}", timeout=30.0, max_retries=4
        )
        task = _video_task_from(data)
        if not task.task_id:
            task.task_id = task_id
        return task

    async def download_to_file(self, url: str, path: Path, *, timeout: float = 600.0) -> int:
        """把远程大文件流式落到本地，返回字节数。

        为什么不用 `generate_image` 那套 `resp.content`：视频动辄 10~50MB，
        整个读进内存既浪费又是并发风险（同时 3 个任务就是 150MB 常驻）。
        这里边收边写，内存占用是一个 chunk 的大小。

        产物 URL 有效期通常 24 小时，所以拿到就得立刻落盘/落库，不能存 URL。
        """
        if not url:
            raise LLMError("下载地址为空")
        total = 0
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=20.0)) as client:
            async with client.stream("GET", url, follow_redirects=True) as resp:
                if resp.status_code >= 400:
                    raise LLMError(f"下载失败 HTTP {resp.status_code}: {url[:150]}")
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("wb") as f:
                    async for chunk in resp.aiter_bytes(1024 * 256):
                        f.write(chunk)
                        total += len(chunk)
        if not total:
            raise LLMError(f"下载到的文件为空：{url[:150]}")
        logger.info("llm.video.downloaded", bytes=total, path=str(path))
        return total


@dataclass
class VideoTask:
    """视频生成任务的状态快照。

    和 `ImageResult` 的根本差别：生图是一次请求一次结果，视频**没有同步形态**。
    服务商返回的是一个任务 id，产物要再查一次才拿得到，而且产物 URL 通常
    只有 24 小时有效期 —— 拿到就得立刻落库，不能存 URL 当引用。

    `status` 归一成五个值，屏蔽各家的叫法差异（火山 queued/running/succeeded/
    failed/cancelled，其它家 processing/error/success 之类）。
    """

    task_id: str = ""
    status: str = "queued"
    video_url: str = ""
    cover_url: str = ""
    error: str = ""
    model: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    # 已经结束的状态：成功、失败、取消
    TERMINAL = ("succeeded", "failed", "canceled")

    @property
    def done(self) -> bool:
        return self.status in self.TERMINAL

    @property
    def ok(self) -> bool:
        return self.status == "succeeded"


_STATUS_ALIASES = {
    "queued": "queued",
    "pending": "queued",
    "submitted": "queued",
    "running": "running",
    "processing": "running",
    "in_progress": "running",
    "succeeded": "succeeded",
    "success": "succeeded",
    "completed": "succeeded",
    "done": "succeeded",
    "failed": "failed",
    "error": "failed",
    "canceled": "canceled",
    "cancelled": "canceled",
}


def _norm_video_status(raw: str) -> str:
    return _STATUS_ALIASES.get(str(raw or "").strip().lower(), "running")


def _video_task_from(data: dict[str, Any]) -> VideoTask:
    """把服务商响应归一成 VideoTask。

    火山把产物放在 `content.video_url`，失败原因在 `error.message`；
    有些网关会直接给顶层 `video_url` / `url`。三种都试，都不改响应原文 ——
    原文留在 `raw` 里，出问题能一眼看到服务商到底回了什么。
    """
    content = data.get("content") if isinstance(data.get("content"), dict) else {}
    err = data.get("error") if isinstance(data.get("error"), dict) else {}
    video_url = (
        content.get("video_url")
        or content.get("url")
        or data.get("video_url")
        or data.get("url")
        or ""
    )
    cover_url = content.get("cover_url") or content.get("poster_url") or data.get("cover_url") or ""
    return VideoTask(
        task_id=str(data.get("id") or data.get("task_id") or ""),
        status=_norm_video_status(data.get("status")),
        video_url=str(video_url or ""),
        cover_url=str(cover_url or ""),
        error=str(err.get("message") or data.get("message") or data.get("error_message") or ""),
        model=str(data.get("model") or ""),
        raw=data,
    )


def _fmt_video_prompt(
    prompt: str,
    *,
    ratio: str | None,
    duration: int | None,
    resolution: str | None,
    watermark: bool | None,
    camera_fixed: bool | None,
) -> str:
    """把参数拼成火山要求的 `--key value` 尾巴。

    为什么不用顶层 JSON 字段：火山 Seedance 只认文本里的 `--ratio` 这类指令，
    顶层多塞 `ratio` / `duration` 会直接 400 UnknownParameter。所以参数
    必须并进 prompt，代价是 prompt 里不能出现形如 `--xxx` 的正文。
    """
    parts = [prompt.strip()]
    if ratio:
        parts.append(f"--ratio {ratio}")
    if duration:
        parts.append(f"--duration {int(duration)}")
    if resolution:
        parts.append(f"--resolution {resolution}")
    if watermark is not None:
        parts.append(f"--watermark {'true' if watermark else 'false'}")
    if camera_fixed is not None:
        parts.append(f"--camerafixed {'true' if camera_fixed else 'false'}")
    return " ".join(p for p in parts if p)


@dataclass
class ImageResult:
    """图片生成结果。

    服务商两种返回习惯：给 URL（多数）或给 b64_json（部分国内服务）。
    这里两个都留着，调用方按需取，不做隐式转换。
    """

    urls: list[str] = field(default_factory=list)
    b64: list[str] = field(default_factory=list)
    revised_prompt: str = ""
    model: str = ""
    latency_ms: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not self.urls and not self.b64


def _to_image_url(src: str) -> str:
    """把图片引用归一成 OpenAI 接受的 image_url。

    支持三种形式：http(s) URL、data: URI、本地文件路径（读出来转 base64）。
    """
    text = (src or "").strip()
    if not text:
        raise LLMError("图片引用为空")
    if text.startswith(("http://", "https://", "data:")):
        return text

    path = Path(text)
    if not path.is_file():
        raise LLMError(f"图片既不是 URL 也不存在于本地：{text[:120]}")
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


class _RetryableError(Exception):
    """内部标记：该错误值得重试"""


# --------------------------------------------------------------------------
# 单例
# --------------------------------------------------------------------------
_llm: LLMClient | None = None
# 按能力缓存的客户端。key = "<capability>:<密钥指纹>"——指纹进 key 是为了让
# 「后台换了密钥」这件事能自动失效旧连接池，否则新 key 永远不生效，很容易踩。
_cap_clients: dict[str, LLMClient] = {}


def get_llm_for(capability: str) -> LLMClient:
    """按能力取客户端（chat / embedding / vision / image ...）。

    配置来源由 registry 决定：后台可视化配置优先，其次是 .env。
    未配置时抛 LLMNotConfiguredError，让上层降级而不是 500。
    """
    from cenkor_admin.apps.cms.ai.registry import get_endpoint

    ep = get_endpoint(capability)
    if ep is None:
        raise LLMNotConfiguredError(
            f"能力「{capability}」尚未配置：请在后台 AI 设置里绑定服务商与模型"
        )

    fingerprint = hashlib.sha256((ep.api_key or "").encode("utf-8")).hexdigest()[:10]
    sig = f"{capability}:{fingerprint}"
    cached = _cap_clients.get(sig)
    if cached is not None:
        return cached

    # 配置变了：先关掉该能力下的旧客户端，否则换几次 key 就攒几个连接池
    for stale in [k for k in _cap_clients if k.startswith(f"{capability}:")]:
        old = _cap_clients.pop(stale)
        try:
            asyncio.get_running_loop().create_task(old.aclose())
        except RuntimeError:
            # 同步上下文（脚本/CLI）里没法 await，交给 GC
            pass

    client = LLMClient(
        base_url=ep.base_url,
        api_key=ep.api_key,
        chat_model=ep.model,
        embed_model=ep.model if capability == "embedding" else "",
        provider=ep.kind or "openai",
        timeout=ep.timeout,
        max_retries=ep.max_retries,
        temperature=float(ep.params.get("temperature", 0.3)),
        extra_headers=ep.extra_headers,
        embed_params=ep.params if capability == "embedding" else None,
    )
    _cap_clients[sig] = client
    logger.debug("llm.client_built", capability=capability, model=ep.model, source=ep.source)
    return client


def get_llm() -> LLMClient:
    """取对话能力客户端（保留旧签名，大量既有代码直接调用）。

    有后台/环境变量配置时走 get_llm_for("chat")；全都没有时仍返回一个
    按 .env 构造的实例，让调用方在真正发请求时收到明确的「未配置」错误，
    而不是在取值这一步就炸。
    """
    global _llm
    from cenkor_admin.apps.cms.ai.registry import get_endpoint

    if get_endpoint("chat") is not None:
        return get_llm_for("chat")

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
            embed_base_url=getattr(s, "AI_EMBED_BASE_URL", "") or "",
            embed_api_key=getattr(s, "AI_EMBED_API_KEY", "") or "",
        )
    return _llm


def ai_enabled() -> bool:
    """是否有任一能力可用。后台配置或 .env 任一成立即为真。"""
    from cenkor_admin.apps.cms.ai.registry import available_capabilities

    if available_capabilities():
        return True
    # registry 还没预热（例如启动早期）时回退旧判断
    s = get_settings()
    return bool(getattr(s, "AI_ENABLED", False)) and bool(getattr(s, "AI_API_KEY", ""))


async def close_llm() -> None:
    """应用关闭时释放全部连接池。"""
    global _llm
    if _llm is not None:
        await _llm.aclose()
        _llm = None
    for key in list(_cap_clients):
        client = _cap_clients.pop(key)
        await client.aclose()
