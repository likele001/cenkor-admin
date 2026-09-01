"""ERP 供应商 + 商品 API 路由"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.core.db import get_db

from .models.supplier import ErpSupplier, ErpSupplierContact
from .models.product import ErpProduct, ErpProductCategory

router = APIRouter()


# ============================================================
# Schemas - 供应商
# ============================================================

class SupplierContactIn(BaseModel):
    name: str
    position: str | None = None
    phone: str | None = None
    email: str | None = None
    wechat: str | None = None
    is_primary: bool = False
    notes: str | None = None


class SupplierContactOut(SupplierContactIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    supplier_id: int


class SupplierIn(BaseModel):
    code: str = Field(..., max_length=32)
    name: str = Field(..., max_length=128)
    short_name: str | None = None
    contact_person: str | None = None
    phone: str | None = None
    email: str | None = None
    tax_id: str | None = None
    category: str | None = None
    payment_terms: str | None = None
    currency: str = "CNY"
    credit_limit: float = 0
    status: str = "active"
    owner_user_id: int | None = None
    notes: str | None = None
    contacts: list[SupplierContactIn] = []


class SupplierOut(SupplierIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: Any
    updated_at: Any
    contacts: list[SupplierContactOut] = []


class SupplierBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    contact_person: str | None = None
    phone: str | None = None
    status: str
    owner_user_id: int | None = None
    created_at: Any


class Page(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[Any]


# ============================================================
# Schemas - 商品
# ============================================================

class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    code: str | None = None
    parent_id: int | None = None
    sort: int
    status: str


class CategoryIn(BaseModel):
    name: str = Field(..., max_length=64)
    code: str | None = None
    parent_id: int | None = None
    sort: int = 0
    status: str = "active"


class ProductIn(BaseModel):
    code: str = Field(..., max_length=32)
    name: str = Field(..., max_length=128)
    model: str | None = None
    category_id: int | None = None
    unit: str = "件"
    barcode: str | None = None
    sale_price: float = 0
    purchase_price: float = 0
    cost_price: float = 0
    min_stock: float = 0
    tax_rate: float = 0
    status: str = "active"
    remarks: str | None = None


class ProductOut(ProductIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: Any
    updated_at: Any
    category: CategoryOut | None = None


class ProductBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    model: str | None = None
    unit: str
    sale_price: float
    status: str


# ============================================================
# Helpers
# ============================================================

async def _get_supplier_or_404(db: AsyncSession, supplier_id: int) -> ErpSupplier:
    row = (
        await db.execute(
            select(ErpSupplier)
            .where(ErpSupplier.id == supplier_id, ErpSupplier.deleted_at.is_(None))
            .options(selectinload(ErpSupplier.contacts))
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="供应商不存在")
    return row


async def _get_product_or_404(db: AsyncSession, product_id: int) -> ErpProduct:
    row = (
        await db.execute(
            select(ErpProduct)
            .where(ErpProduct.id == product_id, ErpProduct.deleted_at.is_(None))
            .options(selectinload(ErpProduct.category))
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="商品不存在")
    return row


# ============================================================
# 供应商 API
# ============================================================

@router.get("/suppliers", response_model=Page)
async def list_suppliers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:supplier:read")),
):
    stmt = select(ErpSupplier).where(ErpSupplier.deleted_at.is_(None))
    count_stmt = select(func.count()).select_from(ErpSupplier).where(ErpSupplier.deleted_at.is_(None))

    if keyword:
        like = f"%{keyword}%"
        cond = or_(ErpSupplier.name.ilike(like), ErpSupplier.code.ilike(like),
                   ErpSupplier.contact_person.ilike(like) if ErpSupplier.contact_person else ErpSupplier.name.ilike(like))
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    if status:
        stmt = stmt.where(ErpSupplier.status == status)
        count_stmt = count_stmt.where(ErpSupplier.status == status)

    total = (await db.execute(count_stmt)).scalar_one()
    rows = (
        await db.execute(
            stmt.order_by(ErpSupplier.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[SupplierBrief.model_validate(r) for r in rows])


@router.get("/suppliers/{supplier_id}", response_model=SupplierOut)
async def get_supplier(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:supplier:read")),
):
    row = await _get_supplier_or_404(db, supplier_id)
    await db.refresh(row, attribute_names=["contacts"])
    return SupplierOut.model_validate(row)


@router.post("/suppliers", response_model=SupplierOut, status_code=201)
async def create_supplier(
    payload: SupplierIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:supplier:write")),
):
    dup = await db.execute(select(ErpSupplier).where(ErpSupplier.code == payload.code))
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"供应商编号已存在：{payload.code}")

    sup = ErpSupplier(
        code=payload.code,
        name=payload.name,
        short_name=payload.short_name,
        contact_person=payload.contact_person,
        phone=payload.phone,
        email=payload.email,
        tax_id=payload.tax_id,
        category=payload.category,
        payment_terms=payload.payment_terms,
        currency=payload.currency,
        credit_limit=payload.credit_limit,
        status=payload.status,
        owner_user_id=payload.owner_user_id or getattr(user, "id", None),
        notes=payload.notes,
    )
    sup.contacts = [ErpSupplierContact(**c.model_dump()) for c in payload.contacts]
    db.add(sup)
    await db.commit()
    await db.refresh(sup, attribute_names=["contacts"])
    return SupplierOut.model_validate(sup)


@router.put("/suppliers/{supplier_id}", response_model=SupplierOut)
async def update_supplier(
    supplier_id: int,
    payload: SupplierIn,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:supplier:write")),
):
    row = await _get_supplier_or_404(db, supplier_id)
    dup = await db.execute(
        select(ErpSupplier).where(ErpSupplier.code == payload.code,
                                  ErpSupplier.id != supplier_id)
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"供应商编号已存在：{payload.code}")

    for field in ("code", "name", "short_name", "contact_person", "phone", "email",
                  "tax_id", "category", "payment_terms", "currency", "credit_limit",
                  "status", "owner_user_id", "notes"):
        setattr(row, field, getattr(payload, field))

    row.contacts = [ErpSupplierContact(**c.model_dump()) for c in payload.contacts]
    await db.commit()
    await db.refresh(row, attribute_names=["contacts"])
    return SupplierOut.model_validate(row)


@router.delete("/suppliers/{supplier_id}", status_code=204)
async def delete_supplier(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:supplier:write")),
):
    row = await _get_supplier_or_404(db, supplier_id)
    row.deleted_at = func.now()
    await db.commit()
    return None


# ============================================================
# 商品分类 API
# ============================================================

@router.get("/product-categories", response_model=list[CategoryOut])
async def list_categories(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:product:read")),
):
    rows = (await db.execute(
        select(ErpProductCategory).order_by(ErpProductCategory.sort, ErpProductCategory.id)
    )).scalars().all()
    return [CategoryOut.model_validate(r) for r in rows]


@router.post("/product-categories", response_model=CategoryOut, status_code=201)
async def create_category(
    payload: CategoryIn,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:product:write")),
):
    cat = ErpProductCategory(**payload.model_dump())
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return CategoryOut.model_validate(cat)


# ============================================================
# 商品 API
# ============================================================

@router.get("/products", response_model=Page)
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: str | None = None,
    category_id: int | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:product:read")),
):
    stmt = select(ErpProduct).where(ErpProduct.deleted_at.is_(None))
    count_stmt = select(func.count()).select_from(ErpProduct).where(ErpProduct.deleted_at.is_(None))

    if keyword:
        like = f"%{keyword}%"
        cond = or_(ErpProduct.name.ilike(like), ErpProduct.code.ilike(like),
                   ErpProduct.model.ilike(like) if ErpProduct.model else ErpProduct.name.ilike(like))
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    if category_id:
        stmt = stmt.where(ErpProduct.category_id == category_id)
        count_stmt = count_stmt.where(ErpProduct.category_id == category_id)
    if status:
        stmt = stmt.where(ErpProduct.status == status)
        count_stmt = count_stmt.where(ErpProduct.status == status)

    total = (await db.execute(count_stmt)).scalar_one()
    rows = (
        await db.execute(
            stmt.order_by(ErpProduct.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return Page(total=total, page=page, page_size=page_size,
                items=[ProductBrief.model_validate(r) for r in rows])


@router.get("/products/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:product:read")),
):
    row = await _get_product_or_404(db, product_id)
    return ProductOut.model_validate(row)


@router.post("/products", response_model=ProductOut, status_code=201)
async def create_product(
    payload: ProductIn,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:product:write")),
):
    dup = await db.execute(select(ErpProduct).where(ErpProduct.code == payload.code))
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"商品编码已存在：{payload.code}")

    if payload.category_id:
        cat = await db.get(ErpProductCategory, payload.category_id)
        if not cat:
            raise HTTPException(status_code=400, detail="商品分类不存在")

    prod = ErpProduct(**payload.model_dump())
    db.add(prod)
    await db.commit()
    await db.refresh(prod)
    row = await _get_product_or_404(db, prod.id)
    return ProductOut.model_validate(row)


@router.put("/products/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: int,
    payload: ProductIn,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:product:write")),
):
    row = await _get_product_or_404(db, product_id)
    dup = await db.execute(
        select(ErpProduct).where(ErpProduct.code == payload.code,
                                 ErpProduct.id != product_id)
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"商品编码已存在：{payload.code}")

    for field in ("code", "name", "model", "category_id", "unit", "barcode",
                  "sale_price", "purchase_price", "cost_price", "min_stock",
                  "tax_rate", "status", "remarks"):
        setattr(row, field, getattr(payload, field))
    await db.commit()
    row = await _get_product_or_404(db, product_id)
    return ProductOut.model_validate(row)


@router.delete("/products/{product_id}", status_code=204)
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:product:write")),
):
    row = await _get_product_or_404(db, product_id)
    row.deleted_at = func.now()
    await db.commit()
    return None