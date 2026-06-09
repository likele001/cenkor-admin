"""CMS App · 后台管理路由（需要鉴权 - MVP 阶段先放开）"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.cms import models, schemas
from cenkor_admin.core.compat import order_nulls_last
from cenkor_admin.core.config import get_settings
from cenkor_admin.core.db import get_db
from cenkor_admin.core.repository import (
    apply_filters,
    paginate,
    stream_for_csv,
)
from cenkor_admin.core.storage import s3

settings = get_settings()
router = APIRouter()


def _media_public_url(bucket: str, key: str, *, presigned_fallback: str | None = None) -> str:
    """与 presign_upload 一致的公网访问 URL"""
    if settings.PUBLIC_BASE_URL:
        base = settings.PUBLIC_BASE_URL.rsplit(":", 1)[0]
        return f"{base}:{settings.S3_API_PORT}/{bucket}/{key}"
    if presigned_fallback:
        return presigned_fallback.split("?")[0]
    endpoint = settings.S3_ENDPOINT.rstrip("/")
    return f"{endpoint}/{bucket}/{key}"


# ===== Product =====
@router.get("/products", response_model=dict[str, Any])
async def list_products(
    db: AsyncSession = Depends(get_db),
    line: str | None = None,
    status: str = "published",
    search: str | None = Query(None, description="按 name / chinese_name / slug 模糊搜索"),
    include_deleted: bool = Query(False, description="包含已删除（回收站）"),
    only_deleted: bool = Query(False, description="只查已删除"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """产品列表（管理端）。"""
    extras = [models.Product.status == status]
    if line:
        extras.append(models.Product.line == line)
    conds = apply_filters(
        models.Product,
        search=search,
        search_fields=["name", "chinese_name", "slug", "tagline"],
        extra=extras,
        include_deleted=include_deleted,
        only_deleted=only_deleted,
    )
    stmt = select(models.Product).where(*conds).order_by(models.Product.sort, models.Product.id.desc())
    data = await paginate(db, stmt, page=page, page_size=page_size)
    return {
        "items": [_to_product_dict(p) for p in data["items"]],
        "total": data["total"],
        "page": data["page"],
        "page_size": data["page_size"],
    }


@router.post("/products/{product_id}/restore", status_code=200)
async def restore_product(product_id: int, db: AsyncSession = Depends(get_db)):
    """恢复软删产品。"""
    await db.execute(
        update(models.Product)
        .where(models.Product.id == product_id)
        .values(deleted_at=None)
    )
    await db.commit()
    return {"id": product_id, "restored": True}


@router.get("/products/export")
async def export_products_csv(
    db: AsyncSession = Depends(get_db),
    line: str | None = None,
    status: str = "published",
    search: str | None = None,
):
    """导出产品 CSV（分块流式）。"""
    extras = [models.Product.status == status]
    if line:
        extras.append(models.Product.line == line)
    conds = apply_filters(
        models.Product,
        search=search,
        search_fields=["name", "chinese_name", "slug", "tagline"],
        extra=extras,
    )
    base_stmt = select(models.Product).where(*conds)

    return StreamingResponse(
        _csv_stream(db, base_stmt, _product_csv_row, "products"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="products_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"',
        },
    )


@router.post("/products", response_model=schemas.ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(body: schemas.ProductCreate, db: AsyncSession = Depends(get_db)):
    # Slug 唯一检查
    existing = await db.execute(select(models.Product).where(models.Product.slug == body.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Slug 已存在: {body.slug}")
    obj = models.Product(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/products/{product_id}", response_model=schemas.ProductOut)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(models.Product, product_id)
    if not obj or obj.deleted_at is not None:
        raise HTTPException(404, "Product not found")
    return obj


@router.patch("/products/{product_id}", response_model=schemas.ProductOut)
async def update_product(
    product_id: int, body: schemas.ProductUpdate, db: AsyncSession = Depends(get_db)
):
    obj = await db.get(models.Product, product_id)
    if not obj or obj.deleted_at is not None:
        raise HTTPException(404, "Product not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: int, db: AsyncSession = Depends(get_db)):
    """软删。"""
    await db.execute(
        update(models.Product)
        .where(models.Product.id == product_id)
        .values(deleted_at=func.now())
    )
    await db.commit()


@router.post("/products/batch-delete", status_code=200)
async def batch_delete_products(body: dict, db: AsyncSession = Depends(get_db)):
    """批量软删产品。body: {ids: [int, ...]}"""
    ids = body.get("ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(400, "ids 必须是非空数组")
    await db.execute(
        update(models.Product)
        .where(models.Product.id.in_(ids))
        .values(deleted_at=func.now())
    )
    await db.commit()
    return {"deleted": len(ids)}


@router.post("/products/batch-status", status_code=200)
async def batch_update_product_status(body: dict, db: AsyncSession = Depends(get_db)):
    """批量更新状态。body: {ids: [...], status: 'published'|'draft'|'archived'}"""
    ids = body.get("ids") or []
    new_status = body.get("status")
    if not isinstance(ids, list) or not ids or new_status not in ("draft", "published", "archived"):
        raise HTTPException(400, "参数错误")
    await db.execute(
        update(models.Product)
        .where(models.Product.id.in_(ids))
        .values(status=new_status)
    )
    await db.commit()
    return {"updated": len(ids), "status": new_status}


# ===== Case =====
@router.get("/cases", response_model=dict[str, Any])
async def list_cases(
    db: AsyncSession = Depends(get_db),
    search: str | None = Query(None, description="按 name / industry / tag 模糊搜索"),
    include_deleted: bool = Query(False),
    only_deleted: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    conds = apply_filters(
        models.Case,
        search=search,
        search_fields=["name", "industry", "tag"],
        include_deleted=include_deleted,
        only_deleted=only_deleted,
    )
    stmt = select(models.Case).where(*conds).order_by(models.Case.sort, models.Case.id.desc())
    data = await paginate(db, stmt, page=page, page_size=page_size)
    return {
        "items": [_to_case_dict(c) for c in data["items"]],
        "total": data["total"],
        "page": data["page"],
        "page_size": data["page_size"],
    }


@router.post("/cases/{case_id}/restore", status_code=200)
async def restore_case(case_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(
        update(models.Case).where(models.Case.id == case_id).values(deleted_at=None)
    )
    await db.commit()
    return {"id": case_id, "restored": True}


@router.get("/cases/export")
async def export_cases_csv(
    db: AsyncSession = Depends(get_db),
    search: str | None = None,
):
    conds = apply_filters(
        models.Case,
        search=search,
        search_fields=["name", "industry", "tag"],
    )
    base_stmt = select(models.Case).where(*conds)
    return StreamingResponse(
        _csv_stream(db, base_stmt, _case_csv_row, "cases"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="cases_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"',
        },
    )


@router.post("/cases", response_model=schemas.CaseOut, status_code=status.HTTP_201_CREATED)
async def create_case(body: schemas.CaseCreate, db: AsyncSession = Depends(get_db)):
    obj = models.Case(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/cases/{case_id}", response_model=schemas.CaseOut)
async def get_case(case_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(models.Case, case_id)
    if not obj or obj.deleted_at is not None:
        raise HTTPException(404, "Case not found")
    return obj


@router.patch("/cases/{case_id}", response_model=schemas.CaseOut)
async def update_case(
    case_id: int, body: schemas.CaseUpdate, db: AsyncSession = Depends(get_db)
):
    obj = await db.get(models.Case, case_id)
    if not obj or obj.deleted_at is not None:
        raise HTTPException(404, "Case not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case(case_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(
        update(models.Case).where(models.Case.id == case_id).values(deleted_at=func.now())
    )
    await db.commit()


@router.post("/cases/batch-delete", status_code=200)
async def batch_delete_cases(body: dict, db: AsyncSession = Depends(get_db)):
    ids = body.get("ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(400, "ids 必须是非空数组")
    await db.execute(
        update(models.Case).where(models.Case.id.in_(ids)).values(deleted_at=func.now())
    )
    await db.commit()
    return {"deleted": len(ids)}


# ===== Site Config =====
@router.get("/site-config", response_model=dict[str, Any])
async def list_site_configs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.SiteConfig))
    return {"items": [_to_site_config_dict(s) for s in result.scalars().all()]}


@router.get("/site-config/{key}", response_model=schemas.SiteConfigOut)
async def get_site_config(key: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(models.SiteConfig, key)
    if not obj:
        raise HTTPException(404, "Config not found")
    return obj


@router.put("/site-config/{key}", response_model=schemas.SiteConfigOut)
async def upsert_site_config(
    key: str, body: schemas.SiteConfigUpdate, db: AsyncSession = Depends(get_db)
):
    obj = await db.get(models.SiteConfig, key)
    if obj:
        obj.value = body.value
        obj.description = body.description
    else:
        obj = models.SiteConfig(key=key, value=body.value, description=body.description)
        db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


# ---- helpers ----
def _to_product_dict(p: models.Product) -> dict:
    return {
        "id": p.id,
        "key": p.slug,
        "name": p.name,
        "chinese_name": p.chinese_name,
        "slug": p.slug,
        "tagline": p.tagline,
        "line": p.line,
        "stack": p.stack,
        "desc": p.desc,
        "features": p.features or [],
        "is_flagship": p.is_flagship,
        "is_open_source": p.is_open_source,
        "github_url": p.github_url,
        "demo_url": p.demo_url,
        "website_url": p.website_url,
        "license": p.license,
        "sort": p.sort,
        "status": p.status,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _to_case_dict(c: models.Case) -> dict:
    return {
        "id": c.id,
        "industry": c.industry,
        "name": c.name,
        "desc": c.desc,
        "tag": c.tag,
        "href": c.href,
        "sort": c.sort,
        "status": c.status,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _to_site_config_dict(s: models.SiteConfig) -> dict:
    return {
        "key": s.key,
        "value": s.value,
        "description": s.description,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


# ===== News =====
@router.get("/news", response_model=dict[str, Any])
async def list_news(
    db: AsyncSession = Depends(get_db),
    publish_status: str = Query("published", alias="status"),
    search: str | None = Query(None, description="按 title / slug / excerpt 模糊搜索"),
    include_deleted: bool = Query(False),
    only_deleted: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    conds = apply_filters(
        models.News,
        search=search,
        search_fields=["title", "slug", "excerpt"],
        extra=[models.News.status == publish_status],
        include_deleted=include_deleted,
        only_deleted=only_deleted,
    )
    stmt = (
        select(models.News)
        .where(*conds)
        .order_by(*order_nulls_last(models.News.published_at), models.News.id.desc())
    )
    data = await paginate(db, stmt, page=page, page_size=page_size)
    return {
        "items": [_to_news_dict(n) for n in data["items"]],
        "total": data["total"],
        "page": data["page"],
        "page_size": data["page_size"],
    }


@router.post("/news/{nid}/restore", status_code=200)
async def restore_news(nid: int, db: AsyncSession = Depends(get_db)):
    await db.execute(
        update(models.News).where(models.News.id == nid).values(deleted_at=None)
    )
    await db.commit()
    return {"id": nid, "restored": True}


@router.get("/news/export")
async def export_news_csv(
    db: AsyncSession = Depends(get_db),
    publish_status: str = Query("published", alias="status"),
    search: str | None = None,
):
    conds = apply_filters(
        models.News,
        search=search,
        search_fields=["title", "slug", "excerpt"],
        extra=[models.News.status == publish_status],
    )
    base_stmt = select(models.News).where(*conds)
    return StreamingResponse(
        _csv_stream(db, base_stmt, _news_csv_row, "news"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="news_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"',
        },
    )


@router.post("/news", response_model=schemas.NewsOut, status_code=status.HTTP_201_CREATED)
async def create_news(body: schemas.NewsCreate, db: AsyncSession = Depends(get_db)):
    obj = models.News(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/news/{nid}", response_model=schemas.NewsOut)
async def get_news(nid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(models.News, nid)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "News not found")
    return obj


@router.patch("/news/{nid}", response_model=schemas.NewsOut)
async def update_news(nid: int, body: schemas.NewsUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(models.News, nid)
    if not obj or obj.deleted_at:
        raise HTTPException(404, "News not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/news/{nid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_news(nid: int, db: AsyncSession = Depends(get_db)):
    await db.execute(update(models.News).where(models.News.id == nid).values(deleted_at=func.now()))
    await db.commit()


@router.post("/news/batch-delete", status_code=200)
async def batch_delete_news(body: dict, db: AsyncSession = Depends(get_db)):
    ids = body.get("ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(400, "ids 必须是非空数组")
    await db.execute(
        update(models.News).where(models.News.id.in_(ids)).values(deleted_at=func.now())
    )
    await db.commit()
    return {"deleted": len(ids)}


@router.post("/news/batch-status", status_code=200)
async def batch_update_news_status(body: dict, db: AsyncSession = Depends(get_db)):
    ids = body.get("ids") or []
    new_status = body.get("status")
    if not isinstance(ids, list) or not ids or new_status not in ("draft", "published", "archived"):
        raise HTTPException(400, "参数错误")
    await db.execute(
        update(models.News).where(models.News.id.in_(ids)).values(status=new_status)
    )
    await db.commit()
    return {"updated": len(ids), "status": new_status}


# ===== Media =====
@router.get("/media", response_model=dict[str, Any])
async def list_media(
    db: AsyncSession = Depends(get_db),
    search: str | None = Query(None, description="按 key / url / mime / alt 模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    conds = apply_filters(
        models.Media,
        search=search,
        search_fields=["key", "url", "mime", "alt"],
    )
    stmt = select(models.Media).where(*conds).order_by(models.Media.id.desc())
    data = await paginate(db, stmt, page=page, page_size=page_size)
    return {
        "items": [_to_media_dict(m) for m in data["items"]],
        "total": data["total"],
        "page": data["page"],
        "page_size": data["page_size"],
    }


@router.post("/media/presign", response_model=schemas.MediaPresignResponse)
async def presign_upload(
    body: schemas.MediaPresignRequest,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    """前端直传预签名（推荐）"""
    bucket = body.bucket or settings.S3_BUCKET_PUBLIC
    await s3.ensure_bucket(bucket)

    # 构造 key：日期/uuid-filename
    ext = body.filename.rsplit(".", 1)[-1] if "." in body.filename else ""
    from datetime import datetime
    key = f"{datetime.now().strftime('%Y/%m')}/{uuid.uuid4().hex}.{ext}" if ext else \
          f"{datetime.now().strftime('%Y/%m')}/{uuid.uuid4().hex}"

    expires = 600
    upload_url = await s3.presigned_put_url(bucket, key, expires=expires)
    public_url = _media_public_url(bucket, key, presigned_fallback=upload_url)

    # 写媒体库记录（前端确认上传完成后再调 confirm）
    media = models.Media(
        bucket=bucket, key=key, url=public_url, mime=body.mime,
        size=body.size, uploader_id=current.id,
    )
    db.add(media)
    await db.commit()
    await db.refresh(media)

    return schemas.MediaPresignResponse(
        upload_url=upload_url, key=key, public_url=public_url,
        expires_in=expires,
        headers={"Content-Type": body.mime},
        media_id=media.id,
    )


@router.post("/media/presign/confirm")
async def confirm_upload(
    media_id: int,
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
):
    """前端直传后调用此接口确认（更新元数据/尺寸）"""
    media = await db.get(models.Media, media_id)
    if not media:
        raise HTTPException(404, "Media not found")
    # 可以这里用 Pillow 等拿尺寸；MVP 暂时不取
    return {"id": media.id, "url": media.url}


@router.post("/media/upload", response_model=schemas.MediaUploadResponse)
async def upload_file(
    db: AsyncSession = Depends(get_db),
    current: auth_models.User = Depends(get_current_user),
    file: UploadFile = File(...),
):
    """服务端代理上传（适合小文件，自动提取图片元数据）"""
    bucket = settings.S3_BUCKET_PUBLIC
    await s3.ensure_bucket(bucket)

    content = await file.read()
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else ""
    from datetime import datetime
    key = f"{datetime.now().strftime('%Y/%m')}/{uuid.uuid4().hex}.{ext}" if ext else \
          f"{datetime.now().strftime('%Y/%m')}/{uuid.uuid4().hex}"

    import io
    await s3.upload_fileobj(bucket, key, io.BytesIO(content), file.content_type or "application/octet-stream")
    public_url = _media_public_url(bucket, key)

    # 提取图片元数据
    img_meta = _extract_image_metadata(content, file.content_type or "")

    media = models.Media(
        bucket=bucket, key=key, url=public_url,
        mime=file.content_type or "application/octet-stream",
        size=len(content),
        width=img_meta.get("width"),
        height=img_meta.get("height"),
        uploader_id=current.id,
    )
    db.add(media)
    await db.commit()
    await db.refresh(media)

    return schemas.MediaUploadResponse(
        id=media.id, url=public_url, mime=media.mime, size=media.size,
        width=img_meta.get("width"),
        height=img_meta.get("height"),
    )


@router.delete("/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(media_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(models.Media, media_id)
    if not obj or obj.deleted_at:
        return  # idempotent
    try:
        await s3.delete(obj.bucket, obj.key)
    except Exception:
        pass  # 即使 S3 删失败也软删 DB
    await db.execute(update(models.Media).where(models.Media.id == media_id).values(deleted_at=func.now()))
    await db.commit()


# ---- helpers ----
def _to_news_dict(n: models.News) -> dict:
    return {
        "id": n.id, "slug": n.slug, "title": n.title, "excerpt": n.excerpt,
        "content_md": n.content_md, "cover_image": n.cover_image,
        "status": n.status, "view_count": n.view_count,
        "published_at": n.published_at.isoformat() if n.published_at else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "updated_at": n.updated_at.isoformat() if n.updated_at else None,
    }


def _to_media_dict(m: models.Media) -> dict:
    return {
        "id": m.id, "bucket": m.bucket, "key": m.key, "url": m.url,
        "mime": m.mime, "size": m.size, "width": m.width, "height": m.height,
        "alt": m.alt, "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _extract_image_metadata(content: bytes, content_type: str) -> dict:
    """提取图片元数据（宽高、EXIF）。失败返回空 dict，不影响主流程。"""
    if not content_type or not content_type.startswith("image/"):
        return {}
    try:
        from io import BytesIO
        from PIL import Image
        img = Image.open(BytesIO(content))
        meta = {"width": img.width, "height": img.height, "format": img.format}
        # EXIF（仅 JPEG）
        if hasattr(img, "_getexif") and img.format == "JPEG":
            exif = img._getexif()
            if exif:
                # 0x0112 = Orientation
                orientation = exif.get(0x0112)
                if orientation in (6, 8):  # 旋转 90° / 270°
                    meta["width"], meta["height"] = img.height, img.width
                    meta["rotated"] = True
        return meta
    except Exception:
        return {}


def _generate_thumbnail_url(bucket: str, key: str, width: int = 300) -> str:
    """生成缩略图 URL（占位：MVP 不真生成，只是约定 key 规则）"""
    return f"{settings.PUBLIC_BASE_URL.rsplit(':', 1)[0]}:{settings.S3_API_PORT}/{bucket}/thumbs/{width}_{key.split('/')[-1]}"


# ===== CSV 导出（流式分块） =====
async def _csv_stream(db: AsyncSession, base_stmt, row_fn, model_id_attr: str):
    """通用 CSV 流：先 yield BOM + header，再按 keyset 分块 yield 行。

    关键点：
    - 输出首部加 BOM 让 Excel 正确识别 UTF-8
    - 使用 keyset（id > last_id）分批，避免 OFFSET 在大表上的性能问题
    - 每批 500 行，足够小以控制内存
    """
    yield "\ufeff"  # UTF-8 BOM
    yield ",".join(_CSV_HEADER) + "\r\n"

    # 反射 base_stmt 对应模型主键
    model = base_stmt.column_descriptions[0]["entity"]
    id_col = getattr(model, model_id_attr)

    async for row in stream_for_csv(db, base_stmt, id_column=id_col, batch_size=500):
        yield row_fn(row)


_CSV_HEADER = [
    "id", "name", "chinese_name", "slug", "industry", "tag", "line",
    "title", "excerpt", "status", "view_count", "published_at",
    "created_at", "updated_at",
]


def _product_csv_row(p) -> str:
    return _csv_line([
        p.id, p.name, p.chinese_name, p.slug, "", "", p.line,
        "", "", p.status, "", "",
        _iso(p.created_at), _iso(p.updated_at),
    ])


def _case_csv_row(c) -> str:
    return _csv_line([
        c.id, c.name, "", "", c.industry, c.tag, "",
        "", "", c.status, "", "",
        _iso(c.created_at), _iso(c.updated_at),
    ])


def _news_csv_row(n) -> str:
    return _csv_line([
        n.id, "", "", n.slug, "", "", "",
        n.title, n.excerpt, n.status, n.view_count, _iso(n.published_at),
        _iso(n.created_at), _iso(n.updated_at),
    ])


def _iso(dt):
    return dt.isoformat() if dt else ""


def _csv_line(values) -> str:
    """将任意值转成 CSV 安全字符串。None -> 空，复杂值 -> str()"""
    parts = []
    for v in values:
        if v is None or v == "":
            parts.append("")
        else:
            # csv.writer 处理引号转义；这里手工简单版
            s = str(v)
            if any(c in s for c in [",", '"', "\n", "\r"]):
                s = '"' + s.replace('"', '""') + '"'
            parts.append(s)
    return ",".join(parts) + "\r\n"
