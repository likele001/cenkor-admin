"""用户手填固定路径（``cms_entries.url_path``）的校验单测。

这组用例守的是一个真实事故：校验顺序写反时，外部地址会被当成站内路径存进库。

``normalize_user_path`` 会把连续斜杠压成一个，于是 ``https://evil.com/x``
规范化后变成 ``/https:/evil.com/x`` —— 协议头已经没了。
如果先规范化再查 ``://``，检查永远通过，外部地址直接入库。
所以协议头检查必须针对原始输入，这类用例就是防止顺序被改回去。
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from cenkor_admin.apps.cms.content_engine_router import _validate_user_path


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("/mes/abc.html", "/mes/abc.html"),
        ("mes/abc.html", "/mes/abc.html"),
        ("//mes//abc.html", "/mes/abc.html"),
        ("/mes/abc.html?utm=1", "/mes/abc.html"),
        ("/mes/abc.html#top", "/mes/abc.html"),
        ("  /mes/abc.html  ", "/mes/abc.html"),
    ],
)
def test_normalize_accepts_relative_paths(raw: str, expected: str) -> None:
    assert _validate_user_path(raw, None) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "https://evil.com/x",
        "http://evil.com/x",
        "ftp://evil.com/x",
        "//evil.com/x",
        "HTTPS://EVIL.COM/x",
    ],
)
def test_rejects_protocol_prefix(raw: str) -> None:
    """协议头必须在**原始输入**上判定。"""
    with pytest.raises(HTTPException) as exc:
        _validate_user_path(raw, None)
    assert exc.value.status_code == 400
    assert "站内相对路径" in str(exc.value.detail)


@pytest.mark.parametrize("raw", ["/a/../b", "/../etc/passwd", "/mes/../../x"])
def test_rejects_parent_traversal(raw: str) -> None:
    with pytest.raises(HTTPException) as exc:
        _validate_user_path(raw, None)
    assert exc.value.status_code == 400
    assert ".." in str(exc.value.detail)


def test_rejects_root_path() -> None:
    with pytest.raises(HTTPException) as exc:
        _validate_user_path("/", None)
    assert exc.value.status_code == 400


def test_rejects_backslash() -> None:
    with pytest.raises(HTTPException) as exc:
        _validate_user_path("/mes\\abc.html", None)
    assert exc.value.status_code == 400


def test_rejects_too_long() -> None:
    with pytest.raises(HTTPException) as exc:
        _validate_user_path("/" + "a" * 400, None)
    assert exc.value.status_code == 400


def test_none_and_blank_mean_no_custom_path() -> None:
    assert _validate_user_path(None, None) is None
    assert _validate_user_path("   ", None) is None


def test_rejects_non_string() -> None:
    with pytest.raises(HTTPException) as exc:
        _validate_user_path(123, None)  # type: ignore[arg-type]
    assert exc.value.status_code == 400
