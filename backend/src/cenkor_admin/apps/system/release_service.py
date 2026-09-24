"""核心平台版本检查服务。

角色由配置决定（与 commerce 的 hub/spoke 一致）：
- 中心（hub）：``RELEASE_CHECK_URL`` 与 ``CENKOR_CLOUD_URL`` 均为空 → 以本地 ``release.json`` 为准，
  不联网检查（自己就是最新版来源）。
- 客户实例（spoke）：``RELEASE_CHECK_URL`` 或 ``CENKOR_CLOUD_URL`` 指向官方云 → 拉取
  ``GET {cloud}/api/v1/release/latest`` 与本地 ``APP_VERSION`` 做语义化比较。

结果缓存进 Redis（默认 6h），避免每次进工作台都打中心；网络异常一律降级为
``has_update=False`` 并附带 ``error``，绝不影响平台可用性。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from cenkor_admin import __version__ as CURRENT_VERSION
from cenkor_admin.core.config import get_settings
from cenkor_admin.core.redis import redis_client

log = structlog.get_logger()

_CACHE_KEY = "release:check:latest"

# release.json 随包分发（在 cenkor_admin 包根目录），中心端据此对外声明最新版本
# 本文件位于 cenkor_admin/apps/system/，parents[2] 即 cenkor_admin 包根
_RELEASE_FILE = Path(__file__).resolve().parents[2] / "release.json"


def _ver_tuple(v: str) -> tuple[int, ...]:
    """语义化版本转可比较元组；非数字段按 0 处理，预发布后缀忽略。"""
    core = (v or "").strip().split("+")[0].split("-")[0]
    parts: list[int] = []
    for seg in core.split(".")[:3]:
        num = "".join(ch for ch in seg if ch.isdigit())
        parts.append(int(num) if num else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def load_local_release() -> dict[str, Any]:
    """读取本地 release.json（中心端权威版本清单），缺失时回退到代码版本。"""
    try:
        data = json.loads(_RELEASE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError) as e:
        log.warning("release.local_read_failed", error=str(e))
    return {
        "version": CURRENT_VERSION,
        "channel": "stable",
        "released_at": None,
        "notes": "release.json 缺失，回退到代码版本",
    }


def _hub_base_url() -> str:
    s = get_settings()
    return (s.RELEASE_CHECK_URL or s.CENKOR_CLOUD_URL or "").rstrip("/")


async def _fetch_remote_latest(hub: str) -> dict[str, Any]:
    import httpx

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{hub}/api/v1/release/latest")
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    return data if isinstance(data, dict) else {}


async def check_latest(force: bool = False) -> dict[str, Any]:
    """返回核心版本检查结果，供工作台横幅与 /release/check 使用。"""
    s = get_settings()
    current = s.APP_VERSION or CURRENT_VERSION

    if not s.RELEASE_CHECK_ENABLED:
        return {"enabled": False, "current": current, "has_update": False}

    if not force:
        try:
            cached = await redis_client.get(_CACHE_KEY)
            if cached:
                return json.loads(cached)
        except Exception:  # noqa: BLE001 - Redis 不可用时直接实时查
            pass

    hub = _hub_base_url()
    result: dict[str, Any] = {
        "enabled": True,
        "current": current,
        "latest": None,
        "has_update": False,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "source": "self" if not hub else "hub",
    }

    try:
        if hub:
            latest = await _fetch_remote_latest(hub)
        else:
            # 本机即中心：以本地 release.json 为准
            latest = load_local_release()
        latest_version = str(latest.get("version") or "")
        result["latest"] = latest_version
        result["notes_url"] = latest.get("notes_url")
        result["upgrade_docs"] = latest.get("upgrade_docs")
        result["docker_image"] = latest.get("docker_image")
        result["core_pkg_url"] = latest.get("core_pkg_url")
        result["released_at"] = latest.get("released_at")
        result["has_update"] = bool(
            latest_version and _ver_tuple(latest_version) > _ver_tuple(current)
        )
    except Exception as e:  # noqa: BLE001 - 任何网络/解析异常都降级，不影响可用性
        log.warning("release.check_failed", error=str(e))
        result["error"] = str(e)[:200]

    try:
        await redis_client.setex(_CACHE_KEY, s.RELEASE_CHECK_TTL_HOURS * 3600, json.dumps(result))
    except Exception:  # noqa: BLE001
        pass
    return result


async def warm_cache() -> None:
    """启动时预热一次（best-effort），发现新版本则记日志。"""
    try:
        data = await check_latest(force=True)
        if data.get("has_update"):
            log.info("release.update_available", current=data.get("current"), latest=data.get("latest"))
        else:
            log.info("release.check.ok", current=data.get("current"), latest=data.get("latest"))
    except Exception as e:  # noqa: BLE001
        log.warning("release.warm_failed", error=str(e))
