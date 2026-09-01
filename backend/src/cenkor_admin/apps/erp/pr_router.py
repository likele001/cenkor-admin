"""ERP 采购申请（PR）+ 审批流 API：申请 / 提交 / 审批 / 驳回 / 转采购订单"""
from __future__ import annotations

from datetime import datetime

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.core.db import get_db

from .models.pr import (
    ErpApprovalRecord,
    ErpPurchaseRequest,
    ErpPurchaseRequestItem,
)
from .models.purchase import ErpPurchaseOrder, ErpPurchaseOrderItem
from .models.supplier import ErpSupplier
from .models.product import ErpProduct

router = APIRouter()


# ============================================================
# Schemas
# ============================================================

class ItemIn(BaseModel):
    product_id: int | None = None
    product_code: str | None = None
    product_name: str | None = None
    spec: str | None = None
    quantity: float = Field(1, gt=0)
    unit: str | None = None
    expected_price: float = 0
    need_date: str | None = None
    remark: str | None = None
    sort: int = 0


class ItemOut(ItemIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    converted_qty: float
    amount: float


class PRIn(BaseModel):
    title: str | None = None
    requester: str | None = None
    department: str | None = None
    required_date: str | None = None
    urgency: str = "normal"
    currency: str = "CNY"
    reason: str | None = None
    items: list[ItemIn] = []


class ApprovalIn(BaseModel):
    decision: str  # approved/rejected
    comment: str | None = None


class ConvertIn(BaseModel):
    supplier_id: int | None = None
    price_override: dict[str, float] = Field(default_factory=dict)  # item_id -> unit_price


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    level: int
    decision: str
    comment: str | None = None
    approver_name: str | None = None
    decided_at: Any


class PROut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    status: str
    title: str | None = None
    requester: str | None = None
    department: str | None = None
    required_date: Any = None
    urgency: str
    expected_total: float
    currency: str
    reason: str | None = None
    current_level: int
    approver_name: str | None = None
    decided_at: Any = None
    rejected_at: Any = None
    reject_reason: str | None = None
    purchase_order_id: int | None = None
    created_at: Any
    items: list[ItemOut] = Field(default_factory=list)
    approvals: list[ApprovalOut] = Field(default_factory=list)


class PRBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    status: str
    title: str | None = None
    requester: str | None = None
    department: str | None = None
    urgency: str
    expected_total: float
    item_count: int = 0
    created_at: Any


class Page(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[Any]


# ============================================================
# Helpers
# ============================================================

async def _next_code(db: AsyncSession, prefix: str, table) -> str:
    row = (await db.execute(
        select(table.id).order_by(table.id.desc()).limit(1)
    )).scalar_one_or_none()
    n = (row or 0) + 1
    return f"{prefix}{n:04d}"


def _compute(items: list[ItemIn]) -> float:
    total = sum(float(it.quantity) * float(it.expected_price) for it in items)
    return round(total, 2)


async def _get_pr(db: AsyncSession, pr_id: int) -> ErpPurchaseRequest:
    row = (await db.execute(
        select(ErpPurchaseRequest)
        .where(ErpPurchaseRequest.id == pr_id, ErpPurchaseRequest.deleted_at.is_(None))
        .options(
            selectinload(ErpPurchaseRequest.items),
            selectinload(ErpPurchaseRequest.approvals),
        )
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="采购申请不存在")
    return row


def _build_items(req: ErpPurchaseRequest, rows: list[ErpPurchaseRequestItem]) -> list[ErpPurchaseRequestItem]:
    del req
    return rows


# ============================================================
# PR API
# ============================================================

@router.get("/pr", response_model=Page)
async def list_prs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = None,
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:pr:read")),
):
    stmt = select(ErpPurchaseRequest).where(ErpPurchaseRequest.deleted_at.is_(None))
    count = select(func.count()).select_from(ErpPurchaseRequest).where(ErpPurchaseRequest.deleted_at.is_(None))
    if status:
        stmt = stmt.where(ErpPurchaseRequest.status == status)
        count = count.where(ErpPurchaseRequest.status == status)
    if keyword:
        like = f"%{keyword}%"
        cond = func.concat(ErpPurchaseRequest.code, " ", ErpPurchaseRequest.title, " ", ErpPurchaseRequest.requester).ilike(like)
        stmt = stmt.where(cond)
        count = count.where(cond)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(ErpPurchaseRequest.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    items = []
    for r in rows:
        n = len(r.items) if r.items else (await db.execute(
            select(func.count()).select_from(ErpPurchaseRequestItem).where(ErpPurchaseRequestItem.request_id == r.id)
        )).scalar_one()
        b = PRBrief.model_validate(r)
        b.item_count = n
        items.append(b)
    return Page(total=total, page=page, page_size=page_size, items=items)


@router.get("/pr/{pr_id}", response_model=PROut)
async def get_pr(
    pr_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:pr:read")),
):
    return PROut.model_validate(await _get_pr(db, pr_id))


@router.post("/pr", response_model=PROut, status_code=201)
async def create_pr(
    payload: PRIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:pr:write")),
):
    if not payload.items:
        raise HTTPException(status_code=400, detail="采购申请至少需要一条明细")
    code = await _next_code(db, "PR", ErpPurchaseRequest)
    items: list[ErpPurchaseRequestItem] = []
    for it in payload.items:
        product = await db.get(ErpProduct, it.product_id) if it.product_id else None
        items.append(ErpPurchaseRequestItem(
            product_id=it.product_id,
            product_code=it.product_code or (product.code if product else None),
            product_name=it.product_name or (product.name if product else None),
            spec=it.spec or (product.spec if product else None),
            quantity=it.quantity, unit=it.unit or (product.unit if product else None),
            expected_price=it.expected_price,
            amount=round(float(it.quantity) * float(it.expected_price), 2),
            need_date=it.need_date, remark=it.remark, sort=it.sort,
        ))
    req = ErpPurchaseRequest(
        code=code,
        title=payload.title or "采购申请",
        requester=payload.requester or getattr(user, "username", None),
        department=payload.department,
        required_date=payload.required_date,
        urgency=payload.urgency,
        expected_total=_compute(payload.items),
        currency=payload.currency,
        reason=payload.reason,
        owner_user_id=getattr(user, "id", None),
    )
    req.items = items
    db.add(req)
    await db.commit()
    return PROut.model_validate(await _get_pr(db, req.id))


@router.put("/pr/{pr_id}", response_model=PROut)
async def update_pr(
    pr_id: int,
    payload: PRIn,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:pr:write")),
):
    req = await _get_pr(db, pr_id)
    if req.status not in ("draft", "rejected"):
        raise HTTPException(status_code=400, detail="仅草稿或已驳回状态的申请可编辑")
    if not payload.items:
        raise HTTPException(status_code=400, detail="采购申请至少需要一条明细")
    req.title = payload.title
    req.requester = payload.requester
    req.department = payload.department
    req.required_date = payload.required_date
    req.urgency = payload.urgency
    req.expected_total = _compute(payload.items)
    req.currency = payload.currency
    req.reason = payload.reason
    req.items = []
    for it in payload.items:
        product = await db.get(ErpProduct, it.product_id) if it.product_id else None
        req.items.append(ErpPurchaseRequestItem(
            product_id=it.product_id,
            product_code=it.product_code or (product.code if product else None),
            product_name=it.product_name or (product.name if product else None),
            spec=it.spec or (product.spec if product else None),
            quantity=it.quantity, unit=it.unit or (product.unit if product else None),
            expected_price=it.expected_price,
            amount=round(float(it.quantity) * float(it.expected_price), 2),
            need_date=it.need_date, remark=it.remark, sort=it.sort,
        ))
    await db.commit()
    return PROut.model_validate(await _get_pr(db, req.id))


@router.post("/pr/{pr_id}/submit", response_model=PROut)
async def submit_pr(
    pr_id: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:pr:write")),
):
    req = await _get_pr(db, pr_id)
    if req.status not in ("draft", "rejected"):
        raise HTTPException(status_code=400, detail="仅草稿或已驳回状态可提交审批")
    req.status = "pending_approval"
    req.current_level = 1
    req.reject_reason = None
    req.decided_at = None
    await db.add(ErpApprovalRecord(
        request_id=req.id, level=0, decision="submitted",
        comment=f"提交审批 by {getattr(user, 'username', '?')}",
        approver_user_id=getattr(user, "id", None),
        approver_name=getattr(user, "username", None),
    ))
    await db.commit()
    return PROut.model_validate(await _get_pr(db, req.id))


@router.post("/pr/{pr_id}/approve", response_model=PROut)
async def approve_pr(
    pr_id: int,
    payload: ApprovalIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:pr:approve")),
):
    return await _do_approve(db, pr_id, payload, user)


@router.post("/pr/{pr_id}/reject", response_model=PROut)
async def reject_pr(
    pr_id: int,
    payload: ApprovalIn,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:pr:approve")),
):
    return await _do_approve(db, pr_id, payload, user, force_reject=True)


async def _do_approve(db, pr_id, payload, user, force_reject=False):
    req = await _get_pr(db, pr_id)
    if req.status != "pending_approval":
        raise HTTPException(status_code=400, detail="仅待审批状态的申请可审批")
    decision = force_reject or (payload.decision or "approved")
    is_reject = (decision == "rejected")
    req.approver_user_id = getattr(user, "id", None)
    req.approver_name = getattr(user, "username", None)
    req.decided_at = func.now()
    if is_reject:
        req.status = "rejected"
        req.reject_reason = payload.comment
    else:
        req.status = "approved"
        req.approved_at = func.now()
        req.reject_reason = None
    db.add(ErpApprovalRecord(
        request_id=req.id, level=req.current_level, decision=decision,
        comment=payload.comment,
        approver_user_id=getattr(user, "id", None),
        approver_name=getattr(user, "username", None),
    ))
    await db.commit()
    return PROut.model_validate(await _get_pr(db, req.id))


@router.post("/pr/{pr_id}/convert", response_model=PROut)
async def convert_pr(
    pr_id: int,
    payload: ConvertIn | None = None,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("erp:pr:write")),
):
    """将已审批 PR 转为采购订单（连线供应商或按明细备注指定）"""
    body = payload or ConvertIn()
    req = await _get_pr(db, pr_id)
    if req.status != "approved":
        raise HTTPException(status_code=400, detail="仅已审批的申请可转为采购订单")
    if req.purchase_order_id:
        raise HTTPException(status_code=409, detail="该申请已转采购订单")

    supplier_id = body.supplier_id
    if not supplier_id:
        # 按明细备注里用到的第一个商品默认供应商（无则取第一个供应商）
        supp = (await db.execute(select(ErpSupplier).where(ErpSupplier.deleted_at.is_(None)).limit(1))).scalar_one_or_none()
        if not supp:
            raise HTTPException(status_code=400, detail="无可用供应商，请先维护供应商资料")
        supplier_id = supp.id

    order_code = await _next_code(db, "PO", ErpPurchaseOrder)
    po = ErpPurchaseOrder(
        code=order_code, supplier_id=supplier_id,
        order_date=datetime.now().strftime("%Y-%m-%d"),
        currency=req.currency, total_amount=0,
        owner_user_id=getattr(user, "id", None),
        notes=f"由采购申请 {req.code} 转单",
    )
    po_items: list[ErpPurchaseOrderItem] = []
    subtotal = 0.0
    for it in req.items:
        price = float(body.price_override.get(str(it.id), it.expected_price) or 0)
        amount = round(float(it.quantity) * price, 2)
        subtotal += amount
        po_items.append(ErpPurchaseOrderItem(
            product_id=it.product_id, product_code=it.product_code, product_name=it.product_name,
            spec=it.spec, quantity=float(it.quantity), unit=it.unit,
            unit_price=price, amount=amount, tax_rate=0, sort=it.sort,
        ))
        it.converted_qty = float(it.quantity)
    po.items = po_items
    po.total_amount = round(subtotal, 2)
    db.add(po)
    await db.flush()
    req.status = "converted"
    req.purchase_order_id = po.id
    await db.commit()
    return PROut.model_validate(await _get_pr(db, req.id))


@router.delete("/pr/{pr_id}", status_code=204)
async def delete_pr(
    pr_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("erp:pr:delete")),
):
    req = (await db.execute(
        select(ErpPurchaseRequest).where(ErpPurchaseRequest.id == pr_id, ErpPurchaseRequest.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="采购申请不存在")
    if req.status in ("converted",):
        raise HTTPException(status_code=400, detail="已转订单的申请不可删除")
    req.deleted_at = func.now()
    await db.commit()
    return None