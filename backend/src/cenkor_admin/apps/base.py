"""App 中心基础类型（V2：支持内容引擎 + 字段定义）"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppManifest:
    """App 元数据描述。

    每个 App 在自己的 manifest.py 里定义一个 MANIFEST 实例，
    启动时由后端扫描 apps/ 目录加载。

    V2 扩展：
    - content_types: 声明本 App 注册的内容类型
    - field_groups: 字段分组模板（tabs）
    - field_definitions: 字段定义（启动时自动注册到 DB）
    - categories_seed: 初始分类（首次安装时种入）
    - public_routes_prefix: 公共 API 路由前缀
    """

    key: str                                       # 唯一标识
    name: str                                      # 显示名
    version: str                                   # semver
    author: str = ""
    description: str = ""
    icon: str = "📦"
    category: str = "system"                       # 分类: business / productivity / content / system / ai
    min_platform_version: str = "0.1.0"
    dependencies: list[str] = field(default_factory=list)
    permissions_required: list[str] = field(default_factory=list)
    menus: list[dict[str, Any]] = field(default_factory=list)

    # ---- 生态收费（P0）----
    # True 时底座会校验授权：未激活 / 过期 / 被吊销一律拦截（HTTP 402）
    license_required: bool = False
    price_model: str = "free"       # free / one_time / seat（试用与订阅已下线）
    price_cents: int = 0            # 建议价（分）；实际以 app_pricing 表为准
    trial_days: int = 0             # 已下线（恒 0），保留字段仅为兼容
    period_days: int = 365          # 授权周期，仅 price_model == "seat" 生效

    # ---- V2 扩展 ----
    content_types: list[dict[str, Any]] = field(default_factory=list)
    field_groups: list[dict[str, Any]] = field(default_factory=list)
    field_definitions: list[dict[str, Any]] = field(default_factory=list)
    categories_seed: list[dict[str, Any]] = field(default_factory=list)
    public_routes_prefix: str = ""

    # ---- 插件框架（M1·P0）----
    # 声明本 App 提供的钩子模块（dotted path），启动时自动 import 并注册其 @hook 处理器。
    # 缺省会尝试 cenkor_admin.apps.{key}.hooks。
    hooks: list[str] = field(default_factory=list)
