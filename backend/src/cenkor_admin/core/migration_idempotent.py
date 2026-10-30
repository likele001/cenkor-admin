"""alembic DDL 的全局幂等层（2026-10-30）

为什么需要
----------
本项目的迁移图是**多条链交织**的结构，不是单线：

    core(29) / erp(19) / crm(6) / mes(9) / commerce(9) / ext(12)

每条链各自有多个「局部 head」，这些局部 head 通过 down_revision **跨目录**挂到
别的链上（例：erp/20260831_0001_erp_init 的 down 指向 ext/20261020_0035_app_publish；
ext/20261027_0100_app_schema 的 down 指向 commerce/20261007_0029_product_commerce）。
全量视图最终合成 1 个 head、1 个 base —— 但**任何按单链推演的算法都会算错**。

这个结构带来一类真实故障：**库结构与 alembic_version 不同步**。
历史上有若干迁移的 DDL 被手工 SQL 补到线上库（见
scripts/apply_app_publish_ddl.py 的事故复盘），版本号没同步推进；加上挂载点
被 codegen/builder.py 的 rebase_closed_chain 反复顺延，版本号落到某个迁移之前。
于是每次启动 alembic 都会重跑那一整串迁移，撞：

    DuplicateColumn: column "schema_version" of relation "app_submissions" already exists
    DuplicateTable: relation "app_orders" already exists

2026-10-30 的 app_submissions.schema_version 就是这个 —— 它在 44 个待跑迁移里
排第 40，前面 39 个因为表已存在而陆续炸掉。

而且状态往往是**混合**的：一部分对象缺、另一部分在。只靠「全有→stamp /
有缺→upgrade」的二分法不够 —— 走 upgrade 一样会撞 DuplicateTable。

正解是让**每个 DDL 操作自己幂等**：执行前查真实库reality，存在就跳过。
这样：
1. 迁移可以安全重跑，版本号漂移到哪都不炸；
2. 空库 / 全新环境不受影响（不存在才执行，行为与原来一致）；
3. 混合状态也能推进 —— 缺的开，不缺的跳过。

判定依据是**真实库结构**（SQLAlchemy inspector），不看 alembic 版本表 ——
版本表本身就是漂移的源头，不能拿它当依据。

实现
----
包装 alembic 的 Operations 类方法。alembic.op 是模块级代理，其实现是
`return _proxy.<name>(*args, **kw)` —— _proxy 是当前 Operations 实例，
所以**替换类方法**即可让所有迁移文件里的 op.xxx 调用都走幂等检查。

只包装「纯 DDL、无副作用」的 6 个方法，不碰 execute()（数据写入必须照常，
否则会静默跳过真实的 INSERT/UPDATE）。

代价：包装会掩盖「列存在但类型/约束不一致」。所以跳过时打 warning，
日志里能看到跳了什么。类型漂移属于另一个问题，由
scripts/check_schema_drift.py 体检负责。
"""
from __future__ import annotations

import inspect
from typing import Any

import sqlalchemy as sa
import structlog
from alembic.operations import Operations

log = structlog.get_logger()

# 只包这些：纯结构变更，且「已存在→跳过」是安全语义
_WRAPPED = (
    "create_table",
    "add_column",
    "create_index",
    "drop_index",
    "create_unique_constraint",
    "drop_constraint",
)

# 原始实现只抓一次，后续重复安装都基于它重建包装（避免套娃）
_ORIGINALS: dict[str, Any] = {}


def _bind(original, args: tuple, kw: dict):
    """按被包装方法的真实签名绑定参数，返回具名参数。

    不能靠猜位置：alembic 各方法的参数形态不一致 ——
    create_table(table_name, *columns) 的 table_name 是仅限关键字（*columns 在后），
    代理层会把它转成 table_name= 关键字传进来；
    add_column(table_name, column) 才是位置传参。
    用 inspect.signature.bind 绑定，位置/关键字都能正确落到名字上。

    original 是未绑定的类方法（签名含 self），绑定时用 None 占位 self。
    """
    sig = inspect.signature(original)
    params = list(sig.parameters.values())
    if params and params[0].name == "self":
        params = params[1:]
        sig = sig.replace(parameters=params)
    return sig.bind(*args, **kw)


class _IdempotentGuard:
    """按真实库结构判断 DDL 是否需要执行。"""

    def __init__(self, conn) -> None:
        self._conn = conn
        self.skipped: list[str] = []
        # 原始实现：由 install_idempotent_ops 填充。
        # 包装层内部要绕过自己调用原始方法，否则无限递归。
        self._originals: dict[str, Any] = {}

    def _table_exists(self, table: str) -> bool:
        """直查 pg_catalog，不用 inspector。

        迁移在同一个连接上连续执行，inspector 的结构缓存不会刷新 ——
        上一个迁移刚建的表，在下一个迁移里查不到。
        """
        try:
            row = self._conn.execute(
                sa.text(
                    "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE c.relname = :t AND n.nspname = current_schema() LIMIT 1"
                ),
                {"t": table},
            ).fetchone()
            return row is not None
        except Exception:
            return False

    def _has_column(self, table: str, column: str) -> bool:
        try:
            row = self._conn.execute(
                sa.text(
                    "SELECT 1 FROM pg_attribute a "
                    "JOIN pg_class c ON c.oid = a.attrelid "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE c.relname = :t AND n.nspname = current_schema() "
                    "AND a.attname = :c AND a.attnum > 0 AND NOT a.attisdropped LIMIT 1"
                ),
                {"t": table, "c": column},
            ).fetchone()
            return row is not None
        except Exception:
            return False

    def _has_index(self, index: str) -> bool:
        return self._index_def(index) is not None

    def _index_def(self, index: str) -> tuple[bool, tuple[str, ...]] | None:
        """取索引的 (是否唯一, 列名元组)。找不到返回 None。

        必须比对定义而不是只看名字：同名索引在不同迁移里可能是不同定义 ——
        0020 建的是【唯一】索引 ix_app_pricing_app_key，0029 把它 drop 掉改成
        【普通】索引（唯一性改由 (product, app_key) 约束保证）。
        只按名字跳过会把 0029 的 drop+recreate 语义吃掉，留下唯一索引。

        直接查 pg_catalog 而不用 inspector：迁移在同一个连接上连续执行，
        inspector 的结构缓存不会刷新 —— 0020 刚建的索引在 0029 里查不到，
        于是 drop 被跳过、create 撞 DuplicateTable。

        注意：PostgreSQL 里 unique=True 的索引建出来就是普通索引对象
        （relkind='i'，indisunique=true），能在 pg_index 里查到。
        """
        try:
            rows = self._conn.execute(
                sa.text(
                    "SELECT i.indisunique, a.attname "
                    "FROM pg_class c "
                    "JOIN pg_index i ON i.indexrelid = c.oid "
                    "JOIN pg_attribute a ON a.attrelid = i.indrelid "
                    "AND a.attnum = ANY(i.indkey) "
                    "WHERE c.relname = :n "
                    "ORDER BY a.attname"
                ),
                {"n": index},
            ).fetchall()
            if rows:
                return bool(rows[0][0]), tuple(r[1] for r in rows)
        except Exception:
            pass
        return None

    def _index_matches(self, index: str, want_unique: bool, want_cols: tuple[str, ...]) -> bool:
        """索引已存在且定义一致 → 可跳过；定义不一致 → 必须重建。"""
        got = self._index_def(index)
        if got is None:
            return False
        unique, cols = got
        if unique != want_unique:
            return False
        return not (want_cols and cols and set(cols) != set(want_cols))

    def _has_unique(self, constraint: str) -> bool:
        """直查 pg_constraint，不用 inspector（同样的缓存问题）。"""
        try:
            row = self._conn.execute(
                sa.text(
                    "SELECT 1 FROM pg_constraint WHERE conname = :c LIMIT 1"
                ),
                {"c": constraint},
            ).fetchone()
            return row is not None
        except Exception:
            return False

    def _skip(self, what: str) -> None:
        self.skipped.append(what)
        log.warning("migration.idempotent_skip", object=what)

    # ---------- 被包装的操作 ----------
    # 每个方法签名：(original, ops, args, kw)
    # ops 是当前 Operations 实例 —— original 是未绑定的类方法，调用时要传 self。

    def create_table(self, original, ops, args: tuple, kw: dict):
        table = _bind(original, args, kw).arguments.get("table_name")
        if table and self._table_exists(table):
            self._skip(f"table {table}")
            return None
        return original(ops, *args, **kw)

    def add_column(self, original, ops, args: tuple, kw: dict):
        bound = _bind(original, args, kw).arguments
        table = bound.get("table_name")
        column = bound.get("column")
        name = getattr(column, "name", None)
        if table and name and self._has_column(table, name):
            self._skip(f"column {table}.{name}")
            return None
        return original(ops, *args, **kw)

    def create_index(self, original, ops, args: tuple, kw: dict):
        bound = _bind(original, args, kw).arguments
        name = bound.get("index_name")
        if name:
            want_unique = bool(bound.get("unique", kw.get("unique", False)))
            want_cols = tuple(bound.get("columns") or ())
            if self._index_matches(name, want_unique, want_cols):
                self._skip(f"index {name}")
                return None
            # 定义不一致（同名但唯一性/列不同）→ 删掉重建，
            # 否则会撞 DuplicateTable，或留下错误定义的索引
            if self._has_index(name):
                self._drop_index_quietly(ops, name, bound.get("table_name"))
        return original(ops, *args, **kw)

    def _drop_index_quietly(self, ops, name: str, table_name: str | None) -> None:
        """删掉定义不一致的同名索引。失败不致命 —— 后面建索引时会给出真实错误。"""
        orig_drop = self._originals.get("drop_index")
        if orig_drop is None:
            return
        try:
            # 直接调原始实现，不能走包装层（会无限递归）
            orig_drop(ops, name, table_name=table_name)
            log.warning("migration.idempotent_reindex", index=name)
        except Exception as exc:
            log.warning("migration.idempotent_reindex_failed", index=name, error=str(exc)[:200])

    def drop_index(self, original, ops, args: tuple, kw: dict):
        bound = _bind(original, args, kw).arguments
        name = bound.get("index_name")
        if name and not self._has_index(name):
            self._skip(f"drop index {name} (不存在)")
            return None
        return original(ops, *args, **kw)

    def create_unique_constraint(self, original, ops, args: tuple, kw: dict):
        bound = _bind(original, args, kw).arguments
        name = bound.get("constraint_name")
        if name and self._has_unique(name):
            self._skip(f"unique {name}")
            return None
        return original(ops, *args, **kw)

    def drop_constraint(self, original, ops, args: tuple, kw: dict):
        bound = _bind(original, args, kw).arguments
        name = bound.get("constraint_name")
        if name and not self._has_unique(name):
            self._skip(f"drop constraint {name} (不存在)")
            return None
        return original(ops, *args, **kw)


def install_idempotent_ops(connection) -> _IdempotentGuard | None:
    """给 alembic 的 DDL 操作装上幂等保护。

    必须在 context.configure() 之后、context.run_migrations() 之前调用。
    离线模式（--sql）没有真实连接，无法查库reality，不装。

    可以重复调用：每次都基于**最初的原始方法**重新包装，并把 guard 换成当前连接。
    同一进程里先后跑两个库（生产 + 测试）时，guard 必须跟着连接换 ——
    复用旧 guard 会去查旧库，判断结果全错。
    """
    if connection is None:
        log.warning("migration.idempotent_skip_install", reason="offline mode")
        return None

    global _ORIGINALS
    if not _ORIGINALS:
        # 第一次调用时抓取原始实现，之后一直复用
        _ORIGINALS = {name: getattr(Operations, name) for name in _WRAPPED}

    guard = _IdempotentGuard(connection)
    guard._originals = _ORIGINALS

    def _make(name: str):
        original = _ORIGINALS[name]

        def patched(self, *args: Any, **kw: Any):
            # self 是 Operations 实例；original 是未绑定的类方法，调用时传 self
            return getattr(guard, name)(original, self, args, kw)

        patched.__name__ = name
        patched.__doc__ = original.__doc__
        return patched

    for name in _WRAPPED:
        setattr(Operations, name, _make(name))

    log.info("migration.idempotent_installed", methods=list(_WRAPPED))
    return guard
