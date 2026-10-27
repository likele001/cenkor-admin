"""Hub 审核校验用例：manifest v2 的静态闸门。

覆盖 ``store_router.validate_manifest_v2`` 与 ``manifest_is_v2``——审核页与
``submit_app`` 共用这两个函数，写错了必须在 400 阶段挡住，而不是等客户实例
装到一半才炸。断言只依赖纯函数，不连库、不起服务。

说明：``store_router`` 在模块级 import 了 structlog / jose / passlib 等第三方库，
本文件只关心其中的纯校验函数，因此对「当前环境确实没装」的可选依赖做最小桩，
让这组用例在精简环境（只有 fastapi + sqlalchemy）里也能跑。
"""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class _Stub(types.ModuleType):
    """占位模块：任意属性再取还是占位模块，可被调用/继承。"""

    def __getattr__(self, name: str):
        if name.startswith("__"):
            raise AttributeError(name)
        mod = _Stub(f"{self.__name__}.{name}")
        setattr(self, name, mod)
        return mod

    def __call__(self, *args, **kwargs):
        return _Stub(self.__name__)


def _import_store_router():
    """导入 store_router；缺失的可选依赖按需打桩（已安装时走真实实现）。"""
    for _ in range(40):
        try:
            return importlib.import_module("cenkor_admin.apps.system.store_router")
        except ModuleNotFoundError as e:
            name = e.name or ""
            # 只桩可选的第三方库；自家包缺失说明路径不对，必须真报错
            if not name or name.startswith("cenkor_admin"):
                raise
            sys.modules[name] = _Stub(name)
    raise RuntimeError("store_router 依赖桩超过 40 层，疑似循环导入")


store_router = _import_store_router()
validate_manifest_v2 = store_router.validate_manifest_v2
manifest_is_v2 = store_router.manifest_is_v2


def _good_v2() -> dict:
    return {
        "key": "stock_safety",
        "name": "安全库存预警",
        "version": "1.0.0",
        "schema_version": 1,
        "manifest_version": 2,
        "min_core_version": "2.2.0",
        "product": "cenkormes",
        "dev_method": "extension",
        "permissions": [
            {"code": "ext.stock_safety.view", "name": "查看"},
            {"code": "ext.stock_safety.manage", "name": "管理"},
        ],
        "menus": [
            {"title": "安全库存", "path": "/ext/stock_safety", "permission": "ext.stock_safety.view"},
        ],
        "data": {
            "retention": "keep",
            "tables": [
                {"name": "ext_ss_rules", "mode": "own"},
                {"name": "stocks", "mode": "read"},
            ],
            "files": [],
        },
        "tasks": {"celery": ["stock_safety.scan"], "beat": []},
        "dependencies": [],
    }


def _errors(manifest: dict, app_key: str = "stock_safety") -> list[str]:
    return validate_manifest_v2(app_key, manifest, "cenkormes", "extension")


def test_valid_v2_passes():
    assert _errors(_good_v2()) == []


def test_detects_v2_by_manifest_version_or_schema_version():
    assert manifest_is_v2({"manifest_version": 2}) is True
    assert manifest_is_v2({"schema_version": 1}) is True
    assert manifest_is_v2({"key": "old_style"}) is False


def test_invalid_key_rejected():
    b = _good_v2()
    assert any("key 不符合" in e for e in _errors(b, app_key="StockSafety"))
    assert any("key 不符合" in e for e in _errors(b, app_key="x"))


def test_semver_enforced():
    b = _good_v2()
    b["version"] = "1.0"
    b["min_core_version"] = "v2"
    errs = _errors(b)
    assert any("version 不是 semver" in e for e in errs)
    assert any("min_core_version 不是 semver" in e for e in errs)


def test_schema_version_must_be_positive_int():
    b = _good_v2()
    b["schema_version"] = 0
    assert any("schema_version 必须是 >=1 的整数" in e for e in _errors(b))
    b["schema_version"] = "abc"
    assert any("schema_version 不是整数" in e for e in _errors(b))


def test_product_and_dev_method_must_match_submission():
    b = _good_v2()
    b["product"] = "cenkor-admin"
    b["dev_method"] = "platform"
    errs = validate_manifest_v2("stock_safety", b, "cenkormes", "extension")
    assert any("manifest.product" in e for e in errs)
    assert any("manifest.dev_method" in e for e in errs)


def test_permission_namespace_and_duplicates():
    b = _good_v2()
    b["permissions"] = [
        {"code": "stock_safety.view"},           # 少了 ext.<key>. 前缀
        {"code": "ext.stock_safety.view"},
        {"code": "ext.stock_safety.view"},       # 重复
        {"name": "缺 code"},
    ]
    errs = _errors(b)
    assert any("权限码越界" in e for e in errs)
    assert any("权限码重复" in e for e in errs)
    assert any("permission 缺 code" in e for e in errs)


def test_menu_path_must_be_under_ext_namespace():
    b = _good_v2()
    b["menus"] = [
        {"title": "越界", "path": "/admin/stock", "permission": "ext.stock_safety.view"},
        {"title": "串到别的扩展", "path": "/ext/other_app", "permission": "ext.stock_safety.view"},
        {"title": "权限未声明", "path": "/ext/stock_safety/x", "permission": "ext.stock_safety.nope"},
    ]
    errs = _errors(b)
    assert any("必须以 /ext/ 开头" in e for e in errs)
    assert any("/ext/stock_safety" in e for e in errs)
    assert any("未在 permissions 里声明" in e for e in errs)


def test_data_retention_rejects_purge():
    b = _good_v2()
    b["data"]["retention"] = "purge"
    assert any("只允许 keep/ask" in e for e in _errors(b))


def test_own_table_must_be_ext_prefixed_and_mode_valid():
    b = _good_v2()
    b["data"]["tables"] = [
        {"name": "users", "mode": "own"},        # 核心表不允许声明为 own
        {"name": "ext_ss_rules", "mode": "rw"},      # mode 只允许 own/read/write
        {"name": "ext_ss_rules", "mode": "own"},
        {"name": "ext_ss_rules", "mode": "own"},   # 同一张表声明两次
        {"name": "ext_ss_alerts", "mode": "own"},
        {"name": "bad name", "mode": "own"},      # 表名非法
    ]
    errs = _errors(b)
    assert any("必须以 ext_ 开头" in e for e in errs)
    assert any("只允许 own/read/write" in e for e in errs)
    assert any("自有表重复声明" in e for e in errs)
    assert any("表名非法" in e for e in errs)


def test_dependencies_and_tasks_types():
    b = _good_v2()
    b["dependencies"] = ["OK", {"key": "x"}]
    b["tasks"] = ["stock_safety.scan"]
    errs = _errors(b)
    assert sum("依赖项必须是扩展 key" in e for e in errs) == 2
    assert any("tasks 必须是对象" in e for e in errs)


def test_v1_style_manifest_still_installable_by_host_bypasses_this_gate():
    """v1 包不走 validate_manifest_v2（submit 时按 manifest_is_v2 分流），
    这里只锁住判定口径：没有 manifest_version / schema_version 的老包不被判成 v2，
    避免把存量 29 个包一起挡在门外。"""
    v1 = {"key": "spc_control", "version": "1.0.0", "permissions": [{"code": "ext.spc_control.view"}]}
    assert manifest_is_v2(v1) is False
