"""核心模块单元测试（不依赖外部服务）"""
from __future__ import annotations

import os

# 在 import 项目模块前强制设置环境
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only-32bytes")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# 独立 stub model：避免触发完整 db 初始化（pool_size 等 PG-only 参数）
class _StubBase(DeclarativeBase):
    pass


class _StubModel(_StubBase):
    __tablename__ = "stub_products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), index=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---- core/repository ----
def test_apply_filters_excludes_deleted_by_default():
    """默认不包含已删除"""
    from cenkor_admin.core.repository import apply_filters
    conds = apply_filters(_StubModel, search=None)
    assert any("deleted_at" in str(c) for c in conds)


def test_apply_filters_include_deleted():
    """include_deleted=True 不加 deleted_at 过滤"""
    from cenkor_admin.core.repository import apply_filters
    conds = apply_filters(_StubModel, search=None, include_deleted=True)
    assert not any("deleted_at" in str(c) for c in conds)


def test_apply_filters_only_deleted():
    """only_deleted=True 加 IS NOT NULL 条件"""
    from cenkor_admin.core.repository import apply_filters
    conds = apply_filters(_StubModel, search=None, only_deleted=True)
    assert any("IS NOT NULL" in str(c) for c in conds)


def test_search_filter_skips_numeric_columns():
    """搜索会跳过数值列避免 cast 错误"""
    from cenkor_admin.core.repository import search_filter
    s = search_filter(_StubModel, "test", ["name", "sort"])
    assert s is not None
    compiled = str(s.compile(compile_kwargs={"literal_binds": True}))
    assert "name" in compiled
    assert "sort" not in compiled


def test_search_filter_empty_returns_none():
    from cenkor_admin.core.repository import search_filter
    assert search_filter(_StubModel, None, ["name"]) is None
    assert search_filter(_StubModel, "", ["name"]) is None
    assert search_filter(_StubModel, "  ", ["name"]) is None


# ---- core/security ----
def test_password_hash_and_verify():
    from cenkor_admin.core.security import hash_password, verify_password
    h = hash_password("secret123")
    assert h != "secret123"
    assert verify_password("secret123", h) is True
    assert verify_password("wrong", h) is False


def test_jwt_round_trip():
    from cenkor_admin.core.security import create_access_token, decode_token
    token = create_access_token(42, {"is_superuser": True})
    payload = decode_token(token)
    assert payload["sub"] == "42"
    assert payload["is_superuser"] is True
    assert payload["type"] == "access"


def test_invalid_jwt_rejected():
    from cenkor_admin.core.security import decode_token
    from jose import JWTError
    with pytest.raises(JWTError):
        decode_token("not-a-jwt")


# ---- core/i18n ----
def test_detect_locale_zh():
    from cenkor_admin.core.i18n import detect_locale
    assert detect_locale("zh-CN,zh;q=0.9") == "zh-CN"
    assert detect_locale("zh") == "zh-CN"


def test_detect_locale_en():
    from cenkor_admin.core.i18n import detect_locale
    assert detect_locale("en-US,en;q=0.9") == "en-US"
    assert detect_locale("en-GB,en;q=0.9") == "en-US"


def test_detect_locale_default():
    from cenkor_admin.core.i18n import detect_locale, DEFAULT_LOCALE
    assert detect_locale("") == DEFAULT_LOCALE
    assert detect_locale(None) == DEFAULT_LOCALE
    assert detect_locale("fr-FR") == DEFAULT_LOCALE  # 不支持 → 默认


def test_detect_locale_quality_weight():
    """q 值大的优先"""
    from cenkor_admin.core.i18n import detect_locale
    # en 权重 0.3，zh 权重 0.9 → 应返回 zh-CN
    assert detect_locale("en;q=0.3,zh;q=0.9") == "zh-CN"


# ---- core/mail ----
def test_send_email_no_smtp_configured():
    """未配 SMTP 时 noop，不抛异常"""
    from cenkor_admin.core.mail import send_email_sync
    from cenkor_admin.core.config import get_settings
    s = get_settings()
    if s.SMTP_HOST:
        pytest.skip("SMTP_HOST 已配置，跳过 noop 测试")
    result = send_email_sync("test@example.com", "subj", "body")
    assert result["ok"] is False
    assert result["reason"] == "SMTP 未配置"


# ---- core/config  方言检测 ----
def test_db_dialect_detects_sqlite(monkeypatch):
    from cenkor_admin import core
    # 重置 lru_cache
    from cenkor_admin.core.config import get_settings
    get_settings.cache_clear()

    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    s = get_settings()
    assert s.db_dialect == "sqlite"
    assert s.is_sqlite is True
    assert s.is_postgres is False
    assert s.is_mysql is False

    get_settings.cache_clear()


def test_db_dialect_detects_postgres(monkeypatch):
    from cenkor_admin.core.config import get_settings
    get_settings.cache_clear()

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x/y")
    s = get_settings()
    assert s.db_dialect == "postgresql"
    assert s.is_postgres is True
    assert s.is_sqlite is False

    get_settings.cache_clear()
