"""Cenkor Admin · 业务 App 集合

应用可放在两处，导入路径统一为 `cenkor_admin.apps.<key>`：

1. 内置应用：`cenkor_admin/apps/<key>/`
   随底座开源发布，进版本库。
2. 外置应用：`backend/src/apps/<key>/`
   独立 / 商业应用，已在 .gitignore 中整体排除，不会进公开仓库。

把外置目录追加进包的 ``__path__`` 之后，``import cenkor_admin.apps.<key>``
会在两处自动查找，外置应用因此可以直接使用
``from cenkor_admin.apps.<key> import models`` 这类绝对导入，
写法与内置应用完全一致，也无需为每个应用单独登记忽略规则。

⚠️ 优先级：``__path__`` 是【内置在前、外置在后】，子模块解析取第一个命中，
所以同一个 ``<key>`` 在两处都有目录时是【内置赢】—— 外置那份被静默遮蔽，
改它不会生效（商店安装落盘到内置目录时踩过：旧版副本压住外置新版源码）。
同名双份属于配置错误，自检：``python3 scripts/check-app-shadowing.py``
（已挂 .githooks/pre-commit，商店安装入口也会拒绝造成遮蔽的包）。
"""
from pathlib import Path as _Path

# .../src/cenkor_admin/apps → 上溯三级到 src，再进 apps
_EXTERNAL_APPS_DIR = _Path(__file__).resolve().parent.parent.parent / "apps"

if _EXTERNAL_APPS_DIR.is_dir() and str(_EXTERNAL_APPS_DIR) not in __path__:
    __path__.append(str(_EXTERNAL_APPS_DIR))
