"""CMS 多站点地基：cms_sites + 各内容表 site_id

本迁移接管原先 `backend/migrations/001_multisite.sql` + `002_multisite_tags.sql`
+ `005_page_form_site.sql` 三份旁路 SQL 的全部内容（2026-10-31 统一到 alembic）。

为什么合并成一条而不是拆三条：那三份 SQL 是同一次改动的三段补丁
（001 漏了 tags 的唯一约束、005 又补 pages/forms 与域名唯一），
合并后是一条「多站点终态」描述，链上更短，也不会有人在中间态误判。

幂等策略：全部走 `to_regclass` / `pg_constraint` 判存后再 DDL，
索引名与约束名**照抄原 SQL**，避免老库上凭空多出重复索引。
- 老库（生产）三份 SQL 早已应用 → 每条都跳过，零副作用；
- 新库（开源 clone / CI / docker）→ 一次性建全。

Revision ID: 20261031_1300_cms_multisite   （27 字符，alembic_version 上限 32）
Revises: 20261031_1100_cms_templates
Create Date: 2026-10-31 13:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261031_1300_cms_multisite"
down_revision: str | Sequence[str] | None = "20261031_1100_cms_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 表 → 该表上要收敛的 DDL。
# old_unique：多站点之前那条全局唯一约束（要拆）
# new_unique/new_cols：站内唯一约束（要建）
# fk：指向 cms_sites 的外键
# indexes：(索引名, 列定义) —— 名字照抄原 SQL
_SITE_TABLES: list[dict] = [
    {
        "table": "cms_entries",
        "old_unique": "uq_entry_ct_slug",
        "new_unique": "uq_entry_site_ct_slug",
        "new_cols": "site_id, content_type_id, slug",
        "fk": "fk_entries_site",
        "indexes": [
            ("idx_entries_site_status", "site_id, status"),
            ("idx_entries_site_ct", "site_id, content_type_id"),
        ],
    },
    {
        "table": "cms_categories",
        "old_unique": "uq_category_ct_slug",
        "new_unique": "uq_category_site_ct_slug",
        "new_cols": "site_id, content_type_id, slug",
        "fk": "fk_categories_site",
        "indexes": [("idx_categories_site", "site_id")],
    },
    {
        "table": "cms_tags",
        "old_unique": "uq_tag_ct_slug",
        "new_unique": "uq_tag_site_ct_slug",
        "new_cols": "site_id, content_type_id, slug",
        "fk": "fk_tags_site",
        "indexes": [("idx_tags_site", "site_id")],
    },
    {
        "table": "cms_media",
        "old_unique": None,
        "new_unique": None,
        "new_cols": None,
        "fk": "fk_media_site",
        "indexes": [("idx_media_site", "site_id")],
    },
    {
        "table": "cms_pages",
        "old_unique": "cms_pages_key_key",
        "new_unique": "uq_pages_site_key",
        "new_cols": "site_id, key",
        "fk": "fk_pages_site",
        "indexes": [("idx_pages_site", "site_id")],
    },
    {
        "table": "cms_forms",
        "old_unique": "cms_forms_key_key",
        "new_unique": "uq_forms_site_key",
        "new_cols": "site_id, key",
        "fk": "fk_forms_site",
        "indexes": [("idx_forms_site", "site_id")],
    },
    # 遗留表：只补 site_id + 索引，没有站内唯一约束
    {
        "table": "cms_news",
        "old_unique": None,
        "new_unique": None,
        "new_cols": None,
        "fk": None,
        "indexes": [("idx_news_site", "site_id")],
    },
    {
        "table": "cms_products",
        "old_unique": None,
        "new_unique": None,
        "new_cols": None,
        "fk": None,
        "indexes": [("idx_products_site", "site_id")],
    },
    {
        "table": "cms_cases",
        "old_unique": None,
        "new_unique": None,
        "new_cols": None,
        "fk": None,
        "indexes": [("idx_cases_site", "site_id")],
    },
]


def _converge_sql(spec: dict) -> str:
    """单表收敛：表在才动，列/约束/索引逐个判存。"""
    t = spec["table"]
    lines = [
        "DO $$",
        "BEGIN",
        f"  IF to_regclass('public.{t}') IS NULL THEN RETURN; END IF;",
        f"  ALTER TABLE {t} ADD COLUMN IF NOT EXISTS site_id integer NOT NULL DEFAULT 1;",
    ]
    if spec["old_unique"]:
        lines.append(f"  ALTER TABLE {t} DROP CONSTRAINT IF EXISTS {spec['old_unique']};")
    if spec["new_unique"] and spec["new_cols"]:
        lines += [
            "  IF NOT EXISTS (SELECT 1 FROM pg_constraint",
            f"                 WHERE conname = '{spec['new_unique']}'",
            f"                   AND conrelid = 'public.{t}'::regclass) THEN",
            f"    ALTER TABLE {t} ADD CONSTRAINT {spec['new_unique']} "
            f"UNIQUE ({spec['new_cols']});",
            "  END IF;",
        ]
    if spec["fk"]:
        lines += [
            "  IF NOT EXISTS (SELECT 1 FROM pg_constraint",
            f"                 WHERE conname = '{spec['fk']}'",
            f"                   AND conrelid = 'public.{t}'::regclass) THEN",
            f"    ALTER TABLE {t} ADD CONSTRAINT {spec['fk']}",
            "      FOREIGN KEY (site_id) REFERENCES cms_sites(id) ON DELETE RESTRICT;",
            "  END IF;",
        ]
    for name, cols in spec["indexes"]:
        lines.append(f"  CREATE INDEX IF NOT EXISTS {name} ON {t} ({cols});")
    lines.append("END $$;")
    return "\n".join(lines)


def _teardown_sql(spec: dict) -> str:
    t = spec["table"]
    lines = [
        "DO $$",
        "BEGIN",
        f"  IF to_regclass('public.{t}') IS NULL THEN RETURN; END IF;",
    ]
    if spec["fk"]:
        lines.append(f"  ALTER TABLE {t} DROP CONSTRAINT IF EXISTS {spec['fk']};")
    if spec["new_unique"]:
        lines.append(f"  ALTER TABLE {t} DROP CONSTRAINT IF EXISTS {spec['new_unique']};")
    for name, _cols in spec["indexes"]:
        lines.append(f"  DROP INDEX IF EXISTS {name};")
    lines.append(f"  ALTER TABLE {t} DROP COLUMN IF EXISTS site_id;")
    lines.append("END $$;")
    return "\n".join(lines)


def upgrade() -> None:
    op.create_table(
        "cms_sites",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="main"),
        sa.Column("domain", sa.String(255), nullable=True),
        sa.Column("locale", sa.String(20), nullable=False, server_default="zh-CN"),
        sa.Column("default_lang", sa.String(20), nullable=True),
        sa.Column("site_mode", sa.String(20), nullable=False, server_default="article"),
        sa.Column("geo", sa.JSON(), nullable=True),
        sa.Column("seo_defaults", sa.JSON(), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    # 单站点部署的默认站点。多站点由后台再建，key 唯一所以可反复执行。
    op.execute(
        "INSERT INTO cms_sites (key, name, kind, site_mode, sort) "
        "VALUES ('main', '主站', 'main', 'article', 0) "
        "ON CONFLICT (key) DO NOTHING"
    )

    for spec in _SITE_TABLES:
        op.execute(_converge_sql(spec))

    # 一个域名只能指向一个站；大小写不敏感，NULL 允许多条（未绑域名的站）
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sites_domain "
        "ON cms_sites (lower(domain)) WHERE domain IS NOT NULL"
    )

    # cms_templates 排在 cms_sites 之前（链上 ai_video_jobs → cms_templates → 本条），
    # 建表时还没有站点表，所以外键只能在这里补 —— 单独处理，不并入 _SITE_TABLES，
    # 免得 downgrade 连它自己的 site_id 列一起删掉。
    op.execute(
        "DO $$ BEGIN "
        "IF to_regclass('public.cms_templates') IS NULL THEN RETURN; END IF; "
        "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_cms_templates_site' "
        "AND conrelid = 'public.cms_templates'::regclass) THEN "
        "ALTER TABLE cms_templates ADD CONSTRAINT fk_cms_templates_site "
        "FOREIGN KEY (site_id) REFERENCES cms_sites(id) ON DELETE CASCADE; "
        "END IF; END $$;"
    )


def downgrade() -> None:
    # 回退顺序：先拆外键/索引/约束，再删列，最后删站点表。
    op.execute(
        "DO $$ BEGIN IF to_regclass('public.cms_templates') IS NOT NULL THEN "
        "ALTER TABLE cms_templates DROP CONSTRAINT IF EXISTS fk_cms_templates_site; "
        "END IF; END $$;"
    )
    for spec in reversed(_SITE_TABLES):
        op.execute(_teardown_sql(spec))

    # 恢复原有的全局唯一约束（有重复数据时会失败，属预期：先清数据再降级）
    _restore = [
        ("cms_entries", "uq_entry_ct_slug", "content_type_id, slug"),
        ("cms_categories", "uq_category_ct_slug", "content_type_id, slug"),
        ("cms_tags", "uq_tag_ct_slug", "content_type_id, slug"),
    ]
    for table, conname, cols in _restore:
        op.execute(
            f"DO $$ BEGIN "
            f"IF to_regclass('public.{table}') IS NOT NULL AND NOT EXISTS ("
            f"SELECT 1 FROM pg_constraint WHERE conname = '{conname}' "
            f"AND conrelid = 'public.{table}'::regclass) THEN "
            f"ALTER TABLE {table} ADD CONSTRAINT {conname} UNIQUE ({cols}); "
            f"END IF; END $$;"
        )

    op.execute("DROP INDEX IF EXISTS uq_sites_domain")
    op.execute("DROP TABLE IF EXISTS cms_sites")
