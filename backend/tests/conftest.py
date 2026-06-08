"""pytest 公共 fixtures"""
import os
import sys
import time
from pathlib import Path

import pytest
import requests

# 强制配置
os.environ["APP_ENV"] = "development"
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://cenkor:li123456@localhost:5433/cenkor")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://cenkor:li123456@localhost:5433/cenkor")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only-32bytes")
os.environ.setdefault("REDIS_URL", "redis://localhost:6380/0")
os.environ.setdefault("S3_ENDPOINT", "http://localhost:9002")
os.environ.setdefault("S3_ACCESS_KEY", "minio")
os.environ.setdefault("S3_SECRET_KEY", "minio12345")
os.environ.setdefault("S3_BUCKET_PUBLIC", "cenkor-public")
os.environ.setdefault("S3_BUCKET_PRIVATE", "cenkor-private")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# 测试用真 uvicorn（已起在 8002）
BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8002")


@pytest.fixture(scope="function")
def client():
    """同步 HTTP 客户端（requests，连真 uvicorn）"""
    s = requests.Session()
    s.base_url = BASE_URL
    yield s
    s.close()


@pytest.fixture(scope="function")
def admin_token(client):
    """获取 admin token（每次新登录，避免 logout 副作用）"""
    r = client.post(f"{BASE_URL}/api/v1/auth/login", json={
        "username": "admin@cenkor.cn",
        "password": "admin123",
    })
    assert r.status_code == 200, f"登录失败: {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="function")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="function")
def unique_id():
    """每个测试用唯一 ID（避免 DB 残留冲突）"""
    return int(time.time() * 1000)
