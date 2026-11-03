"""SSO · 绑定表补列与唯一约束

复用现有的两张绑定表（``portal_user_oauth`` / ``auth_user_oauth``）而不是
新建一张 ``sso_identities``：这两张表当前都是 **0 条数据**，加列没有任何
兼容负担；而多建一张表意味着运维排障时要多记一个表名、备份恢复要多核对
一处。少一张表是实实在在的收益。

补的内容：

1. 两张表都加 ``raw_profile``（jsonb）：存渠道返回的原始用户信息。
   为什么要存：第三方昵称/头像会变，登录页要显示"你绑的是哪个账号"就得
   有个能刷新展示的地方；排障时也能直接看到渠道到底返回了什么。
   不存 token 明文——token 走 ``core.secrets`` 加密后进 ``*_enc`` 字段。
2. 两张表都加 ``last_login_at``：区分"绑过"和"最近在用"，用于清理僵尸绑定。
3. ``auth_user_oauth`` 补 ``UNIQUE(provider, open_id)``：
   原表注释里写了这条约束但**根本没建**。没有它，同一个飞书账号可以被并发
   请求插成两行，之后按 (provider, open_id) 查会 ``scalar_one_or_none()``
   抛 MultipleResultsFound。
4. ``auth_user_oauth`` 补外键到 ``auth_users`` ON DELETE CASCADE：
   原表连外键都没有，删用户后绑定记录变孤儿，重新注册同 id 就会串号。

全部用「先查存在性再执行」的幂等写法，重复跑不会报错。
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261103_0930_sso_bindings"
down_revision = "20261102_2140_cms_ai_missing"
branch_labels = None
depends_on = None

_PORTAL_TABLE = "portal_user_oauth"
_ADMIN_TABLE = "auth_user_oauth"


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "select 1 from information_schema.columns "
        "where table_schema='public' and table_name=:t and column_name=:c"
    ), {"t": table, "c": column})
    return result.scalar_one_or_none() is not None


def _has_constraint(table: str, name: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "select 1 from pg_constraint c "
        "join pg_class t on t.oid = c.conrelid "
        "where t.relname = :t and c.conname = :n"
    ), {"t": table, "n": name})
    return result.scalar_one_or_none() is not None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "select 1 from information_schema.tables "
        "where table_schema='public' and table_name=:t"
    ), {"t": table})
    return result.scalar_one_or_none() is not None


def upgrade() -> None:
    for table in (_PORTAL_TABLE, _ADMIN_TABLE):
        if not _table_exists(table):
            # 老版本可能没有这两张表（portal 是后来加的 App），跳过而不是硬失败
            continue
        if not _has_column(table, "raw_profile"):
            op.add_column(
                table,
                sa.Column("raw_profile", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            )
        if not _has_column(table, "last_login_at"):
            op.add_column(
                table,
                sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
            )

    # ---- auth_user_oauth：补唯一约束与外键 ----
    if _table_exists(_ADMIN_TABLE):
        if not _has_constraint(_ADMIN_TABLE, "uq_auth_oauth_provider_openid"):
            # 先清掉可能的重复行再建约束，否则建约束会失败。
            # 保留 id 最大的一行（最新绑定），这是唯一能自动判定的"有效"依据。
            op.execute(sa.text(f"""
                delete from {_ADMIN_TABLE} a
                using {_ADMIN_TABLE} b
                where a.provider = b.provider
                  and a.open_id = b.open_id
                  and a.id < b.id
            """))
            op.create_unique_constraint(
                "uq_auth_oauth_provider_openid",
                _ADMIN_TABLE,
                ["provider", "open_id"],
            )

        if not _has_constraint(_ADMIN_TABLE, "fk_auth_oauth_user"):
            # 孤儿行先删掉，否则加外键会失败
            op.execute(sa.text(f"""
                delete from {_ADMIN_TABLE} o
                where not exists (select 1 from auth_users u where u.id = o.user_id)
            """))
            op.create_foreign_key(
                "fk_auth_oauth_user",
                _ADMIN_TABLE,
                "auth_users",
                ["user_id"],
                ["id"],
                ondelete="CASCADE",
            )

    # 绑定查询是 (provider, open_id) 等值查，投影到 user_id；
    # 已有单列索引在 PG 上能走 BitmapAnd，但复合索引对高频登录路径更快。
    if _table_exists(_PORTAL_TABLE) and not _has_constraint(
        _PORTAL_TABLE, "uq_portal_oauth_provider_openid"
    ):
        op.create_unique_constraint(
            "uq_portal_oauth_provider_openid",
            _PORTAL_TABLE,
            ["provider", "open_id"],
        )


def downgrade() -> None:
    # 只回滚本迁移新增的列与约束；表和历史数据保留（降级不该丢数据）
    for table in (_PORTAL_TABLE, _ADMIN_TABLE):
        if not _table_exists(table):
            continue
        if _has_column(table, "raw_profile"):
            op.drop_column(table, "raw_profile")
        if _has_column(table, "last_login_at"):
            op.drop_column(table, "last_login_at")

    if _table_exists(_ADMIN_TABLE):
        if _has_constraint(_ADMIN_TABLE, "fk_auth_oauth_user"):
            op.drop_constraint("fk_auth_oauth_user", _ADMIN_TABLE, type_="foreignkey")
        if _has_constraint(_ADMIN_TABLE, "uq_auth_oauth_provider_openid"):
            op.drop_constraint(
                "uq_auth_oauth_provider_openid", _ADMIN_TABLE, type_="unique"
            )
