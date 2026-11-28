"""敏感词匹配。

只做两件确定性的事：
1. 归一化后做子串匹配（全半角、大小写、空格/常见分隔符）；
2. 命中 block 词就拒绝，命中 warn 词只提示。

不做「AI 语义判断」这一层：语义判断误杀率高，且每次提交都要一次模型调用，
成本不该花在每篇草稿上。确实需要模糊判断的，放审核环节人工看。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.sensitive_models import SensitiveWord

# 归一化时直接丢弃的分隔符：用户写「敏 感 词」也要能命中
_DROP = re.compile(r"[\s\-_·、,，.。*＊|/\\]+")


def normalize(text: str) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", str(text)).lower()
    return _DROP.sub("", t)


async def list_words(db: AsyncSession, site_id: int) -> list[SensitiveWord]:
    rows = (
        await db.execute(
            select(SensitiveWord)
            .where(
                or_(
                    SensitiveWord.scope == "global",
                    and_(SensitiveWord.scope == "site", SensitiveWord.site_id == site_id),
                )
            )
            .order_by(SensitiveWord.id.desc())
        )
    ).scalars().all()
    return list(rows)


async def check_text(db: AsyncSession, site_id: int, text: str) -> dict[str, Any]:
    """返回命中明细。`blocked=True` 时调用方应拒绝流程。"""
    norm_text = normalize(text)
    if not norm_text:
        return {"blocked": False, "hits": [], "checked": 0}

    words = await list_words(db, site_id)
    hits: list[dict[str, str]] = []
    for w in words:
        nw = normalize(w.word)
        if nw and nw in norm_text:
            hits.append({"word": w.word, "level": w.level, "scope": w.scope})

    blocked = any(h["level"] == "block" for h in hits)
    return {"blocked": blocked, "hits": hits, "checked": len(words)}
