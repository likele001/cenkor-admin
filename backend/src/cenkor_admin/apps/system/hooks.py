"""内置示例钩子（core 提供，演示插件框架）。

在「内容保存」时额外写一条审计记录，证明 hook 机制端到端可用：
- 安装后（进程启动即 import 本模块）自动注册；
- 任意 App / 内置逻辑保存 Entry 时触发；
- 卸载/清空时不再触发（失败隔离，单钩子异常不影响主流程）。
"""
from __future__ import annotations

import structlog

from cenkor_admin.core.audit import AuditLog
from cenkor_admin.core.hooks import hook

log = structlog.get_logger()


@hook("entry.saved", app_key="core", priority=10)
async def audit_on_entry_saved(*, entry=None, db=None, user=None, **kwargs) -> None:
    """内容保存后写审计（演示 + 实用）。"""
    if db is None or entry is None:
        return
    try:
        db.add(AuditLog(
            request_id="hook:entry.saved",
            user_id=getattr(user, "id", None),
            method="HOOK",
            path=f"/cms/entries/{entry.id}/saved",
            status_code=200,
            duration_ms=0,
            ip=None,
            user_agent="cenkor-hooks",
            diff={
                "entry_id": entry.id,
                "content_type_id": entry.content_type_id,
                "title": entry.title,
                "status": entry.status,
            },
        ))
        await db.commit()
    except Exception as e:  # noqa: BLE001 - 钩子失败隔离
        log.warning("hook.audit_on_entry_saved.failed", entry_id=getattr(entry, "id", None), error=str(e))
