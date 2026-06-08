"""App 中心基础类型（MVP 阶段：代码级模块化）"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppManifest:
    """App 元数据描述。

    MVP 阶段：每个 App 在自己的 manifest.py 里定义一个 MANIFEST 实例，
    启动时由后端扫描 apps/ 目录加载。
    """

    key: str                                       # 唯一标识
    name: str                                      # 显示名
    version: str                                   # semver
    author: str = ""
    description: str = ""
    icon: str = "📦"
    min_platform_version: str = "0.1.0"
    dependencies: list[str] = field(default_factory=list)
    permissions_required: list[str] = field(default_factory=list)
    menus: list[dict[str, Any]] = field(default_factory=list)
