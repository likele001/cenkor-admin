"""会话记忆 —— 让同一篇内容的多个 AI 环节共享上下文。

问题不在「聊天断了」，而在「每个动作各自失明」：
- SEO 生成时只看得到了入库那一刻的标题，编辑后来改过三版它不知道；
- 翻译时不知道编辑要求过「参数口径统一用 MPa」；
- 再分发时不知道前一步已经把字数压到了 900。

所以按 `entry:{id}` 建会话，把每次 AI 动作的**输入要点 + 产出要点**记一轮。
下一次调用只读最近若干轮，压缩后拼进 system prompt 末尾。

三条铁律：
1. 只记要点，不记全文 —— 全文在条目和 cms_ai_generations 里，这里存了会漂。
2. 写入失败绝不能连带业务失败：会话记忆是增益，不是依赖。
3. 注入有预算上限 —— 条目本身的内容才是主体，记忆不能挤掉素材。
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import delete as sa_delete
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.ai.models import CmsAiSession, CmsAiSessionTurn

# 注入时最多带几轮
MAX_TURNS = 8
# 会话上下文预算（字符）。600 字符 ≈ 300 token，只是提示，不该喧宾夺主。
DEFAULT_BUDGET = 900

KIND_LABEL = {
    "note": "人工备注",
    "draft": "起草",
    "rewrite": "改写",
    "seo": "SEO",
    "translate": "翻译",
    "redistribute": "再分发",
    "tag": "打标签",
    "illustration": "配图",
    "video": "视频",
    "ask": "问答",
}


def _site_id() -> int:
    try:
        from cenkor_admin.core.site_scope import current_site_id

        return current_site_id() or 1
    except Exception:  # noqa: BLE001
        return 1


def _entry_key(entry_id: int) -> str:
    return f"entry:{entry_id}"


async def get_or_create_entry_session(
    session: AsyncSession, entry_id: int, *, title: str = "", created_by: int | None = None
) -> CmsAiSession:
    """取该条目的会话，没有就建。**不 commit**，交给调用方的事务。"""
    key = _entry_key(entry_id)
    row = (
        await session.execute(select(CmsAiSession).where(CmsAiSession.session_key == key))
    ).scalar_one_or_none()
    if row is not None:
        return row

    row = CmsAiSession(
        site_id=_site_id(),
        session_key=key,
        entry_id=entry_id,
        title=(title or "")[:200],
        turn_count=0,
        created_by=created_by,
    )
    session.add(row)
    try:
        await session.flush()
    except Exception:
        # 并发下可能被别人抢先插入，回滚这一次 flush 后再查一遍
        await session.rollback()
        row = (
            await session.execute(select(CmsAiSession).where(CmsAiSession.session_key == key))
        ).scalar_one()
    return row


async def add_turn(
    session: AsyncSession,
    entry_id: int,
    *,
    kind: str,
    content: str,
    role: str = "assistant",
    meta: dict[str, Any] | None = None,
    title: str = "",
    created_by: int | None = None,
    commit: bool = True,
) -> None:
    """记一轮。**任何异常都吞掉**——记忆写失败不该让用户的起草失败。"""
    text_value = (content or "").strip()
    if not text_value:
        return
    try:
        sess = await get_or_create_entry_session(
            session, entry_id, title=title, created_by=created_by
        )
        session.add(
            CmsAiSessionTurn(
                session_id=sess.id,
                role=role,
                kind=kind,
                content=text_value[:2000],
                meta=meta or None,
                created_by=created_by,
            )
        )
        sess.turn_count = int(sess.turn_count or 0) + 1
        if title and not sess.title:
            sess.title = title[:200]
        if commit:
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("cms.session_turn_failed entry={} kind={} err={}", entry_id, kind, exc)
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            pass


async def render_entry_context(
    session: AsyncSession, entry_id: int | None, *, budget: int = DEFAULT_BUDGET
) -> str:
    """把该条目最近的会话压成一段提示词。没有会话就返回空串。"""
    if not entry_id:
        return ""
    try:
        sess = (
            await session.execute(
                select(CmsAiSession).where(CmsAiSession.session_key == _entry_key(entry_id))
            )
        ).scalar_one_or_none()
        if sess is None:
            return ""

        rows = (
            (
                await session.execute(
                    select(CmsAiSessionTurn)
                    .where(CmsAiSessionTurn.session_id == sess.id)
                    .order_by(desc(CmsAiSessionTurn.created_at), desc(CmsAiSessionTurn.id))
                    .limit(MAX_TURNS)
                )
            )
            .scalars()
            .all()
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("cms.session_render_failed entry={} err={}", entry_id, exc)
        return ""

    if not rows:
        return ""

    lines: list[str] = ["【这份稿子的来龙去脉】（按时间倒序，供你保持一致，不要复述）"]
    used = len(lines[0])
    kept = 0
    for row in rows:  # 已按时间倒序，先放最近发生的
        label = KIND_LABEL.get(row.kind, row.kind)
        who = "人要求" if row.role == "user" else ("系统记录" if row.role == "system" else "AI 产出")
        line = f"- [{label}·{who}] {row.content.strip()}"
        if used + len(line) > budget:
            break
        lines.append(line)
        used += len(line)
        kept += 1

    if kept == 0:
        return ""
    return "\n".join(lines)


async def list_sessions(
    session: AsyncSession, *, limit: int = 50, keyword: str | None = None
) -> list[dict[str, Any]]:
    """会话列表（按最近活动倒序）。附带最后一轮的摘要，列表页不用二次请求。"""
    stmt = (
        select(CmsAiSession)
        .where(CmsAiSession.turn_count > 0)
        .order_by(desc(CmsAiSession.updated_at))
        .limit(max(1, min(limit, 200)))
    )
    if keyword:
        stmt = stmt.where(CmsAiSession.title.ilike(f"%{keyword.strip()}%"))
    rows = (await session.execute(stmt)).scalars().all()

    out: list[dict[str, Any]] = []
    for row in rows:
        last = (
            await session.execute(
                select(CmsAiSessionTurn)
                .where(CmsAiSessionTurn.session_id == row.id)
                .order_by(desc(CmsAiSessionTurn.created_at), desc(CmsAiSessionTurn.id))
                .limit(1)
            )
        ).scalar_one_or_none()
        out.append(
            {
                "id": row.id,
                "entry_id": row.entry_id,
                "title": row.title or "",
                "turn_count": row.turn_count,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "last_kind": KIND_LABEL.get(last.kind, last.kind) if last else "",
                "last_content": (last.content[:120] if last else ""),
            }
        )
    return out


async def get_session_detail(session: AsyncSession, session_id: int) -> dict[str, Any] | None:
    sess = (
        await session.execute(select(CmsAiSession).where(CmsAiSession.id == session_id))
    ).scalar_one_or_none()
    if sess is None:
        return None
    rows = (
        (
            await session.execute(
                select(CmsAiSessionTurn)
                .where(CmsAiSessionTurn.session_id == sess.id)
                .order_by(CmsAiSessionTurn.created_at, CmsAiSessionTurn.id)
            )
        )
        .scalars()
        .all()
    )
    return {
        "id": sess.id,
        "entry_id": sess.entry_id,
        "title": sess.title or "",
        "turn_count": sess.turn_count,
        "updated_at": sess.updated_at.isoformat() if sess.updated_at else None,
        "turns": [
            {
                "id": t.id,
                "role": t.role,
                "kind": t.kind,
                "kind_label": KIND_LABEL.get(t.kind, t.kind),
                "content": t.content,
                "meta": t.meta or {},
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in rows
        ],
    }


async def delete_session(session: AsyncSession, session_id: int) -> bool:
    row = (
        await session.execute(select(CmsAiSession).where(CmsAiSession.id == session_id))
    ).scalar_one_or_none()
    if row is None:
        return False
    await session.execute(sa_delete(CmsAiSessionTurn).where(CmsAiSessionTurn.session_id == session_id))
    await session.execute(sa_delete(CmsAiSession).where(CmsAiSession.id == session_id))
    await session.commit()
    return True


async def delete_turn(session: AsyncSession, turn_id: int) -> bool:
    row = (
        await session.execute(select(CmsAiSessionTurn).where(CmsAiSessionTurn.id == turn_id))
    ).scalar_one_or_none()
    if row is None:
        return False
    sess = (
        await session.execute(select(CmsAiSession).where(CmsAiSession.id == row.session_id))
    ).scalar_one_or_none()
    await session.execute(sa_delete(CmsAiSessionTurn).where(CmsAiSessionTurn.id == turn_id))
    if sess is not None:
        sess.turn_count = max(int(sess.turn_count or 1) - 1, 0)
    await session.commit()
    return True


async def session_stats(session: AsyncSession) -> dict[str, Any]:
    total = await session.scalar(select(func.count(CmsAiSession.id))) or 0
    turns = await session.scalar(select(func.count(CmsAiSessionTurn.id))) or 0
    notes = (
        await session.scalar(
            select(func.count(CmsAiSessionTurn.id)).where(CmsAiSessionTurn.kind == "note")
        )
        or 0
    )
    return {"sessions": int(total), "turns": int(turns), "notes": int(notes)}
