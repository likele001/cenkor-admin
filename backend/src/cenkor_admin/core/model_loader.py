"""把全部 app 的 ORM 模型并入 `Base.metadata`。

`alembic/env.py`（真正跑迁移）和 `scripts/check_schema_drift.py`（体检）都必须用
**同一份**加载逻辑。两边各写一遍的话，迟早出现「体检说表都在、autogenerate 却要
drop 一批」的情况，比不做检查更误导。

为什么这件事值得单独成模块：少加载一个 app，autogenerate 就会把那个 app 的全部表
判成「库里多出来的表」并生成 `drop_table`。2026-10 就是这样差点删库 ——
`erp/models.py` 其实是包目录，旧循环只认单文件 `models.py`，ERP 74 张表从未进过
metadata，一次 autogenerate 生成 101 个 drop_table。
"""
from __future__ import annotations

import importlib
import os
import pkgutil
import sys

# 文件名不叫 models 的模型模块，必须显式登记
EXTRA_MODEL_MODULES = (
    # 应用商店：app_developers / app_submissions / app_intros
    "cenkor_admin.apps.system.store_models",
)

# 递归扫描时要跳过的子包：routers/ 下也有 models.py，但那是 API 层定义，
# 且常与真模型重名（crm/routers/models.py 就有 crm_customers），
# 加载会抛 "Table 'xxx' is already defined for this MetaData instance"。
_SKIP_SEGMENTS = ("routers", "tests", "schemas")


def apps_dirs() -> tuple[str, str | None]:
    """返回 (内置 apps 目录, 外置 apps 目录或 None)。"""
    import cenkor_admin.apps as _apps_pkg  # 触发 __init__.py 把外置目录挂进 __path__

    apps_dir = os.path.dirname(_apps_pkg.__file__)
    ext_dir = os.path.join(os.path.dirname(os.path.dirname(apps_dir)), "apps")
    return apps_dir, (ext_dir if os.path.isdir(ext_dir) else None)


def _load_one_dir(base_dir: str, pkg_prefix: str) -> list[str]:
    failed: list[str] = []
    for name in sorted(os.listdir(base_dir)):
        if name.startswith("_"):
            continue
        appdir = os.path.join(base_dir, name)
        if not os.path.isdir(appdir):
            continue

        mods: list[str] = []
        if os.path.isfile(os.path.join(appdir, "models.py")) or \
                os.path.isfile(os.path.join(appdir, "models", "__init__.py")):
            mods.append(f"{pkg_prefix}.{name}.models")

        for mi in pkgutil.walk_packages([appdir], prefix=f"{pkg_prefix}.{name}."):
            if any(seg in _SKIP_SEGMENTS for seg in mi.name.split(".")):
                continue
            if (mi.name.endswith(".models") or ".models." in mi.name) and mi.name not in mods:
                mods.append(mi.name)

        for m in mods:
            try:
                importlib.import_module(m)
            except Exception as e:
                failed.append(f"{m}: {type(e).__name__}: {e}")
    return failed


def load_all_models(verbose: bool = False) -> list[str]:
    """加载内置 + 外置 app 的全部模型。

    返回加载失败的模块清单（空 = 全部成功）。
    `verbose=True` 时把失败原因打到 stderr —— env.py 用这个，
    否则「少加载了」会完全静默，正是它把上次的事故藏了一个月。
    """
    apps_dir, ext_dir = apps_dirs()
    failed = _load_one_dir(apps_dir, "cenkor_admin.apps")
    if ext_dir:
        failed += _load_one_dir(ext_dir, "cenkor_admin.apps")

    for m in EXTRA_MODEL_MODULES:
        try:
            importlib.import_module(m)
        except Exception as e:
            failed.append(f"{m}: {type(e).__name__}: {e}")

    if verbose:
        for f in failed:
            print(f"[models] 加载失败 {f}", file=sys.stderr)
    return failed
