"""Security 模块测试"""
import pytest


@pytest.mark.asyncio
async def test_password_hash_and_verify():
    """密码哈希可逆验证"""
    from cenkor_admin.core.security import hash_password, verify_password
    h = hash_password("my-secret-password")
    assert h != "my-secret-password"  # 不应该明文
    assert verify_password("my-secret-password", h) is True
    assert verify_password("wrong-password", h) is False


@pytest.mark.asyncio
async def test_jwt_round_trip():
    """JWT 编解码"""
    from cenkor_admin.core.security import create_access_token, decode_token
    token = create_access_token(42, {"role": "admin"})
    payload = decode_token(token)
    assert payload["sub"] == "42"
    assert payload["type"] == "access"
    assert payload["role"] == "admin"


@pytest.mark.asyncio
async def test_invalid_jwt_rejected():
    """非法 token 被拒"""
    from jose import JWTError
    from cenkor_admin.core.security import decode_token
    with pytest.raises(JWTError):
        decode_token("not-a-valid-token")
