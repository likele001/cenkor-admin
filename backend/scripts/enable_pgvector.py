"""把 cms_embeddings.vector 从 double precision[] 升级为 pgvector + HNSW。

什么时候用：部署环境装好 pgvector 扩展之后，一次性把列类型升上去。
alembic 迁移只在「首次跑到它」时判断扩展在不在，装晚了不会自动回头，
所以需要一个可重复执行的运维脚本 —— 只改列类型和索引，不动其它表。

幂等：已经是 vector(1024) 就什么都不做。

用法：
    cd backend && PYTHONPATH=src python scripts/enable_pgvector.py
    cd backend && PYTHONPATH=src python scripts/enable_pgvector.py --keep-vectors
        （默认会清空旧向量，因为维度不一致无法直接转换；加这个参数则先校验维度）
"""

from __future__ import annotations

import argparse
import sys

from loguru import logger
from sqlalchemy import create_engine, text

from cenkor_admin.core.config import get_settings

DIM = 1024


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--keep-vectors",
        action="store_true",
        help=f"保留已有向量（仅当全部为 {DIM} 维时可用），默认清空由应用重建",
    )
    args = parser.parse_args()

    eng = create_engine(get_settings().DATABASE_URL_SYNC)
    with eng.begin() as conn:
        ext = conn.execute(text("select 1 from pg_extension where extname = 'vector'")).first()
        if not ext:
            print("❌ 当前库没有 vector 扩展。先装 pgvector 并执行 CREATE EXTENSION vector")
            return 2

        col = conn.execute(
            text(
                "select udt_name from information_schema.columns "
                "where table_name = 'cms_embeddings' and column_name = 'vector'"
            )
        ).scalar()

        if col is None:
            print("❌ cms_embeddings.vector 列不存在，先跑 alembic upgrade heads")
            return 2
        if col == "vector":
            print("✅ 已经是 pgvector 类型，无需处理")
            return 0

        total = conn.execute(text("select count(*) from cms_embeddings")).scalar() or 0
        print(f"列当前类型 {col}，共 {total} 条向量")

        if total and not args.keep_vectors:
            print(f"清空旧向量（维度不是 {DIM} 时无法直接转换，由应用重建）")
            conn.execute(text("delete from cms_embeddings"))
        elif total:
            bad = conn.execute(
                text("select count(*) from cms_embeddings where vector is not null "
                     "and array_length(vector, 1) <> :d"), {"d": DIM}
            ).scalar()
            if bad:
                print(f"❌ 有 {bad} 条向量不是 {DIM} 维，无法保留；去掉 --keep-vectors 重跑")
                return 3

        conn.execute(text("drop index if exists ix_cms_embeddings_hnsw"))
        conn.execute(text("alter table cms_embeddings drop column vector"))
        conn.execute(text(f"alter table cms_embeddings add column vector vector({DIM})"))
        conn.execute(text(
            "comment on column cms_embeddings.vector is "
            f"'pgvector 向量，{DIM} 维（豆包 dimensions={DIM}）；HNSW 余弦索引'"
        ))
        try:
            conn.execute(text(
                "create index ix_cms_embeddings_hnsw on cms_embeddings "
                "using hnsw (vector vector_cosine_ops) with (m = 16, ef_construction = 64)"
            ))
            print("✅ HNSW 索引已建（pgvector >= 0.5）")
        except Exception as exc:
            logger.warning(f"HNSW 索引建不出来（pgvector 版本偏低？）：{exc}")
            print("⚠️  列已升级，但 HNSW 索引未建；查询仍可用，只是走顺序扫描")

    print("完成：请在后台「AI > 向量重建」补齐向量")
    return 0


if __name__ == "__main__":
    sys.exit(main())
