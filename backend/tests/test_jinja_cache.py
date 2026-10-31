"""模板编译缓存的行为约束。

Jinja 的 env.cache 按「模板名」缓存编译产物，key 不含源码 ——
`{% include %}` 出来的 partial 一旦编译过，换 resolver（预览的未保存内容）
也拿不回来。flush_compiled_templates() 就是给这个场景用的：
预览渲染前必须清，否则「改了 partials/header.html，预览还是老样子」。
"""
import pytest

from cenkor_admin.core import jinja_env


@pytest.fixture(autouse=True)
def _clean_cache():
    jinja_env.clear_template_cache()
    yield
    jinja_env.clear_template_cache()


def test_include_picks_up_changed_source_after_flush():
    r1 = {
        'partials/x.html': '<b>OLD</b>',
        'main.html': 'A{% include "partials/x.html" %}',
    }
    r2 = {
        'partials/x.html': '<b>NEW</b>',
        'main.html': 'A{% include "partials/x.html" %}',
    }

    t1 = jinja_env.set_resolver(r1.get)
    try:
        assert 'OLD' in jinja_env.render_template_file('main.html', {})
    finally:
        jinja_env.reset_resolver(t1)

    # 换 resolver（模拟预览注入未保存内容）。修复前这里命中 env.cache 拿到 OLD。
    t2 = jinja_env.set_resolver(r2.get)
    try:
        jinja_env.flush_compiled_templates()
        assert 'NEW' in jinja_env.render_template_file('main.html', {})
        assert 'OLD' not in jinja_env.render_template_file('main.html', {})
    finally:
        jinja_env.reset_resolver(t2)


def test_render_source_caches_by_content():
    """render_source 那条路按「源码 md5」缓存，同名不同源码互不干扰，不需要 flush。"""
    assert jinja_env.render_source('X{{ n }}', {'n': 1}, name='t.html') == 'X1'
    assert jinja_env.render_source('X{{ n }}', {'n': 2}, name='t.html') == 'X2'
