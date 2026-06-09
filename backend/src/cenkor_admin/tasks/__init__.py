"""Celery 异步任务"""
from __future__ import annotations

import structlog

from cenkor_admin.core.celery_app import celery_app
from cenkor_admin.core.mail import send_email_sync

log = structlog.get_logger()


@celery_app.task(name="cenkor.send_email", bind=True, max_retries=3, default_retry_delay=60)
def send_email_task(self, to: str, subject: str, body: str, html: bool = False) -> dict:
    """异步发邮件（生产）；失败重试 3 次。"""
    try:
        return send_email_sync(to, subject, body, html=html)
    except Exception as e:
        log.warning("email.task.retry", error=str(e), to=to)
        raise self.retry(exc=e)


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


# 任务注册表（用于定时任务 UI 展示 / 调度）
TASK_REGISTRY: list[dict] = [
    {
        "name": "cenkor.send_email",
        "title": "发送邮件",
        "description": "异步发送邮件（生产）；失败自动重试 3 次",
        "default_schedule": "on_demand",
    },
    {
        "name": "cenkor.generate_thumbnail",
        "title": "生成缩略图",
        "description": "为上传的媒体生成缩略图",
        "default_schedule": "on_demand",
    },
    {
        "name": "cenkor.archive_audit_logs",
        "title": "归档审计日志",
        "description": "将 N 天前的审计日志归档到冷存储",
        "default_schedule": "0 3 * * *",  # 每天凌晨 3 点
    },
]
