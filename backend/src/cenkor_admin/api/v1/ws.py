"""WebSocket 端点：实时通知 + 在线心跳。

- /api/v1/ws/notifications：已登录用户的实时通知推送
- 通过 token 查询参数做轻量鉴权（生产可换 Sec-WebSocket-Protocol）
- 心跳：每 25s 客户端发送 ping，服务端回复 pong
"""
from __future__ import annotations

import asyncio
import json
import time

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError

from cenkor_admin.core.redis import redis_client
from cenkor_admin.core.security import decode_token

log = structlog.get_logger()
router = APIRouter()


@router.websocket("/ws/notifications")
async def notifications_ws(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
):
    """实时通知 WS 连接。

    协议（JSON 消息）：
    - 客户端 -> 服务端：{"type": "ping"}
    - 服务端 -> 客户端：{"type": "pong", "ts": ...}
    - 服务端 -> 客户端：{"type": "notification", "data": {...}}
    """
    # 鉴权
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            await websocket.close(code=4001)
            return
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        await websocket.close(code=4001)
        return

    # 与 HTTP 依赖同等待遇：查用户状态 + token_version。
    # 否则被禁用/删除的用户、已登出的会话仍能挂着 WS 收通知直到 token 过期
    from cenkor_admin.apps.auth import models as auth_models
    from cenkor_admin.core.db import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        ws_user = await session.get(auth_models.User, user_id)
    if ws_user is None or ws_user.deleted_at is not None or ws_user.status != "active":
        await websocket.close(code=4001)
        return
    tv = payload.get("tv")
    if tv is not None and tv != (ws_user.token_version or 0):
        await websocket.close(code=4001)
        return

    await websocket.accept()
    log.info("ws.connected", user_id=user_id)

    # 订阅 Redis pubsub（如果有通知服务 publish）
    last_ping_ts = 0.0

    async def reader():
        nonlocal last_ping_ts
        while True:
            try:
                msg = await websocket.receive_text()
                if msg == "ping" or (msg.startswith("{") and json.loads(msg).get("type") == "ping"):
                    await websocket.send_text(json.dumps({"type": "pong", "ts": time.time()}))
                    last_ping_ts = time.time()
            except WebSocketDisconnect:
                raise
            except Exception as e:
                log.warning("ws.read.error", error=str(e))
                raise

    async def heartbeat():
        nonlocal last_ping_ts
        while True:
            await asyncio.sleep(30)
            if time.time() - last_ping_ts > 90:
                # 客户端 90s 没心跳，关闭
                await websocket.close(code=4002)
                return
            try:
                await websocket.send_text(json.dumps({"type": "heartbeat", "ts": time.time()}))
            except Exception:
                return

    async def notifier():
        """从 Redis pubsub 拉通知，广播给客户端。"""
        try:
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(f"notify:user:{user_id}")
            async for raw in pubsub.listen():
                if raw["type"] != "message":
                    continue
                try:
                    data = json.loads(raw["data"])
                    await websocket.send_text(json.dumps({"type": "notification", "data": data}))
                except Exception as e:
                    log.warning("ws.notify.send_failed", error=str(e))
        except Exception as e:
            log.info("ws.pubsub.unavailable", error=str(e), hint="dev 环境无 redis 是正常的，连接将退化为 heartbeat-only")

    tasks = [
        asyncio.create_task(reader(), name="ws.reader"),
        asyncio.create_task(heartbeat(), name="ws.heartbeat"),
        asyncio.create_task(notifier(), name="ws.notifier"),
    ]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        # 必须把已完成任务的异常取走：客户端关标签页时 reader 会抛 WebSocketDisconnect，
        # 没人 retrieve 的话 asyncio 会在事件循环退出时刷一条
        # "Task exception was never retrieved" ERROR —— 纯噪音，还会掩盖真错误。
        for t in done:
            if t.cancelled():
                continue
            exc = t.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                log.warning("ws.task_failed", task=t.get_name(), error=str(exc))
        # 等 cancel 真正生效，避免退出时留下悬挂任务
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    except WebSocketDisconnect:
        pass
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        log.info("ws.disconnected", user_id=user_id)
