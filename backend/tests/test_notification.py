"""P2 新增端点的纯单元测试（不依赖真 uvicorn，用 ASGITransport）。

策略：
- 用 httpx.AsyncClient + ASGITransport 直接打 FastAPI app
- 共享内存 SQLite（file:./test.db?mode=memory&cache=shared）
- 跑一次 alembic 升级 + seed
- 跳过真 uvicorn 启动
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 必须在 import cenkor_admin 前设置环境
os.environ["APP_ENV"] = "development"
os.environ["SECRET_KEY"] = "test-secret-key-for-unit-tests-only-32bytes"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["DATABASE_URL_SYNC"] = "sqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["SMTP_HOST"] = ""  # 关闭 SMTP 避免外部连接
os.environ["SMTP_FROM"] = "test@local"

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from cenkor_admin import __version__  # noqa
from cenkor_admin.core.db import Base, get_db
from cenkor_admin.main import app


# ---- fixtures ----
@pytest_asyncio.fixture
async def engine():
    """in-memory 异步引擎，跨连接共享"""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as s:
        yield s


@pytest_asyncio.fixture
async def client(engine):
    """httpx AsyncClient 绑定 ASGI app；覆盖 get_db 走 in-memory"""

    async def _override_get_db():
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        async with async_session() as s:
            yield s

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_token(client, engine):
    """用 seed 创建 admin 后获取 token"""
    from cenkor_admin.apps.auth import models as auth_models
    from cenkor_admin.core.security import hash_password
    from cenkor_admin.scripts.seed import DEFAULT_PERMISSIONS, DEFAULT_ROLES, DEFAULT_USERS
    from cenkor_admin.apps.rbac import models as rbac_models
    from cenkor_admin.core.db import AsyncSessionLocal
    from sqlalchemy import select

    # 用直接 import 的 AsyncSessionLocal 写测试数据
    async with AsyncSessionLocal() as db:
        # 强制设置 session 走我们的 in-memory engine
        # 简单办法：禁用原 session，用本 fixture 的 engine
        pass

    # 直接用 fixture 的 engine 写
    from sqlalchemy.ext.asyncio import async_sessionmaker
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        # 创建 permission
        perms = {}
        for code, type_, name in DEFAULT_PERMISSIONS:
            p = rbac_models.Permission(code=code, type=type_, name=name)
            db.add(p)
            perms[code] = p
        await db.flush()

        # 角色
        for code, name_, desc, is_sys, p_codes, _menus in DEFAULT_ROLES:
            role = rbac_models.Role(code=code, name=name_, description=desc, is_system=is_sys)
            db.add(role)
            await db.flush()
            for pc in p_codes:
                db.add(rbac_models.RolePermission(role_id=role.id, permission_id=perms[pc].id))

        # admin 用户
        admin = auth_models.User(
            username="admin", email="admin@cenkor.cn",
            password_hash=hash_password("admin123"),
            nickname="超级管理员", is_superuser=True, status="active",
        )
        db.add(admin)
        await db.commit()

    # 登录（带合法 captcha_token 绕过滑动验证）
    r = await client.post("/api/v1/auth/login", json={
        "username": "admin@cenkor.cn",
        "password": "admin123",
        "captcha_token": "0" * 32,  # 32 位 hex 满足 _verify_slider_captcha
    })
    assert r.status_code == 200, f"登录失败: {r.text}"
    return r.json()["access_token"]


@pytest.fixture
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---- 通知 ----
@pytest.mark.asyncio
async def test_unread_count_admin(client, admin_token, auth_headers):
    r = await client.get("/api/v1/notifications/unread-count", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["unread"] == 0


@pytest.mark.asyncio
async def test_list_notifications_unauth(client):
    r = await client.get("/api/v1/notifications")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_notification_lifecycle(client, admin_token, auth_headers, engine):
    """创建通知 → 列表 → 标记已读 → 全部已读"""
    from cenkor_admin.apps.notification import models
    from sqlalchemy.ext.asyncio import async_sessionmaker
    Session = async_sessionmaker(engine, expire_on_commit=False)

    # 直接写一条通知（user_id=1 是 admin）
    async with Session() as db:
        db.add(models.Notification(user_id=1, type="system", title="测试通知", body="内容"))
        await db.commit()

    r = await client.get("/api/v1/notifications", headers=auth_headers)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["read"] is False
    nid = items[0]["id"]

    # mark read
    r = await client.post(f"/api/v1/notifications/{nid}/read", headers=auth_headers)
    assert r.status_code == 200

    # mark all read
    r = await client.post("/api/v1/notifications/read-all", headers=auth_headers)
    assert r.status_code == 200

    # unread 应为 0
    r = await client.get("/api/v1/notifications/unread-count", headers=auth_headers)
    assert r.json()["unread"] == 0


# ---- 系统设置 ----
@pytest.mark.asyncio
async def test_settings_upsert_and_read(client, admin_token, auth_headers):
    test_key = f"test.unit_upsert"

    r = await client.put(
        f"/api/v1/system/settings/{test_key}",
        json={"value": "hello", "description": "unit test"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["key"] == test_key
    assert data["value"] == "hello"

    r2 = await client.get(f"/api/v1/system/settings/{test_key}", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["value"] == "hello"


@pytest.mark.asyncio
async def test_settings_list(client, admin_token, auth_headers):
    r = await client.get("/api/v1/system/settings", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    # 默认应空
    assert data["total"] == 0


# ---- 定时任务 ----
@pytest.mark.asyncio
async def test_tasks_list(client, admin_token, auth_headers):
    r = await client.get("/api/v1/system/tasks", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    names = {t["name"] for t in data["items"]}
    assert "cenkor.send_email" in names
    assert "cenkor.archive_audit_logs" in names


@pytest.mark.asyncio
async def test_tasks_toggle(client, admin_token, auth_headers):
    r = await client.put(
        "/api/v1/system/tasks/cenkor.send_email/schedule",
        json={"enabled": False, "cron": None},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is False


# ---- API Key ----
@pytest.mark.asyncio
async def test_api_keys_crud(client, admin_token, auth_headers):
    r0 = await client.get("/api/v1/api-keys", headers=auth_headers)
    assert r0.status_code == 200
    before = r0.json()["total"]

    r1 = await client.post(
        "/api/v1/api-keys",
        json={"name": "unit-test-key", "scopes": ["cms:product:read"], "expires_days": 30},
        headers=auth_headers,
    )
    assert r1.status_code == 201
    data = r1.json()
    assert data["name"] == "unit-test-key"
    assert data["token"].startswith("ck_")
    assert data["revoked"] is False
    key_id = data["id"]

    r2 = await client.post(f"/api/v1/api-keys/{key_id}/revoke", headers=auth_headers)
    assert r2.status_code == 200

    r3 = await client.get("/api/v1/api-keys", headers=auth_headers)
    assert r3.status_code == 200
    keys = {k["id"]: k for k in r3.json()["items"]}
    assert keys[key_id]["revoked"] is True


# ---- 登录历史 ----
@pytest.mark.asyncio
async def test_login_history_after_login(client, admin_token, auth_headers):
    """登录后查 login-history 应有 1 条"""
    r = await client.get(
        "/api/v1/auth/users/1/login-history",
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert data["items"][0]["success"] is True


# ---- i18n ----
@pytest.mark.asyncio
async def test_health_includes_supported_locales(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert "supported_locales" in data
    assert "zh-CN" in data["supported_locales"]


@pytest.mark.asyncio
async def test_accept_language_header(client):
    r = await client.get(
        "/api/health",
        headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    assert r.status_code == 200
    assert r.headers.get("content-language") == "en-US"
