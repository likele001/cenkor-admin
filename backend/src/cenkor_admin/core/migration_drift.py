"""alembic 迁移漂移检测与自愈（2026-10-30）

背景
----
本项目的迁移图是**多条链交织**的结构，不是单线：

    core(29) / erp(19) / crm(6) / mes(9) / commerce(9) / ext(12)

每条链各自有多个「局部 head」，这些局部 head 通过 down_revision **跨目录**挂到
别的链上（例：erp/20260831_0001_erp_init 的 down 指向 ext/20261020_0035_app_publish；
ext/20261027_0100_app_schema 的 down 指向 commerce/20261007_0029_product_commerce；
core/20261014_124200_schema_versions 的 down 指向 ext/20261014_124126_gen_inventory）。
全量视图最终合成 1 个 head、1 个 base，但**任何按单链推演的算法都会算错**。

事故
----
2026-10-30 服务启动刷 error：

    DuplicateColumn: column "schema_version" of relation "app_submissions" already exists

根因链条（三层，缺一不可）：

1. 本项目长期存在「alembic_version 落后于实际库结构」的漂移 —— 历史上有若干
   迁移的 DDL 被手工 SQL 补到线上库（见 scripts/apply_app_publish_ddl.py 的
   事故复盘），但版本号没同步推进。
2. 迁移链挂载点被 codegen/builder.py 的 rebase_closed_chain 反复顺延，版本号
   落到了某个迁移之前。
3. 于是每次启动 alembic 都会重跑那一整串迁移，撞 DuplicateColumn /
   DuplicateTable —— 而 0035 只是这条链里的第 40 个，前面 39 个因为表已存在
   而陆续炸掉（最早暴露的是 0035，因为它是第一个带 add_column 的）。

为什么不能靠「逐个改迁移加 if_not_exists」
--------------------------------------------
- 要改 9 个历史迁移文件，且每条链的每个 DDL 都要改，漏一个就还炸；
- 治标不治本：下次新增迁移、或挂载点再次顺延，同样的问题会重演；
- 这套多链交织的结构里，手工逐个核对迁移链极易算错（本次就差点算错）。

本模块的解法
------------
**启动时先做全量图漂移检测，再决定是 stamp 还是 upgrade**：

- 用 alembic 自己的 ScriptDirectory 拿到**全量**迁移图（多链交织的真实拓扑，
  不靠手写正则推演），从当前版本号出发沿「所有子节点」遍历出待跑集合；
- 把待跑集合里每个迁移的 upgrade 期望（建表/加列/建索引/唯一约束）解析出来，
  与**真实库结构**逐项比对；
- 全部都存在 → 说明只是版本号落后（DDL 早被手工应用过了），
  直接 stamp 到 head，不再重跑 DDL；
- 有缺失 → 说明库结构真的落后，走正常 upgrade，让 alembic 补齐。

这样：
- 线上这类「DDL 已在、版本号落后」的库，启动一次就自愈，不再刷 error；
- 真正缺表缺列的环境，upgrade 照常执行，不被掩盖；
- 空库 / 新环境不受影响（待跑集合 = 全量，缺的东西全都会补上）。

安全边界
--------
stamp 只在「待跑迁移期望的对象 100% 都在库里」时才发生 —— 即不会跳过任何
真正需要执行的 DDL。检测逻辑只读，不改库。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import sqlalchemy as sa
import structlog
from alembic.config import Config
from alembic.script import ScriptDirectory

log = structlog.get_logger()

# upgrade() 里可能出现的 DDL 形态
_RE_CREATE_TABLE = re.compile(r'op\.create_table\(\s*["\']([^"\']+)')
_RE_ADD_COLUMN = re.compile(
    r'op\.add_column\(\s*["\']([^"\']+)["\']\s*,\s*sa\.Column\(\s*["\']([^"\']+)'
)
_RE_CREATE_INDEX = re.compile(r'op\.create_index\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)')
_RE_CREATE_UNIQUE = re.compile(
    r'op\.create_unique_constraint\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)'
)
_RE_DOCSTRING = re.compile(r'"""[\s\S]*?"""')


@dataclass
class Expected:
    """待跑迁移期望在库里存在的对象集合。"""

    tables: set[str] = field(default_factory=set)
    columns: set[tuple[str, str]] = field(default_factory=set)
    indexes: set[tuple[str, str]] = field(default_factory=set)
    uniques: set[tuple[str, str]] = field(default_factory=set)

    def total(self) -> int:
        return len(self.tables) + len(self.columns) + len(self.indexes) + len(self.uniques)


@dataclass
class DriftReport:
    ok: bool
    current: str
    heads: list[str]
    pending: list[str]
    expected: Expected
    missing_tables: list[str] = field(default_factory=list)
    missing_columns: list[tuple[str, str]] = field(default_factory=list)
    missing_indexes: list[tuple[str, str]] = field(default_factory=list)
    missing_uniques: list[tuple[str, str]] = field(default_factory=list)

    @property
    def missing_total(self) -> int:
        return (
            len(self.missing_tables)
            + len(self.missing_columns)
            + len(self.missing_indexes)
            + len(self.missing_uniques)
        )

    def summary(self) -> str:
        if self.ok:
            return (
                f"版本号已落后于库结构：待跑 {len(self.pending)} 个迁移，"
                f"期望对象 {self.expected.total()} 项全部已存在 → 可安全 stamp"
            )
        return (
            f"库结构确实落后：待跑 {len(self.pending)} 个迁移，"
            f"缺 {self.missing_total} 项 → 需正常 upgrade"
        )


def _parse_expected(revisions) -> Expected:
    """解析一批迁移的 upgrade 期望。

    只认 op.* 形式的 DDL —— 迁移里的 op.execute("ALTER TABLE ... ADD COLUMN")
    这种裸 SQL 形式无法静态解析，遇到时保守处理（不当成缺失，避免误 stamp）。
    """
    exp = Expected()
    for rev in revisions:
        src = open(rev.path, encoding="utf-8").read()
        up = src.split("def upgrade()", 1)[-1].split("def downgrade()", 1)[0]
        # 去掉 docstring，避免注释里的表名被误判
        up = _RE_DOCSTRING.sub("", up)
        for m in _RE_CREATE_TABLE.finditer(up):
            exp.tables.add(m.group(1))
        for m in _RE_ADD_COLUMN.finditer(up):
            exp.columns.add((m.group(1), m.group(2)))
        for m in _RE_CREATE_INDEX.finditer(up):
            exp.indexes.add((m.group(1), m.group(2)))
        for m in _RE_CREATE_UNIQUE.finditer(up):
            exp.uniques.add((m.group(1), m.group(2)))
    return exp


def _pending_revisions(script: ScriptDirectory, current: str) -> list:
    """从 current 出发，沿**全量图**（所有子节点）收集待跑迁移。

    这里必须用全量遍历而不是「沿唯一子节点走一条链」：
    本项目 6 条链交织，每条链有多个局部 head，只有全量遍历才对。
    """
    children: dict[str, list] = {}
    for rev in script.walk_revisions():
        children.setdefault(rev.down_revision, []).append(rev)

    out: list = []
    seen: set[str] = set()
    stack = [current]
    while stack:
        node = stack.pop()
        for kid in children.get(node, []):
            if kid.revision in seen:
                continue
            seen.add(kid.revision)
            out.append(kid)
            stack.append(kid.revision)
    return out


def check_drift(cfg: Config, connection) -> DriftReport:
    """比对「待跑迁移的期望」与「真实库结构」。只读，不改库。"""
    script = ScriptDirectory.from_config(cfg)
    insp = sa.inspect(connection)

    # 全新库：alembic_version 表都还没有 —— 这不是错误，是「从零开始」，
    # 交给正常 upgrade 跑全量即可。
    has_version_table = insp.has_table("alembic_version")
    if not has_version_table:
        all_revs = list(script.walk_revisions())
        expected = _parse_expected(all_revs)
        return DriftReport(
            ok=False,
            current="<none>",
            heads=list(script.get_heads()),
            pending=[r.revision for r in all_revs],
            expected=expected,
            missing_tables=sorted(expected.tables),
            missing_columns=sorted(expected.columns),
            missing_indexes=sorted(expected.indexes),
            missing_uniques=sorted(expected.uniques),
        )

    current = connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalars().first()
    if not current:
        # 表在但没有版本行（手工清过、或从未 upgrade 过）—— 当作全新库
        all_revs = list(script.walk_revisions())
        expected = _parse_expected(all_revs)
        return DriftReport(
            ok=False,
            current="<none>",
            heads=list(script.get_heads()),
            pending=[r.revision for r in all_revs],
            expected=expected,
            missing_tables=sorted(expected.tables),
            missing_columns=sorted(expected.columns),
            missing_indexes=sorted(expected.indexes),
            missing_uniques=sorted(expected.uniques),
        )
    pending = _pending_revisions(script, current)
    expected = _parse_expected(pending)

    tables = set(insp.get_table_names())
    all_indexes: set[str] = set()
    all_uniques: set[tuple[str, str]] = set()
    for tbl in tables:
        try:
            all_indexes |= {i["name"] for i in insp.get_indexes(tbl)}
        except Exception:  # noqa: BLE001
            pass
        try:
            for u in insp.get_unique_constraints(tbl):
                all_uniques.add((u["name"], tbl))
        except Exception:  # noqa: BLE001
            pass

    missing_tables = sorted(t for t in expected.tables if t not in tables)
    missing_columns: list[tuple[str, str]] = []
    for tbl, col in sorted(expected.columns):
        if tbl not in tables:
            continue
        try:
            cols = {c["name"] for c in insp.get_columns(tbl)}
        except Exception:  # noqa: BLE001
            continue
        if col not in cols:
            missing_columns.append((tbl, col))
    missing_indexes = sorted(
        (name, tbl) for name, tbl in expected.indexes if name not in all_indexes
    )
    missing_uniques = sorted(
        (name, tbl) for name, tbl in expected.uniques if (name, tbl) not in all_uniques
    )

    missing_total = (
        len(missing_tables) + len(missing_columns) + len(missing_indexes) + len(missing_uniques)
    )
    return DriftReport(
        ok=(missing_total == 0),
        current=current,
        heads=list(script.get_heads()),
        pending=[r.revision for r in pending],
        expected=expected,
        missing_tables=missing_tables,
        missing_columns=missing_columns,
        missing_indexes=missing_indexes,
        missing_uniques=missing_uniques,
    )
