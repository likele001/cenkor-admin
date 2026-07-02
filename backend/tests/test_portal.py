"""Portal 用户体系测试

覆盖：
- Portal 用户注册/登录/刷新
- Portal 用户资料更新/密码修改
- Portal 用户 OAuth 绑定管理
- 路由隔离（portal token 无法访问后台 API）
"""

import time
import requests

BASE_URL = "http://localhost:8002"


def get_portal_token(username="test", password="test123456"):
    """获取 portal token"""
    # 先尝试登录
    r = requests.post(f"{BASE_URL}/api/v1/public/portal/auth/login", json={
        "username": username,
        "password": password,
        "captcha_token": "a" * 32,
    })
    if r.status_code == 200:
        return r.json()["access_token"]
    # 登录失败则注册新用户
    ts = int(time.time())
    r = requests.post(f"{BASE_URL}/api/v1/public/portal/auth/register", json={
        "username": f"test_{ts}",
        "email": f"test_{ts}@example.com",
        "password": "test123456",
        "nickname": "Test User",
        "captcha_token": "a" * 32,
    })
    assert r.status_code == 201, f"注册失败: {r.text}"
    return r.json()["access_token"]


def test_portal_register():
    """Portal 用户注册"""
    ts = int(time.time())
    r = requests.post(f"{BASE_URL}/api/v1/public/portal/auth/register", json={
        "username": f"reg_test_{ts}",
        "email": f"reg_test_{ts}@example.com",
        "password": "test123456",
        "nickname": "注册测试",
        "captcha_token": "a" * 32,
    })
    assert r.status_code == 201, f"注册失败: {r.text}"
    data = r.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["username"] == f"reg_test_{ts}"
    assert data["user"]["nickname"] == "注册测试"


def test_portal_register_duplicate_username():
    """重复用户名应返回 409"""
    ts = int(time.time())
    username = f"dup_test_{ts}"
    # 第一次注册
    r = requests.post(f"{BASE_URL}/api/v1/public/portal/auth/register", json={
        "username": username,
        "email": f"{username}@example.com",
        "password": "test123456",
        "captcha_token": "a" * 32,
    })
    assert r.status_code == 201
    # 重复注册
    r = requests.post(f"{BASE_URL}/api/v1/public/portal/auth/register", json={
        "username": username,
        "email": f"{username}_2@example.com",
        "password": "test123456",
        "captcha_token": "a" * 32,
    })
    assert r.status_code == 409


def test_portal_login():
    """Portal 用户登录"""
    ts = int(time.time())
    # 先注册
    r = requests.post(f"{BASE_URL}/api/v1/public/portal/auth/register", json={
        "username": f"login_test_{ts}",
        "email": f"login_test_{ts}@example.com",
        "password": "test123456",
        "captcha_token": "a" * 32,
    })
    assert r.status_code == 201

    # 用用户名登录
    r = requests.post(f"{BASE_URL}/api/v1/public/portal/auth/login", json={
        "username": f"login_test_{ts}",
        "password": "test123456",
        "captcha_token": "a" * 32,
    })
    assert r.status_code == 200, f"登录失败: {r.text}"
    data = r.json()
    assert "access_token" in data
    assert data["user"]["username"] == f"login_test_{ts}"

    # 用邮箱登录
    r = requests.post(f"{BASE_URL}/api/v1/public/portal/auth/login", json={
        "username": f"login_test_{ts}@example.com",
        "password": "test123456",
        "captcha_token": "a" * 32,
    })
    assert r.status_code == 200


def test_portal_login_wrong_password():
    """密码错误返回 401"""
    ts = int(time.time())
    r = requests.post(f"{BASE_URL}/api/v1/public/portal/auth/register", json={
        "username": f"pwd_test_{ts}",
        "email": f"pwd_test_{ts}@example.com",
        "password": "test123456",
        "captcha_token": "a" * 32,
    })
    assert r.status_code == 201

    r = requests.post(f"{BASE_URL}/api/v1/public/portal/auth/login", json={
        "username": f"pwd_test_{ts}",
        "password": "wrong_password",
        "captcha_token": "a" * 32,
    })
    assert r.status_code == 401


def test_portal_refresh_token():
    """Refresh token 流程"""
    ts = int(time.time())
    r = requests.post(f"{BASE_URL}/api/v1/public/portal/auth/register", json={
        "username": f"refresh_test_{ts}",
        "email": f"refresh_test_{ts}@example.com",
        "password": "test123456",
        "captcha_token": "a" * 32,
    })
    assert r.status_code == 201
    refresh_token = r.json()["refresh_token"]

    r = requests.post(f"{BASE_URL}/api/v1/public/portal/auth/refresh", json={
        "refresh_token": refresh_token,
    })
    assert r.status_code == 200, f"刷新失败: {r.text}"
    data = r.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_portal_me():
    """获取当前 Portal 用户信息"""
    token = get_portal_token()
    r = requests.get(f"{BASE_URL}/api/v1/public/portal/me", headers={
        "Authorization": f"Bearer {token}",
    })
    assert r.status_code == 200, f"获取用户信息失败: {r.text}"
    data = r.json()
    assert "id" in data
    assert "username" in data


def test_portal_update_profile():
    """更新 Portal 用户资料"""
    token = get_portal_token()
    r = requests.patch(f"{BASE_URL}/api/v1/public/portal/me/profile", headers={
        "Authorization": f"Bearer {token}",
    }, json={
        "nickname": "Updated Nickname",
    })
    assert r.status_code == 200, f"更新失败: {r.text}"
    assert r.json()["nickname"] == "Updated Nickname"


def test_portal_change_password():
    """修改 Portal 用户密码"""
    ts = int(time.time())
    username = f"pwd_change_{ts}"
    # 注册
    r = requests.post(f"{BASE_URL}/api/v1/public/portal/auth/register", json={
        "username": username,
        "email": f"{username}@example.com",
        "password": "old_password",
        "captcha_token": "a" * 32,
    })
    assert r.status_code == 201
    token = r.json()["access_token"]

    # 修改密码
    r = requests.post(f"{BASE_URL}/api/v1/public/portal/me/change-password", headers={
        "Authorization": f"Bearer {token}",
    }, json={
        "old_password": "old_password",
        "new_password": "new_password_123",
    })
    assert r.status_code == 204, f"修改密码失败: {r.text}"

    # 用新密码登录
    r = requests.post(f"{BASE_URL}/api/v1/public/portal/auth/login", json={
        "username": username,
        "password": "new_password_123",
        "captcha_token": "a" * 32,
    })
    assert r.status_code == 200, f"新密码登录失败: {r.text}"


def test_portal_oauth_bind_unbind():
    """OAuth 绑定和解绑"""
    token = get_portal_token()

    # 绑定
    r = requests.post(f"{BASE_URL}/api/v1/public/portal/me/oauth/bind", headers={
        "Authorization": f"Bearer {token}",
    }, json={
        "provider": "wechat",
        "open_id": f"test_openid_{int(time.time())}",
        "union_id": "test_unionid",
    })
    assert r.status_code == 201, f"绑定失败: {r.text}"
    oauth_id = r.json()["id"]

    # 列出绑定
    r = requests.get(f"{BASE_URL}/api/v1/public/portal/me/oauth", headers={
        "Authorization": f"Bearer {token}",
    })
    assert r.status_code == 200
    bindings = r.json()
    assert any(b["id"] == oauth_id for b in bindings)

    # 解绑
    r = requests.delete(f"{BASE_URL}/api/v1/public/portal/me/oauth/{oauth_id}", headers={
        "Authorization": f"Bearer {token}",
    })
    assert r.status_code == 204, f"解绑失败: {r.text}"


def test_portal_token_cannot_access_admin_api():
    """Portal token 无法访问后台 API"""
    token = get_portal_token()

    # 尝试访问后台 CMS API
    r = requests.get(f"{BASE_URL}/api/v1/cms/content-types", headers={
        "Authorization": f"Bearer {token}",
    })
    assert r.status_code == 403, f"应该返回 403，但返回了 {r.status_code}"
    assert "前台用户" in r.json()["detail"]

    # 尝试访问后台用户列表
    r = requests.get(f"{BASE_URL}/api/v1/auth/users", headers={
        "Authorization": f"Bearer {token}",
    })
    assert r.status_code == 403


def test_admin_token_cannot_access_portal_me():
    """Admin token 无法访问 Portal /me"""
    # 获取 admin token
    r = requests.post(f"{BASE_URL}/api/v1/auth/login", json={
        "username": "admin@cenkor.cn",
        "password": "admin123",
        "captcha_token": "a" * 32,
    })
    assert r.status_code == 200
    admin_token = r.json()["access_token"]

    # 尝试访问 portal /me
    r = requests.get(f"{BASE_URL}/api/v1/public/portal/me", headers={
        "Authorization": f"Bearer {admin_token}",
    })
    assert r.status_code in (401, 403), f"应该返回 401 或 403，但返回了 {r.status_code}"


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
        except Exception as e:
            print(f"  ✗ {t.__name__}: {e}")
