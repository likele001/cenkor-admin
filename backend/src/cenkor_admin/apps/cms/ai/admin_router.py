"""AI 配置管理 API · 后台可视化配置的后端。

覆盖三件事：
1. **服务商**的增删改查（base_url / 密钥 / 超时 / 重试 / 自定义头）
2. **能力绑定**：chat / embedding / vision / image / rerank / asr / tts
   各自绑到哪个服务商的哪个模型、带什么参数
3. **连通性测试**：真的发一次最小请求，把「配了但连不上」在界面上暴露出来

两条安全约定：
- 密钥出接口永远只有掩码（``****a1b2``），编辑时原样回传掩码等于「不修改」
- 读要 ``cms:ai:read``，写要 ``cms:ai:manage``；超管自动放行
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import get_current_user, require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms.ai import registry
from cenkor_admin.apps.cms.ai.models import CmsAiCapability, CmsAiProvider
from cenkor_admin.apps.cms.ai.registry import CAPABILITIES, PARAM_SPECS, sanitize_params
from cenkor_admin.core.config import get_settings
from cenkor_admin.core.db import get_db
from cenkor_admin.core.llm import LLMClient, LLMError
from cenkor_admin.core.secrets import (
    decrypt_secret,
    encrypt_secret,
    is_masked_input,
    secret_hint,
)

router = APIRouter(tags=["cms-ai-admin"])

_READ = Depends(require_permission("cms:ai:read"))
_WRITE = Depends(require_permission("cms:ai:manage"))


# ---------------------------------------------------------------- 内置预设

# 前端「添加服务商」时一键填充。只填 base_url 与推荐模型，
# 密钥永远由用户自己填——把 key 写进代码是任何情况下都不该做的事。
PRESETS: list[dict[str, Any]] = [
    {
        "slug": "openai",
        "name": "OpenAI",
        "kind": "openai",
        "base_url": "https://api.openai.com/v1",
        "models": {
            "chat": "gpt-4o-mini",
            "embedding": "text-embedding-3-small",
            "vision": "gpt-4o-mini",
            "image": "gpt-image-1",
        },
        "note": "能力最全，需外网可达",
    },
    {
        "slug": "dashscope",
        "name": "阿里通义 DashScope",
        "kind": "openai",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": {
            "chat": "qwen-plus",
            "embedding": "text-embedding-v3",
            "vision": "qwen-vl-plus",
            "image": "wanx2.1-t2i-turbo",
        },
        "note": "国内直连，chat 与 embedding 都全",
    },
    {
        "slug": "deepseek",
        "name": "DeepSeek",
        "kind": "openai",
        "base_url": "https://api.deepseek.com/v1",
        "models": {"chat": "deepseek-chat"},
        "note": "只有对话，无 embedding / 视觉 / 出图",
    },
    {
        "slug": "moonshot",
        "name": "Moonshot Kimi",
        "kind": "openai",
        "base_url": "https://api.moonshot.cn/v1",
        "models": {"chat": "moonshot-v1-8k", "vision": "moonshot-v1-8k-vision-preview"},
        "note": "长文本强，无 embedding",
    },
    {
        "slug": "zhipu",
        "name": "智谱 GLM",
        "kind": "openai",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": {
            "chat": "glm-4-flash",
            "embedding": "embedding-3",
            "vision": "glm-4v-flash",
            "image": "cogview-3-flash",
        },
        "note": "全能力覆盖，有免费档",
    },
    {
        "slug": "siliconflow",
        "name": "硅基流动 SiliconFlow",
        "kind": "openai",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": {
            "chat": "Qwen/Qwen2.5-72B-Instruct",
            "embedding": "BAAI/bge-m3",
            "vision": "Qwen/Qwen2-VL-72B-Instruct",
            "image": "Kwai-Kolors/Kolors",
        },
        "note": "一个 key 覆盖 chat/embedding/视觉/出图，性价比高",
    },
    {
        "slug": "ollama",
        "name": "本地 Ollama",
        "kind": "openai",
        "base_url": "http://127.0.0.1:11434/v1",
        "models": {"chat": "qwen2.5:7b", "embedding": "bge-m3", "vision": "llava"},
        "note": "无需密钥，数据不出机器",
    },
]


# ---------------------------------------------------------------- 载荷


class ProviderIn(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=80)
    kind: str = Field(default="openai", max_length=32)
    base_url: str = Field(min_length=1, max_length=400)
    # 新建时必填；更新时留空或传掩码串表示「不修改」
    api_key: str = ""
    extra_headers: dict[str, str] | None = None
    timeout_seconds: int = Field(default=60, ge=5, le=600)
    max_retries: int = Field(default=2, ge=0, le=5)
    enabled: bool = True
    remark: str | None = Field(default=None, max_length=255)


class ProviderPatch(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    kind: str | None = Field(default=None, max_length=32)
    base_url: str | None = Field(default=None, max_length=400)
    api_key: str | None = None
    extra_headers: dict[str, str] | None = None
    timeout_seconds: int | None = Field(default=None, ge=5, le=600)
    max_retries: int | None = Field(default=None, ge=0, le=5)
    enabled: bool | None = None
    remark: str | None = Field(default=None, max_length=255)


class CapabilityIn(BaseModel):
    provider_id: int
    model: str = Field(min_length=1, max_length=160)
    params: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


# ---------------------------------------------------------------- 工具


def _norm_base(url: str) -> str:
    text = (url or "").strip().rstrip("/")
    if not text.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="base_url 必须以 http:// 或 https:// 开头",
        )
    # 常见错填：把完整端点点进来了（.../v1/chat/completions）
    for suffix in ("/chat/completions", "/embeddings", "/images/generations"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    return text


async def _provider_out(db: AsyncSession, row: CmsAiProvider) -> dict[str, Any]:
    bound = await db.execute(
        select(CmsAiCapability.capability).where(CmsAiCapability.provider_id == row.id)
    )
    caps = list(bound.scalars().all())
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "kind": row.kind,
        "base_url": row.base_url,
        "api_key_hint": row.api_key_hint or ("****已配置" if row.api_key_enc else ""),
        "has_api_key": bool(row.api_key_enc),
        "extra_headers": row.extra_headers or {},
        "timeout_seconds": row.timeout_seconds,
        "max_retries": row.max_retries,
        "enabled": row.enabled,
        "remark": row.remark,
        "is_builtin": row.is_builtin,
        "bound_capabilities": caps,
        "last_test_at": row.last_test_at.isoformat() if row.last_test_at else None,
        "last_test_ok": row.last_test_ok,
        "last_test_error": row.last_test_error,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _make_client(row: CmsAiProvider, model: str, timeout: float | None = None) -> LLMClient:
    key = decrypt_secret(row.api_key_enc)
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该服务商的密钥无法解密（SECRET_KEY 可能已变更），请重新填写密钥",
        )
    return LLMClient(
        base_url=row.base_url,
        api_key=key,
        chat_model=model,
        embed_model=model,
        provider=row.kind or "openai",
        timeout=timeout or float(row.timeout_seconds or 60),
        max_retries=0,  # 测试要立刻看到结果，不重试
        extra_headers=dict(row.extra_headers or {}),
    )


# ---------------------------------------------------------------- 总览


@router.get("/overview", summary="AI 配置总览", dependencies=[_READ])
async def overview(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    reg = await registry.load(db, force=True)
    settings = get_settings()

    provider_count = (
        await db.execute(select(func.count()).select_from(CmsAiProvider))
    ).scalar() or 0
    enabled_count = (
        await db.execute(
            select(func.count()).select_from(CmsAiProvider).where(CmsAiProvider.enabled.is_(True))
        )
    ).scalar() or 0

    caps = []
    for spec in CAPABILITIES:
        ep = reg.endpoint(spec.key)
        caps.append(
            {
                "key": spec.key,
                "label": spec.label,
                "hint": spec.hint,
                "wired": spec.wired,
                "ready": ep is not None,
                "source": ep.source if ep else "none",
                "provider_name": ep.provider_name if ep else "",
                "model": ep.model if ep else "",
            }
        )

    return {
        "ready": any(c["ready"] for c in caps),
        "providers": {"total": provider_count, "enabled": enabled_count},
        "capabilities": caps,
        "env_fallback": {
            "AI_ENABLED": bool(getattr(settings, "AI_ENABLED", False)),
            "has_key": bool(getattr(settings, "AI_API_KEY", "")),
            "note": "后台未配置的能力会自动回退到 .env；后台一旦绑定就以后台为准",
        },
        "registry_error": reg.last_error,
    }


@router.get("/presets", summary="内置服务商预设", dependencies=[_READ])
async def presets() -> list[dict[str, Any]]:
    return PRESETS


# ---------------------------------------------------------------- 服务商


@router.get("/providers", summary="服务商列表", dependencies=[_READ])
async def list_providers(db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    rows = (await db.execute(select(CmsAiProvider).order_by(CmsAiProvider.id))).scalars().all()
    return [await _provider_out(db, row) for row in rows]


@router.post("/providers", status_code=status.HTTP_201_CREATED, summary="新增服务商")
async def create_provider(
    payload: ProviderIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
    _: Any = _WRITE,
) -> dict[str, Any]:
    slug = payload.slug.strip().lower()
    exists = (await db.execute(select(CmsAiProvider.id).where(CmsAiProvider.slug == slug))).first()
    if exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"标识 {slug} 已存在，请换一个"
        )

    row = CmsAiProvider(
        slug=slug,
        name=payload.name.strip(),
        kind=(payload.kind or "openai").strip(),
        base_url=_norm_base(payload.base_url),
        api_key_enc=encrypt_secret(payload.api_key),
        api_key_hint=secret_hint(payload.api_key),
        extra_headers=payload.extra_headers or None,
        timeout_seconds=payload.timeout_seconds,
        max_retries=payload.max_retries,
        enabled=payload.enabled,
        remark=payload.remark,
        updated_by=user.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await registry.load(db, force=True)
    return await _provider_out(db, row)


@router.patch("/providers/{provider_id}", summary="修改服务商")
async def update_provider(
    provider_id: int,
    payload: ProviderPatch,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
    _: Any = _WRITE,
) -> dict[str, Any]:
    row = await db.get(CmsAiProvider, provider_id)
    if row is None:
        raise HTTPException(status_code=404, detail="服务商不存在")

    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.kind is not None:
        row.kind = payload.kind.strip() or "openai"
    if payload.base_url is not None:
        row.base_url = _norm_base(payload.base_url)
    if payload.extra_headers is not None:
        row.extra_headers = payload.extra_headers or None
    if payload.timeout_seconds is not None:
        row.timeout_seconds = payload.timeout_seconds
    if payload.max_retries is not None:
        row.max_retries = payload.max_retries
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.remark is not None:
        row.remark = payload.remark

    # 密钥：留空或回传掩码串 = 不修改。这个判断必须在前端拿到 hint 之后再存，
    # 否则「编辑其他字段」会顺手把密钥覆盖成 ****a1b2，服务直接不可用。
    if (
        payload.api_key is not None
        and payload.api_key != ""
        and not is_masked_input(payload.api_key)
    ):
        row.api_key_enc = encrypt_secret(payload.api_key)
        row.api_key_hint = secret_hint(payload.api_key)

    row.updated_by = user.id
    await db.commit()
    await db.refresh(row)
    await registry.load(db, force=True)
    return await _provider_out(db, row)


@router.delete("/providers/{provider_id}", summary="删除服务商")
async def delete_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
    _: Any = _WRITE,
) -> dict[str, Any]:
    row = await db.get(CmsAiProvider, provider_id)
    if row is None:
        raise HTTPException(status_code=404, detail="服务商不存在")

    bound = (
        (
            await db.execute(
                select(CmsAiCapability.capability).where(CmsAiCapability.provider_id == provider_id)
            )
        )
        .scalars()
        .all()
    )
    if bound:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"该服务商仍被这些能力使用：{'、'.join(bound)}。请先解绑或改绑再删除",
        )

    await db.delete(row)
    await db.commit()
    await registry.load(db, force=True)
    return {"ok": True, "deleted": provider_id}


@router.post("/providers/{provider_id}/test", summary="测试服务商连通性")
async def test_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
    _: Any = _WRITE,
) -> dict[str, Any]:
    """两级探测：先拉模型列表（便宜且不消耗 token），失败再发一次最小对话。

    只测「通不通」，不测「模型好不好」——后者交给能力测试。
    """
    row = await db.get(CmsAiProvider, provider_id)
    if row is None:
        raise HTTPException(status_code=404, detail="服务商不存在")
    if not row.api_key_enc:
        raise HTTPException(status_code=400, detail="该服务商尚未填写密钥")

    ok = False
    detail = ""
    models: list[str] = []
    latency_ms = 0

    key = decrypt_secret(row.api_key_enc)
    if key is None:
        raise HTTPException(status_code=409, detail="密钥无法解密，请重新填写")

    started = time.monotonic()
    try:
        headers = {"Authorization": f"Bearer {key}", **dict(row.extra_headers or {})}
        async with httpx.AsyncClient(
            base_url=row.base_url, timeout=httpx.Timeout(15.0, connect=8.0), headers=headers
        ) as http:
            resp = await http.get("/models")
        latency_ms = int((time.monotonic() - started) * 1000)
        if resp.status_code == 200:
            body = resp.json()
            items = body.get("data") if isinstance(body, dict) else None
            if isinstance(items, list):
                models = [
                    str(it.get("id")) for it in items if isinstance(it, dict) and it.get("id")
                ][:400]
            ok = True
            detail = f"连接正常，可见 {len(models)} 个模型" if models else "连接正常"
        else:
            detail = f"/models 返回 HTTP {resp.status_code}：{resp.text[:200]}"
    except Exception as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        detail = f"网络不可达：{type(exc).__name__}: {str(exc)[:180]}"

    # /models 不一定实现，退回最小对话探测
    if not ok:
        try:
            client = _make_client(row, model="probe", timeout=20.0)
            # 模型名未知时用该服务商任一能力绑定的模型；都没有就跳过对话探测
            probe_model = ""
            cap_row = (
                (
                    await db.execute(
                        select(CmsAiCapability).where(CmsAiCapability.provider_id == provider_id)
                    )
                )
                .scalars()
                .first()
            )
            if cap_row and cap_row.model:
                probe_model = cap_row.model
            if probe_model:
                started = time.monotonic()
                result = await client.chat(
                    [{"role": "user", "content": "ping"}], model=probe_model, max_tokens=4
                )
                latency_ms = int((time.monotonic() - started) * 1000)
                ok = True
                detail = f"对话接口正常（{result.model}）"
            else:
                detail += "；未绑定模型，无法做对话探测"
            await client.aclose()
        except (LLMError, HTTPException) as exc:
            detail += f"；对话探测失败：{str(exc)[:180]}"
        except Exception as exc:  # pragma: no cover
            detail += f"；对话探测异常：{type(exc).__name__}: {str(exc)[:150]}"

    row.last_test_at = datetime.now(UTC)
    row.last_test_ok = ok
    row.last_test_error = None if ok else detail[:1000]
    await db.commit()

    return {"ok": ok, "detail": detail, "latency_ms": latency_ms, "models": models}


# ---------------------------------------------------------------- 能力绑定


@router.get("/capabilities", summary="能力绑定总览", dependencies=[_READ])
async def list_capabilities(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    # 返回 {capabilities: [...], providers: [...]} 而不是裸列表：
    # 前端绑定卡片同时需要「可选服务商下拉」。此前注解写成 list[...] 而实际返回
    # dict，FastAPI 拿注解当 response_model 校验，直接 500（响应体校验失败）。
    rows = (await db.execute(select(CmsAiCapability))).scalars().all()
    by_cap = {row.capability: row for row in rows}
    reg = await registry.load(db)

    providers = (await db.execute(select(CmsAiProvider).order_by(CmsAiProvider.id))).scalars().all()

    out: list[dict[str, Any]] = []
    for spec in CAPABILITIES:
        row = by_cap.get(spec.key)
        ep = reg.endpoint(spec.key)
        specs = PARAM_SPECS.get(spec.key, {})
        out.append(
            {
                "key": spec.key,
                "label": spec.label,
                "hint": spec.hint,
                "wired": spec.wired,
                "param_specs": [
                    {
                        "key": pkey,
                        "type": pspec.type,
                        "min": pspec.lo,
                        "max": pspec.hi,
                        "enum": list(pspec.enum),
                    }
                    for pkey, pspec in specs.items()
                ],
                "binding": (
                    {
                        "provider_id": row.provider_id,
                        "model": row.model,
                        "params": row.params or {},
                        "enabled": row.enabled,
                        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    }
                    if row
                    else None
                ),
                "effective": (
                    {
                        "source": ep.source,
                        "provider_name": ep.provider_name,
                        "model": ep.model,
                        "params": ep.params,
                    }
                    if ep
                    else None
                ),
            }
        )

    return {
        "capabilities": out,
        "providers": [
            {
                "id": p.id,
                "slug": p.slug,
                "name": p.name,
                "enabled": p.enabled,
                "has_api_key": bool(p.api_key_enc),
            }
            for p in providers
        ],
    }


@router.put("/capabilities/{capability}", summary="绑定/更新能力")
async def upsert_capability(
    capability: str,
    payload: CapabilityIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
    _: Any = _WRITE,
) -> dict[str, Any]:
    if capability not in registry.CAPABILITY_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"未知能力 {capability}，可选：{'、'.join(registry.CAPABILITY_KEYS)}",
        )
    prov = await db.get(CmsAiProvider, payload.provider_id)
    if prov is None:
        raise HTTPException(status_code=404, detail="服务商不存在")
    if not prov.enabled:
        raise HTTPException(status_code=400, detail="该服务商已停用，请先启用")

    params = sanitize_params(capability, payload.params)
    row = await db.get(CmsAiCapability, capability)
    if row is None:
        row = CmsAiCapability(capability=capability)
        db.add(row)

    row.provider_id = payload.provider_id
    row.model = payload.model.strip()
    row.params = params or None
    row.enabled = payload.enabled
    row.updated_by = user.id

    await db.commit()
    await registry.load(db, force=True)
    await db.refresh(row)
    return {
        "capability": row.capability,
        "provider_id": row.provider_id,
        "model": row.model,
        "params": row.params or {},
        "enabled": row.enabled,
    }


@router.delete("/capabilities/{capability}", summary="解绑能力")
async def delete_capability(
    capability: str,
    db: AsyncSession = Depends(get_db),
    _: Any = _WRITE,
) -> dict[str, Any]:
    row = await db.get(CmsAiCapability, capability)
    if row is None:
        raise HTTPException(status_code=404, detail="该能力未绑定")
    await db.delete(row)
    await db.commit()
    await registry.load(db, force=True)
    return {"ok": True, "capability": capability}


@router.post("/capabilities/{capability}/test", summary="按绑定关系实测能力")
async def test_capability(
    capability: str,
    db: AsyncSession = Depends(get_db),
    _: Any = _WRITE,
) -> dict[str, Any]:
    """按真实调用链测一次。参数从绑定里读，测的就是线上实际会走的路径。"""
    reg = await registry.load(db, force=True)
    ep = reg.endpoint(capability)
    if ep is None:
        raise HTTPException(status_code=400, detail=f"能力「{capability}」尚未绑定可用的服务商")

    spec = registry.CAPABILITY_MAP[capability]
    if not spec.wired:
        return {
            "ok": False,
            "detail": f"{spec.label} 尚未接入调用链，配置已保存但暂不可测",
            "latency_ms": 0,
            "result": None,
        }

    client = LLMClient(
        base_url=ep.base_url,
        api_key=ep.api_key,
        chat_model=ep.model,
        embed_model=ep.model if capability == "embedding" else "",
        provider=ep.kind or "openai",
        timeout=min(ep.timeout, 30.0),
        max_retries=0,
        temperature=float(ep.params.get("temperature", 0.3)),
        extra_headers=ep.extra_headers,
    )

    started = time.monotonic()
    try:
        if capability == "chat":
            r = await client.chat(
                [{"role": "user", "content": "用两个字回答：收到"}],
                max_tokens=int(ep.params.get("max_tokens", 32)),
            )
            result: Any = {"text": r.text[:200], "model": r.model, "tokens": r.usage.total_tokens}
        elif capability == "embedding":
            vec = await client.embed_one("连通性测试")
            result = {"dim": len(vec), "model": ep.model, "preview": vec[:3]}
        elif capability == "vision":
            # 1x1 透明 PNG，只验证多模态通道能不能走通
            pixel = (
                "data:image/png;base64,"
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8AAAwAB"
                "Af4B9xyB4QAAAABJRU5ErkJggg=="
            )
            r = await client.vision_chat(
                "这张图是什么颜色？只回答颜色。",
                [pixel],
                detail=str(ep.params.get("detail", "low")),
                max_tokens=int(ep.params.get("max_tokens", 32)),
            )
            result = {"text": r.text[:200], "model": r.model}
        elif capability == "image":
            r = await client.generate_image(
                "一个纯红色圆点，白色背景，极简",
                size=ep.params.get("size"),
                quality=ep.params.get("quality"),
                n=1,
            )
            if r.empty:
                raise LLMError("返回里既没有 url 也没有 b64_json")
            result = {
                "urls": r.urls[:2],
                "has_b64": bool(r.b64),
                "model": r.model,
                "revised_prompt": r.revised_prompt[:120],
            }
        else:  # pragma: no cover - 未来能力
            raise LLMError(f"能力 {capability} 暂无测试实现")
    except Exception as exc:  # 提供商侧什么都可能抛，统一转成可读结果
        await client.aclose()
        return {
            "ok": False,
            "detail": f"{type(exc).__name__}: {str(exc)[:400]}",
            "latency_ms": int((time.monotonic() - started) * 1000),
            "result": None,
        }

    latency = int((time.monotonic() - started) * 1000)
    await client.aclose()
    return {"ok": True, "detail": "调用成功", "latency_ms": latency, "result": result}
