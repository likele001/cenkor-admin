"""公告 App 钩子：订阅 scheduler.tick，驱动 CHANGELOG → 首页公告自动同步。

每 30 秒 tick 一次；sync_if_changed 内部有进程内 md5 指纹缓存，
文件没变时零数据库查询，成本可忽略。同步放后台任务，不阻塞 tick。
App 停用/卸载时 hooks.clear_app 会自动摘掉订阅。
"""
from __future__ import annotations

import asyncio

from cenkor_admin.core.hooks import hook


@hook("scheduler.tick")
async def autolog_tick(**_: object) -> None:
    from cenkor_admin.apps.announcements import autolog

    asyncio.create_task(autolog.sync_if_changed())
