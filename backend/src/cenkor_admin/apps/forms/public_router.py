"""Forms App · 公共路由（无需鉴权，M4·P3 4.3）"""
from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.forms.models import Form, FormSubmission
from cenkor_admin.core.db import get_db

log = structlog.get_logger()
router = APIRouter()


@router.get("/forms", response_model=dict[str, Any])
async def list_public_forms(db: AsyncSession = Depends(get_db)):
    """公开表单列表（仅启用，含字段定义供前端渲染）。"""
    rows = (await db.execute(
        select(Form).where(Form.enabled.is_(True)).order_by(Form.id)
    )).scalars().all()
    return {"items": [{
        "id": f.id, "key": f.key, "title": f.title, "description": f.description,
        "fields": f.fields or [], "success_message": f.success_message,
    } for f in rows]}


@router.post("/forms/{key}/submit", response_model=dict[str, Any], status_code=201)
async def submit_form(
    key: str,
    body: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """提交表单。body: {values: {field_key: value}}。"""
    form = (await db.execute(
        select(Form).where(Form.key == key, Form.enabled.is_(True))
    )).scalar_one_or_none()
    if not form:
        raise HTTPException(404, "表单不存在或已停用")

    values = body.get("values") or {}
    # 必填校验
    fields = form.fields or []
    missing = []
    for f in fields:
        fk = f.get("key") if isinstance(f, dict) else getattr(f, "key", None)
        if f.get("required") and (fk not in values or values.get(fk) in ("", None)):
            missing.append(fk)
    if missing:
        raise HTTPException(400, f"缺少必填项: {missing}")

    # 蜜罐：前端放一个视觉隐藏的 _hp 字段，真人不会填。
    # 命中就当机器人处理 —— 假装成功、不落库、不建线索，
    # 让刷量的人拿不到任何反馈信号。
    if str(body.get("_hp") or "").strip():
        log.info("forms.honeypot_hit", form=form.key)
        return {"id": 0, "message": form.success_message or "提交成功"}

    obj = FormSubmission(
        form_id=form.id,
        data=values,
        ip=request.client.host if request.client else None,
    )
    db.add(obj)
    await db.flush()

    lead_id = None
    if getattr(form, "create_lead", False):
        lead_id = await _create_lead(db, form, values, obj.ip)

    await db.commit()
    await db.refresh(obj)
    return {
        "id": obj.id,
        "message": form.success_message or "提交成功",
        "lead_id": lead_id,
    }


# 只有这些线索列允许被表单映射写入。白名单而不是黑名单：
# lead_mapping 是运营在后台配的，配错了不该把模型搞崩，
# 更不该让人有机会写 owner_user_id 这类改归属的字段。
_LEAD_WRITABLE = (
    "name", "company", "contact_name", "phone", "mobile",
    "email", "industry", "province", "city", "address", "notes",
)


async def _create_lead(db: AsyncSession, form: "Form", values: dict, ip: str | None) -> int | None:
    """把一次表单提交落成 CRM 线索。

    用 SAVEPOINT 包住：线索写失败只回滚这一个 savepoint，
    提交记录照样落库。直接 try/except 是不行的 —— 一次失败的 INSERT
    会把整个事务标成 aborted，后面 commit 必炸，访客看到 500，
    而运营还以为是没人留资。
    """
    import time

    from sqlalchemy import select as _select

    from cenkor_admin.apps.crm.models import CrmLead

    try:
        async with db.begin_nested():
            mapping = form.lead_mapping or {}
            flat = {}
            for lead_field, form_key in mapping.items():
                if lead_field not in _LEAD_WRITABLE:
                    continue
                v = values.get(form_key)
                if v in (None, ""):
                    continue
                flat[lead_field] = str(v).strip()[:200]

            # 兜底：映射配歪 / 表单字段名不统一时，直接从 values 里捞常见字段。
            # 留资是第一优先级，宁可多写一列，也不能让手机号丢了。
            if not flat.get("mobile") and not flat.get("phone"):
                fallback_phone = values.get("phone") or values.get("mobile") or values.get("tel")
                if fallback_phone:
                    flat["mobile"] = str(fallback_phone).strip()[:200]
            if not flat.get("notes"):
                fallback_msg = values.get("message") or values.get("remark") or values.get("desc")
                if fallback_msg:
                    flat["notes"] = str(fallback_msg).strip()[:200]
            if not flat.get("name") and values.get("name"):
                flat["name"] = str(values["name"]).strip()[:200]

            name = flat.get("name") or flat.get("company") or "落地页访客"
            for attempt in range(5):
                code = f"LP{int(time.time())}{attempt}"
                if not (await db.execute(_select(CrmLead.id).where(CrmLead.code == code))).scalar():
                    break
            else:
                code = f"LP{int(time.time() * 1000)}"

            notes = flat.get("notes") or ""
            lead = CrmLead(
                code=code,
                name=name[:128],
                company=(flat.get("company") or None),
                contact_name=(flat.get("name") or None),
                phone=(flat.get("phone") or None),
                mobile=(flat.get("mobile") or flat.get("phone") or None),
                email=(flat.get("email") or None),
                industry=(flat.get("industry") or None),
                province=(flat.get("province") or None),
                city=(flat.get("city") or None),
                address=(flat.get("address") or None),
                source="web",
                source_detail=f"lp:{form.key}",
                status="new",
                is_in_public_sea=True,
                notes=("%s\n--\n来自表单 %s｜IP %s" % (notes, form.key, ip or "-"))[:2000],
            )
            db.add(lead)
            await db.flush()
            return lead.id
    except Exception as exc:  # noqa: BLE001
        log.warning("forms.lead_create_failed", form=form.key, error=str(exc))
        return None
