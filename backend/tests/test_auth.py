"""Auth 模块测试（用真 uvicorn）"""


def test_health(client):
    """健康检查"""
    r = client.get(f"{client.base_url}/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["db"] == "postgresql"


def test_login_success(client):
    """登录成功"""
    r = client.post(f"{client.base_url}/api/v1/auth/login", json={
        "username": "admin@cenkor.cn",
        "password": "admin123",
    })
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["username"] == "admin"
    assert data["user"]["is_superuser"] is True
    assert len(data["user"]["permissions"]) > 0


def test_login_wrong_password(client):
    """密码错误"""
    r = client.post(f"{client.base_url}/api/v1/auth/login", json={
        "username": "admin@cenkor.cn",
        "password": "wrong-password",
    })
    assert r.status_code == 401


def test_login_nonexistent_user(client):
    """用户不存在"""
    r = client.post(f"{client.base_url}/api/v1/auth/login", json={
        "username": "nobody@cenkor.cn",
        "password": "whatever",
    })
    assert r.status_code == 401


def test_me_with_token(client, auth_headers):
    """/me 鉴权 + 权限返回"""
    r = client.get(f"{client.base_url}/api/v1/auth/me", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["username"] == "admin"
    assert data["is_superuser"] is True
    assert "cms:product:read" in data["permissions"]
    assert len(data["menus"]) > 0


def test_me_without_token(client):
    """/me 未鉴权"""
    r = client.get(f"{client.base_url}/api/v1/auth/me")
    assert r.status_code == 401


def test_refresh_token(client):
    """refresh token 流程"""
    login_r = client.post(f"{client.base_url}/api/v1/auth/login", json={
        "username": "admin@cenkor.cn",
        "password": "admin123",
    })
    refresh = login_r.json()["refresh_token"]
    r = client.post(f"{client.base_url}/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data


def test_invalid_refresh_token(client):
    """非法 refresh token"""
    r = client.post(f"{client.base_url}/api/v1/auth/refresh", json={"refresh_token": "invalid-token"})
    assert r.status_code == 401


def test_logout_increments_token_version(client, auth_headers, unique_id):
    """登出应成功 204（token_version 在下次 refresh 时才校验）"""
    r = client.post(f"{client.base_url}/api/v1/auth/logout", headers=auth_headers)
    assert r.status_code == 204
    # 注：access token 仍能用到 15 分钟，但 refresh 会被拒
    # 完整测试 token_version 流程在 rbac/test_rbac.py 里有
