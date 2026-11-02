"""第三方 App 的模板标签注册机制。

站点主题有 16 个内置数据 API + 16 个过滤器，那是核心资产，App 不能覆盖。
这里约束的是 App 自己带进来的标签（apps/<key>/template_tags.py）：

- 名字合法、不撞内置、不跨 App 重名，否则静默跳过并留 warning
- 函数签名的第一个参数固定是 ctx，绑定时注入当前 TemplateContext
- 卸载后必须真的消失，不能留在 env.filters 里继续可用
"""
import pytest
from jinja2.exceptions import SecurityError, TemplateAssertionError

from cenkor_admin.core import jinja_env


@pytest.fixture(autouse=True)
def _isolate():
    jinja_env.clear_template_cache()
    yield
    for key in ("t_app", "t_other"):
        jinja_env.unregister_template_api(key)
    jinja_env.clear_template_cache()


def test_function_gets_ctx_injected():
    seen = {}

    def whoami(ctx, suffix="!"):
        seen["ctx"] = ctx
        return f"hello{suffix}"

    jinja_env.register_template_api("t_app", functions={"t_whoami": whoami})
    ctx = object()
    bound = jinja_env.bind_app_function(whoami, ctx)
    out = jinja_env.render_source("{{ t_whoami('?') }}", {"t_whoami": bound})

    assert out == "hello?"
    assert seen["ctx"] is ctx


def test_bound_function_is_callable_in_sandbox():
    fn = jinja_env.bind_app_function(lambda ctx: "ok", object())
    assert getattr(fn, "__cms_api__", False) is True


def test_unregistered_tag_is_not_callable():
    # sandbox 把未定义的函数调用拦成 SecurityError（实测：Undefined is not safely callable）
    with pytest.raises(SecurityError):
        jinja_env.render_source("{{ nosuchtag() }}", {})


def test_unregister_removes_function():
    jinja_env.register_template_api("t_app", functions={"t_x": lambda ctx: "X"})
    assert "t_x" in jinja_env.app_template_functions()

    jinja_env.unregister_template_api("t_app")
    assert "t_x" not in jinja_env.app_template_functions()


def test_reserved_name_rejected():
    result = jinja_env.register_template_api(
        "t_app", functions={"content_list": lambda ctx: 1}
    )
    assert result["functions"] == 0
    assert "content_list" not in jinja_env.app_template_functions()


def test_builtin_filter_name_rejected():
    # date 是核心过滤器，App 不许静默覆盖
    result = jinja_env.register_template_api("t_app", filters={"date": lambda v: "x"})
    assert result["filters"] == 0


def test_bad_names_rejected():
    result = jinja_env.register_template_api(
        "t_app",
        functions={"Bad-Name": lambda ctx: 1, "9start": lambda ctx: 1, "": lambda ctx: 1},
        filters={"UPPER": lambda v: v},
    )
    assert result["functions"] == 0
    assert result["filters"] == 0


def test_non_callable_rejected():
    result = jinja_env.register_template_api("t_app", functions={"t_str": "not-callable"})
    assert result["functions"] == 0


def test_cross_app_conflict_rejected():
    first = jinja_env.register_template_api("t_app", functions={"t_dup": lambda ctx: 1})
    second = jinja_env.register_template_api("t_other", functions={"t_dup": lambda ctx: 2})

    assert first["functions"] == 1
    assert second["functions"] == 0


def test_same_app_reregister_overwrites():
    jinja_env.register_template_api("t_app", functions={"t_v": lambda ctx: "old"})
    jinja_env.register_template_api("t_app", functions={"t_v": lambda ctx: "new"})

    fn = jinja_env.app_template_functions()["t_v"]
    assert fn(None) == "new"


def test_filter_usable_after_register():
    jinja_env.register_template_api(
        "t_app", filters={"t_shout": lambda v: str(v).upper() + "!"}
    )
    out = jinja_env.render_source("{{ 'hi'|t_shout }}", {})
    assert out == "HI!"


def test_filter_gone_after_unregister():
    jinja_env.register_template_api("t_app", filters={"t_shout": lambda v: "x"})
    assert "t_shout" in jinja_env.app_template_filters()

    jinja_env.unregister_template_api("t_app")

    assert "t_shout" not in jinja_env.app_template_filters()
    assert "t_shout" not in jinja_env.get_env().filters
    # 过滤器在编译期被判定不存在 -> TemplateAssertionError（TemplateSyntaxError 的子类）
    with pytest.raises(TemplateAssertionError):
        jinja_env.render_source("{{ 'hi'|t_gone_filter }}", {})


def test_plain_callable_still_blocked():
    class Box:
        def danger(self):
            return "boom"

    # sandbox 不允许调用任意对象方法 -> SecurityError
    with pytest.raises(SecurityError):
        jinja_env.render_source("{{ b.danger() }}", {"b": Box()})
