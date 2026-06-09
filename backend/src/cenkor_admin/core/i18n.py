"""i18n 工具：检测客户端语言。

- 解析 Accept-Language 头（RFC 7231 简化版）
- 支持语言：zh-CN / en-US（默认 zh-CN）
"""
from __future__ import annotations

from fastapi import Request

SUPPORTED_LOCALES = ("zh-CN", "en-US")
DEFAULT_LOCALE = "zh-CN"


def detect_locale(accept_language: str | None) -> str:
    if not accept_language:
        return DEFAULT_LOCALE
    # 解析 "zh-CN,zh;q=0.9,en;q=0.8"
    parts: list[tuple[str, float]] = []
    for raw in accept_language.split(","):
        raw = raw.strip()
        if not raw:
            continue
        lang, _, q = raw.partition(";q=")
        try:
            weight = float(q) if q else 1.0
        except ValueError:
            weight = 1.0
        parts.append((lang.strip(), weight))
    parts.sort(key=lambda x: -x[1])
    for lang, _ in parts:
        # 精确匹配
        if lang in SUPPORTED_LOCALES:
            return lang
        # 短前缀匹配：zh -> zh-CN
        prefix = lang.split("-")[0].lower()
        for supported in SUPPORTED_LOCALES:
            if supported.lower().startswith(prefix):
                return supported
    return DEFAULT_LOCALE


def get_locale(request: Request) -> str:
    """FastAPI 依赖：拿当前请求的 locale。"""
    return getattr(request.state, "locale", DEFAULT_LOCALE)
