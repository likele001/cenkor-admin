"""邮件发送（SMTP 接入）。

- 优先使用 Celery 异步任务（生产）
- dev 环境（DEBUG=True）直接同步发送，方便调试
"""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

import structlog

from cenkor_admin.core.config import get_settings

log = structlog.get_logger()


def send_email_sync(to: str, subject: str, body: str, *, html: bool = False) -> dict:
    """同步发送邮件（dev / 调试用）。

    返回 {ok, transport}，失败抛出异常由调用方决定是否回退。
    """
    settings = get_settings()
    if not settings.SMTP_HOST:
        log.warning("email.smtp.not_configured", to=to, subject=subject)
        return {"ok": False, "transport": "noop", "reason": "SMTP 未配置"}

    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    if html:
        msg.set_content("This email requires an HTML viewer.")
        msg.add_alternative(body, subtype="html")
    else:
        msg.set_content(body)

    try:
        if settings.SMTP_PORT == 465:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, context=ctx, timeout=10) as s:
                if settings.SMTP_USER:
                    s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                s.send_message(msg)
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as s:
                s.ehlo()
                if settings.SMTP_USE_TLS:
                    s.starttls(context=ssl.create_default_context())
                    s.ehlo()
                if settings.SMTP_USER:
                    s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                s.send_message(msg)
        log.info("email.sent", to=to, subject=subject, transport="smtp")
        return {"ok": True, "transport": "smtp"}
    except Exception as e:
        log.error("email.send.failed", to=to, subject=subject, error=str(e))
        raise


def send_email(to: str, subject: str, body: str, *, html: bool = False) -> dict:
    """统一入口：dev 同步 / 生产 Celery 异步。"""
    settings = get_settings()
    if settings.DEBUG or not settings.SMTP_HOST:
        return send_email_sync(to, subject, body, html=html)
    try:
        from cenkor_admin.tasks import send_email_task
        send_email_task.delay(to, subject, body)
        return {"ok": True, "transport": "celery"}
    except Exception as e:
        log.warning("email.celery.unavailable", error=str(e))
        return send_email_sync(to, subject, body, html=html)
