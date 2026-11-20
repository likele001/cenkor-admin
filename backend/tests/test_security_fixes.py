"""2026-11-11 安全修复回归测试（纯单元，不依赖 DB / 真服务）。

覆盖：register 下线 / markdown 净化 / CSV 公式注入 / 重置链接白名单 /
JWT tv 撤销与 jti 旋转 / 媒体上传白名单 / 生产配置断言。
"""
import pytest
from fastapi import HTTPException

# ---- P0：公开注册下线 ----

async def test_register_endpoint_gone():
    """/auth/register 必须返回 410，不能再创建后台账号。"""
    from cenkor_admin.apps.auth.router import register

    with pytest.raises(HTTPException) as ei:
        await register(None, None)  # type: ignore[arg-type]
    assert ei.value.status_code == 410


# ---- P1：markdown 输出净化 ----

def test_markdown_strips_script():
    from cenkor_admin.core.jinja_env import _f_markdown

    out = str(_f_markdown("<script>alert(1)</script>**bold**"))
    assert "<script" not in out
    assert "alert(1)" not in out
    assert "<strong>bold</strong>" in out


def test_markdown_strips_event_handlers():
    from cenkor_admin.core.jinja_env import _f_markdown

    out = str(_f_markdown('<img src=x onerror="alert(1)">'))
    assert "onerror" not in out


def test_markdown_strips_javascript_urls():
    from cenkor_admin.core.jinja_env import _f_markdown

    out = str(_f_markdown("[click](javascript:alert(1))"))
    assert "javascript:" not in out


# ---- P2：CSV 公式注入 ----

def test_csv_formula_neutralized():
    from cenkor_admin.apps.auth.router import _csv_cell

    assert _csv_cell("=SUM(A1)").startswith("'")
    assert _csv_cell("+1+1").startswith("'")
    assert _csv_cell("-1+1").startswith("'")
    assert _csv_cell("@SUM(A1)").startswith("'")
    assert _csv_cell("normal") == "normal"
    assert _csv_cell(None) == ""


# ---- P1：重置链接域名白名单 ----

def test_reset_base_rejects_evil_domain():
    from cenkor_admin.apps.auth.router import _safe_reset_base
    from cenkor_admin.core.config import get_settings

    settings = get_settings()
    assert _safe_reset_base("https://evil.com") == settings.PUBLIC_BASE_URL.rstrip("/")
    assert _safe_reset_base(None) == settings.PUBLIC_BASE_URL.rstrip("/")
    # 协议降级 / 畸形输入同样回落
    assert _safe_reset_base("ftp://evil.com") == settings.PUBLIC_BASE_URL.rstrip("/")


def test_reset_base_allows_whitelisted_origin():
    from cenkor_admin.apps.auth.router import _safe_reset_base
    from cenkor_admin.core.config import get_settings

    settings = get_settings()
    origin = (settings.cors_origins_list or [settings.PUBLIC_BASE_URL])[0]
    candidate = origin.rstrip("/") + "/admin"
    assert _safe_reset_base(candidate) == candidate


# ---- P1/P2：JWT tv 撤销 + refresh jti 旋转 ----

def test_access_token_carries_tv():
    from cenkor_admin.core.security import create_access_token, decode_token

    payload = decode_token(create_access_token(42, token_version=3))
    assert payload["tv"] == 3
    # 遗留调用方不传 tv → 不带字段（校验端放行至自然过期）
    assert "tv" not in decode_token(create_access_token(42))


def test_refresh_token_has_unique_jti():
    from cenkor_admin.core.security import create_refresh_token, decode_token

    a = decode_token(create_refresh_token(42, 0))
    b = decode_token(create_refresh_token(42, 0))
    assert a["jti"] and b["jti"]
    assert a["jti"] != b["jti"]


def test_portal_tokens_carry_tv_and_jti():
    from cenkor_admin.apps.portal.auth import (
        create_portal_access_token,
        create_portal_refresh_token,
        decode_portal_token,
    )

    access = decode_portal_token(create_portal_access_token(7, token_version=2))
    assert access["tv"] == 2
    refresh = decode_portal_token(create_portal_refresh_token(7, 2))
    assert refresh["jti"]


# ---- P1：媒体上传白名单 ----

def test_media_ext_whitelist():
    from cenkor_admin.apps.cms.router import _media_ext

    assert _media_ext("photo.JPG") == "jpg"
    assert _media_ext("a/b/c.png") == "png"
    for bad in ("evil.html", "x.svg", "shell.js", "noext", "a.php", "x.htm"):
        with pytest.raises(HTTPException) as ei:
            _media_ext(bad)
        assert ei.value.status_code == 400


def test_media_mime_hardening():
    from cenkor_admin.apps.cms.router import _safe_media_mime

    assert _safe_media_mime("image/png") == "image/png"
    assert _safe_media_mime("application/pdf") == "application/pdf"
    # SVG / HTML 一律降级为下载型 MIME，杜绝内联渲染
    assert _safe_media_mime("image/svg+xml") == "application/octet-stream"
    assert _safe_media_mime("text/html") == "application/octet-stream"
    assert _safe_media_mime(None) == "application/octet-stream"


# ---- P2：生产配置启动断言 ----

def test_production_assert_rejects_default_secret():
    from cenkor_admin.core.config import Settings

    s = Settings(
        APP_ENV="production",
        SECRET_KEY="dev-secret-change-me-32-bytes-min",
        _env_file=None,
    )
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        s.assert_production_ready()


def test_production_assert_rejects_wildcard_cors():
    from cenkor_admin.core.config import Settings

    s = Settings(
        APP_ENV="production",
        SECRET_KEY="x" * 40,
        CORS_ORIGINS="*",
        _env_file=None,
    )
    with pytest.raises(RuntimeError, match="CORS"):
        s.assert_production_ready()


def test_production_assert_passes_when_configured():
    from cenkor_admin.core.config import Settings

    s = Settings(
        APP_ENV="production",
        SECRET_KEY="x" * 40,
        CORS_ORIGINS="https://admin.example.com",
        _env_file=None,
    )
    s.assert_production_ready()  # 不抛即通过
    # 开发环境不做强制
    Settings(APP_ENV="development", _env_file=None).assert_production_ready()
