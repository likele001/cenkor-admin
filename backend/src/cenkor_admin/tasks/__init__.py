"""Celery 异步任务"""
from __future__ import annotations

import structlog

from cenkor_admin.core.celery_app import celery_app

log = structlog.get_logger()


@celery_app.task(name="cenkor.send_email")
def send_email_task(to: str, subject: str, body: str) -> dict:
    """发送邮件（MVP：仅记录日志，后续接 SMTP）"""
    log.info("email.send", to=to, subject=subject)
    return {"ok": True, "to": to}


@celery_app.task(name="cenkor.generate_thumbnail")
def generate_thumbnail_task(media_id: int, width: int = 300) -> dict:
    """媒体缩略图生成占位任务"""
    log.info("thumbnail.generate", media_id=media_id, width=width)
    return {"ok": True, "media_id": media_id, "width": width}


@celery_app.task(name="cenkor.archive_audit_logs")
def archive_audit_logs_task(days: int = 365) -> dict:
    """审计日志归档占位任务"""
    log.info("audit.archive", days=days)
    return {"ok": True, "days": days}
