"""内置主题（随代码发布，不依赖数据库）

**真正的定义在 ``apps/cms/themes/``**，一个主题一个模块。本文件是门面：
``get_builtin_source`` / ``get_builtin_meta`` / ``list_builtin_themes`` 这些
老接口继续可用，调用方一行都不用改。

三层回落链的中间那一层就是这里：

    磁盘 var/themes/<主题>/  →  DB(cms_templates)  →  内置本主题  →  内置 default

用户没建主题、主题只覆盖了部分文件、模板渲染失败要回退 —— 都落到这一层。

## 新增的两件事

1. ``get_theme_manifest()`` —— 读主题的 ``theme.json``，返回 ``ThemeManifest``。
   渲染时靠它把 ``settings`` 的默认值注入模板（``theme.brand_color`` 这种写法）。
2. ``resolve_settings()`` —— 清单默认值 + 站点覆盖，得到模板里 ``theme`` 对象。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from cenkor_admin.apps.cms import theme_package
from cenkor_admin.apps.cms.themes import DEFAULT_THEME, MANIFESTS, THEMES

__all__ = [
    "BUILTIN_THEMES",
    "DEFAULT_THEME",
    "get_builtin_meta",
    "get_builtin_source",
    "get_theme_manifest",
    "list_builtin_themes",
    "resolve_settings",
]

logger = logging.getLogger(__name__)

# 主题名 → 该主题自有文件。语义是「本主题覆盖了哪些」，不是「完整主题有哪些」。
# 完整文件表要合并 default，由 render.theme_documents() 负责。
BUILTIN_THEMES: dict[str, dict[str, str]] = THEMES


def get_builtin_source(theme: str, path: str) -> str | None:
    """取本主题自带的某个文件。没覆盖返回 None，交给调用方回落 default。"""
    return BUILTIN_THEMES.get(theme or DEFAULT_THEME, {}).get(path)


@lru_cache(maxsize=64)
def get_theme_manifest(theme: str) -> theme_package.ThemeManifest | None:
    """解析主题的 ``theme.json``。

    内置主题的清单在模块里；用户主题的清单在文件表里（导出/导入时跟着走）。
    两者都走同一个解析器，口径不会漂。

    解析失败不让渲染挂掉 —— 清单是元数据，坏了大不了配置项不生效，
    页面照常出。所以这里吞异常并返回 None。
    """
    key = theme or DEFAULT_THEME
    raw = MANIFESTS.get(key)
    if raw is None:
        raw = get_builtin_source(key, theme_package.MANIFEST_NAME)
    if raw is None:
        # 用户主题可能没带清单（旧版导出包），退回到 default 的清单太误导，
        # 给一个空壳：没有 settings，模板里 theme.xxx 就是 undefined。
        return None
    try:
        return theme_package.manifest_from_json(raw, legacy_key=key)
    except ValueError as exc:
        logger.warning("主题 %s 的 theme.json 解析失败：%s", key, exc)
        return None


def get_builtin_meta(theme: str) -> dict[str, Any] | None:
    """主题元信息（老接口）。返回 theme.json 的字典形式。"""
    manifest = get_theme_manifest(theme)
    return manifest.as_dict() if manifest else None


def list_builtin_themes() -> list[str]:
    return list(BUILTIN_THEMES.keys())


def resolve_settings(theme: str, site_settings: dict[str, Any] | None) -> dict[str, Any]:
    """模板里 ``theme`` 对象的最终内容 = 清单默认值 + 站点覆盖。

    没有清单时返回空 dict —— 模板里 ``{{ theme.foo }}`` 会渲染成空串
    （Jinja 默认的 undefined 行为），不会抛错。这是刻意的：主题没声明设置项
    是作者的疏忽，不该让访客看到 500。
    """
    manifest = get_theme_manifest(theme)
    if manifest is None:
        return {}
    return theme_package.resolve_settings(manifest, site_settings)
