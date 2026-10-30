"""AI 落地页 / 官网子站生成。

三个关键取舍：

1. **只生成白名单区块**。模型很爱自创 type（`pricing`、`team`、`contact_map`），
   渲染器不认识就直接消失，用户看到的是「生成了但页面缺一半」。所以生成后
   逐块校验，不认识的直接丢，并在返回体里告诉用户丢了什么。

2. **表单一并生成，且默认挂 CRM**。落地页不带表单等于宣传册。生成的表单
   落库时带 `create_lead=True` 与默认字段映射，提交即进线索池，转化率才算得出来。

3. **链接由服务端重写，不信模型给的 href**。模型会写 `/contact`、`#contact`、
   `https://example.com` 这类东西，发布后全是死链。页面之间的跳转一律按
   真实 key 重建。

数字与客户名是幻觉重灾区，提示词里明令只允许使用素材里出现的数字。
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.ai import prompt_registry as prompts
from cenkor_admin.apps.cms.ai.copilot import _as_object, _record
from cenkor_admin.apps.cms.ai.landing_blocks import AI_BLOCK_TYPES, clean_blocks
from cenkor_admin.core.llm import LLMError, LLMNotConfiguredError, get_llm

# 单次生成的规模上限：超了就是模型没节制的信号，截断比报错友好
MAX_BLOCKS_PER_PAGE = 12
MAX_PAGES = 5

# 默认线索字段映射：表单字段 key -> CRM 线索字段
# {线索字段: 表单字段}。方向别写反 —— 写成 "phone": "mobile" 的意思是
# 「读表单的 mobile 字段，写进线索的 phone」，表单字段多半叫 phone，于是永远取空。
DEFAULT_LEAD_MAPPING = {
    "name": "name",
    "company": "company",
    "mobile": "phone",
    "phone": "phone",
    "email": "email",
    "notes": "message",
}

_SPEC = """可用区块（type + data 字段，未列出的 type 一律不要用）：
- navbar  {brand, links:[{label,href}], cta:{label,href}}
- hero    {eyebrow, title, subtitle, bullets:[最多4条], primary:{label,href}, secondary:{label,href}}
- features{title, desc, items:[{icon:一个符号, title, desc}] 3~6 个}
- steps   {title, items:[{title, desc}] 3~5 个}
- stats   {title, items:[{value, label}] 3~4 个}
- testimonial {title, items:[{quote, name, company}] 2~3 个}
- faq     {title, items:[{q, a}] 4~6 个}
- cta     {title, desc, primary:{label, href}}
- form    {title, desc, submit_label，form_key 留空由系统填}
- footer  {brand, links:[{label,href}], note}
"""

_SYSTEM = """你是一位做过大量 B2B 官网与投放落地页的文案与信息架构师。

## 硬规则
1. 只输出 JSON，不要任何解释文字、不要 markdown 代码块。
2. 只用下面列出的区块类型，不要自创 type。
3. **不许编造具体数字、客户名、资质、奖项、认证**。素材里没有的数字不要写；
   `stats` 区块如果素材里没有真实数据，改用 3 条定性描述（如「上线周期：2 周」这类可从素材推出的）。
4. 文案要具体：写清楚「谁、什么问题、怎么解决、得到什么」，不要用「赋能」「一站式」
   「数字化转型」这类空话。一句话不超过 30 字。
5. 每页 5~8 个区块，首块必须是 hero，必须包含一个 form 区块（除「关于」页外）。
6. 中文输出。

## 区块规格
""" + _SPEC


_SITE_SYSTEM = _SYSTEM + """
## 本次任务：生成一个官网子站（不是单页）
输出四页：首页 home / 产品 product / 关于 about / 联系 contact。
首页讲价值与转化，产品页讲能力与场景，关于页讲团队与做法，联系页只放 form。
各页导航一致，links 里的 href 先随便写（系统会按 key 重写）。
"""


def _user_prompt(brief: str, *, goal: str, tone: str, brand: str, modes: str) -> str:
    return f"""## 素材
一句话需求：{brief}
品牌名：{brand or "（未提供，用行业通称，如「本方案」）"}
页面目标：{goal}
语气：{tone}
形态：{modes}

## 输出 JSON 结构
{{
  "site": {{"brand": "品牌名", "accent": "#2563eb"}},
  "form": {{"key": "lead", "title": "...", "success_message": "...",
           "fields": [{{"key":"name","label":"称呼","type":"text","required":true}},
                      {{"key":"company","label":"公司","type":"text","required":false}},
                      {{"key":"phone","label":"手机","type":"tel","required":true}},
                      {{"key":"message","label":"想解决的问题","type":"textarea","required":false}}]}},
  "pages": [
    {{"key": "home", "name": "首页", "title": "...",
      "seo": {{"title": "不超过 30 字", "description": "不超过 80 字", "keywords": "3~5 个词逗号分隔"}},
      "blocks": [ ... ]}}
  ]
}}
form 只需给一份，所有页面的 form 区块共用它。"""


def _slug(s: str, fallback: str = "page") -> str:
    t = re.sub(r"[^a-z0-9\-]+", "-", str(s or "").lower()).strip("-")
    t = re.sub(r"-{2,}", "-", t)
    return (t or fallback)[:50]


def _clip(v: Any, n: int) -> str:
    return str(v if v is not None else "").strip()[:n]


def _norm_payload(raw: dict[str, Any], *, mode: str) -> dict[str, Any]:
    """把模型输出收敛成可落库的形状。丢掉的区块会记在 dropped 里。"""
    site = raw.get("site") if isinstance(raw.get("site"), dict) else {}
    brand = _clip(site.get("brand"), 40)
    accent = _clip(site.get("accent"), 9)
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", accent or ""):
        accent = ""

    form_raw = raw.get("form") if isinstance(raw.get("form"), dict) else {}
    fields: list[dict[str, Any]] = []
    for f in (form_raw.get("fields") or [])[:8]:
        if not isinstance(f, dict):
            continue
        k = _slug(f.get("key") or f.get("label"), "")
        if not k or not k.replace("-", "").isalnum():
            continue
        ftype = str(f.get("type") or "text")
        if ftype not in ("text", "email", "tel", "textarea", "number", "select"):
            ftype = "text"
        fields.append({
            "key": k.replace("-", "_"),
            "label": _clip(f.get("label") or k, 30),
            "type": ftype,
            "required": bool(f.get("required")),
        })
    if not any(f["key"] in ("name", "phone", "mobile") for f in fields):
        fields.insert(0, {"key": "name", "label": "称呼", "type": "text", "required": True})
    if not any(f["key"] == "phone" or f["key"] == "mobile" for f in fields):
        fields.append({"key": "phone", "label": "手机", "type": "tel", "required": True})
    form = {
        "key": _slug(form_raw.get("key") or "lead", "lead"),
        "title": _clip(form_raw.get("title") or "留下联系方式", 40),
        "success_message": _clip(form_raw.get("success_message") or "提交成功，我们会尽快联系你", 120),
        "fields": fields,
    }

    pages: list[dict[str, Any]] = []
    dropped: list[str] = []
    for i, p in enumerate((raw.get("pages") or [])[:MAX_PAGES]):
        if not isinstance(p, dict):
            continue
        blocks, drop = clean_blocks(p.get("blocks") or [], limit=MAX_BLOCKS_PER_PAGE)
        dropped.extend(drop)
        if not blocks:
            continue
        seo = p.get("seo") if isinstance(p.get("seo"), dict) else {}
        pages.append({
            "key": _slug(p.get("key") or f"page-{i + 1}", f"page-{i + 1}"),
            "name": _clip(p.get("name") or p.get("title") or f"第 {i + 1} 页", 30),
            "title": _clip(p.get("title") or seo.get("title") or "未命名页面", 80),
            "seo": {
                "title": _clip(seo.get("title") or p.get("title"), 70),
                "description": _clip(seo.get("description"), 200),
                "keywords": _clip(seo.get("keywords"), 120),
                "accent": accent,
            },
            "blocks": blocks,
        })

    if mode == "site" and len(pages) > 1:
        # key 去重，否则同 key 的页会互相覆盖
        seen: set[str] = set()
        for p in pages:
            k, n = p["key"], 2
            while k in seen:
                k = f"{p['key']}-{n}"
                n += 1
            p["key"] = k
            seen.add(k)

    return {"brand": brand, "accent": accent, "form": form, "pages": pages, "dropped": sorted(set(dropped))}


def _rewrite_links(pages: list[dict[str, Any]], *, site_key: str | None, mode: str) -> None:
    """把页内 href 统一改写成真实地址。

    模型写的 href 一律不信：`/contact`、`#form`、`https://example.com` 发布后
    都是死链或跑到别人家。这里按 key 重建，找不到目标就指向第一个 form 所在页。
    """
    urls: dict[str, str] = {}
    for p in pages:
        urls[p["key"]] = (
            f"/lp/{site_key}/{p['key']}" if mode == "site" and site_key else f"/lp/{p['key']}"
        )
    form_target = next(
        (urls[p["key"]] for p in pages if any(b.get("type") == "form" for b in p["blocks"])),
        urls[pages[0]["key"]],
    )

    def fix(href: Any) -> str:
        h = str(href or "").strip()
        if h.startswith(("http://", "https://", "mailto:", "tel:")):
            return h
        # 锚点到表单：落地页的主 CTA 几乎都是「留个联系方式」
        if h in ("", "#", "#form", "#lead-form", "#contact"):
            return form_target + "#lead-form"
        tail = h.strip("/").split("/")[-1]
        if tail in urls:
            return urls[tail]
        return form_target

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for k in ("href",):
                if k in node:
                    node[k] = fix(node[k])
            if "cta" in node and isinstance(node["cta"], dict):
                node["cta"]["href"] = fix(node["cta"].get("href"))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for p in pages:
        walk(p["blocks"])


async def _call_model(session: AsyncSession, system: str, user: str, *, max_tokens: int = 7000) -> tuple[dict, Any]:
    llm = get_llm()
    raw, result = await llm.chat_json(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.5,
        max_tokens=max_tokens,
    )
    return _as_object(raw, "落地页"), result


async def draft(
    session: AsyncSession,
    brief: str,
    *,
    mode: str = "page",
    goal: str = "获取线索",
    tone: str = "专业、克制",
    brand: str = "",
    use_kb: bool = True,
    created_by: int | None = None,
) -> dict[str, Any]:
    """生成落地页草稿（不落库）。返回 {brand, form, pages, dropped, kb_used}。"""
    text = (brief or "").strip()
    if not text:
        raise ValueError("brief 不能为空")
    mode = "site" if mode == "site" else "page"

    kb_block = ""
    kb_used = 0
    if use_kb:
        # 有企业资料就带上：落地页最怕写空话，真实参数与流程是最好的素材
        try:
            from cenkor_admin.apps.cms import knowledge
            from cenkor_admin.core.site_scope import current_site_id

            kb_text, kb_sources = await knowledge.context_for_prompt(
                session, text[:500], site_id=current_site_id() or 1, limit=3, max_chars=2200
            )
            kb_used = len(kb_sources)
            if kb_text:
                kb_block = (
                    "## 企业资料摘录（事实以此为准，没有的不要编）\n"
                    f"{kb_text}\n\n"
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("cms.landing.kb_failed", error=str(exc))

    system = await prompts.get(
        session, "landing_page", _SITE_SYSTEM if mode == "site" else _SYSTEM
    )

    # 子站拆成两路并发：单路 2 页，避开模型 60s 读超时
    groups: list[list[tuple[str, str]]]
    if mode == "site":
        groups = [
            [("home", "首页：讲价值与转化，必须含 form")],
            [("product", "产品页：讲能力与适用场景，可含 form")],
            [("about", "关于页：讲团队与做事方式，不要 form")],
            [("contact", "联系页：只放 form")],
        ]
    else:
        groups = [[("home", "单页落地页：讲价值、讲证据、最后留资，必须含 form")]]

    async def _gen(group: list[tuple[str, str]], idx: int) -> dict:
        spec = "\n".join(f"- key={k}：{desc}" for k, desc in group)
        user = (
            kb_block
            + _user_prompt(
                text, goal=goal, tone=tone, brand=brand,
                modes=(
                    "多页官网子站的其中一部分（系统分两批生成，你只负责下面这几页）"
                    if mode == "site" else "单页落地页"
                ),
            )
            + f"\n\n## 本次只生成这 {len(group)} 页（不要写别的页）\n{spec}"
            + ("\n\nform 字段定义必须给出（其它批次不再重复）。" if idx == 0 else "\n\nform 可以给 null，系统会沿用。")
        )
        obj, result = await _call_model(session, system, user, max_tokens=7000)
        payload = _norm_payload(obj, mode=mode)
        payload["_result"] = result
        payload["_prompt"] = user
        return payload

    results = await asyncio.gather(
        *[_gen(g, i) for i, g in enumerate(groups)], return_exceptions=True
    )
    good = [r for r in results if isinstance(r, dict)]
    errs = [r for r in results if isinstance(r, Exception)]
    if not good:
        first = errs[0] if errs else RuntimeError("模型没有返回内容")
        await _record(
            session, kind="landing", target=f"mode:{mode}", result=None,
            status="failed", error=str(first), created_by=created_by, prompt=text,
        )
        if isinstance(first, LLMNotConfiguredError):
            raise first
        raise RuntimeError(f"生成失败：{str(first)[:160]}")

    pages: list[dict[str, Any]] = []
    dropped: list[str] = []
    for r in good:
        pages.extend(r["pages"])
        dropped.extend(r.get("dropped") or [])

    merged_brand = next((r["brand"] for r in good if r.get("brand")), "")
    accent = next((r["accent"] for r in good if r.get("accent")), "")
    form = next((r["form"] for r in good if (r.get("form") or {}).get("fields")), good[0]["form"])

    # 子站按固定顺序排，别让并发返回顺序影响首页判定
    if mode == "site":
        order = {"home": 0, "product": 1, "about": 2, "contact": 3}
        pages.sort(key=lambda p: order.get(p["key"], 9))

    payload: dict[str, Any] = {
        "brand": merged_brand,
        "accent": accent,
        "form": form,
        "pages": pages[:MAX_PAGES],
        "dropped": sorted(set(dropped)),
        "kb_used": kb_used,
        "mode": mode,
        "_partial": bool(errs),
    }
    payload["generation_id"] = await _record(
        session, kind="landing", target=f"mode:{mode}", result=good[0].get("_result"),
        params={"brief": text[:120], "pages": len(pages), "mode": mode, "partial": bool(errs)},
        created_by=created_by, prompt=good[0].get("_prompt") or text,
    )
    if errs:
        logger.warning("cms.landing.partial", errors=len(errs), got=len(pages))
    payload.pop("_partial", None)
    for p in pages:
        p.pop("_result", None)
    if not payload["pages"]:
        raise ValueError("模型没有产出可用区块，请换个说法再试")
    return payload


def _s_brand(payload: dict[str, Any]) -> str:
    return str(payload.get("brand") or "").strip()


async def save(
    session: AsyncSession,
    payload: dict[str, Any],
    *,
    site_id: int = 1,
    site_key: str | None = None,
    page_key: str | None = None,
    created_by: int | None = None,
) -> dict[str, Any]:
    """把草稿落库：建表单 + 建页面（均为 draft）。返回 {pages:[...], form_key, urls}。"""
    from cenkor_admin.apps.builder.models import Page
    from cenkor_admin.apps.forms.models import Form

    pages_in = payload.get("pages") or []
    if not pages_in:
        raise ValueError("没有可保存的页面")
    mode = "site" if payload.get("mode") == "site" else "page"

    # ---- 表单：带留资映射，提交即进 CRM 线索池 ----
    form_in = payload.get("form") or {}
    base = _slug(form_in.get("key") or "lead", "lead")
    form_key = base
    n = 2
    while (await session.execute(select(Form.id).where(Form.key == form_key))).scalar():
        form_key = f"{base}-{n}"
        n += 1
    form = Form(
        site_id=site_id,
        key=form_key,
        title=_clip(form_in.get("title") or "留下联系方式", 40),
        description=None,
        fields=form_in.get("fields") or [],
        success_message=_clip(form_in.get("success_message") or "提交成功，我们会尽快联系你", 120),
        enabled=True,
        create_lead=True,
        lead_mapping=DEFAULT_LEAD_MAPPING,
    )
    session.add(form)
    await session.flush()

    # ---- 站点 key ----
    if mode == "site":
        site_key = _slug(site_key or payload.get("brand") or pages_in[0]["key"], "site")
        exists = (
            await session.execute(
                select(Page.id).where(Page.site_id == site_id, Page.site_key == site_key)
            )
        ).scalar()
        if exists:
            raise ValueError(f"子站标识已被占用：{site_key}")

    # ---- 链接重写 + form_key 注入 ----
    for p in pages_in:
        for b in p["blocks"]:
            if b.get("type") == "form":
                b.setdefault("data", {})["form_key"] = form_key
    _rewrite_links(pages_in, site_key=site_key, mode=mode)

    nav = [
        {
            "label": p.get("name") or p.get("title"),
            "href": f"/lp/{site_key}/{p['key']}" if mode == "site" else f"/lp/{p['key']}",
        }
        for p in pages_in
    ]

    if mode == "site":
        brand_name = (_s_brand(payload) or (payload.get("brand") or "")).strip() or "首页"
        nav_links = [{"label": x["label"], "href": x["href"]} for x in nav]
        for p in pages_in:
            types = [b.get("type") for b in p["blocks"]]
            # 已有 navbar/footer 也要把 links 换成真实导航：
            # 模型写的 href 经过 _rewrite_links 会全部塌成一个锚点
            for b in p["blocks"]:
                if b.get("type") in ("navbar", "footer"):
                    b.setdefault("data", {})["links"] = [dict(x) for x in nav_links]
                    if b["type"] == "navbar" and not (b["data"].get("cta") or {}).get("href"):
                        b["data"]["cta"] = {"label": "预约演示", "href": nav[0]["href"] + "#lead-form"}
                    if b["type"] == "navbar" and not b["data"].get("brand"):
                        b["data"]["brand"] = brand_name
            if "navbar" not in types:
                p["blocks"].insert(0, {
                    "type": "navbar",
                    "data": {
                        "brand": brand_name,
                        "links": [{"label": x["label"], "href": x["href"]} for x in nav],
                        "cta": {"label": "预约演示", "href": nav[0]["href"] + "#lead-form"},
                    },
                })
            if "footer" not in types:
                p["blocks"].append({
                    "type": "footer",
                    "data": {
                        "brand": brand_name,
                        "links": [{"label": x["label"], "href": x["href"]} for x in nav],
                        "note": "本站内容由 AI 辅助生成，事实与参数以实际交付说明为准。",
                    },
                })

    # 顺序规范化：navbar 提到最前、footer 压到最后（与模型怎么写无关）
    for p in pages_in:
        blocks = p.get("blocks") or []
        navs = [b for b in blocks if b.get("type") == "navbar"]
        foots = [b for b in blocks if b.get("type") == "footer"]
        mids = [b for b in blocks if b.get("type") not in ("navbar", "footer")]
        p["blocks"] = navs[:1] + mids + foots[-1:]

    created: list[dict[str, Any]] = []
    for i, p in enumerate(pages_in):
        key = p["key"]
        if mode == "page" and i == 0 and page_key:
            # 运营想自己定 URL 就听他的，只做安全字符过滤
            key = _slug(page_key, key)
        full = f"{site_key}/{key}" if mode == "site" else key
        # 单页：撞了就加后缀，别为了一个 slug 让用户重生成 50 秒的内容。
        # 子站：site_key 已经检查过唯一，这里再撞说明数据脏了，直接报错更安全。
        n2 = 2
        while (
            await session.execute(
                select(Page.id).where(Page.site_id == site_id, Page.key == full)
            )
        ).scalar():
            if mode == "site":
                raise ValueError(f"页面标识已被占用：{full}")
            full = f"{key}-{n2}"
            n2 += 1
        page_key = full
        kind = "site_home" if (mode == "site" and i == 0) else ("site_child" if mode == "site" else "page")
        page = Page(
            site_id=site_id,
            key=full,
            title=p["title"],
            schema=p["blocks"],
            status="draft",
            seo=p.get("seo") or {},
            kind=kind,
            site_key=site_key if mode == "site" else None,
            nav=nav if mode == "site" else [],
            ai_generation_id=payload.get("generation_id"),
        )
        session.add(page)
        await session.flush()
        created.append({
            "id": page.id,
            "key": full,
            "title": page.title,
            "kind": kind,
            "url": f"/lp/{full}",
        })

    return {"pages": created, "form_key": form_key, "site_key": site_key, "mode": mode}


def load_forms_for(blocks: list[dict[str, Any]], form_defs: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """挑出页面用到的表单定义（预览/渲染时注入）。"""
    keys = {
        str((b.get("data") or {}).get("form_key") or "")
        for b in blocks or []
        if b.get("type") == "form"
    }
    return {k: form_defs[k] for k in keys if k in form_defs}


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def ai_block_types() -> tuple[str, ...]:
    return tuple(AI_BLOCK_TYPES)
