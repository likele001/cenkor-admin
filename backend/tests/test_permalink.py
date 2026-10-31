"""permalink 引擎单测。纯函数，不依赖 DB / FastAPI，可直接 pytest 跑。"""

from __future__ import annotations

import pytest

from cenkor_admin.apps.cms import permalink as P

# ---------------------------------------------------------------- 校验


@pytest.mark.parametrize(
    "pattern,kind",
    [
        ("{type}/{slug}.html", "article"),
        ("{catdir}/{slug}.html", "article"),
        ("{catdir}/{id}.html", "product"),
        ("{type}/{year}/{month}/{slug}.html", "news"),
        ("p/{slug}.html", "page"),
        ("category/{slug}/", "category"),
        ("tag/{slug}/", "tag"),
        ("{catdir}/", "category"),
        ("{parent}/{slug}/", "category"),
    ],
)
def test_validate_accepts(pattern: str, kind: str) -> None:
    assert P.validate_pattern(pattern, kind)


@pytest.mark.parametrize(
    "pattern,kind,fragment",
    [
        ("", "article", "不能为空"),
        ("/{slug}.html", "article", ""),  # 首斜杠会被规范掉，属正常
        ("article/", "article", "至少要有一个变量"),
        ("{type}/{catdir}.html", "article", "必须有"),
        ("{nope}/{slug}.html", "article", "不支持变量"),
        ("{slug}/{slug}.html", "article", "重复"),
        ("{catdir}/{slug}.html", "tag", "不支持变量"),
        ("{parent}/{slug}.html", "article", "不支持变量"),
        ("{slug}.html/../../etc", "article", "不允许"),
        ("a/b/c/d/e/f/{slug}", "article", "层级过深"),
    ],
)
def test_validate_rejects(pattern: str, kind: str, fragment: str) -> None:
    if pattern.startswith("/") and fragment == "":
        assert P.validate_pattern(pattern, kind) == "{slug}.html"
        return
    with pytest.raises(P.RuleError) as exc:
        P.validate_pattern(pattern, kind)
    assert fragment in str(exc.value)


# ---------------------------------------------------------------- 生成：默认规则必须复刻现状


def test_default_patterns_reproduce_current_urls() -> None:
    """改造前的线上形态，一个字都不能变 —— 这是上线的安全底线。"""
    cases = [
        (
            "article",
            {"type": "article", "slug": "content-ops-counterintuitive"},
            "/article/content-ops-counterintuitive.html",
        ),
        (
            "product",
            {"type": "product", "slug": "mes-scheduling-misconceptions"},
            "/product/mes-scheduling-misconceptions.html",
        ),
        (
            "news",
            {"type": "news", "slug": "manufacturing-ai-paths"},
            "/news/manufacturing-ai-paths.html",
        ),
        (
            "case",
            {"type": "case", "slug": "auto-parts-yield-case"},
            "/case/auto-parts-yield-case.html",
        ),
        ("page", {"type": "page", "slug": "about"}, "/p/about.html"),
        ("category", {"type": "article", "slug": "mes"}, "/category/mes/"),
        ("tag", {"type": "article", "slug": "lean"}, "/tag/lean/"),
        ("_list", {"type": "article"}, "/article/"),
    ]
    for kind, values, expected in cases:
        got = P.build_url(P.DEFAULT_PATTERNS[kind], values)
        assert got == expected, f"{kind}: {got} != {expected}"


def test_catdir_with_parent() -> None:
    url = P.build_url("{catdir}/{slug}.html", {"catdir": "hangye/xinwen", "slug": "abc"})
    assert url == "/hangye/xinwen/abc.html"


def test_catdir_empty_is_not_applicable() -> None:
    """没栏目的内容套不上带 catdir 的规则，必须回落而不是拼出 //x.html。"""
    with pytest.raises(P.RuleNotApplicable):
        P.build_url("{catdir}/{slug}.html", {"catdir": "", "slug": "abc"})


def test_id_pattern() -> None:
    assert P.build_url("{type}/{id}.html", {"type": "product", "id": 1024}) == "/product/1024.html"


def test_date_pattern() -> None:
    url = P.build_url(
        "{type}/{year}/{month}/{slug}.html",
        {"type": "article", "year": 2026, "month": 10, "slug": "abc"},
    )
    assert url == "/article/2026/10/abc.html"


def test_no_suffix_pattern() -> None:
    assert P.build_url("{catdir}/{slug}/", {"catdir": "mes", "slug": "abc"}) == "/mes/abc/"


# ---------------------------------------------------------------- 解析（反向）


def test_parse_default_article() -> None:
    rules = [P.Rule("article", "{type}/{slug}.html")]
    m = P.parse_path("/article/abc.html", rules)
    assert m is not None
    assert m.kind == "article"
    assert m.get("slug") == "abc"
    assert m.get("type") == "article"


def test_parse_catdir_nested() -> None:
    rules = [P.Rule("article", "{catdir}/{slug}.html")]
    m = P.parse_path("/hangye/xinwen/abc.html", rules)
    assert m is not None
    assert m.get("catdir") == "hangye/xinwen"
    assert m.get("slug") == "abc"


def test_parse_catdir_single_segment() -> None:
    rules = [P.Rule("article", "{catdir}/{slug}.html")]
    m = P.parse_path("/mes/abc.html", rules)
    assert m is not None
    assert m.get("catdir") == "mes"
    assert m.get("slug") == "abc"


def test_parse_catdir_backtracks_without_suffix() -> None:
    """{catdir} 贪婪吃到底之后必须能回溯，不能把 slug 吞掉。"""
    rules = [P.Rule("category", "{catdir}/")]
    m = P.parse_path("/hangye/xinwen/", rules)
    assert m is not None
    assert m.get("catdir") == "hangye/xinwen"


def test_parse_category_default() -> None:
    rules = [P.Rule("category", "category/{slug}/")]
    m = P.parse_path("/category/mes/", rules)
    assert m is not None and m.get("slug") == "mes"


def test_parse_miss_returns_none() -> None:
    rules = [P.Rule("article", "p/{slug}.html")]
    assert P.parse_path("/article/abc.html", rules) is None


def test_parse_respects_specificity() -> None:
    """具体规则先匹配，不靠列表顺序碰运气。"""
    rules = [
        P.Rule("article", "{slug}.html"),
        P.Rule("article", "{catdir}/{slug}.html"),
    ]
    m = P.parse_path("/mes/abc.html", rules)
    assert m is not None
    assert m.get("catdir") == "mes"
    assert m.get("slug") == "abc"


def test_parse_skips_broken_rule() -> None:
    """库里存着脏规则不能让整个站点 500。"""
    bad = P.Rule.__new__(P.Rule)
    object.__setattr__(bad, "kind", "article")
    object.__setattr__(bad, "pattern", "{nope}/{slug}.html")
    object.__setattr__(bad, "source", "site")
    object.__setattr__(bad, "priority", 0)
    good = P.Rule("article", "{type}/{slug}.html")
    m = P.parse_path("/article/abc.html", [bad, good])
    assert m is not None and m.get("slug") == "abc"


# ---------------------------------------------------------------- 分页


@pytest.mark.parametrize(
    "path,base,page",
    [
        ("/article/", "/article/", 1),
        ("/article/page/2/", "/article/", 2),
        ("/category/mes/page/3/", "/category/mes/", 3),
        ("/tag/lean/page/2", "/tag/lean/", 2),
        ("/hangye/xinwen/abc.html", "/hangye/xinwen/abc.html", 1),
    ],
)
def test_split_page(path: str, base: str, page: int) -> None:
    assert P.split_page(path) == (base, page)


# ---------------------------------------------------------------- 冲突


def test_conflict_type_vs_cat() -> None:
    """{type} 与 {cat} 都能吃 /article/x.html，必须拦下。"""
    a = P.Rule("article", "{type}/{slug}.html", source="site")
    b = P.Rule("article", "{cat}/{slug}.html", source="category:5")
    conflicts = P.find_conflicts([a, b])
    assert conflicts
    assert conflicts[0][2] == "/article/demo.html"


def test_no_conflict_when_paths_disjoint() -> None:
    """带栏目目录的规则和裸 slug 规则路径不相交，共存是合理的。"""
    a = P.Rule("article", "{catdir}/{slug}.html")
    b = P.Rule("article", "{slug}.html")
    assert P.find_conflicts([a, b]) == []


def test_no_conflict_between_category_and_tag() -> None:
    a = P.Rule("category", "category/{slug}/")
    b = P.Rule("tag", "tag/{slug}/")
    assert P.find_conflicts([a, b]) == []


# ---------------------------------------------------------------- 排序


def test_sort_rules_more_specific_first() -> None:
    loose = P.Rule("article", "{slug}.html")
    tight = P.Rule("article", "{type}/{catdir}/{slug}.html")
    ordered = P.sort_rules([loose, tight])
    assert ordered[0] is tight


def test_source_label_preserved() -> None:
    r = P.Rule("article", "{catdir}/{slug}.html", source="category:12", priority=5)
    assert r.source == "category:12"
    assert r.priority == 5


# ---------------------------------------------------------------- {type} 绑定


def test_type_var_bound_to_kind_prefix() -> None:
    """{type} 是本类型的前缀，不是通配。

    编译成通配的话，news 的 `{type}/{slug}.html` 会把 /product/x.html
    认领成 news —— 各类型规则互相抢路径。
    """
    rx_news = P.compile_pattern("{type}/{slug}.html", "news")
    assert rx_news.match("/news/hello.html")
    assert not rx_news.match("/product/hello.html")

    rx_product = P.compile_pattern("{type}/{slug}.html", "product")
    assert rx_product.match("/product/hello.html")
    assert not rx_product.match("/news/hello.html")


def test_type_var_bound_for_page_kind() -> None:
    """单页类型 key 是 page，但地址前缀是 p。"""
    rx = P.compile_pattern("{type}/{slug}.html", "page")
    assert rx.match("/p/about.html")
    assert not rx.match("/page/about.html")


def test_type_var_stays_wildcard_for_list_rule() -> None:
    """列表页规则不属于具体类型，{type} 必须保持通配。

    绑死的话 `/{type}/` 只认得下 article 一个前缀，
    product / news / case 的列表页全部匹配不上。
    """
    rx = P.compile_pattern("{type}/", "_list")
    assert rx.match("/article/")
    assert rx.match("/product/")
    assert rx.match("/news/")


def test_different_kinds_do_not_steal_each_other() -> None:
    """news 与 product 都用 {type}/{slug}.html 时，路径不能串。"""
    rules = [P.Rule("news", "{type}/{slug}.html"), P.Rule("product", "{type}/{slug}.html")]
    m = P.parse_path("/product/x.html", rules)
    assert m is not None
    assert m.rule.kind == "product"
    assert m.get("type") == "product"

    m2 = P.parse_path("/news/x.html", rules)
    assert m2 is not None
    assert m2.rule.kind == "news"


def test_type_prefix_table_covers_all_detail_kinds() -> None:
    """每个能配 {type} 的类型都得有前缀，否则会退化成 kind 本身。"""
    for kind in ("article", "product", "news", "case", "page"):
        assert kind in P.TYPE_PREFIX
