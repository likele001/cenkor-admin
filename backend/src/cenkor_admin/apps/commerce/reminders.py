"""授权到期提醒（门户买家侧）。

触发方式：
- 定时：``apps/commerce/hooks.py`` 订阅 ``scheduler.tick``，每 6 小时最多扫一次；
- 手工：``POST /api/v1/store/reminders/run``（管理员，排查/补发用）。

设计要点：
- **只提醒门户买家**：买断（``expires_at`` 为空）不提醒；退款/吊销状态不发。
- **两档提醒**：距到期 ≤7 天发 ``d7``，≤30 天发 ``d30``，各发一次。
- **去重**：发送成功后在 ``system_settings`` 落 ``license.remind.{key}.{stage}``，
  跨重启、跨进程都只发一次。
- **SMTP 未配置时不落标记**：否则等配置好邮件后这些授权就永远错过了提醒。
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.commerce import models as cm
from cenkor_admin.apps.portal.models import PortalUser
from cenkor_admin.core.config import get_settings
from cenkor_admin.core.licensing import get_setting, put_setting
from cenkor_admin.core.mail import send_email_sync

log = structlog.get_logger()

HORIZON_DAYS = 30
STAGE_DAYS = (7, 30)  # 依次判断，命中第一个即停


def _dedupe_key(license_key: str, stage: str) -> str:
    return f"license.remind.{license_key}.{stage}"


def _stage_for(days: int) -> str | None:
    for d in STAGE_DAYS:
        if days <= d:
            return f"d{d}"
    return None


def _body(lic: cm.AppLicense, days: int, portal_url: str) -> str:
    expiry = lic.expires_at.date().isoformat() if lic.expires_at else "—"
    return (
        f"你好，\n\n"
        f"你购买的「{lic.app_name or lic.app_key}」授权（{lic.license_key}）"
        f"将在 {days} 天后（{expiry}）到期。\n\n"
        f"到期后该应用的接口会返回 402，实例上的相关功能将不可用。"
        f"请提前续费，避免影响业务。\n\n"
        f"查看授权：{portal_url}/my/licenses\n\n"
        f"—— 辰科 Cenkor"
    )


async def run_expiry_reminders(
    db: AsyncSession, *, dry_run: bool = False
) -> dict[str, int]:
    """扫描并发送到期提醒，返回统计。``dry_run`` 只统计不发送、不落标记。"""
    s = get_settings()
    now = datetime.now(UTC)
    horizon = now + timedelta(days=HORIZON_DAYS)

    rows = (await db.execute(
        select(cm.AppLicense).where(
            cm.AppLicense.buyer_type == "portal",
            cm.AppLicense.buyer_id.is_not(None),
            cm.AppLicense.expires_at.is_not(None),
            cm.AppLicense.expires_at > now,
            cm.AppLicense.expires_at <= horizon,
            cm.AppLicense.status.in_(("issued", "active")),
        )
    )).scalars().all()

    stats = {"candidates": len(rows), "sent": 0, "skipped": 0, "failed": 0, "no_smtp": 0}
    if not rows:
        return stats

    if not s.SMTP_HOST:
        # 邮件通道没配：不发送、不落去重标记，等配置好后下一轮仍会提醒
        stats["no_smtp"] = len(rows)
        return stats

    portal_url = (s.PUBLIC_BASE_URL or "https://portal.cenkor.cn").rstrip("/")
    if "admin." in portal_url:
        portal_url = portal_url.replace("admin.", "portal.")

    for lic in rows:
        days = max(0, (lic.expires_at - now).days)
        stage = _stage_for(days)
        if not stage:
            continue
        if await get_setting(db, _dedupe_key(lic.license_key, stage)):
            stats["skipped"] += 1
            continue

        user = await db.get(PortalUser, lic.buyer_id)
        if not user or user.deleted_at is not None or not user.email:
            stats["skipped"] += 1
            continue

        if dry_run:
            stats["sent"] += 1
            continue

        subject = f"【辰科】{lic.app_name or lic.app_key} 授权将在 {days} 天后到期"
        try:
            res = await asyncio.to_thread(
                send_email_sync, user.email, subject, _body(lic, days, portal_url)
            )
        except Exception as exc:  # 单封失败不影响批次
            stats["failed"] += 1
            log.warning("commerce.expiry_reminder_failed", license=lic.license_key, error=str(exc))
            continue
        if not res.get("ok"):
            stats["failed"] += 1
            log.warning(
                "commerce.expiry_reminder_failed",
                license=lic.license_key,
                reason=res.get("reason"),
            )
            continue

        # system_settings.value 是 jsonb，put_setting 内部已 commit
        await put_setting(
            db, _dedupe_key(lic.license_key, stage),
            json.dumps({"sent_at": now.isoformat(), "stage": stage}),
            f"{lic.license_key} 到期提醒（{stage}）",
        )
        stats["sent"] += 1
        log.info("commerce.expiry_reminder_sent", license=lic.license_key,
                 stage=stage, days=days, to=user.email)

    return stats
