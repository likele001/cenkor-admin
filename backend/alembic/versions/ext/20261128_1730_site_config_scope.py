"""站点配置按站点隔离：cms_site_config 加 site_id，主键改复合

Revision ID: 20261128_1730_site_config_scope
Revises: 20261128_1200_notify
Create Date: 2026-11-28 17:30

设计要点
--------
1. **主键从 `key` 改为 `(site_id, key)`**。原表 key 单列主键，意味着
   `brand.name` 全站只能有一份 —— 多站点下每个站要自己的品牌名、SEO 默认值、
   联系方式，必须靠 site_id 区分。

2. **存量 72 条配置全部归属 site_id=1（主站）**，不做数据分裂。理由：改造前
   这些配置事实上就是「全站共用」，其值描述的是主站（`brand.domain=cenkor.cn`）。
   把它们挂在主站名下最符合原语义，也让 site_id=1 的行为与改造前完全一致。

3. **新站点在「建站」时复制主站的配置**（在 `site_router.create_site` 里做，
   不在本迁移里）。这样每个新站一上来就有完整的品牌/SEO/联系方式初始值，
   后台不会满屏空白；之后各站独立修改，主站再改不会同步过去。
   本迁移只负责历史数据的归属，不预先给未来的站点造数据。

4. **site_id 用 NOT NULL + server_default '1'**：给存量行填 1 的同时，让
   迁移窗口期若还有旧代码 INSERT（不带 site_id）也不至于炸。代码上线后
   可以再单独一次迁移把 server_default 去掉。

5. **不加外键约束到 cms_sites.id**：`cms_sites` 在清理站点时是物理删除
   （`site_router.delete_site`），加 FK 会让删站失败或需要级联删配置。
   配置行在删站时由代码显式清理，语义更清楚。

6. **索引**：复合主键自带 `(site_id, key)` 索引，按站点查全部配置走它；
   再补一个 `key` 单列索引 —— 少数场景按 key 跨站查（如迁移脚本、
   统计「哪些站还没配 brand.name」）。

上线顺序
--------
迁移与代码**必须同时**上线，不能只上其一：

- 先上迁移、代码还旧：旧代码 `db.get(SiteConfig, key)` 只传 key，复合主键
  下会报错（找不到主键列）。
- 先上代码、迁移还旧：新代码查 `SiteConfig.site_id` 列不存在，直接 500。

本迁移是 `NOT NULL DEFAULT 1` 的增量变更，`alembic upgrade heads` 秒级完成，
不需要停服窗口。回滚脚本会还原成单列主键，但**多站点产生的配置行会因主键
冲突而保留 site_id=1 的那条**，即回滚会丢弃非主站配置 —— 回滚前请先备份。
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261128_1730_site_config_scope"
# 挂在 notify 之后。库里有两条 head（notify 与 crm_app 的 merge_closed_cms
# 是两个分支），本迁移只动 cms 侧的表，挂在 cms 这条链上即可，
# `alembic upgrade heads` 会把它作为 notify 的唯一后继应用。
down_revision: str | None = "20261128_1200_notify"
branch_labels: str | None = None
depends_on: str | None = None


def _columns(insp: sa.engine.reflection.Inspector, table: str) -> set[str]:
    return {c["name"] for c in insp.get_columns(table)}


def _pk_columns(insp: sa.engine.reflection.Inspector, table: str) -> list[str]:
    return list(insp.get_pk_constraint(table).get("constrained_columns") or [])


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    cols = _columns(insp, "cms_site_config")
    pk = _pk_columns(insp, "cms_site_config")

    # 幂等：重复执行到已迁移的库上不报错（宝塔重跑迁移脚本很常见）
    if "site_id" in cols and pk == ["site_id", "key"]:
        return

    # ---- 1. 先加列（可空），回填，再收紧成 NOT NULL ----
    # 分三步而不是一步 ADD COLUMN NOT NULL DEFAULT 1：PG 11+ 虽然能秒完成，
    # 但先加可空列能让我们在回填后显式校验「没有 NULL 残留」再收紧，
    # 出问题时停在中间态而不是带着错误默认值继续。
    if "site_id" not in cols:
        op.add_column(
            "cms_site_config",
            sa.Column("site_id", sa.Integer(), nullable=True),
        )

    # ---- 2. 存量数据归属主站 ----
    # 主站 = id 最小的站点。写死 1 是不安全的：理论上 id=1 可能被删过
    # （cms_sites 是物理删除），所以查真实的最小 id。
    conn = op.get_bind()
    main_id = conn.execute(sa.text("SELECT min(id) FROM cms_sites")).scalar()
    if main_id is None:
        # 空库/无站点：没有可归属的对象，配置表也该是空的。给 1 兜底，
        # 避免 NOT NULL 收紧失败。
        main_id = 1
    conn.execute(
        sa.text("UPDATE cms_site_config SET site_id = :sid WHERE site_id IS NULL"),
        {"sid": int(main_id)},
    )

    # 回填后自检：还有 NULL 就是数据异常，宁可让迁移失败也别带病上线
    left = conn.execute(
        sa.text("SELECT count(*) FROM cms_site_config WHERE site_id IS NULL")
    ).scalar()
    if left:
        raise RuntimeError(
            f"cms_site_config 仍有 {left} 行 site_id 为空，回填失败，已中止迁移"
        )

    # ---- 3. 换主键：(key) → (site_id, key) ----
    # 先删旧 PK 再建新 PK。中间的短暂窗口内表无主键约束，但本迁移在事务里，
    # 外部看不到中间态（PG 的 DDL 是事务性的）。
    op.drop_constraint("cms_site_config_pkey", "cms_site_config", type_="primary")

    # 收紧 NOT NULL。server_default 保留，给迁移窗口期的旧代码兜底。
    op.alter_column(
        "cms_site_config",
        "site_id",
        existing_type=sa.Integer(),
        nullable=False,
        server_default="1",
    )

    op.create_primary_key(
        "cms_site_config_pkey", "cms_site_config", ["site_id", "key"]
    )

    # ---- 4. 补 key 单列索引 ----
    # 复合 PK 的索引前缀是 site_id，按 key 跨站查用不上它。
    op.create_index(
        "ix_cms_site_config_key",
        "cms_site_config",
        ["key"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    cols = _columns(insp, "cms_site_config")
    pk = _pk_columns(insp, "cms_site_config")

    if "site_id" not in cols:
        return

    # 回滚前先收敛数据：单列主键下 key 必须全局唯一。
    # 保留每个 key 在**主站**的那一行，其余站点产生的行会被删除。
    # 这是有损回滚，迁移文档里已注明要先备份。
    if pk == ["site_id", "key"]:
        conn = op.get_bind()
        main_id = conn.execute(sa.text("SELECT min(id) FROM cms_sites")).scalar() or 1
        conn.execute(
            sa.text(
                "DELETE FROM cms_site_config "
                "WHERE site_id <> :sid AND key IN ("
                "  SELECT key FROM cms_site_config WHERE site_id = :sid"
                ")"
            ),
            {"sid": int(main_id)},
        )
        # 剩下的非主站行 key 可能唯一，但语义上应归主站，统一改写
        conn.execute(
            sa.text("UPDATE cms_site_config SET site_id = :sid WHERE site_id <> :sid"),
            {"sid": int(main_id)},
        )

        op.drop_constraint("cms_site_config_pkey", "cms_site_config", type_="primary")

    # 索引先删（它依赖列存在）
    try:
        op.drop_index("ix_cms_site_config_key", table_name="cms_site_config")
    except Exception:
        pass

    if pk == ["site_id", "key"]:
        op.create_primary_key("cms_site_config_pkey", "cms_site_config", ["key"])

    op.drop_column("cms_site_config", "site_id")
