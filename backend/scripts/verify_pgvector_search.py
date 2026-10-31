"""验证 pgvector 检索：索引可用性 + 结果合理性 + 耗时。"""

import asyncio
import time

from sqlalchemy import text

from cenkor_admin.apps.cms.ai import registry as ai_registry
from cenkor_admin.apps.cms.ai.search import has_pgvector, semantic_search
from cenkor_admin.core.db import AsyncSessionLocal
from cenkor_admin.core.llm import get_llm_for

QUERIES = ["机械加工报价怎么算", "青岛有哪些靠谱的加工厂", "产品交付周期多久"]
PLAN_SQL = (
    "EXPLAIN SELECT entry_id FROM cms_embeddings "
    "WHERE lang='base' AND field='combined' AND vector IS NOT NULL "
    "ORDER BY vector <=> CAST(:q AS vector) LIMIT 10"
)


async def main() -> None:
    async with AsyncSessionLocal() as db:
        await ai_registry.load(db, force=True)
        print(f"pgvector 可用: {await has_pgvector(db)}")

        qvec = await get_llm_for("embedding").embed_one("机械加工报价怎么算")
        q = "[" + ",".join(f"{x:.6f}" for x in qvec) + "]"

        for label, setting in (("默认", "on"), ("禁用全表扫", "off")):
            await db.execute(text(f"SET enable_seqscan = {setting}"))
            plan = (await db.execute(text(PLAN_SQL), {"q": q})).scalars().all()
            print(f"\n查询计划（enable_seqscan={setting}，{label}）:")
            for line in plan:
                # 向量字面量很长，只留前 60 字符
                print(f"  {line[:60]}")
        await db.execute(text("SET enable_seqscan = on"))

        print()
        for query in QUERIES:
            t = time.perf_counter()
            hits = await semantic_search(db, query, limit=5, include_drafts=True)
            dt = (time.perf_counter() - t) * 1000
            print(f"[{query}] {dt:.0f}ms 命中 {len(hits)}")
            for h in hits[:3]:
                print(f"  {h.score:.3f}  {h.title[:44]}")


if __name__ == "__main__":
    asyncio.run(main())
