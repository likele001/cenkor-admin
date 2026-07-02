"""CMS 内容引擎路由（Content Types / Field Groups / Field Definitions / Field Options / Categories / Tags / Entries）"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms import models, schemas
from cenkor_admin.apps.cms.field_types import FIELD_TYPES, NEEDS_OPTIONS, validate_field_value
from cenkor_admin.core.db import get_db
from cenkor_admin.core.repository import apply_filters, paginate

router = APIRouter()


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
        category_id=body.get("category_id"),
        status=body.get("status", "draft"),
        author_id=current.id,
        published_at=body.get("published_at"),
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
    for k in ("title", "slug", "content", "custom_fields", "category_id", "status", "published_at", "sort"):
        if k in body:
            setattr(obj, k, body[k])

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
    return _entry_to_dict(obj)


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
