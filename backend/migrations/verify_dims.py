"""验证 dimensions=1024 是否真的透传到豆包 API。"""

import asyncio

from cenkor_admin.apps.cms.ai import registry as ai_registry
from cenkor_admin.core.db import AsyncSessionLocal
from cenkor_admin.core.llm import get_llm_for


async def main() -> None:
    async with AsyncSessionLocal() as db:
        reg = await ai_registry.load(db)
        ep = reg.endpoint("embedding")
        print(f"Endpoint.params = {ep.params}" if ep else "NO embedding endpoint")

    llm = get_llm_for("embedding")
    print(f"LLMClient.embed_params = {llm.embed_params}")

    v = await llm.embed_one("青岛机械加工厂零部件加工报价怎么算")
    print(f"实际返回维度 = {len(v)}")
    print("判定:", "✅ 降维生效" if len(v) == 1024 else f"❌ 仍是 {len(v)} 维")
    await llm.aclose()


if __name__ == "__main__":
    asyncio.run(main())
