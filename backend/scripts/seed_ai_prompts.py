"""把 copilot.py 里现有的 5 套提示词作为 v1 存入 DB 并激活。

幂等：某个 key 已有任何版本就跳过（不覆盖运营已改过的内容）。
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import func, select

from cenkor_admin.apps.cms.ai import copilot
from cenkor_admin.apps.cms.ai.models import CmsAiPrompt
from cenkor_admin.core.db import AsyncSessionLocal

SOURCES = {
    "ct": lambda: copilot._CT_SYSTEM,
    "draft": lambda: copilot._DRAFT_SYSTEM,
    "translate": lambda: copilot._TRANSLATE_SYSTEM,
    "seo": lambda: copilot._SEO_SYSTEM,
    "rewrite": lambda: copilot._REWRITE_SYSTEM,
}


async def main() -> None:
    ok = skip = 0
    async with AsyncSessionLocal() as db:
        for key, getter in SOURCES.items():
            existing = (
                await db.execute(
                    select(func.count()).select_from(CmsAiPrompt).where(
                        CmsAiPrompt.prompt_key == key
                    )
                )
            ).scalar()
            if existing:
                print(f"  SKIP {key:10s} 已有 {existing} 个版本")
                skip += 1
                continue

            content = (getter() or "").strip()
            if not content:
                print(f"  WARN {key:10s} 代码常量为空，跳过")
                continue

            db.add(
                CmsAiPrompt(
                    prompt_key=key,
                    version=1,
                    content=content,
                    note="初始版本（来自代码常量）",
                    is_active=True,
                )
            )
            print(f"  OK   {key:10s} v1 已入库（{len(content)} 字）")
            ok += 1
        await db.commit()

    print(f"\n完成：新增 {ok} / 跳过 {skip}")
    if ok == 0 and skip == 0:
        sys.exit("异常：一个都没处理")


if __name__ == "__main__":
    asyncio.run(main())
