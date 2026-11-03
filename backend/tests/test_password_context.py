"""口令哈希上下文测试（bcrypt 4.x 兼容层回归保护）。"""
import bcrypt


def test_bcrypt_about_shim_installed():
    """bcrypt >=4.1 删了 __about__，core.pwd 必须补回，否则 passlib 版本探测失败。

    passlib 1.7.4 在 _load_backend_mixin 里读 bcrypt.__about__.__version__，
    缺失时会打印 "(trapped) error reading bcrypt version" 并进入版本未知分支。
    """
    from cenkor_admin.core import pwd  # noqa: F401  导入即装垫片

    assert hasattr(bcrypt, "__about__")
    assert bcrypt.__about__.__version__ == bcrypt.__version__


def test_pwd_context_is_single_instance():
    """core / portal / security 必须共用同一个 CryptContext，避免参数分叉。"""
    from cenkor_admin.apps.portal.auth import pwd_context as portal_ctx
    from cenkor_admin.core.pwd import pwd_context as core_ctx
    from cenkor_admin.core.security import pwd_context as security_ctx

    assert portal_ctx is core_ctx is security_ctx


def test_hash_format_and_cross_module_verify():
    """core 生成的 $2b$ 哈希必须能被 portal 校验（跨入口口令互通）。"""
    from cenkor_admin.apps.portal.auth import verify_password as portal_verify
    from cenkor_admin.core.security import hash_password

    hashed = hash_password("跨模块口令-test")
    assert hashed.startswith("$2b$")
    assert portal_verify("跨模块口令-test", hashed) is True
    assert portal_verify("错误口令", hashed) is False
