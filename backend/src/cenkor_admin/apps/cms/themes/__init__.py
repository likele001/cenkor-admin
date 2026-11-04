"""内置主题集合 —— 一个主题一个模块。

## 组织方式

每个主题模块只导出 ``FILES``（该主题**有差异**的文件）和 ``MANIFEST_JSON``。
完整主题 = ``default`` 基线 + 本主题覆盖，合并动作在 ``builtin_theme._merge``。

这么拆是因为上一版是一个 344 行的 ``builtin_theme.py``，所有模板挤在同一个
文件里。加第二个主题时问题立刻暴露：改 blog 的 CSS 要滚过 corporate 的
500 行，diff 里全是噪声。

## 回落链

``render._make_resolver`` 的顺序是「磁盘 → DB → 本主题内置 → default 内置」。
所以主题模块**只需要写想改的文件** —— 比如 blog 没写 ``detail.html``，
它自动用 default 的。改了 default 的某个 partial，其余主题立刻跟着变，
不用逐份同步。这是「少写文件」的直接收益，也是少出错的原因。

## 加一个官方主题要做什么

1. 新建 ``_<key>.py``，写 ``MANIFEST_JSON`` + ``FILES``（至少 ``assets/style.css``）
2. 在下面 ``_MODULES`` 里登记
3. 跑 ``python scripts/cenkor-theme.py lint --theme <key>``

不需要改 ``builtin_theme.py``，也不需要改任何调用方。
"""

from __future__ import annotations

from typing import Any

from cenkor_admin.apps.cms.themes import _blog, _corporate, _default, _landing

__all__ = ["DEFAULT_THEME", "MANIFESTS", "THEMES", "THEME_MODULES"]

DEFAULT_THEME = "default"

# 登记表。顺序就是后台「新建主题」下拉框的顺序，default 放第一个。
_MODULES: dict[str, Any] = {
    "default": _default,
    "blog": _blog,
    "corporate": _corporate,
    "landing": _landing,
}

# 主题 → 该主题的自有文件（不含 default 回落的那些）
THEMES: dict[str, dict[str, str]] = {key: dict(mod.FILES) for key, mod in _MODULES.items()}

# 主题 → theme.json 原文。解析成 ThemeManifest 的动作交给 theme_package，
# 这里保持原始文本 —— 打包时要把原文原样写回 zip，不能重新序列化
# （重新序列化会丢掉键顺序和作者的换行，diff 里全是噪音）。
MANIFESTS: dict[str, str] = {key: mod.MANIFEST_JSON for key, mod in _MODULES.items()}

THEME_MODULES = tuple(_MODULES)
