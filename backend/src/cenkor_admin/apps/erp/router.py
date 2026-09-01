"""ERP App 路由 — 主路由（聚合各业务模块子路由）"""
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

from .models.customer import (
    ErpCustomer,
    ErpCustomerAddress,
    ErpCustomerContact,
    ErpFollowUp,
)

# 供应商 + 商品模块子路由
from .sp_router import router as sp_router
# 销售订单模块子路由（报价单 + 订单 + 出货）
from .so_router import router as so_router
# 采购 + 仓库模块子路由（采购订单 + 收货 + 仓库 + 库存）
from .po_router import router as po_router
# 财务模块子路由（发票 + 收付款 + 应收应付）
from .fin_router import router as fin_router
# 财务闭环子路由（总账/凭证/三大报表）
from .gl_router import router as gl_router
# 仓储深度子路由（库位/批次/序列号/盘点/安全库存预警）
from .wh_router import router as wh_router
# 制造基础子路由（BOM/工单/领料/完工/报工/质检/可用量）
from .mfg_router import router as mfg_router
# 采购申请 + 审批流子路由（PR 申请/审批/转PO）
from .pr_router import router as pr_router
# 制造深化子路由（工作中心/工艺路线/生产排程）
from .manufacturing_ext_router import router as mfge_router

router = APIRouter()
router.include_router(sp_router)
router.include_router(so_router)
router.include_router(po_router)
router.include_router(fin_router)
router.include_router(gl_router)
router.include_router(wh_router)
router.include_router(mfg_router)
router.include_router(pr_router)
router.include_router(mfge_router)


# ============================================================
# Pydantic Schemas
# ============================================================

class ContactIn(BaseModel):
    name: str
    position: str | None = None
    phone: str | None = None
    email: str | None = None
    wechat: str | None = None
    is_primary: bool = False
    birthday: str | None = None
    notes: str | None = None


class AddressIn(BaseModel):
    address_type: str = "shipping"
    recipient: str | None = None
    phone: str | None = None
    province: str | None = None
    city: str | None = None
    district: str | None = None
    detail: str | None = None
    is_default: bool = False


class CustomerIn(BaseModel):
    code: str
    name: str
    short_name: str | None = None
    customer_type: str = "company"
    tax_id: str | None = None
    currency: str = "CNY"
    payment_terms: str | None = None
    credit_limit: float = 0.0
    industry: str | None = None
    scale: str | None = None
    status: str = "active"
    owner_user_id: int | None = None
    notes: str | None = None
    contacts: list[ContactIn] = Field(default_factory=list)
    addresses: list[AddressIn] = Field(default_factory=list)


class ContactOut(ContactIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    customer_id: int


class AddressOut(AddressIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    customer_id: int


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    short_name: str | None = None
    customer_type: str
    tax_id: str | None = None
    currency: str
    payment_terms: str | None = None
    credit_limit: float | None = None
    industry: str | None = None
    scale: str | None = None
    status: str
    owner_user_id: int | None = None
    notes: str | None = None
    created_at: Any
    contacts: list[ContactOut] = Field(default_factory=list)
    addresses: list[AddressOut] = Field(default_factory=list)


class CustomerBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    customer_type: str
    status: str
    owner_user_id: int | None = None
    created_at: Any


class Page(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[CustomerBrief]


# ============================================================
# Helpers
# ============================================================

async def _get_customer_or_404(db: AsyncSession, customer_id: int) -> ErpCustomer:
    row = (
        await db.execute(
            select(ErpCustomer)
            .where(
                ErpCustomer.id == customer_id,
                ErpCustomer.deleted_at.is_(None),
            )
            .options(
                selectinload(ErpCustomer.contacts),
                selectinload(ErpCustomer.addresses),
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="客户不存在")
    return row


# ============================================================
# 客户 API
# ============================================================

@router.get("/customers", response_model=Page)
async def list_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: str | None = None,
    status: str | None = None,
    owner_user_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:customer:read")),
):
    stmt = select(ErpCustomer).where(ErpCustomer.deleted_at.is_(None))
    count_stmt = select(func.count()).select_from(ErpCustomer).where(ErpCustomer.deleted_at.is_(None))

    if keyword:
        like = f"%{keyword}%"
        cond = or_(
            ErpCustomer.name.ilike(like),
            ErpCustomer.code.ilike(like),
            ErpCustomer.short_name.ilike(like),
        )
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    if status:
        stmt = stmt.where(ErpCustomer.status == status)
        count_stmt = count_stmt.where(ErpCustomer.status == status)
    if owner_user_id:
        stmt = stmt.where(ErpCustomer.owner_user_id == owner_user_id)
        count_stmt = count_stmt.where(ErpCustomer.owner_user_id == owner_user_id)

    total = (await db.execute(count_stmt)).scalar_one()
    rows = (
        await db.execute(
            stmt.order_by(ErpCustomer.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return Page(total=total, page=page, page_size=page_size, items=[CustomerBrief.model_validate(r) for r in rows])


@router.get("/customers/{customer_id}", response_model=CustomerOut)
async def get_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:customer:read")),
):
    row = await _get_customer_or_404(db, customer_id)
    await db.refresh(row, attribute_names=["contacts", "addresses"])
    return CustomerOut.model_validate(row)


@router.post("/customers", response_model=CustomerOut, status_code=201)
async def create_customer(
    payload: CustomerIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:customer:write")),
):
    # 编号唯一校验
    dup = (
        await db.execute(select(ErpCustomer).where(ErpCustomer.code == payload.code))
    ).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail=f"客户编号已存在：{payload.code}")

    customer = ErpCustomer(
        code=payload.code,
        name=payload.name,
        short_name=payload.short_name,
        customer_type=payload.customer_type,
        tax_id=payload.tax_id,
        currency=payload.currency,
        payment_terms=payload.payment_terms,
        credit_limit=payload.credit_limit,
        industry=payload.industry,
        scale=payload.scale,
        status=payload.status,
        owner_user_id=payload.owner_user_id or getattr(user, "id", None),
        notes=payload.notes,
    )
    customer.contacts = [
        ErpCustomerContact(**c.model_dump()) for c in payload.contacts
    ]
    customer.addresses = [
        ErpCustomerAddress(**a.model_dump()) for a in payload.addresses
    ]
    db.add(customer)
    await db.commit()
    await db.refresh(customer, attribute_names=["contacts", "addresses"])
    return CustomerOut.model_validate(customer)


@router.put("/customers/{customer_id}", response_model=CustomerOut)
async def update_customer(
    customer_id: int,
    payload: CustomerIn,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:customer:write")),
):
    row = await _get_customer_or_404(db, customer_id)

    dup = (
        await db.execute(
            select(ErpCustomer).where(
                ErpCustomer.code == payload.code,
                ErpCustomer.id != customer_id,
            )
        )
    ).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail=f"客户编号已存在：{payload.code}")

    for field in ("code", "name", "short_name", "customer_type", "tax_id", "currency",
                  "payment_terms", "credit_limit", "industry", "scale", "status",
                  "owner_user_id", "notes"):
        setattr(row, field, getattr(payload, field))

    # 重建子表
    row.contacts = [ErpCustomerContact(**c.model_dump()) for c in payload.contacts]
    row.addresses = [ErpCustomerAddress(**a.model_dump()) for a in payload.addresses]

    await db.commit()
    await db.refresh(row, attribute_names=["contacts", "addresses"])
    return CustomerOut.model_validate(row)


@router.delete("/customers/{customer_id}", status_code=204)
async def delete_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:customer:delete")),
):
    row = await _get_customer_or_404(db, customer_id)
    row.deleted_at = func.now()
    await db.commit()
    return None


# ============================================================
# 跟进记录 API（客户详情内部使用）
# ============================================================

class FollowUpIn(BaseModel):
    contact_id: int | None = None
    follow_type: str = "call"
    follow_date: str
    summary: str | None = None
    next_action: str | None = None
    next_follow_date: str | None = None


class FollowUpOut(FollowUpIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    customer_id: int
    owner_user_id: int | None = None
    created_at: Any


@router.get("/customers/{customer_id}/follow-ups", response_model=list[FollowUpOut])
async def list_follow_ups(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:customer:read")),
):
    await _get_customer_or_404(db, customer_id)
    rows = (
        await db.execute(
            select(ErpFollowUp)
            .where(ErpFollowUp.customer_id == customer_id)
            .order_by(ErpFollowUp.follow_date.desc())
        )
    ).scalars().all()
    return [FollowUpOut.model_validate(r) for r in rows]


@router.post("/customers/{customer_id}/follow-ups", response_model=FollowUpOut, status_code=201)
async def create_follow_up(
    customer_id: int,
    payload: FollowUpIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:customer:write")),
):
    await _get_customer_or_404(db, customer_id)
    row = ErpFollowUp(
        customer_id=customer_id,
        contact_id=payload.contact_id,
        follow_type=payload.follow_type,
        follow_date=payload.follow_date,
        summary=payload.summary,
        next_action=payload.next_action,
        next_follow_date=payload.next_follow_date,
        owner_user_id=getattr(user, "id", None),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return FollowUpOut.model_validate(row)