"""URL 规则引擎（伪静态 URL pattern）

市面 CMS 的「伪静态」重点不在 URL 长什么样，而在**规则可配**：
站点给一套默认模板，栏目可以覆盖，单条内容还能手填。

这个模块只做纯计算，不碰 DB / ORM：

    正向（生成）  build_url("{catdir}/{slug}.html", {...}) -> "/hangye/xinwen/abc.html"
    反向（解析）  parse_path("/hangye/xinwen/abc.html", rules) -> Match(kind="article", ...)

路由层、模板层、sitemap、llms.txt 必须共用同一份规则。历史上 ``TemplateContext.url()``
和 ``public_router._page_path()`` 各写一套硬编码，结果是页面点着都对、爬虫看到的
canonical 全错 —— 这类错只能靠对比页面源码发现，排查成本极高。

变量说明（同一变量在不同场景语义一致）
--------------------------------------
``{type}``    内容类型前缀                       article / product / news / case
``{catdir}``  栏目从根到自身的完整目录链         hangye/xinwen
``{cat}``     栏目自身目录名（不含父级）         xinwen
``{parent}``  父级目录链（不含自身）             hangye
``{slug}``    内容 / 栏目 / 标签的 slug          mes-paichan-wuqu
``{id}``      主键                                1024
``{year}`` ``{month}`` ``{day}``  发布日            2026 / 10 / 31

``{catdir}`` 至少要有一段。没栏目的内容套不上带 catdir 的规则，
生成时抛 :class:`RuleNotApplicable` 让调用方回落到站点默认规则 —— 不硬拼出
``//abc.html`` 这种脏地址。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

__all__ = [
    "ALLOWED_VARS",
    "DEFAULT_PATTERNS",
    "TYPE_PREFIX",
    "Conflict",
    "Match",
    "Rule",
    "RuleError",
    "RuleNotApplicable",
    "build_url",
    "classify_conflicts",
    "compile_pattern",
    "find_conflicts",
    "iter_matches",
    "normalize_pattern",
    "parse_path",
    "sample_paths",
    "sort_rules",
    "specificity",
    "split_page",
    "validate_pattern",
    "variables_of",
]


class RuleError(ValueError):
    """规则本身不合法（未知变量、重复变量、缺唯一标识等）。"""


class RuleNotApplicable(Exception):  # noqa: N818 - 是控制流信号，不是错误
    """规则合法，但这组数据套不上（比如带 {catdir} 但内容没有栏目）。"""


# ---------------------------------------------------------------- 变量定义

# 每个变量能匹配的字符形态。{catdir} 限制最多 4 段，既够表达三级栏目，
# 又避免 `[^/]+(?:/[^/]+)*` 在长路径上回溯失控。
VAR_PATTERN: dict[str, str] = {
    "type": r"[A-Za-z0-9_-]+",
    "catdir": r"[^/]+(?:/[^/]+){0,3}",
    "cat": r"[^/]+",
    "parent": r"[^/]+(?:/[^/]+){0,3}",
    "slug": r"[^/]+",
    "id": r"\d+",
    "year": r"\d{4}",
    "month": r"\d{2}",
    "day": r"\d{2}",
}

_DETAIL_VARS = frozenset({"type", "catdir", "cat", "slug", "id", "year", "month", "day"})
_CATEGORY_VARS = frozenset({"type", "catdir", "cat", "parent", "slug", "id"})
_TAG_VARS = frozenset({"type", "slug", "id"})

ALLOWED_VARS: dict[str, frozenset[str]] = {
    "article": _DETAIL_VARS,
    "product": _DETAIL_VARS,
    "news": _DETAIL_VARS,
    "case": _DETAIL_VARS,
    "page": _DETAIL_VARS,
    "category": _CATEGORY_VARS,
    "tag": _TAG_VARS,
    # 列表页规则只描述入口，形如 `{type}/`
    "_list": frozenset({"type"}),
}

# 一条规则至少要含其中一个变量，才能唯一确定「说的是哪条内容/哪个栏目」。
# 栏目页用 `{catdir}/` 这种写法是合法的（目录链本身就能定位栏目），
# 所以详情页和栏目页的标识集不同。
_DETAIL_IDENTITY = frozenset({"slug", "id"})
_IDENTITY_VARS: dict[str, frozenset[str]] = {
    "category": frozenset({"slug", "id", "catdir", "cat"}),
    "tag": _DETAIL_IDENTITY,
}

# 内容类型 -> URL 前缀。{type} 变量在反向解析时**必须**按这个表绑定成字面量，
# 不能编译成通配正则 —— 否则不同类型的规则会互相抢路径：
# `news: {type}/{slug}.html` 会把 `/product/xxx.html` 认领成 news，
# 因为 `{type}` 能匹配任意字符串，且 type 的特异性权重高于 catdir。
TYPE_PREFIX: dict[str, str] = {
    "article": "article",
    "product": "product",
    "news": "news",
    "case": "case",
    "page": "p",
}

# 默认规则 = 改造前的线上形态，保证切换后所有地址一字不变。
DEFAULT_PATTERNS: dict[str, str] = {
    "article": "{type}/{slug}.html",
    "product": "{type}/{slug}.html",
    "news": "{type}/{slug}.html",
    "case": "{type}/{slug}.html",
    "page": "p/{slug}.html",
    "category": "category/{slug}/",
    "tag": "tag/{slug}/",
    "_list": "{type}/",
}

# 排序权重：字面量最值钱，其次是取值空间小的变量（{type} 只有 4 个值，
# {id} 是纯数字），{catdir} 最泛化所以最不值钱。
_VAR_WEIGHT: dict[str, int] = {
    "type": 6,
    "id": 3,
    "year": 4,
    "month": 4,
    "day": 4,
    "slug": 2,
    "cat": 2,
    "parent": 1,
    "catdir": 1,
}

_TOKEN_RE = re.compile(r"\{([a-z]+)\}")
_MAX_DEPTH = 6


# ---------------------------------------------------------------- 规则对象


@dataclass(frozen=True)
class Rule:
    """一条 URL 规则。

    ``source`` 标出规则来源，用来在冲突报告里指清楚是哪一层配错了：
    ``site`` / ``category:12`` / ``tag:7`` / ``entry:99``。
    ``priority`` 是人工优先级，同特异性时大的先匹配。
    """

    kind: str
    pattern: str
    source: str = "site"
    priority: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "pattern", normalize_pattern(self.pattern))


@dataclass(frozen=True)
class Match:
    """一条路径被某条规则认领的结果。"""

    kind: str
    params: dict[str, str]
    rule: Rule

    def get(self, name: str, default: str | None = None) -> str | None:
        return self.params.get(name, default)


# ---------------------------------------------------------------- 规范化


def normalize_pattern(pattern: str) -> str:
    """去掉首部斜杠、压掉重复斜杠。尾部斜杠有语义，保留。"""
    raw = (pattern or "").strip()
    if not raw:
        raise RuleError("URL 规则不能为空")
    body = raw.lstrip("/")
    body = re.sub(r"/{2,}", "/", body)
    if not body:
        raise RuleError("URL 规则不能只有斜杠")
    return body


def variables_of(pattern: str) -> list[str]:
    """按出现顺序返回规则里用到的变量名。"""
    return [m.group(1) for m in _TOKEN_RE.finditer(pattern or "")]


def _allowed_for(kind: str) -> frozenset[str]:
    return ALLOWED_VARS.get(kind, _DETAIL_VARS)


def validate_pattern(pattern: str, kind: str) -> str:
    """校验规则合法性，返回规范化后的写法；不合法抛 :class:`RuleError`。

    FastAPI / nginx 都不会替我们挡错配置，脏规则一旦存库就是全站 404，
    所以能静态检查的都在这里检查掉。
    """
    body = normalize_pattern(pattern)
    allowed = _allowed_for(kind)

    names = variables_of(body)
    if not names:
        raise RuleError("规则至少要有一个变量，否则所有内容会指向同一个地址")

    unknown = sorted({n for n in names if n not in allowed})
    if unknown:
        raise RuleError(
            f"{kind} 不支持变量 {', '.join('{' + n + '}' for n in unknown)}；"
            f"可用：{', '.join('{' + n + '}' for n in sorted(allowed))}"
        )

    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise RuleError(f"变量重复出现：{', '.join('{' + n + '}' for n in dup)}")

    # 必须有一个能唯一定位内容的变量，否则多条内容抢同一个地址。
    #
    # 列表页规则（_list）是例外：它描述的是「某一类内容的列表入口」，
    # `/{type}/` 里的 {type} 就是定位变量，不需要 slug/id。
    if kind == "_list":
        identity_ok = "type" in names
        opts = "{type}"
    else:
        identity = _IDENTITY_VARS.get(kind, _DETAIL_IDENTITY)
        identity_ok = bool(identity & set(names))
        opts = " 或 ".join("{" + n + "}" for n in sorted(identity))
    if not identity_ok:
        raise RuleError(f"规则里必须有 {opts}，否则多条内容会指向同一个地址")

    if ".." in body or "\\" in body:
        raise RuleError("规则里不允许出现 `..` 或反斜杠")

    if body.count("/") + 1 > _MAX_DEPTH:
        raise RuleError(f"路径层级过深（最多 {_MAX_DEPTH} 段）")

    if "{" in _TOKEN_RE.sub("", body) or "}" in _TOKEN_RE.sub("", body):
        raise RuleError("存在未闭合或非法的花括号")

    return body


def compile_pattern(pattern: str, kind: str = "article") -> re.Pattern[str]:
    """规则 -> 正则。用于反向解析。

    ``{type}`` **按 kind 绑定成字面量前缀**，不编译成通配。

    这是个必须钉死的语义：``{type}`` 表示「本条内容类型的 URL 前缀」，
    不是「任意一串字符」。当成通配的话，``news: {type}/{slug}.html``
    会把 ``/product/xxx.html`` 认领成 news —— 因为 ``[A-Za-z0-9_-]+``
    能匹配 "product"。各类型的规则会互相抢路径，表现为
    「有的文章 404、有的文章打开是别的类型」。

    绑定成字面量后，``news`` 规则只匹配 ``/news/...``，``product``
    规则只匹配 ``/product/...``，互不干扰。
    """
    body = validate_pattern(pattern, kind)
    # 规则里不含前导斜杠（normalize 去掉了），但请求路径一定带，
    # 这里补上，否则每条规则都会漏匹配。
    out: list[str] = ["^/"]
    pos = 0
    for m in _TOKEN_RE.finditer(body):
        out.append(re.escape(body[pos : m.start()]))
        name = m.group(1)
        if name == "type":
            prefix = TYPE_PREFIX.get(kind)
            if prefix is None:
                # 列表页规则（_list）这类不属于具体类型的，{type} 保持通配，
                # 否则 ``/{type}/`` 只认得下 article 一个前缀。
                out.append(f"(?P<type>{VAR_PATTERN['type']})")
            else:
                out.append(f"(?P<type>{re.escape(prefix)})")
        else:
            out.append(f"(?P<{name}>{VAR_PATTERN[name]})")
        pos = m.end()
    out.append(re.escape(body[pos:]))
    out.append("$")
    return re.compile("".join(out))


def specificity(pattern: str) -> int:
    """规则特异性评分，越大越该优先匹配。

    字面量按字符数计重权，路径层级次之，变量按取值空间大小给分。
    靠这个排序，而不是靠数据库返回顺序碰运气 —— 顺序一变，路由就是另一种结果。
    """
    body = normalize_pattern(pattern)
    literal = _TOKEN_RE.sub("", body)
    score = len(literal.replace("/", "")) * 10 + body.count("/") * 5
    score += sum(_VAR_WEIGHT.get(n, 1) for n in variables_of(body))
    return score


def sort_rules(rules: Iterable[Rule]) -> list[Rule]:
    """按「人工优先级 > 特异性 > 路径段数」降序排。"""
    return sorted(
        rules,
        key=lambda r: (r.priority, specificity(r.pattern), r.pattern.count("/")),
        reverse=True,
    )


# ---------------------------------------------------------------- 正向生成


def _quote_segment(value: str) -> str:
    # catdir / parent 自带斜杠，必须保留；其余字符一律转义
    return quote(value, safe="/-_.~")


def build_url(pattern: str, values: Mapping[str, Any]) -> str:
    """按规则拼出绝对路径。缺值抛 :class:`RuleNotApplicable`，由调用方回落。"""
    body = normalize_pattern(pattern)
    missing: list[str] = []

    def _sub(m: re.Match[str]) -> str:
        name = m.group(1)
        raw = values.get(name)
        if raw is None or str(raw).strip() == "":
            missing.append(name)
            return ""
        return _quote_segment(str(raw).strip())

    filled = _TOKEN_RE.sub(_sub, body)
    if missing:
        raise RuleNotApplicable(f"缺少变量 {', '.join('{' + n + '}' for n in missing)}")

    path = "/" + filled.lstrip("/")
    path = re.sub(r"/{2,}", "/", path)
    # 只有根路径保留单斜杠，其余保持规则里的尾部语义
    return path


# ---------------------------------------------------------------- 反向解析


def split_page(path: str) -> tuple[str, int]:
    """把 ``/article/page/2/`` 拆成 ``('/article/', 2)``。

    分页段固定为 ``page/{n}/``，不参与规则配置：页码是可枚举的低价值路径，
    开放配置只会让「第 2 页」和某篇文章的 slug 撞车。
    """
    p = path if path.startswith("/") else "/" + path
    m = re.match(r"^(?P<base>.*/)page/(?P<n>\d+)/?$", p)
    if not m:
        return p, 1
    return m.group("base") or "/", int(m.group("n"))


def parse_path(path: str, rules: Sequence[Rule]) -> Match | None:
    """在给定规则集里找一条能认领该路径的，没有返回 None。

    调用方负责规则集的构成（比如先试栏目级再试站点级），这里只按
    传入顺序逐个匹配 —— 顺序由 :func:`sort_rules` 保证。
    """
    for m in iter_matches(path, rules):
        return m
    return None


def iter_matches(path: str, rules: Sequence[Rule]) -> Iterator[Match]:
    """按顺序产出**所有**能认领该路径的匹配。

    为什么不能只取第一条：栏目级规则是用「栏目页地址」模板写的，
    但编译出来的正则并不知道自己只对某个栏目有效 —— 栏目 7 的规则
    ``{catdir}/{slug}.html`` 同样能匹配栏目 9 的路径。

    只认第一条的话，栏目 9 的页面会被栏目 7 的规则抢走，
    然后拿内容 slug 去查栏目表 → 查不到 → 404。
    调用方拿到匹配后要**回库核对**归属，对不上就继续试下一条。
    """
    target = path if path.startswith("/") else "/" + path
    for rule in sort_rules(rules):
        try:
            rx = compile_pattern(rule.pattern, rule.kind)
        except RuleError:
            # 库里存着的历史脏规则不应该让整个站点 500
            continue
        m = rx.match(target)
        if m:
            yield Match(kind=rule.kind, params=dict(m.groupdict()), rule=rule)


# ---------------------------------------------------------------- 冲突检测


_SAMPLE_VALUES: dict[str, tuple[str, ...]] = {
    "type": ("article", "product"),
    "catdir": ("mes", "mes/flow"),
    "cat": ("mes",),
    "parent": ("mes",),
    "slug": ("demo", "demo-two"),
    "id": ("42",),
    "year": ("2026",),
    "month": ("10",),
    "day": ("31",),
}


def sample_paths(pattern: str, limit: int = 24, kind: str = "") -> list[str]:
    """为一个规则生成若干条代表性路径，用于和其他规则对撞。

    完整判定两个正则的交集不可行（需要正则求交），工程上够用的替代是
    「拿 A 的样本去撞 B 的正则」。样本覆盖了每个变量的首值和次值，
    现实里的冲突几乎都落在这些形态上。

    ``kind`` 传了的话，``{type}`` 的样本会取该类型**真实的 URL 前缀**
    （article 类型取 ``article``，单页取 ``p``）。不传就会取通用值
    ``article``/``product`` 各一份 —— 于是「单页规则」也会生成
    ``/article/xxx.html`` 这种样本，白白撞上文章规则。
    """
    body = normalize_pattern(pattern)
    names = variables_of(body)

    type_values = _SAMPLE_VALUES["type"]
    if kind:
        prefix = TYPE_PREFIX.get(kind)
        if prefix:
            type_values = (prefix,)

    def _values_for(name: str) -> tuple[str, ...]:
        if name == "type":
            return type_values
        return _SAMPLE_VALUES.get(name, ("x",))

    base: dict[str, str] = {}
    for n in names:
        base[n] = _values_for(n)[0]

    paths: list[str] = []
    try:
        paths.append(build_url(body, base))
    except RuleNotApplicable:
        return paths

    for n in names:
        for v in _values_for(n)[1:]:
            try:
                paths.append(build_url(body, {**base, n: v}))
            except RuleNotApplicable:
                continue
    seen: set[str] = set()
    uniq = [p for p in paths if not (p in seen or seen.add(p))]
    return uniq[:limit]


def _overlap(a: Rule, b: Rule) -> str | None:
    """两条规则有没有交集，有就返回一条能同时被两者认领的示例路径。

    双向对撞：拿 A 的样本撞 B 的正则，再拿 B 的样本撞 A。
    只靠单向会漏掉「B 更宽、A 的样本恰好都不在 B 范围内」这类情形。

    注意这里**不看特异性**。特异性只决定谁先匹配，不消除歧义：
    站点默认 ``{type}/{slug}.html`` 和某栏目 ``{cat}/{slug}.html`` 在栏目
    目录名恰好叫 ``article`` 时都能吃 ``/article/x.html``，用户根本猜不到
    哪条生效 —— 这是必须拦下的配置，不是「更具体的赢」就完事。
    """
    for sample in sample_paths(a.pattern, kind=a.kind):
        try:
            rx_b = compile_pattern(b.pattern, b.kind)
        except RuleError:
            continue
        if rx_b.match(sample):
            return sample
    for sample in sample_paths(b.pattern, kind=b.kind):
        try:
            rx_a = compile_pattern(a.pattern, a.kind)
        except RuleError:
            continue
        if rx_a.match(sample):
            return sample
    return None


def find_conflicts(rules: Sequence[Rule]) -> list[tuple[Rule, Rule, str]]:
    """找出会互相遮蔽的规则对，返回 ``(规则A, 规则B, 撞车示例路径)``。"""
    out: list[tuple[Rule, Rule, str]] = []
    for i, a in enumerate(rules):
        for b in rules[i + 1 :]:
            sample = _overlap(a, b)
            if sample:
                out.append((a, b, sample))
    return out


# ---------------------------------------------------------------- 冲突分级


@dataclass(frozen=True)
class Conflict:
    """一条冲突及其严重级别。

    分级的原因：把「同一层级的两条规则真的分不清谁生效」和「层级之间的正常覆盖」
    混为一谈，会让「栏目带目录名」这种最常见的配置直接被拦死。

    - ``block``：两条规则在**同一层级**都可能认领同一条内容，
      用户无法判断点开会看到什么 —— 必须拦下。
    - ``warn``：跨层级的交集。栏目规则本来就该盖过站点默认，
      这是设计好的覆盖关系，只提醒不拦。
    """

    a: Rule
    b: Rule
    sample: str
    severity: str
    reason: str


def _is_type_bound(rule: Rule) -> bool:
    """这条规则的 ``{type}`` 是否被绑成字面量前缀。

    只有详情类规则（article/product/news/case/page）会绑。
    ``{type}`` 绑成字面量后，不同类型的规则天然互不重叠。
    """
    if "type" not in variables_of(rule.pattern):
        return False
    return TYPE_PREFIX.get(rule.kind) is not None


def _tier_of(rule: Rule) -> str:
    """规则所属层级。

    ``site`` = 站点默认，``override`` = 栏目/标签覆盖，``other`` = 历史存档等。
    同一层级内的冲突才是「真的分不清」，跨层级是设计好的覆盖。
    """
    src = rule.source or ""
    if src == "site" or src == "pending":
        return "site"
    if src.startswith("category:") or src.startswith("tag:"):
        return "override"
    return "other"


def _leading_literal(pattern: str) -> str:
    """取规则的第一段字面量（非变量部分）。

    用来判断「这条规则写死了一个前缀，恰好等于另一个类型的前缀」——
    比如 article 规则写成 ``product/{slug}.html``，那它跟 product 的
    默认规则必然抢同一条地址，属于配错了，必须拦下。
    """
    body = normalize_pattern(pattern)
    first = body.split("/", 1)[0]
    if "{" in first:
        return ""
    return first


def classify_conflicts(rules: Sequence[Rule]) -> list[Conflict]:
    """把冲突分成「必须拦下」和「只提醒」两级。

    跟 :func:`find_conflicts` 的区别：那个函数只回答「有没有交集」，
    这个函数回答「这个交集要不要拦」。

    判定原则：
    - 同一层级 + 同一内容类型 → 两条规则都能认领同一条内容，
      用户没法判断点开会看到什么，**必须拦下**。
    - 写死的前缀撞上另一个类型的前缀 → 必然抢地址，**必须拦下**。
    - 其余（跨层级覆盖、跨类型的理论交集）→ 只提醒。
      栏目规则盖过站点默认是设计好的覆盖关系，拦下来功能就没法用了。
    """
    out: list[Conflict] = []
    for i, a in enumerate(rules):
        for b in rules[i + 1 :]:
            sample = _overlap(a, b)
            if not sample:
                continue
            tier_a = _tier_of(a)
            tier_b = _tier_of(b)

            # 前缀撞前缀：必然抢地址，不管是不是同层级
            lit_a = _leading_literal(a.pattern)
            lit_b = _leading_literal(b.pattern)
            bound_a = TYPE_PREFIX.get(a.kind)
            bound_b = TYPE_PREFIX.get(b.kind)
            if (lit_a and bound_b and lit_a == bound_b and a.kind != b.kind) or (
                lit_b and bound_a and lit_b == bound_a and a.kind != b.kind
            ):
                out.append(
                    Conflict(
                        a,
                        b,
                        sample,
                        "block",
                        f"`{a.pattern}` 写死的前缀与 `{b.pattern}` 的类型前缀重复，"
                        f"两者会认领同一批地址",
                    )
                )
                continue

            if tier_a == tier_b and a.kind == b.kind:
                # 待保存的规则是在**替换**同类型的站点默认，两者本就是二选一，
                # 不算冲突 —— 否则「改规则」这个动作永远无法保存。
                replacing = (a.source == "pending" and b.source == "site") or (
                    b.source == "pending" and a.source == "site"
                )
                if replacing:
                    continue
                out.append(
                    Conflict(
                        a,
                        b,
                        sample,
                        "block",
                        "同层级、同类型的两条规则都会认领同一条内容",
                    )
                )
                continue

            out.append(
                Conflict(
                    a,
                    b,
                    sample,
                    "warn",
                    f"`{a.pattern}` 与 `{b.pattern}` 理论上都能认领 `{sample}`，"
                    f"实际以匹配顺序为准（覆盖关系）",
                )
            )
    return out
