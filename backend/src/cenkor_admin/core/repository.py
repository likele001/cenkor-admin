"""通用仓储层：分页 + 搜索 + 软删。

把 list 端点重复的 `select + where deleted_at + count + offset/limit` 抽出来。
新增 list 端点只需指定：
- model：SQLAlchemy ORM 类
- search_fields：可搜索的列名列表
- extra_filters：额外的 where 条件 callable
"""
from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


async def paginate(
    db: AsyncSession,
    stmt: Select,
    *,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """对 stmt 做分页 + 总数统计，返回 `{items, total, page, page_size}`。

    会基于传入的 stmt 派生 count 查询（保证与列表条件一致）。
    """
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0
    paged = stmt.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(paged)).scalars().all()
    return {
        "items": list(items),
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


def soft_delete_filter(model) -> Any:
    """软删过滤（deleted_at IS NULL）。"""
    return model.deleted_at.is_(None)


def search_filter(
    model,
    search: str | None,
    fields: Sequence[str],
    *,
    case_insensitive: bool = True,
) -> Any:
    """跨字段模糊搜索。

    - search 为空/None 时返回恒真条件（不会过滤掉任何行）
    - 字段类型为数值类型时会跳过（避免 cast 报错）
    - PG: ILIKE；MySQL: LIKE（不区分大小写由 collation 控制）
    """
    if not search or not search.strip():
        return None
    keyword = f"%{search.strip()}%"
    column_objs = [getattr(model, f) for f in fields]
    conds = []
    for col in column_objs:
        col_type = col.type.__class__.__name__.lower()
        if "integer" in col_type or "float" in col_type or "numeric" in col_type or "boolean" in col_type:
            continue
        if case_insensitive and hasattr(col, "ilike"):
            conds.append(col.ilike(keyword))
        else:
            conds.append(col.like(keyword))
    if not conds:
        return None
    return or_(*conds)


def apply_filters(
    model,
    *,
    search: str | None = None,
    search_fields: Sequence[str] | None = None,
    extra: Sequence[Any] | None = None,
    include_deleted: bool = False,
    only_deleted: bool = False,
) -> list[Any]:
    """汇总：返回 where 条件列表（不含 deleted_at 之外的语义）。

    - include_deleted=False（默认）: 软删过滤（deleted_at IS NULL）
    - include_deleted=True: 不过滤 deleted_at
    - only_deleted=True: 只查已删除（deleted_at IS NOT NULL）
    """
    conds: list[Any] = []
    if hasattr(model, "deleted_at"):
        if only_deleted:
            conds.append(model.deleted_at.is_not(None))
        elif not include_deleted:
            conds.append(soft_delete_filter(model))
    if search and search_fields:
        s = search_filter(model, search, search_fields)
        if s is not None:
            conds.append(s)
    if extra:
        conds.extend([c for c in extra if c is not None])
    return conds


async def stream_for_csv(
    db: AsyncSession,
    base_stmt: Select,
    *,
    id_column,
    batch_size: int = 500,
):
    """按 batch 流式迭代，用于 CSV 导出（避免一次性加载大表到内存）。

    使用 keyset 思路在主键上分批；
    调用方需传入主键列，例如 `models.Product.id`。
    """
    last_id = 0
    while True:
        batch_stmt = (
            base_stmt.where(id_column > last_id)
            .order_by(id_column)
            .limit(batch_size)
        )
        result = await db.execute(batch_stmt)
        rows = result.scalars().all()
        if not rows:
            break
        for row in rows:
            yield row
        last_id = getattr(rows[-1], "id")
        if len(rows) < batch_size:
            break
