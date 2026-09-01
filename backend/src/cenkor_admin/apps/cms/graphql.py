"""CMS GraphQL API（M2·P1 2.1）。

基于 strawberry，提供内容类型与条目的只读查询；
挂载于 /api/v1/cms/graphql（受后台鉴权保护），/graphiql 调试可用。
与现有 REST 并存，不互相影响。
"""
from __future__ import annotations

from typing import Any

import strawberry
from strawberry.fastapi import GraphQLRouter
from strawberry.types import Info
from sqlalchemy import select

from cenkor_admin.apps.cms import models
from cenkor_admin.core.db import get_db


# ============================================================
# GraphQL 类型
# ============================================================

@strawberry.type
class ContentTypeGQL:
    id: strawberry.ID
    key: str
    name: str
    description: str | None = None
    translatable: bool = False


@strawberry.type
class EntryGQL:
    id: strawberry.ID
    content_type_id: int
    slug: str | None = None
    title: str
    status: str
    published_at: str | None = None
    content: strawberry.scalars.JSON | None = None
    custom_fields: strawberry.scalars.JSON | None = None

    @classmethod
    def from_model(cls, e: models.Entry) -> "EntryGQL":
        return cls(
            id=str(e.id),
            content_type_id=e.content_type_id,
            slug=e.slug,
            title=e.title,
            status=e.status,
            published_at=e.published_at.isoformat() if e.published_at else None,
            content=e.content or {},
            custom_fields=e.custom_fields or {},
        )


# ============================================================
# Query
# ============================================================

@strawberry.type
class Query:
    @strawberry.field
    async def content_types(self, info: Info) -> list[ContentTypeGQL]:
        db = info.context["db"]
        rows = (await db.execute(
            select(models.ContentType).where(models.ContentType.deleted_at.is_(None))
        )).scalars().all()
        return [
            ContentTypeGQL(
                id=str(ct.id), key=ct.key, name=ct.name,
                description=ct.description, translatable=ct.translatable,
            )
            for ct in rows
        ]

    @strawberry.field
    async def entries(
        self,
        info: Info,
        content_type_key: str | None = None,
        status: str | None = None,
        first: int = 20,
        offset: int = 0,
    ) -> list[EntryGQL]:
        db = info.context["db"]
        conds = [models.Entry.deleted_at.is_(None)]
        if content_type_key:
            ct = (await db.execute(
                select(models.ContentType).where(models.ContentType.key == content_type_key)
            )).scalar_one_or_none()
            if ct:
                conds.append(models.Entry.content_type_id == ct.id)
        if status:
            conds.append(models.Entry.status == status)
        rows = (await db.execute(
            select(models.Entry).where(*conds)
            .order_by(models.Entry.id.desc()).offset(offset).limit(first)
        )).scalars().all()
        return [EntryGQL.from_model(e) for e in rows]

    @strawberry.field
    async def entry(self, info: Info, id: strawberry.ID) -> EntryGQL | None:
        db = info.context["db"]
        e = await db.get(models.Entry, int(id))
        if not e or e.deleted_at:
            return None
        return EntryGQL.from_model(e)


# ============================================================
# Schema + Router
# ============================================================

schema = strawberry.Schema(query=Query)


async def _graphql_context() -> dict[str, Any]:
    async for db in get_db():
        yield {"db": db}


graphql_router = GraphQLRouter(
    schema,
    path="/graphql",
    context_getter=_graphql_context,
    graphql_ide="graphiql",
)
