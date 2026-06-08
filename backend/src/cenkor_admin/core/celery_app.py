"""Celery 应用入口"""
from __future__ import annotations

from celery import Celery

from cenkor_admin.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "cenkor_admin",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["cenkor_admin.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
)
