"""codegen 迁移文件收集的回归测试。

背景：迁移布局从「扁平」改成「按 App 分目录」（`alembic.ini` 的
`version_locations` 列了 core / erp / crm / mes / commerce / ext），但
`all_migration_files()` 仍然只 `glob("*.py")` 顶层目录 → 收集到 0 个文件 →
`scripts/gen-app.py` 用默认参数直接报「迁移图没有 head」，二次开发第一步就卡住。

这里锁住：迁移放在任意层子目录时都要能收集到，并正确算出唯一 head。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cenkor_admin.codegen import builder as B

MIG_TMPL = '''"""test migration"""
revision = {rev!r}
down_revision = {down!r}


def upgrade():
    pass


def downgrade():
    pass
'''


def _write(path: Path, rev: str, down: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(MIG_TMPL.format(rev=rev, down=down), encoding="utf-8")


def test_collects_migrations_from_subdirs(tmp_path):
    """分目录（core/ext）也要被收集——扁平布局下这里会是 0 个。"""
    versions = tmp_path / "versions"
    _write(versions / "core" / "20260101_0001_a.py", "rev_a", None)
    _write(versions / "ext" / "20260102_0002_b.py", "rev_b", "rev_a")

    files = B.all_migration_files(versions)

    assert len(files) == 2
    assert {f.name for f in files} == {"20260101_0001_a.py", "20260102_0002_b.py"}


def test_head_resolves_when_migrations_live_in_subdirs(tmp_path):
    """head 计算要能穿过子目录找到链尾。"""
    versions = tmp_path / "versions"
    _write(versions / "core" / "20260101_0001_a.py", "rev_a", None)
    _write(versions / "core" / "20260102_0002_b.py", "rev_b", "rev_a")
    _write(versions / "mes" / "20260103_0003_c.py", "rev_c", "rev_b")

    assert B.current_head(versions) == "rev_c"


def test_skips_dunder_and_pycache(tmp_path):
    """__init__.py 与 __pycache__ 里的残渣不能进候选集。"""
    versions = tmp_path / "versions"
    _write(versions / "core" / "20260101_0001_a.py", "rev_a", None)
    (versions / "core" / "__init__.py").write_text("", encoding="utf-8")
    pycache = versions / "core" / "__pycache__"
    pycache.mkdir(parents=True, exist_ok=True)
    (pycache / "junk.py").write_text("", encoding="utf-8")

    files = B.all_migration_files(versions)

    assert [f.name for f in files] == ["20260101_0001_a.py"]


def test_missing_versions_dir_raises(tmp_path):
    """目录不存在要明确报错，而不是静默返回空列表。"""
    with pytest.raises(SystemExit):
        B.all_migration_files(tmp_path / "nope")
