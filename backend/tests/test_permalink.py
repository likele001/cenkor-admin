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


# ---------------------------------------------------------------- 冲突分级


def _site_defaults() -> list[P.Rule]:
    """站点默认规则全集（与 DEFAULT_PATTERNS 一致）。"""
    return [
        P.Rule("article", "{type}/{slug}.html", source="site"),
        P.Rule("product", "{type}/{slug}.html", source="site"),
        P.Rule("news", "{type}/{slug}.html", source="site"),
        P.Rule("case", "{type}/{slug}.html", source="site"),
        P.Rule("page", "p/{slug}.html", source="site"),
        P.Rule("category", "category/{slug}/", source="site"),
        P.Rule("tag", "tag/{slug}/", source="site"),
    ]


def test_same_kind_different_types_do_not_conflict() -> None:
    """article 与 product 都用 {type}/{slug}.html，绑成字面量后不该相交。

    之前这里会误报：样本值对所有类型都取 ``article``，
    于是 product 规则的样本也长成 ``/article/xxx.html``，
    硬生生撞上 article 规则。
    """
    cs = P.classify_conflicts(_site_defaults())
    assert cs == [], [f"{c.a.pattern} VS {c.b.pattern}" for c in cs]


def test_pending_replaces_same_kind_site_rule() -> None:
    """待保存规则是「替换」同类型的站点默认，不算冲突。

    否则「改规则」这个动作永远保存不下去。
    """
    rules = [*_site_defaults(), P.Rule("article", "{catdir}/{slug}.html", source="pending")]
    cs = P.classify_conflicts(rules)
    assert not [c for c in cs if c.severity == "block"]


def test_literal_prefix_clash_is_blocked() -> None:
    """article 规则写死 product 前缀 = 必然抢地址，必须拦下。"""
    rules = [*_site_defaults(), P.Rule("article", "product/{slug}.html", source="pending")]
    cs = P.classify_conflicts(rules)
    blocking = [c for c in cs if c.severity == "block"]
    assert blocking, "写死别人前缀的规则必须被拦下"


def test_category_override_is_only_warning() -> None:
    """栏目规则盖过站点默认是设计好的覆盖关系，不该拦。"""
    rules = [*_site_defaults(), P.Rule("article", "{catdir}/{slug}.html", source="category:5")]
    cs = P.classify_conflicts(rules)
    assert not [c for c in cs if c.severity == "block"]


def test_two_category_overrides_same_kind_conflict() -> None:
    """两个栏目各配一条同类规则且会撞车 —— 这才是真歧义，必须拦。"""
    rules = [
        *_site_defaults(),
        P.Rule("article", "{cat}/{slug}.html", source="category:5"),
        P.Rule("article", "{catdir}/{slug}.html", source="category:6"),
    ]
    cs = P.classify_conflicts(rules)
    assert [c for c in cs if c.severity == "block"]


def test_sample_paths_respect_kind_type_prefix() -> None:
    """样本路径的 {type} 必须取该类型的真实前缀。"""
    assert P.sample_paths("{type}/{slug}.html", kind="product")[0] == "/product/demo.html"
    assert P.sample_paths("{type}/{slug}.html", kind="page")[0] == "/p/demo.html"
    # 不传 kind 时保留通用样本，供老调用方使用
    assert P.sample_paths("{type}/{slug}.html")[0].startswith("/")


# ---------------------------------------------------------------- 栏目级规则的语义分层


def test_category_rule_only_governs_category_page() -> None:
    """栏目级规则只管**栏目页**，不管该栏目下内容的详情页。

    这是本轮修掉的核心缺陷：``cms_categories.url_pattern`` 曾经被
    ``detail_url()`` 当成「该栏目下内容的详情页模板」，
    又被 ``_expand_rules()`` 当成「栏目页规则」，同一份模板两种含义。

    后果：给任意栏目配一条规则 → 该栏目下所有条目反解时拿**内容 slug**
    去查**栏目表** → 查不到 → 整批 404。
    """
    from cenkor_admin.apps.cms import url_resolver as R

    rules = R.RuleSet(
        defaults={
            "article": "{type}/{slug}.html",
            "category": "category/{slug}/",
            "tag": "tag/{slug}/",
        },
        category_patterns={7: "{catdir}/{slug}.html"},
    )

    # 栏目页走栏目级规则
    assert R.category_base(
        rules, slug="mes", catdir="mes", category_id=7
    ) == "/mes/mes.html"

    # 该栏目下的**内容详情页**仍走站点默认详情规则，跟栏目级规则无关
    assert R.detail_url(rules, "article", slug="abc", catdir="mes", category_id=7) == (
        "/article/abc.html"
    )

    # 不带栏目目录时也一样 —— 栏目级规则不插手
    assert R.detail_url(rules, "article", slug="abc") == "/article/abc.html"


def test_tag_rule_only_governs_tag_page() -> None:
    """标签级规则只管标签页，跟栏目级对称。"""
    from cenkor_admin.apps.cms import url_resolver as R

    rules = R.RuleSet(
        defaults={
            "article": "{type}/{slug}.html",
            "category": "category/{slug}/",
            "tag": "tag/{slug}/",
        },
        tag_patterns={3: "t/{slug}/"},
    )
    assert R.tag_base(rules, slug="ai", tag_id=3) == "/t/ai/"
    assert R.detail_url(rules, "article", slug="abc") == "/article/abc.html"


def test_category_override_does_not_affect_detail_url() -> None:
    """栏目覆盖不该顺手改掉该栏目下内容的详情地址。"""
    from cenkor_admin.apps.cms import url_resolver as R

    rules = R.RuleSet(
        defaults={"article": "{type}/{slug}.html"},
        category_patterns={7: "{catdir}/{slug}.html"},
    )
    # category_id 传了也不该影响详情页
    assert R.detail_url(rules, "article", slug="abc", category_id=7) == "/article/abc.html"


def test_manual_url_path_wins_over_every_rule() -> None:
    """手填路径钉死不动，规则改多少都不影响。"""
    from cenkor_admin.apps.cms import url_resolver as R

    rules = R.RuleSet(defaults={"article": "{type}/{slug}.html"})
    assert (
        R.detail_url(rules, "article", slug="abc", url_path="/custom/pinned.html")
        == "/custom/pinned.html"
    )


def test_list_base_uses_list_rule() -> None:
    """列表页地址由列表页规则（``url.list``）决定。"""
    from cenkor_admin.apps.cms import url_resolver as R

    rules = R.RuleSet(defaults={"_list": "{type}/"})
    assert R.list_base(rules, "article") == "/article/"
    assert R.list_base(rules, "product") == "/product/"

    custom = R.RuleSet(defaults={"_list": "list/{type}/"})
    assert R.list_base(custom, "article") == "/list/article/"


def test_list_url_appends_page_segment() -> None:
    """第 1 页是基路径本身，第 N 页接 ``page/N/``。"""
    from cenkor_admin.apps.cms import url_resolver as R

    rules = R.RuleSet(defaults={"_list": "{type}/"})
    assert R.list_url(rules, "article", 1) == "/article/"
    assert R.list_url(rules, "article", 3) == "/article/page/3/"


def test_parent_var_only_for_nested_category() -> None:
    """``{parent}`` 是父栏目链；顶层栏目没有父级 → 规则套不上就回落默认。"""
    from cenkor_admin.apps.cms import url_resolver as R

    rules = R.RuleSet(defaults={"category": "{parent}/{slug}/"})
    # 顶层栏目：parent 缺失 → 回落默认
    assert R.category_base(rules, slug="mes", catdir="mes", category_id=1) == "/category/mes/"
    # 二级栏目：parent = 父链
    assert R.category_base(rules, slug="xinwen", catdir="mes/xinwen", category_id=2) == (
        "/mes/xinwen/"
    )


# ---------------------------------------------------------------- iter_matches：归属核对


def test_iter_matches_yields_all_candidates() -> None:
    """一条路径可能被多条规则认领 —— 必须全部产出，不能只取第一条。"""
    # 两条规则都能认领 /mes/abc.html：
    # 站点默认按 {catdir}/{slug}.html 走，栏目 7 的覆盖规则形状相同。
    rules = [
        P.Rule("article", "{catdir}/{slug}.html", source="site"),
        P.Rule("category", "{catdir}/{slug}.html", source="category:7", priority=1),
    ]
    matches = list(P.iter_matches("/mes/abc.html", rules))
    assert len(matches) == 2
    assert {m.rule.source for m in matches} == {"site", "category:7"}


def test_parse_path_still_returns_first_match() -> None:
    """``parse_path`` 保持旧语义（第一条），调用方按需改用 iter_matches。"""
    rules = [
        P.Rule("article", "{catdir}/{slug}.html", source="site"),
        P.Rule("category", "{catdir}/{slug}.html", source="category:7", priority=1),
    ]
    m = P.parse_path("/mes/abc.html", rules)
    assert m is not None
    assert m.rule.source == "category:7"


def test_iter_matches_skips_invalid_rule() -> None:
    """脏规则（编译不过）不能把整条链路带崩。"""
    rules = [
        P.Rule("article", "{nope}/{slug}.html", source="site"),
        P.Rule("article", "{type}/{slug}.html", source="site"),
    ]
    matches = list(P.iter_matches("/article/abc.html", rules))
    assert [m.rule.source for m in matches] == ["site"]
