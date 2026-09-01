"""CMS 内容引擎路由（Content Types / Field Groups / Field Definitions / Field Options / Categories / Tags / Entries）"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, update, delete, or_, cast, Text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from cenkor_admin.api.deps import get_current_user, require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms import models, schemas
from cenkor_admin.apps.cms.field_types import FIELD_TYPES, NEEDS_OPTIONS, validate_field_value
from cenkor_admin.core.db import get_db
from cenkor_admin.core.hooks import dispatch
from cenkor_admin.core.repository import apply_filters, paginate

router = APIRouter()
log = logging.getLogger(__name__)


def _parse_dt(v: Any) -> datetime | None:
    """将 ISO 字符串/对象安全转为 tz-aware datetime（asyncpg timestamptz 拒绝裸字符串）。"""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        try:
            # Python 3.11+ fromisoformat 支持 'Z'
            return datetime.fromisoformat(v)
        except ValueError:
            return None
    return None


async def _snapshot_version(
    db: AsyncSession,
    entry: models.Entry,
    user_id: int | None,
    note: str | None = None,
) -> models.EntryVersion:
    """为 Entry 生成下一条版本快照（不可变，M1·P0 版本控制）。"""
    last = (await db.execute(
        select(func.max(models.EntryVersion.version))
        .where(models.EntryVersion.entry_id == entry.id)
    )).scalar()
    next_version = (last or 0) + 1
    snap = models.EntryVersion(
        entry_id=entry.id,
        version=next_version,
        data={
            "slug": entry.slug,
            "title": entry.title,
            "content": entry.content or {},
            "custom_fields": entry.custom_fields or {},
            "seo": entry.seo or {},
            "category_id": entry.category_id,
            "status": entry.status,
            "published_at": entry.published_at.isoformat() if entry.published_at else None,
            "scheduled_at": entry.scheduled_at.isoformat() if entry.scheduled_at else None,
            "expire_at": entry.expire_at.isoformat() if entry.expire_at else None,
            "sort": entry.sort,
        },
        created_by=user_id,
        note=note,
    )
    db.add(snap)
    await db.commit()
    await db.refresh(snap)
    return snap


# ============================================================
# Content Types
# ============================================================

@router.get("/content-types", response_model=dict[str, Any])
async def list_content_types(
    db: AsyncSession = Depends(get_db),
    search: str | None = Query(None),
    include_deleted: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    conds = apply_filters(
        models.ContentType,
        search=search,
        search_fields=["key", "name"],
        include_deleted=include_deleted,
    )
    stmt = (
        select(models.ContentType)
        .where(*conds)
        .options(
            selectinload(models.ContentType.field_groups),
            selectinload(models.ContentType.field_definitions)
            .selectinload(models.FieldDefinition.field_options),
        )
        .order_by(models.ContentType.id)
    )
    data = await paginate(db, stmt, page=page, page_size=page_size)
    return {
        "items": [schemas.ContentTypeOut.model_validate(ct).model_dump() for ct in data["items"]],
        "total": data["total"],
        "page": data["page"],
        "page_size": data["page_size"],
    }


@router.post("/content-types", response_model=schemas.ContentTypeOut, status_code=status.HTTP_201_CREATED)
async def create_content_type(
    body: schemas.ContentTypeCreate,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    existing = await db.execute(select(models.ContentType).where(models.ContentType.key == body.key))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Content type key 已存在: {body.key}")
    obj = models.ContentType(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    # 插件框架：触发 content_type 创建事件
    try:
        await dispatch("content_type.created", content_type=obj, db=db, user=current)
    except Exception as e:
        log.warning("hook.dispatch_failed", hook="content_type.created", error=str(e))
    return obj


@router.get("/content-types/{ct_id}", response_model=schemas.ContentTypeOut)
async def get_content_type(ct_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(models.ContentType)
        .where(models.ContentType.id == ct_id, models.ContentType.deleted_at.is_(None))
        .options(
            selectinload(models.ContentType.field_groups),
            selectinload(models.ContentType.field_definitions)
            .selectinload(models.FieldDefinition.field_options),
        )
    )
    obj = (await db.execute(stmt)).unique().scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Content type not found")
    return obj


@router.patch("/content-types/{ct_id}", response_model=schemas.ContentTypeOut)
async def update_content_type(
    ct_id: int,
    body: schemas.ContentTypeUpdate,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    obj = await db.get(models.ContentType, ct_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "Content type not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/content-types/{ct_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_content_type(
    ct_id: int,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    obj = await db.get(models.ContentType, ct_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "Content type not found")
    await db.execute(
        update(models.ContentType).where(models.ContentType.id == ct_id).values(deleted_at=func.now())
    )
    await db.commit()
    # 插件框架：触发 content_type 删除事件
    try:
        await dispatch("content_type.deleted", content_type_id=ct_id, db=db, user=current)
    except Exception as e:
        log.warning("hook.dispatch_failed", hook="content_type.deleted", error=str(e))


@router.post("/content-types/{ct_id}/restore", status_code=200)
async def restore_content_type(ct_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(
        update(models.ContentType).where(models.ContentType.id == ct_id).values(deleted_at=None)
    )
    await db.commit()
    return {"id": ct_id, "restored": True}


# ============================================================
# Field Groups
# ============================================================

@router.get("/content-types/{ct_id}/field-groups", response_model=list[schemas.FieldGroupOut])
async def list_field_groups(ct_id: int, db: AsyncSession = Depends(get_db)):
    ct = await db.get(models.ContentType, ct_id)
    if not ct or ct.deleted_at:
        raise HTTPException(404, "Content type not found")
    result = await db.execute(
        select(models.FieldGroup)
        .where(models.FieldGroup.content_type_id == ct_id)
        .order_by(models.FieldGroup.sort)
    )
    return result.scalars().all()


@router.post("/content-types/{ct_id}/field-groups", response_model=schemas.FieldGroupOut, status_code=status.HTTP_201_CREATED)
async def create_field_group(
    ct_id: int,
    body: schemas.FieldGroupCreate,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    ct = await db.get(models.ContentType, ct_id)
    if not ct or ct.deleted_at:
        raise HTTPException(404, "Content type not found")
    existing = await db.execute(
        select(models.FieldGroup).where(
            models.FieldGroup.content_type_id == ct_id,
            models.FieldGroup.key == body.key,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Field group key '{body.key}' 已存在")
    obj = models.FieldGroup(content_type_id=ct_id, **body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.patch("/content-types/{ct_id}/field-groups/{gid}", response_model=schemas.FieldGroupOut)
async def update_field_group(
    ct_id: int,
    gid: int,
    body: schemas.FieldGroupUpdate,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    obj = await db.get(models.FieldGroup, gid)
    if not obj or obj.content_type_id != ct_id:
        raise HTTPException(404, "Field group not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/content-types/{ct_id}/field-groups/{gid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_field_group(
    ct_id: int, gid: int,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    obj = await db.get(models.FieldGroup, gid)
    if not obj or obj.content_type_id != ct_id:
        raise HTTPException(404, "Field group not found")
    await db.delete(obj)
    await db.commit()


@router.post("/content-types/{ct_id}/field-groups/reorder", status_code=200)
async def reorder_field_groups(
    ct_id: int,
    body: schemas.ReorderRequest,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    for item in body.items:
        await db.execute(
            update(models.FieldGroup)
            .where(models.FieldGroup.id == item.id, models.FieldGroup.content_type_id == ct_id)
            .values(sort=item.sort)
        )
    await db.commit()
    return {"updated": len(body.items)}


# ============================================================
# Field Definitions
# ============================================================

@router.get("/content-types/{ct_id}/field-definitions", response_model=list[schemas.FieldDefinitionOut])
async def list_field_definitions(ct_id: int, db: AsyncSession = Depends(get_db)):
    ct = await db.get(models.ContentType, ct_id)
    if not ct or ct.deleted_at:
        raise HTTPException(404, "Content type not found")
    stmt = (
        select(models.FieldDefinition)
        .where(models.FieldDefinition.content_type_id == ct_id)
        .options(selectinload(models.FieldDefinition.field_options))
        .order_by(models.FieldDefinition.sort)
    )
    result = await db.execute(stmt)
    return result.unique().scalars().all()


@router.post("/content-types/{ct_id}/field-definitions", response_model=schemas.FieldDefinitionOut, status_code=status.HTTP_201_CREATED)
async def create_field_definition(
    ct_id: int,
    body: schemas.FieldDefinitionCreate,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    ct = await db.get(models.ContentType, ct_id)
    if not ct or ct.deleted_at:
        raise HTTPException(404, "Content type not found")
    if body.field_type not in FIELD_TYPES:
        raise HTTPException(400, f"Invalid field_type: {body.field_type}")
    existing = await db.execute(
        select(models.FieldDefinition).where(
            models.FieldDefinition.content_type_id == ct_id,
            models.FieldDefinition.field_key == body.field_key,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Field key '{body.field_key}' 已存在")
    if body.group_id:
        fg = await db.get(models.FieldGroup, body.group_id)
        if not fg or fg.content_type_id != ct_id:
            raise HTTPException(400, f"Field group {body.group_id} 不属于此内容类型")
    obj = models.FieldDefinition(
        content_type_id=ct_id,
        created_by=current.id,
        **body.model_dump(),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/field-definitions/{fd_id}", response_model=schemas.FieldDefinitionOut)
async def get_field_definition(fd_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(models.FieldDefinition)
        .where(models.FieldDefinition.id == fd_id)
        .options(selectinload(models.FieldDefinition.field_options))
    )
    obj = (await db.execute(stmt)).unique().scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Field definition not found")
    return obj


@router.patch("/field-definitions/{fd_id}", response_model=schemas.FieldDefinitionOut)
async def update_field_definition(
    fd_id: int,
    body: schemas.FieldDefinitionUpdate,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    obj = await db.get(models.FieldDefinition, fd_id)
    if not obj:
        raise HTTPException(404, "Field definition not found")
    if body.field_type is not None and body.field_type not in FIELD_TYPES:
        raise HTTPException(400, f"Invalid field_type: {body.field_type}")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/field-definitions/{fd_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_field_definition(
    fd_id: int,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    obj = await db.get(models.FieldDefinition, fd_id)
    if not obj:
        raise HTTPException(404, "Field definition not found")
    await db.delete(obj)
    await db.commit()


@router.post("/content-types/{ct_id}/field-definitions/reorder", status_code=200)
async def reorder_field_definitions(
    ct_id: int,
    body: schemas.ReorderRequest,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    for item in body.items:
        await db.execute(
            update(models.FieldDefinition)
            .where(models.FieldDefinition.id == item.id, models.FieldDefinition.content_type_id == ct_id)
            .values(sort=item.sort)
        )
    await db.commit()
    return {"updated": len(body.items)}


# ============================================================
# Field Options
# ============================================================

@router.get("/field-definitions/{fd_id}/options", response_model=list[schemas.FieldOptionOut])
async def list_field_options(fd_id: int, db: AsyncSession = Depends(get_db)):
    fd = await db.get(models.FieldDefinition, fd_id)
    if not fd:
        raise HTTPException(404, "Field definition not found")
    result = await db.execute(
        select(models.FieldOption)
        .where(models.FieldOption.definition_id == fd_id)
        .order_by(models.FieldOption.sort)
    )
    return result.scalars().all()


@router.post("/field-options", response_model=schemas.FieldOptionOut, status_code=status.HTTP_201_CREATED)
async def create_field_option(
    body: schemas.FieldOptionCreate,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    fd = await db.get(models.FieldDefinition, body.definition_id)
    if not fd:
        raise HTTPException(404, "Field definition not found")
    if fd.field_type not in NEEDS_OPTIONS:
        raise HTTPException(400, f"Field type '{fd.field_type}' 不支持选项")
    obj = models.FieldOption(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.patch("/field-options/{opt_id}", response_model=schemas.FieldOptionOut)
async def update_field_option(
    opt_id: int,
    body: schemas.FieldOptionUpdate,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    obj = await db.get(models.FieldOption, opt_id)
    if not obj:
        raise HTTPException(404, "Field option not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/field-options/{opt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_field_option(
    opt_id: int,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    obj = await db.get(models.FieldOption, opt_id)
    if not obj:
        raise HTTPException(404, "Field option not found")
    await db.delete(obj)
    await db.commit()


# ============================================================
# Categories
# ============================================================

@router.get("/categories", response_model=dict[str, Any])
async def list_categories(
    db: AsyncSession = Depends(get_db),
    content_type_key: str | None = Query(None),
    parent_id: int | None = Query(None),
    include_deleted: bool = Query(False),
):
    conds = []
    if content_type_key:
        ct = (await db.execute(
            select(models.ContentType).where(models.ContentType.key == content_type_key)
        )).scalar_one_or_none()
        if ct:
            conds.append(models.Category.content_type_id == ct.id)
    if parent_id is not None:
        conds.append(models.Category.parent_id == parent_id)
    if not include_deleted:
        conds.append(models.Category.deleted_at.is_(None))

    stmt = select(models.Category).where(*conds).order_by(models.Category.sort)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return {"items": [_category_to_dict(c) for c in items]}


@router.get("/categories/tree", response_model=list[dict[str, Any]])
async def category_tree(
    db: AsyncSession = Depends(get_db),
    content_type_key: str = Query(...),
):
    ct = (await db.execute(
        select(models.ContentType).where(models.ContentType.key == content_type_key)
    )).scalar_one_or_none()
    if not ct:
        raise HTTPException(404, f"Content type '{content_type_key}' not found")
    result = await db.execute(
        select(models.Category)
        .where(models.Category.content_type_id == ct.id, models.Category.deleted_at.is_(None))
        .order_by(models.Category.sort)
    )
    all_cats = result.scalars().all()
    tree = _build_category_tree(all_cats)
    return tree


@router.post("/categories", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_category(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    ct_key = body.get("content_type_key") or body.get("content_type_id")
    if not ct_key:
        raise HTTPException(400, "content_type_key or content_type_id required")
    if isinstance(ct_key, str):
        ct = (await db.execute(
            select(models.ContentType).where(models.ContentType.key == ct_key)
        )).scalar_one_or_none()
        if not ct:
            raise HTTPException(404, f"Content type '{ct_key}' not found")
        ct_id = ct.id
    else:
        ct_id = ct_key
    slug = body.get("slug")
    name = body.get("name")
    if not slug or not name:
        raise HTTPException(400, "slug and name required")
    obj = models.Category(
        content_type_id=ct_id,
        parent_id=body.get("parent_id"),
        slug=slug,
        name=name,
        icon=body.get("icon"),
        color=body.get("color"),
        sort=body.get("sort", 0),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _category_to_dict(obj)


@router.patch("/categories/{cat_id}", response_model=dict[str, Any])
async def update_category(
    cat_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    obj = await db.get(models.Category, cat_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "Category not found")
    for k in ("name", "slug", "icon", "color", "sort", "status", "parent_id"):
        if k in body:
            setattr(obj, k, body[k])
    await db.commit()
    await db.refresh(obj)
    return _category_to_dict(obj)


@router.delete("/categories/{cat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    cat_id: int,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    obj = await db.get(models.Category, cat_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "Category not found")
    child_count = (await db.execute(
        select(func.count()).select_from(models.Category)
        .where(models.Category.parent_id == cat_id, models.Category.deleted_at.is_(None))
    )).scalar()
    if child_count and child_count > 0:
        raise HTTPException(400, f"该分类下还有 {child_count} 个子分类，请先移动或删除")
    await db.execute(
        update(models.Category).where(models.Category.id == cat_id).values(deleted_at=func.now())
    )
    await db.commit()


@router.post("/categories/reorder", status_code=200)
async def reorder_categories(
    body: schemas.ReorderRequest,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    for item in body.items:
        await db.execute(
            update(models.Category).where(models.Category.id == item.id).values(sort=item.sort)
        )
    await db.commit()
    return {"updated": len(body.items)}


# ============================================================
# Tags
# ============================================================

@router.get("/tags", response_model=dict[str, Any])
async def list_tags(
    db: AsyncSession = Depends(get_db),
    content_type_key: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    conds = []
    if content_type_key:
        ct = (await db.execute(
            select(models.ContentType).where(models.ContentType.key == content_type_key)
        )).scalar_one_or_none()
        if ct:
            conds.append(models.Tag.content_type_id == ct.id)
    if search:
        conds.append(models.Tag.name.ilike(f"%{search}%"))
    stmt = select(models.Tag).where(*conds).order_by(models.Tag.name)
    data = await paginate(db, stmt, page=page, page_size=page_size)
    return {
        "items": [_tag_to_dict(t) for t in data["items"]],
        "total": data["total"],
        "page": data["page"],
        "page_size": data["page_size"],
    }


@router.post("/tags", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_tag(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    ct_key = body.get("content_type_key") or body.get("content_type_id")
    if not ct_key:
        raise HTTPException(400, "content_type_key or content_type_id required")
    if isinstance(ct_key, str):
        ct = (await db.execute(
            select(models.ContentType).where(models.ContentType.key == ct_key)
        )).scalar_one_or_none()
        if not ct:
            raise HTTPException(404, f"Content type '{ct_key}' not found")
        ct_id = ct.id
    else:
        ct_id = ct_key
    slug = body.get("slug")
    name = body.get("name")
    if not slug or not name:
        raise HTTPException(400, "slug and name required")
    existing = await db.execute(
        select(models.Tag).where(
            models.Tag.content_type_id == ct_id,
            models.Tag.slug == slug,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Tag slug '{slug}' 已存在")
    obj = models.Tag(
        content_type_id=ct_id,
        slug=slug,
        name=name,
        color=body.get("color"),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _tag_to_dict(obj)


@router.patch("/tags/{tag_id}", response_model=dict[str, Any])
async def update_tag(
    tag_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    obj = await db.get(models.Tag, tag_id)
    if not obj:
        raise HTTPException(404, "Tag not found")
    for k in ("name", "slug", "color"):
        if k in body:
            setattr(obj, k, body[k])
    await db.commit()
    await db.refresh(obj)
    return _tag_to_dict(obj)


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    obj = await db.get(models.Tag, tag_id)
    if not obj:
        raise HTTPException(404, "Tag not found")
    await db.delete(obj)
    await db.commit()


# ============================================================
# Entries (通用内容)
# ============================================================

@router.get("/entries", response_model=dict[str, Any])
async def list_entries(
    db: AsyncSession = Depends(get_db),
    content_type_key: str | None = Query(None),
    category_id: int | None = Query(None),
    tag_id: int | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None),
    include_deleted: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    conds = apply_filters(
        models.Entry,
        search=search,
        search_fields=["title", "slug"],
        include_deleted=include_deleted,
    )
    if content_type_key:
        ct = (await db.execute(
            select(models.ContentType).where(models.ContentType.key == content_type_key)
        )).scalar_one_or_none()
        if ct:
            conds.append(models.Entry.content_type_id == ct.id)
    if category_id:
        conds.append(models.Entry.category_id == category_id)
    if status_filter:
        conds.append(models.Entry.status == status_filter)
    if tag_id:
        conds.append(models.Entry.id.in_(
            select(models.ContentTag.content_id).where(models.ContentTag.tag_id == tag_id)
        ))
    stmt = select(models.Entry).where(*conds).order_by(models.Entry.sort, models.Entry.id.desc())
    data = await paginate(db, stmt, page=page, page_size=page_size)
    return {
        "items": [_entry_to_dict(e) for e in data["items"]],
        "total": data["total"],
        "page": data["page"],
        "page_size": data["page_size"],
    }


@router.post("/entries", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_entry(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    ct_key = body.get("content_type_key") or body.get("content_type_id")
    if not ct_key:
        raise HTTPException(400, "content_type_key or content_type_id required")
    if isinstance(ct_key, str):
        ct = (await db.execute(
            select(models.ContentType).where(models.ContentType.key == ct_key)
        )).scalar_one_or_none()
        if not ct:
            raise HTTPException(404, f"Content type '{ct_key}' not found")
        ct_id = ct.id
    else:
        ct_id = ct_key

    title = body.get("title")
    if not title:
        raise HTTPException(400, "title required")

    tag_ids = body.pop("tag_ids", [])

    if "content_type_key" in body:
        del body["content_type_key"]

    obj = models.Entry(
        content_type_id=ct_id,
        slug=body.get("slug"),
        title=title,
        content=body.get("content", {}),
        custom_fields=body.get("custom_fields", {}),
        seo=body.get("seo"),
        category_id=body.get("category_id"),
        status=body.get("status", "draft"),
        author_id=current.id,
        published_at=_parse_dt(body.get("published_at")),
        scheduled_at=_parse_dt(body.get("scheduled_at")),
        expire_at=_parse_dt(body.get("expire_at")),
        sort=body.get("sort", 0),
    )
    db.add(obj)
    await db.flush()

    for tid in tag_ids:
        db.add(models.ContentTag(
            content_type_id=ct_id,
            content_id=obj.id,
            tag_id=tid,
        ))

    await db.commit()
    await db.refresh(obj)
    # 插件框架：触发 entry 保存/创建事件（失败隔离）
    try:
        await dispatch("entry.created", entry=obj, db=db, user=current)
        await dispatch("entry.saved", entry=obj, db=db, user=current)
    except Exception as e:
        log.warning("hook.dispatch_failed", hook="entry.saved", error=str(e))
    # 版本控制：创建时生成 v1 快照
    try:
        await _snapshot_version(db, obj, current.id, note="创建")
    except Exception as e:
        log.warning("version.snapshot_failed", entry_id=obj.id, error=str(e))
    return _entry_to_dict(obj)


@router.get("/entries/{entry_id}", response_model=dict[str, Any])
async def get_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(models.Entry, entry_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "Entry not found")
    return _entry_to_dict(obj)


@router.patch("/entries/{entry_id}", response_model=dict[str, Any])
async def update_entry(
    entry_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    obj = await db.get(models.Entry, entry_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "Entry not found")

    tag_ids = body.pop("tag_ids", None)
    for k in ("title", "slug", "content", "custom_fields", "seo", "category_id", "status", "sort"):
        if k in body:
            setattr(obj, k, body[k])
    for k in ("published_at", "scheduled_at", "expire_at"):
        if k in body:
            setattr(obj, k, _parse_dt(body[k]))

    if tag_ids is not None:
        await db.execute(
            models.ContentTag.__table__.delete().where(
                models.ContentTag.c.content_id == entry_id,
                models.ContentTag.c.content_type_id == obj.content_type_id,
            )
        )
        for tid in tag_ids:
            db.add(models.ContentTag(
                content_type_id=obj.content_type_id,
                content_id=obj.id,
                tag_id=tid,
            ))

    await db.commit()
    await db.refresh(obj)
    # 插件框架：触发 entry 更新/保存事件（失败隔离）
    try:
        await dispatch("entry.updated", entry=obj, db=db, user=current)
        await dispatch("entry.saved", entry=obj, db=db, user=current)
    except Exception as e:
        log.warning("hook.dispatch_failed", hook="entry.saved", error=str(e))
    # 版本控制：更新后生成新快照
    try:
        await _snapshot_version(db, obj, current.id, note="更新")
    except Exception as e:
        log.warning("version.snapshot_failed", entry_id=obj.id, error=str(e))
    return _entry_to_dict(obj)


@router.get("/entries/{entry_id}/versions", response_model=dict[str, Any])
async def list_entry_versions(entry_id: int, db: AsyncSession = Depends(get_db)):
    """版本历史列表（不含 data，保持轻量，M1·P0 版本控制）。"""
    entry = await db.get(models.Entry, entry_id)
    if not entry or entry.deleted_at:
        raise HTTPException(404, "Entry not found")
    rows = (await db.execute(
        select(models.EntryVersion)
        .where(models.EntryVersion.entry_id == entry_id)
        .order_by(models.EntryVersion.version.desc())
    )).scalars().all()
    return {
        "items": [_version_to_dict(v, include_data=False) for v in rows],
        "total": len(rows),
    }


@router.get("/entries/{entry_id}/versions/{version}", response_model=dict[str, Any])
async def get_entry_version(entry_id: int, version: int, db: AsyncSession = Depends(get_db)):
    """单个版本快照详情。"""
    v = (await db.execute(
        select(models.EntryVersion).where(
            models.EntryVersion.entry_id == entry_id,
            models.EntryVersion.version == version,
        )
    )).scalar_one_or_none()
    if not v:
        raise HTTPException(404, "Version not found")
    return _version_to_dict(v, include_data=True)


@router.post("/entries/{entry_id}/restore/{version}", response_model=dict[str, Any])
async def restore_entry_version(
    entry_id: int,
    version: int,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    """回滚到指定版本：先快照当前状态（回滚可回滚），再覆盖内容。"""
    entry = await db.get(models.Entry, entry_id)
    if not entry or entry.deleted_at:
        raise HTTPException(404, "Entry not found")
    v = (await db.execute(
        select(models.EntryVersion).where(
            models.EntryVersion.entry_id == entry_id,
            models.EntryVersion.version == version,
        )
    )).scalar_one_or_none()
    if not v:
        raise HTTPException(404, f"Version {version} not found")

    # 先快照当前状态（回滚本身也是可回滚的）
    try:
        await _snapshot_version(db, entry, current.id, note=f"回滚前 v{version}")
    except Exception as e:
        log.warning("version.snapshot_failed", entry_id=entry.id, error=str(e))

    data = v.data or {}
    for k in ("slug", "title", "content", "custom_fields", "seo", "category_id", "status", "sort"):
        if k in data:
            setattr(entry, k, data[k])
    for k in ("published_at", "scheduled_at", "expire_at"):
        if k in data and data[k]:
            from datetime import datetime as _dt
            try:
                setattr(entry, k, _dt.fromisoformat(data[k]))
            except ValueError:
                setattr(entry, k, None)
    await db.commit()
    await db.refresh(entry)
    # 版本控制：回滚后追加一条"回滚自 vN"快照
    try:
        await _snapshot_version(db, entry, current.id, note=f"回滚自 v{version}")
    except Exception as e:
        log.warning("version.snapshot_failed", entry_id=entry.id, error=str(e))
    return _entry_to_dict(entry)


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    obj = await db.get(models.Entry, entry_id)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "Entry not found")
    await db.execute(
        update(models.Entry).where(models.Entry.id == entry_id).values(deleted_at=func.now())
    )
    await db.commit()
    # 插件框架：触发 entry 删除事件
    try:
        await dispatch("entry.deleted", entry_id=entry_id, db=db, user=current)
    except Exception as e:
        log.warning("hook.dispatch_failed", hook="entry.deleted", error=str(e))


@router.post("/entries/batch-delete", status_code=200)
async def batch_delete_entries(body: dict, db: AsyncSession = Depends(get_db)):
    ids = body.get("ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(400, "ids 必须是非空数组")
    await db.execute(
        update(models.Entry).where(models.Entry.id.in_(ids)).values(deleted_at=func.now())
    )
    await db.commit()
    return {"deleted": len(ids)}


@router.post("/entries/batch-status", status_code=200)
async def batch_update_entry_status(body: dict, db: AsyncSession = Depends(get_db)):
    ids = body.get("ids") or []
    new_status = body.get("status")
    if not isinstance(ids, list) or not ids or new_status not in ("draft", "published", "archived"):
        raise HTTPException(400, "参数错误")
    await db.execute(
        update(models.Entry).where(models.Entry.id.in_(ids)).values(status=new_status)
    )
    await db.commit()
    return {"updated": len(ids), "status": new_status}


# ---- 定时发布调度：手动触发（M2·P1 2.5） ----
@router.post("/entries/scheduler/run", status_code=200)
async def run_entry_scheduler(
    current: auth_models.User = Depends(get_current_user),
):
    """立即执行一次定时发布/下线扫描（用于调试或手动触发）。"""
    from cenkor_admin.core.scheduler import scheduler_tick
    return await scheduler_tick()


# ============================================================
# M2·P1 站内全文搜索 / 批量导入 / 发布工作流
# ============================================================

@router.get("/search", response_model=dict[str, Any])
async def search_entries(
    q: str = Query(..., min_length=1, description="关键词"),
    db: AsyncSession = Depends(get_db),
    content_type_key: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """全文搜索（管理端）：匹配标题 / slug / 正文 / 自定义字段文本。"""
    like = f"%{q}%"
    conds = [
        models.Entry.deleted_at.is_(None),
        or_(
            models.Entry.title.ilike(like),
            models.Entry.slug.ilike(like),
            cast(models.Entry.content, Text).ilike(like),
            cast(models.Entry.custom_fields, Text).ilike(like),
        ),
    ]
    if content_type_key:
        ct = (await db.execute(
            select(models.ContentType).where(models.ContentType.key == content_type_key)
        )).scalar_one_or_none()
        if ct:
            conds.append(models.Entry.content_type_id == ct.id)
    if status_filter:
        conds.append(models.Entry.status == status_filter)
    stmt = select(models.Entry).where(*conds).order_by(models.Entry.updated_at.desc())
    data = await paginate(db, stmt, page=page, page_size=page_size)
    return {
        "items": [_entry_to_dict(e) for e in data["items"]],
        "total": data["total"],
        "page": data["page"],
        "page_size": data["page_size"],
    }


@router.post("/entries/import", status_code=200)
async def import_entries(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    """批量导入（M2·P1 2.3）：支持 JSON 数组 或 CSV 字符串。

    body 结构：
      content_type_key: 目标内容类型 key
      items: [{title, slug?, content?, custom_fields?, category_id?, status?,
               published_at?, scheduled_at?, expire_at?, sort?}, ...]
      csv:   "title,slug\\n标题一,slug-one\\n..."（与 items 二选一）
      upsert: true（默认）时按 slug 更新已存在条目，否则视为重复跳过
    """
    ct_key = body.get("content_type_key")
    if not ct_key:
        raise HTTPException(400, "content_type_key required")
    ct = (await db.execute(
        select(models.ContentType).where(models.ContentType.key == ct_key)
    )).scalar_one_or_none()
    if not ct:
        raise HTTPException(404, f"Content type '{ct_key}' not found")

    raw_items: list[dict] = list(body.get("items") or [])
    csv_text = body.get("csv")
    if csv_text:
        import csv as _csv
        import io as _io
        reader = _csv.DictReader(_io.StringIO(csv_text))
        raw_items = [dict(row) for row in reader]
    if not raw_items:
        raise HTTPException(400, "items 或 csv 不能为空")

    upsert = bool(body.get("upsert", True))
    results: list[dict[str, Any]] = []
    created = updated = failed = 0
    for i, item in enumerate(raw_items, 1):
        try:
            title = item.get("title")
            if not title:
                raise ValueError("title 必填")
            slug = item.get("slug") or None
            existing = None
            if slug and upsert:
                existing = (await db.execute(
                    select(models.Entry).where(
                        models.Entry.content_type_id == ct.id,
                        models.Entry.slug == slug,
                        models.Entry.deleted_at.is_(None),
                    )
                )).scalar_one_or_none()
            if existing:
                for k in ("title", "content", "custom_fields", "seo", "category_id", "status", "sort"):
                    if k in item:
                        setattr(existing, k, item[k])
                for k in ("published_at", "scheduled_at", "expire_at"):
                    if k in item:
                        setattr(existing, k, _parse_dt(item[k]))
                await db.commit()
                await db.refresh(existing)
                try:
                    await _snapshot_version(db, existing, current.id, note="批量导入更新")
                except Exception:
                    pass
                updated += 1
                results.append({"row": i, "ok": True, "action": "updated", "id": existing.id})
            else:
                obj = models.Entry(
                    content_type_id=ct.id,
                    slug=slug,
                    title=title,
                    content=item.get("content", {}),
                    custom_fields=item.get("custom_fields", {}),
                    seo=item.get("seo"),
                    category_id=item.get("category_id"),
                    status=item.get("status", "draft"),
                    author_id=current.id,
                    published_at=_parse_dt(item.get("published_at")),
                    scheduled_at=_parse_dt(item.get("scheduled_at")),
                    expire_at=_parse_dt(item.get("expire_at")),
                    sort=item.get("sort", 0),
                )
                db.add(obj)
                await db.commit()
                await db.refresh(obj)
                try:
                    await _snapshot_version(db, obj, current.id, note="批量导入创建")
                except Exception:
                    pass
                created += 1
                results.append({"row": i, "ok": True, "action": "created", "id": obj.id})
        except Exception as e:  # noqa: BLE001 - 逐行隔离
            failed += 1
            results.append({"row": i, "ok": False, "error": str(e)[:200]})
    return {
        "total": len(raw_items), "created": created,
        "updated": updated, "failed": failed, "results": results,
    }


# ---- 发布工作流（M2·P1 2.4）----
async def _write_review_log(
    db: AsyncSession, *, entry_id: int, old: str, new: str,
    action: str, reviewer_id: int | None, comment: str | None = None,
) -> None:
    """仅将审批记录加入 session（由调用方统一 commit，保证原子性）。"""
    db.add(models.EntryReviewLog(
        entry_id=entry_id, from_status=old, to_status=new,
        action=action, reviewer_id=reviewer_id, comment=comment,
    ))


@router.post("/entries/{entry_id}/submit-review", response_model=dict[str, Any])
async def submit_entry_for_review(
    entry_id: int,
    body: dict | None = None,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    """提交审核：draft / approved → pending_review。body 可选 {comment}。"""
    entry = await db.get(models.Entry, entry_id)
    if not entry or entry.deleted_at:
        raise HTTPException(404, "Entry not found")
    if entry.status not in ("draft", "approved"):
        raise HTTPException(400, f"当前状态 {entry.status} 不能提交审核")
    old = entry.status
    entry.status = "pending_review"
    await _write_review_log(
        db, entry_id=entry_id, old=old, new="pending_review", action="submit",
        reviewer_id=current.id, comment=(body or {}).get("comment"),
    )
    await db.commit()
    await db.refresh(entry)
    return _entry_to_dict(entry)


@router.post("/entries/{entry_id}/review", response_model=dict[str, Any])
async def review_entry(
    entry_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(require_permission("cms:entry:review")),
):
    """审批：body {action: approve|reject, comment?}。approve→published，reject→draft。"""
    entry = await db.get(models.Entry, entry_id)
    if not entry or entry.deleted_at:
        raise HTTPException(404, "Entry not found")
    if entry.status != "pending_review":
        raise HTTPException(400, f"当前状态 {entry.status} 不在待审核")
    action = body.get("action")
    if action not in ("approve", "reject"):
        raise HTTPException(400, "action 必须是 approve / reject")
    old = entry.status
    if action == "approve":
        entry.status = "published"
        if not entry.published_at:
            entry.published_at = datetime.now(timezone.utc)
    else:
        entry.status = "draft"
    await _write_review_log(
        db, entry_id=entry_id, old=old, new=entry.status, action=action,
        reviewer_id=current.id, comment=body.get("comment"),
    )
    await db.commit()
    await db.refresh(entry)
    return _entry_to_dict(entry)


@router.get("/entries/{entry_id}/review-log", response_model=dict[str, Any])
async def list_entry_review_log(entry_id: int, db: AsyncSession = Depends(get_db)):
    """审批时间线。"""
    rows = (await db.execute(
        select(models.EntryReviewLog)
        .where(models.EntryReviewLog.entry_id == entry_id)
        .order_by(models.EntryReviewLog.id.desc())
    )).scalars().all()
    return {
        "items": [{
            "id": r.id, "action": r.action,
            "from_status": r.from_status, "to_status": r.to_status,
            "reviewer_id": r.reviewer_id, "comment": r.comment,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in rows],
        "total": len(rows),
    }


# ============================================================
# 多语言 i18n（M1·P0）
# ============================================================

@router.get("/languages", response_model=dict[str, Any])
async def list_languages(db: AsyncSession = Depends(get_db)):
    """语言列表（默认语言置顶）。"""
    rows = (await db.execute(
        select(models.Language).order_by(models.Language.is_default.desc(), models.Language.sort, models.Language.id)
    )).scalars().all()
    return {"items": [_language_to_dict(l) for l in rows], "total": len(rows)}


@router.post("/languages", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_language(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    """新增语言。code 示例：en-US / zh-CN / ja-JP。"""
    code = body.get("code")
    name = body.get("name")
    if not code or not name:
        raise HTTPException(400, "code and name required")
    existing = await db.execute(select(models.Language).where(models.Language.code == code))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Language '{code}' 已存在")
    if body.get("is_default"):
        await db.execute(update(models.Language).values(is_default=False))
    obj = models.Language(
        code=code, name=name,
        flag=body.get("flag"),
        is_default=body.get("is_default", False),
        enabled=body.get("enabled", True),
        sort=body.get("sort", 0),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _language_to_dict(obj)


@router.patch("/languages/{code}", response_model=dict[str, Any])
async def update_language(
    code: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    """更新语言（设为默认时自动取消其它默认）。"""
    obj = (await db.execute(select(models.Language).where(models.Language.code == code))).scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Language not found")
    if body.get("is_default"):
        await db.execute(update(models.Language).values(is_default=False))
    for k in ("name", "flag", "is_default", "enabled", "sort"):
        if k in body:
            setattr(obj, k, body[k])
    await db.commit()
    await db.refresh(obj)
    return _language_to_dict(obj)


@router.delete("/languages/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_language(
    code: str,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    """删除语言（默认语言不可删；同时清理其翻译）。"""
    obj = (await db.execute(select(models.Language).where(models.Language.code == code))).scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Language not found")
    if obj.is_default:
        raise HTTPException(400, "不能删除默认语言")
    await db.execute(delete(models.EntryTranslation).where(models.EntryTranslation.lang == code))
    await db.delete(obj)
    await db.commit()


@router.get("/entries/{entry_id}/translations", response_model=dict[str, Any])
async def list_entry_translations(entry_id: int, db: AsyncSession = Depends(get_db)):
    """条目已保存的翻译列表。"""
    entry = await db.get(models.Entry, entry_id)
    if not entry or entry.deleted_at:
        raise HTTPException(404, "Entry not found")
    rows = (await db.execute(
        select(models.EntryTranslation).where(models.EntryTranslation.entry_id == entry_id)
    )).scalars().all()
    return {"items": [_translation_to_dict(t) for t in rows], "total": len(rows)}


@router.put("/entries/{entry_id}/translations/{lang}", response_model=dict[str, Any])
async def upsert_entry_translation(
    entry_id: int,
    lang: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    """保存/覆盖某语言的翻译。field_values: {title, content, custom_fields, slug}。"""
    entry = await db.get(models.Entry, entry_id)
    if not entry or entry.deleted_at:
        raise HTTPException(404, "Entry not found")
    row = (await db.execute(
        select(models.EntryTranslation).where(
            models.EntryTranslation.entry_id == entry_id,
            models.EntryTranslation.lang == lang,
        )
    )).scalar_one_or_none()
    field_values = body.get("field_values") or {}
    status_ = body.get("status", "draft")
    if row:
        row.field_values = field_values
        row.status = status_
        row.created_by = current.id
    else:
        row = models.EntryTranslation(
            entry_id=entry_id, lang=lang,
            field_values=field_values, status=status_,
            created_by=current.id,
        )
        db.add(row)
    await db.commit()
    await db.refresh(row)
    return _translation_to_dict(row)


@router.delete("/entries/{entry_id}/translations/{lang}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry_translation(
    entry_id: int,
    lang: str,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    """删除某条翻译（回到默认语言）。"""
    row = (await db.execute(
        select(models.EntryTranslation).where(
            models.EntryTranslation.entry_id == entry_id,
            models.EntryTranslation.lang == lang,
        )
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Translation not found")
    await db.delete(row)
    await db.commit()


# ============================================================
# 暂存预览（M4·P3 4.4 staging）
# ============================================================
@router.post("/entries/{entry_id}/preview", response_model=dict[str, Any])
async def create_entry_preview(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    """为草稿/已通过内容生成暂存预览链接（复用未过期的，7 天有效期）。"""
    import secrets as _secrets
    from datetime import timedelta as _td

    entry = await db.get(models.Entry, entry_id)
    if not entry or entry.deleted_at:
        raise HTTPException(404, "Entry not found")
    if entry.status == "published":
        raise HTTPException(400, "内容已发布，无需预览（请直接访问正式页面）")
    now = datetime.now(timezone.utc)
    existing = (await db.execute(
        select(models.EntryPreview).where(
            models.EntryPreview.entry_id == entry_id,
            models.EntryPreview.expires_at.is_not(None),
            models.EntryPreview.expires_at > now,
        ).order_by(models.EntryPreview.id.desc())
    )).scalars().first()
    if existing:
        token, expires_at = existing.token, existing.expires_at
    else:
        token = _secrets.token_hex(32)
        expires_at = now + _td(days=7)
        db.add(models.EntryPreview(
            entry_id=entry_id, token=token, created_by=current.id, expires_at=expires_at,
        ))
        await db.commit()
    return {
        "token": token,
        "url": f"/api/v1/public/preview/{token}",
        "json_url": f"/api/v1/public/preview/{token}.json",
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


@router.delete("/entries/{entry_id}/preview", status_code=200)
async def revoke_entry_preview(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    """撤销该条目的全部暂存预览。"""
    rows = (await db.execute(
        select(models.EntryPreview).where(models.EntryPreview.entry_id == entry_id)
    )).scalars().all()
    for r in rows:
        await db.delete(r)
    await db.commit()
    return {"revoked": len(rows)}


# ============================================================
# Field Types (metadata endpoint)
# ============================================================
@router.get("/field-types", response_model=dict[str, Any])
async def list_field_types():
    from cenkor_admin.apps.cms.field_types import FIELD_DEFAULTS, VALIDATION_RULES, NEEDS_OPTIONS
    return {
        "types": FIELD_TYPES,
        "defaults": FIELD_DEFAULTS,
        "validation_rules": VALIDATION_RULES,
        "needs_options": list(NEEDS_OPTIONS),
    }


# ============================================================
# Helpers
# ============================================================

def _category_to_dict(c: models.Category) -> dict:
    return {
        "id": c.id,
        "content_type_id": c.content_type_id,
        "parent_id": c.parent_id,
        "slug": c.slug,
        "name": c.name,
        "icon": c.icon,
        "color": c.color,
        "sort": c.sort,
        "status": c.status,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _tag_to_dict(t: models.Tag) -> dict:
    return {
        "id": t.id,
        "content_type_id": t.content_type_id,
        "slug": t.slug,
        "name": t.name,
        "color": t.color,
    }


def _language_to_dict(l: models.Language) -> dict:
    return {
        "id": l.id,
        "code": l.code,
        "name": l.name,
        "flag": l.flag,
        "is_default": l.is_default,
        "enabled": l.enabled,
        "sort": l.sort,
        "created_at": l.created_at.isoformat() if l.created_at else None,
        "updated_at": l.updated_at.isoformat() if l.updated_at else None,
    }


def _translation_to_dict(t: models.EntryTranslation) -> dict:
    return {
        "id": t.id,
        "entry_id": t.entry_id,
        "lang": t.lang,
        "field_values": t.field_values or {},
        "status": t.status,
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _version_to_dict(v: models.EntryVersion, include_data: bool = True) -> dict:
    d = {
        "id": v.id,
        "entry_id": v.entry_id,
        "version": v.version,
        "created_by": v.created_by,
        "note": v.note,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }
    if include_data:
        d["data"] = v.data or {}
    return d


def _entry_to_dict(e: models.Entry) -> dict:
    return {
        "id": e.id,
        "content_type_id": e.content_type_id,
        "slug": e.slug,
        "title": e.title,
        "content": e.content or {},
        "custom_fields": e.custom_fields or {},
        "category_id": e.category_id,
        "status": e.status,
        "author_id": e.author_id,
        "published_at": e.published_at.isoformat() if e.published_at else None,
        "scheduled_at": e.scheduled_at.isoformat() if e.scheduled_at else None,
        "expire_at": e.expire_at.isoformat() if e.expire_at else None,
        "sort": e.sort,
        "view_count": e.view_count,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


def _build_category_tree(categories: list[models.Category], parent_id: int | None = None) -> list[dict]:
    result = []
    for c in categories:
        if c.parent_id == parent_id:
            node = _category_to_dict(c)
            node["children"] = _build_category_tree(categories, c.id)
            result.append(node)
    return result


# ============================================================
# 兼容层：将旧的 /cms/products 等 API 转发到 cms_entries
# ============================================================

@router.get("/products", response_model=dict[str, Any])
async def compat_list_products(
    db: AsyncSession = Depends(get_db),
    line: str | None = None,
    status: str = "published",
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """兼容旧 API：/cms/products → cms_entries(content_type_key=product)"""
    ct = (await db.execute(
        select(models.ContentType).where(models.ContentType.key == "product")
    )).scalar_one_or_none()
    if not ct:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    conds = [
        models.Entry.content_type_id == ct.id,
        models.Entry.status == status,
        models.Entry.deleted_at.is_(None),
    ]
    if search:
        conds.append(models.Entry.title.ilike(f"%{search}%"))

    stmt = (
        select(models.Entry)
        .where(*conds)
        .order_by(models.Entry.sort, models.Entry.id.desc())
    )
    data = await paginate(db, stmt, page=page, page_size=page_size)

    items = []
    for e in data["items"]:
        # 转回 Product 格式
        c = e.content or {}
        items.append({
            "id": e.id,
            "key": e.slug,
            "name": c.get("name") or e.title,
            "chinese_name": c.get("chinese_name"),
            "slug": e.slug,
            "tagline": c.get("tagline", ""),
            "line": c.get("line", line or "enterprise"),
            "stack": c.get("stack", ""),
            "desc": c.get("desc", ""),
            "features": c.get("features", []),
            "is_flagship": c.get("is_flagship", False),
            "is_open_source": c.get("is_open_source", False),
            "github_url": c.get("github_url"),
            "demo_url": c.get("demo_url"),
            "website_url": c.get("website_url"),
            "license": c.get("license"),
            "sort": e.sort,
            "status": e.status,
            "custom_fields": e.custom_fields or {},
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "updated_at": e.updated_at.isoformat() if e.updated_at else None,
        })

    return {"items": items, "total": data["total"], "page": data["page"], "page_size": data["page_size"]}


@router.get("/products/{product_id}", response_model=dict[str, Any])
async def compat_get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    """兼容旧 API：/cms/products/{id}"""
    ct = (await db.execute(
        select(models.ContentType).where(models.ContentType.key == "product")
    )).scalar_one_or_none()
    if not ct:
        raise HTTPException(404, "Product not found")

    e = (await db.execute(
        select(models.Entry).where(
            models.Entry.id == product_id,
            models.Entry.content_type_id == ct.id,
            models.Entry.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not e:
        raise HTTPException(404, "Product not found")

    c = e.content or {}
    return {
        "id": e.id,
        "key": e.slug,
        "name": c.get("name") or e.title,
        "chinese_name": c.get("chinese_name"),
        "slug": e.slug,
        "tagline": c.get("tagline", ""),
        "line": c.get("line", "enterprise"),
        "stack": c.get("stack", ""),
        "desc": c.get("desc", ""),
        "features": c.get("features", []),
        "is_flagship": c.get("is_flagship", False),
        "is_open_source": c.get("is_open_source", False),
        "github_url": c.get("github_url"),
        "demo_url": c.get("demo_url"),
        "website_url": c.get("website_url"),
        "license": c.get("license"),
        "sort": e.sort,
        "status": e.status,
        "custom_fields": e.custom_fields or {},
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }
