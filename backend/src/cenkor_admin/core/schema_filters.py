"""alembic diff 的过滤规则 —— `alembic/env.py` 与 `scripts/check_schema_drift.py` 共用。

放在 core 而不是 env.py 里，是为了让「体检脚本」和「真正跑迁移的进程」用**同一套**
过滤规则。两边规则一旦漂移，体检报告和 autogenerate 结论就会不一致，比不体检更误导。

两条硬事实（2026-10 排查结论，别随手删）：

1. **视图托管表**：ERP 侧 20 个 `erp_xxx` 在库里是**视图**，透传到 MES 的 `mes_xxx`
   真表。追溯记录要连通「采购收货 → 生产制造 → 销售出货」多段经历，共用一张真表
   + 同名视图兼容最省。ORM 仍按 `erp_xxx` 映射，但库里同名对象是视图，
   autogenerate 会误判成「表缺失 → create_table」。运行时查出视图名一律排除。

2. **无 ORM 的遗留表**：`*_legacy`（改名前的历史备份）、`mes_*` 老结构（已被
   `mesx_*` 取代、但 erp 视图仍指向它们）、只有 DDL 没有 models 的 `inventory_*`。
   这些表代码不再写、历史还要读，既不该被 drop，也不该出现在 diff 里。
"""
from __future__ import annotations

# 库里存在、但已没有任何 ORM 映射的遗留表
LEGACY_UNMAPPED_TABLES = frozenset({
    # ERP 时代建、后被 MES 用 mesx_* 取代的结构；erp_xxx 视图仍映射到这些真表
    "mes_bom_items", "mes_boms", "mes_equip_check_plans", "mes_equip_checks",
    "mes_equip_maintenance_plans", "mes_equip_maintenance_records", "mes_equip_repairs",
    "mes_op_reports", "mes_production_schedules", "mes_qc_defects", "mes_qc_inspections",
    "mes_qc_items", "mes_quality_checks", "mes_routing_steps", "mes_routings",
    "mes_work_order_items",
    # 迁移已建表但模块代码尚未落地（只有 DDL，没有 models）
    "inventory_warehouse", "inventory_location",
    # 只建过表、始终没有 ORM 的附件表
    "erp_attachments",
    # 由 core/app_schema.py 用裸 SQL 维护（无 ORM 模型），不参与 diff
    "app_schema_versions",
})

# 由 App 自带 schema.sql 管理的表前缀（方案 D / 2026-10-27）。
#
# 这些应用的表已从 alembic 主链剥离，改由 apps/<key>/schema.sql 在启动时创建。
# 它们的表**不再参与 alembic diff** —— 要改表结构请改应用目录下的 schema.sql，
# 并发版推进 manifest.version（校验和会变，启动时自动重跑幂等 DDL）。
#
# 代价要说清楚：以后改这些表，autogenerate 不会给任何提示。这是「应用表归应用管」
# 的必然结果，换来的是「基础版只有一个应用的表」。
APP_SCHEMA_PREFIXES = {
    "crm": ("crm_",),
    "erp": ("erp_",),
    "mes": ("mes_", "mesx_"),
}


def is_app_managed_table(name: str) -> bool:
    """该表是否由某个应用的 schema.sql 托管。"""
    for prefixes in APP_SCHEMA_PREFIXES.values():
        if name.startswith(prefixes):
            return True
    return False


# 名字前缀：泄露处置时留下的明文备份表
IGNORED_TABLE_PREFIXES = ("pay_channels_bak",)
# 名字后缀：表重命名前的历史备份
IGNORED_TABLE_SUFFIXES = ("_legacy",)


def is_ignored_table(name: str, view_names: set[str] | frozenset[str] = frozenset()) -> bool:
    """该表名是否应排除在 diff 之外。"""
    if name in LEGACY_UNMAPPED_TABLES or name in view_names:
        return True
    if is_app_managed_table(name):
        return True
    if name.endswith(IGNORED_TABLE_SUFFIXES):
        return True
    return name.startswith(IGNORED_TABLE_PREFIXES)


def make_include_object(
    view_names: set[str] | frozenset[str] = frozenset(),
    scope: set[str] | None = None,
):
    """构造 `include_object`。

    view_names: 当前 schema 的视图名集合（视图托管表要排除）
    scope:      只关心这些表（定向 diff，避开历史漂移噪音）。
                对应环境变量 ``ALEMBIC_SCOPE_TABLES=t1,t2``。
    """

    def include_object(obj, name, type_, reflected, compare_to):
        if type_ == "table":
            if is_ignored_table(name, view_names):
                return False
            if scope and name not in scope:
                return False
        elif scope:
            table_name = getattr(getattr(obj, "table", None), "name", None)
            if table_name and table_name not in scope:
                return False
        return True

    return include_object


def scope_from_env() -> set[str] | None:
    """从环境变量读定向 diff 的表名清单。"""
    import os

    raw = os.environ.get("ALEMBIC_SCOPE_TABLES", "")
    names = {t.strip() for t in raw.split(",") if t.strip()}
    return names or None


def fetch_view_names(connection) -> set[str]:
    """查询当前 schema 的视图名（用于排除视图托管表）。"""
    rows = connection.exec_driver_sql(
        "SELECT table_name FROM information_schema.views "
        "WHERE table_schema = current_schema()"
    )
    return {r[0] for r in rows}
