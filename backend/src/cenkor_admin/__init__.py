"""Cenkor Admin Platform.

版本号单一来源：优先环境变量 APP_VERSION，其次包内 VERSION 文件，最后回退内置常量。
发版时由 scripts/release.sh 统一改写 VERSION 文件，避免多处漂移。
"""
from __future__ import annotations

import os
from pathlib import Path

_FALLBACK_VERSION = "0.1.0"


def _read_version() -> str:
    env = (os.environ.get("APP_VERSION") or "").strip()
    if env:
        return env
    try:
        v = (Path(__file__).resolve().parent / "VERSION").read_text(encoding="utf-8").strip()
        return v or _FALLBACK_VERSION
    except OSError:
        return _FALLBACK_VERSION


__version__ = _read_version()
