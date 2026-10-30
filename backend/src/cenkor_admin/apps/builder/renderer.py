"""Builder · 区块渲染（把 blocks schema 渲染成可直接投放的落地页 HTML）

设计取舍：
1. **不引模板引擎**。整页 HTML 由 f-string 拼，少一个运行时依赖，且渲染
   路径足够短 —— 落地页是给人看的门面，它不能因为某个模板变量拼错就 500。
2. **CSS 内联进页面**。落地页要能独立发出去、单独部署、被别人用 iframe
   嵌，外链 CSS 会带来一串路径问题。代价是每页多 ~6KB，可接受。
3. **所有文本一律转义**，链接只放行 http(s)/mailto/tel/相对路径。
   `html` 区块保留原样是为了兼容已有的自定义页，但 AI 永远不会生成它。
4. **表单真的能提交**。落地页的核心动作是留资，不是把联系方式写成一段字。
"""

from __future__ import annotations

import html as _html
import json
from typing import Any

BLOCK_TYPES = (
    "navbar",
    "hero",
    "features",
    "steps",
    "stats",
    "testimonial",
    "faq",
    "cta",
    "form",
    "footer",
    # 基础块（早期页面在用，保持兼容）
    "heading",
    "text",
    "image",
    "list",
    "html",
)

# 落地页能用的区块（AI 只允许生成这些，`html` 不在其中）
AI_BLOCK_TYPES = (
    "navbar",
    "hero",
    "features",
    "steps",
    "stats",
    "testimonial",
    "faq",
    "cta",
    "form",
    "footer",
)

_SAFE_SCHEMES = ("http://", "https://", "mailto:", "tel:", "/", "#")


def _esc(v: Any) -> str:
    return _html.escape(str(v if v is not None else ""), quote=True)


def _href(v: Any) -> str:
    """只放行安全的链接协议。`javascript:` 这类一律降级成 #。"""
    s = str(v or "").strip()
    if not s:
        return "#"
    low = s.lower()
    if low.startswith(_SAFE_SCHEMES):
        return _esc(s)
    return "#"


def _txt(v: Any, limit: int = 4000) -> str:
    s = str(v if v is not None else "").strip()
    return _esc(s[:limit])


def _items(d: dict, key: str = "items", limit: int = 12) -> list[dict]:
    raw = d.get(key) or []
    if not isinstance(raw, list):
        return []
    out = [x for x in raw[:limit] if isinstance(x, dict)]
    return out


# ---------------------------------------------------------------------------
# 各区块
# ---------------------------------------------------------------------------
def _blk_navbar(d: dict, ctx: dict) -> str:
    brand = _txt(d.get("brand") or ctx.get("site_name") or "首页", 40)
    links = "".join(
        f'<a href="{_href(x.get("href"))}">{_txt(x.get("label"), 20)}</a>'
        for x in _items(d, "links", 6)
    )
    cta = d.get("cta") if isinstance(d.get("cta"), dict) else {}
    cta_html = (
        f'<a class="lp-nav-cta" href="{_href(cta.get("href"))}">{_txt(cta.get("label"), 20)}</a>'
        if cta.get("label")
        else ""
    )
    return (
        '<header class="lp-nav"><div class="lp-wrap lp-nav-inner">'
        f'<a class="lp-brand" href="{_href(d.get("brand_href") or "/")}">{brand}</a>'
        f'<nav class="lp-nav-links">{links}</nav>{cta_html}'
        "</div></header>"
    )


def _blk_hero(d: dict, ctx: dict) -> str:
    eyebrow = _txt(d.get("eyebrow"), 40)
    bullets = "".join(f"<li>{_txt(b, 60)}</li>" for b in (d.get("bullets") or [])[:4])
    primary = d.get("primary") if isinstance(d.get("primary"), dict) else {}
    secondary = d.get("secondary") if isinstance(d.get("secondary"), dict) else {}
    btns = []
    if primary.get("label"):
        btns.append(f'<a class="lp-btn lp-btn-primary" href="{_href(primary.get("href"))}">{_txt(primary.get("label"), 24)}</a>')
    if secondary.get("label"):
        btns.append(f'<a class="lp-btn lp-btn-ghost" href="{_href(secondary.get("href"))}">{_txt(secondary.get("label"), 24)}</a>')
    img = _href(d.get("image")) if d.get("image") else ""
    media = f'<div class="lp-hero-media"><img src="{img}" alt="{_txt(d.get("image_alt") or "", 80)}" loading="lazy" /></div>' if img else ""
    return (
        '<section class="lp-hero"><div class="lp-wrap lp-hero-inner">'
        '<div class="lp-hero-copy">'
        + (f'<p class="lp-eyebrow">{eyebrow}</p>' if eyebrow else "")
        + f'<h1>{_txt(d.get("title"), 80)}</h1>'
        + (f'<p class="lp-lead">{_txt(d.get("subtitle"), 300)}</p>' if d.get("subtitle") else "")
        + (f'<ul class="lp-hero-bullets">{bullets}</ul>' if bullets else "")
        + (f'<div class="lp-hero-actions">{"".join(btns)}</div>' if btns else "")
        + "</div>" + media + "</div></section>"
    )


def _blk_features(d: dict, ctx: dict) -> str:
    cards = "".join(
        '<article class="lp-card">'
        f'<div class="lp-card-icon">{_txt(x.get("icon") or "◆", 4)}</div>'
        f'<h3>{_txt(x.get("title"), 40)}</h3>'
        f'<p>{_txt(x.get("desc"), 300)}</p>'
        "</article>"
        for x in _items(d, "items", 9)
    )
    head = _section_head(d)
    return f'<section class="lp-section"><div class="lp-wrap">{head}<div class="lp-grid">{cards}</div></div></section>'


def _blk_steps(d: dict, ctx: dict) -> str:
    rows = "".join(
        f'<li><span class="lp-step-no">{i}</span><div><h3>{_txt(x.get("title"), 40)}</h3>'
        f'<p>{_txt(x.get("desc"), 300)}</p></div></li>'
        for i, x in enumerate(_items(d, "items", 6), start=1)
    )
    head = _section_head(d)
    return f'<section class="lp-section lp-section-alt"><div class="lp-wrap">{head}<ol class="lp-steps">{rows}</ol></div></section>'


def _blk_stats(d: dict, ctx: dict) -> str:
    cells = "".join(
        f'<div class="lp-stat"><strong>{_txt(x.get("value"), 16)}</strong>'
        f'<span>{_txt(x.get("label"), 30)}</span></div>'
        for x in _items(d, "items", 4)
    )
    head = _section_head(d)
    body = f'<div class="lp-stats">{cells}</div>'
    if head:
        return f'<section class="lp-section"><div class="lp-wrap">{head}{body}</div></section>'
    return f'<section class="lp-stats-band"><div class="lp-wrap">{body}</div></section>'


def _blk_testimonial(d: dict, ctx: dict) -> str:
    cards = "".join(
        '<figure class="lp-quote">'
        f'<blockquote>{_txt(x.get("quote"), 300)}</blockquote>'
        f'<figcaption>{_txt(x.get("name"), 30)}'
        + (f' · {_txt(x.get("company"), 40)}' if x.get("company") else "")
        + "</figcaption></figure>"
        for x in _items(d, "items", 4)
    )
    head = _section_head(d)
    return f'<section class="lp-section"><div class="lp-wrap">{head}<div class="lp-grid lp-grid-2">{cards}</div></div></section>'


def _blk_faq(d: dict, ctx: dict) -> str:
    rows = "".join(
        "<details>"
        f"<summary>{_txt(x.get('q'), 120)}</summary>"
        f"<p>{_txt(x.get('a') or x.get('desc'), 600)}</p>"
        "</details>"
        for x in _items(d, "items", 10)
    )
    head = _section_head(d)
    ctx.setdefault("faqs", []).extend(
        {"q": str(x.get("q") or ""), "a": str(x.get("a") or x.get("desc") or "")}
        for x in _items(d, "items", 10)
    )
    return f'<section class="lp-section lp-section-alt"><div class="lp-wrap lp-narrow">{head}<div class="lp-faq">{rows}</div></div></section>'


def _blk_cta(d: dict, ctx: dict) -> str:
    primary = d.get("primary") if isinstance(d.get("primary"), dict) else {}
    btn = (
        f'<a class="lp-btn lp-btn-light" href="{_href(primary.get("href"))}">{_txt(primary.get("label"), 24)}</a>'
        if primary.get("label")
        else ""
    )
    return (
        '<section class="lp-cta"><div class="lp-wrap lp-cta-inner">'
        f'<h2>{_txt(d.get("title"), 80)}</h2>'
        + (f'<p>{_txt(d.get("desc"), 200)}</p>' if d.get("desc") else "")
        + btn
        + "</div></section>"
    )


_FORM_FIELD_TYPES = ("text", "email", "tel", "textarea", "select", "number")


def _blk_form(d: dict, ctx: dict) -> str:
    """留资表单。字段优先取库里的表单定义，取不到就用区块自带的（预览态）。"""
    form_key = str(d.get("form_key") or "").strip()
    fdef = (ctx.get("forms") or {}).get(form_key) or {}
    fields = fdef.get("fields") or d.get("fields") or []
    fields = [f for f in fields if isinstance(f, dict)][:10]

    rows: list[str] = []
    for f in fields:
        key = str(f.get("key") or "").strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        label = _txt(f.get("label") or key, 40)
        ftype = f.get("type") if f.get("type") in _FORM_FIELD_TYPES else "text"
        req = " required" if f.get("required") else ""
        req_mark = ' <em>*</em>' if f.get("required") else ""
        if ftype == "textarea":
            ctrl = f'<textarea name="{_esc(key)}" rows="3"{req} placeholder="{_txt(f.get("placeholder"), 60)}"></textarea>'
        elif ftype == "select":
            opts = "".join(
                f'<option value="{_txt(o, 40)}">{_txt(o, 40)}</option>'
                for o in (f.get("options") or [])[:20]
            )
            ctrl = f'<select name="{_esc(key)}"{req}>{opts}</select>'
        else:
            itype = {"tel": "tel", "email": "email", "number": "number"}.get(ftype, "text")
            ctrl = (
                f'<input type="{itype}" name="{_esc(key)}"{req} '
                f'placeholder="{_txt(f.get("placeholder"), 60)}" />'
            )
        rows.append(f'<label class="lp-field"><span>{label}{req_mark}</span>{ctrl}</label>')

    success = _txt(fdef.get("success_message") or d.get("success_text") or "提交成功，我们会尽快联系你", 120)
    note = _txt(d.get("note") or "我们只用这些信息联系你，不会用于其他用途。", 160)
    head = _section_head(d)
    submit = _txt(d.get("submit_label") or "提交", 20)
    return (
        '<section class="lp-section lp-form-section" id="lead-form"><div class="lp-wrap lp-narrow">'
        f"{head}"
        f'<form class="lp-form" data-key="{_esc(form_key)}" data-success="{success}" novalidate>'
        f'{"".join(rows)}'
        # 蜜罐：真人看不见也不会填，填了就是机器人
        '<div class="lp-hp" aria-hidden="true"><label>网址<input type="text" name="_hp" tabindex="-1" autocomplete="off" /></label></div>'
        f'<button type="submit" class="lp-btn lp-btn-primary lp-btn-block">{submit}</button>'
        f'<p class="lp-form-note">{note}</p>'
        '<p class="lp-form-msg" role="status"></p>'
        "</form></div></section>"
    )


def _blk_footer(d: dict, ctx: dict) -> str:
    links = "".join(
        f'<a href="{_href(x.get("href"))}">{_txt(x.get("label"), 20)}</a>'
        for x in _items(d, "links", 8)
    )
    return (
        '<footer class="lp-footer"><div class="lp-wrap">'
        f'<div class="lp-footer-brand">{_txt(d.get("brand") or ctx.get("site_name") or "", 40)}</div>'
        f'<div class="lp-footer-links">{links}</div>'
        f'<p class="lp-footer-note">{_txt(d.get("note"), 200)}</p>'
        "</div></footer>"
    )


def _section_head(d: dict) -> str:
    title = _txt(d.get("title"), 80)
    desc = _txt(d.get("desc"), 300)
    if not title and not desc:
        return ""
    return (
        '<div class="lp-head">'
        + (f"<h2>{title}</h2>" if title else "")
        + (f"<p>{desc}</p>" if desc else "")
        + "</div>"
    )


# ---- 基础块（兼容旧页面） ----
def _blk_heading(d: dict, ctx: dict) -> str:
    lvl = d.get("level", 2)
    lvl = lvl if lvl in (1, 2, 3, 4, 5, 6) else 2
    return f'<section class="lp-section lp-section-plain"><div class="lp-wrap"><h{lvl}>{_txt(d.get("text"))}</h{lvl}></div></section>'


def _blk_text(d: dict, ctx: dict) -> str:
    return f'<section class="lp-section lp-section-plain"><div class="lp-wrap"><p class="lp-text">{_txt(d.get("text"), 4000)}</p></div></section>'


def _blk_image(d: dict, ctx: dict) -> str:
    src = _href(d.get("src"))
    if src == "#":
        return ""
    return (
        '<section class="lp-section lp-section-plain"><div class="lp-wrap">'
        f'<img class="lp-img" src="{src}" alt="{_txt(d.get("alt"), 80)}" loading="lazy" />'
        "</div></section>"
    )


def _blk_list(d: dict, ctx: dict) -> str:
    items = "".join(f"<li>{_txt(i, 200)}</li>" for i in (d.get("items") or [])[:20])
    return f'<section class="lp-section lp-section-plain"><div class="lp-wrap"><ul class="lp-list">{items}</ul></div></section>'


def _blk_html(d: dict, ctx: dict) -> str:
    return f'<div class="lp-html">{d.get("html", "")}</div>'


_RENDER = {
    "navbar": _blk_navbar,
    "hero": _blk_hero,
    "features": _blk_features,
    "steps": _blk_steps,
    "stats": _blk_stats,
    "testimonial": _blk_testimonial,
    "faq": _blk_faq,
    "cta": _blk_cta,
    "form": _blk_form,
    "footer": _blk_footer,
    "heading": _blk_heading,
    "text": _blk_text,
    "image": _blk_image,
    "list": _blk_list,
    "html": _blk_html,
}


def render_blocks(blocks: list[dict], ctx: dict | None = None) -> str:
    """渲染区块列表。ctx 透传表单定义、站点名等上下文。"""
    ctx = ctx if ctx is not None else {}
    parts: list[str] = []
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        fn = _RENDER.get(str(b.get("type") or ""))
        if not fn:
            continue
        d = b.get("data") if isinstance(b.get("data"), dict) else {}
        try:
            parts.append(fn(d, ctx))
        except Exception:
            # 单个区块渲染失败不该让整页白屏：落地页是要投广告的
            continue
    return "\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# 整页
# ---------------------------------------------------------------------------
_CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{--lp-accent:#2563eb;--lp-accent-2:#1d4ed8;--lp-ink:#111827;--lp-muted:#4b5563;
--lp-line:#e5e7eb;--lp-bg:#ffffff;--lp-soft:#f8fafc;--lp-radius:14px}
html{scroll-behavior:smooth}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;
color:var(--lp-ink);background:var(--lp-bg);line-height:1.7;-webkit-font-smoothing:antialiased}
img{max-width:100%;display:block}
a{color:inherit;text-decoration:none}
h1,h2,h3{line-height:1.25;margin:0 0 .5em;letter-spacing:-.01em}
h1{font-size:clamp(30px,4.2vw,50px);font-weight:800}
h2{font-size:clamp(24px,2.8vw,34px);font-weight:700}
h3{font-size:17px;font-weight:650}
p{margin:0 0 1em}
.lp-wrap{max-width:1080px;margin:0 auto;padding:0 24px}
.lp-narrow{max-width:760px}
.lp-nav{position:sticky;top:0;z-index:20;background:rgba(255,255,255,.92);
backdrop-filter:saturate(180%) blur(8px);border-bottom:1px solid var(--lp-line)}
.lp-nav-inner{display:flex;align-items:center;gap:24px;height:64px}
.lp-brand{font-weight:700;font-size:17px}
.lp-nav-links{display:flex;gap:20px;margin-left:auto;font-size:14px;color:var(--lp-muted)}
.lp-nav-links a:hover{color:var(--lp-ink)}
.lp-nav-cta{background:var(--lp-accent);color:#fff;padding:9px 16px;border-radius:10px;font-size:14px;font-weight:600}
.lp-hero{padding:64px 0 72px;background:
radial-gradient(900px 380px at 15% -10%,rgba(37,99,235,.10),transparent 60%),
radial-gradient(700px 320px at 100% 0%,rgba(29,78,216,.08),transparent 55%),var(--lp-bg)}
.lp-hero-inner{display:grid;grid-template-columns:1.15fr .85fr;gap:48px;align-items:center}
.lp-eyebrow{font-size:13px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--lp-accent);margin-bottom:14px}
.lp-lead{font-size:clamp(16px,1.6vw,19px);color:var(--lp-muted);max-width:40em}
.lp-hero-bullets{list-style:none;padding:0;margin:18px 0 0;display:grid;gap:8px}
.lp-hero-bullets li{position:relative;padding-left:24px;color:var(--lp-muted);font-size:15px}
.lp-hero-bullets li::before{content:"";position:absolute;left:0;top:.55em;width:12px;height:12px;
border-radius:50%;background:var(--lp-accent);opacity:.18}
.lp-hero-actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:28px}
.lp-hero-media img{border-radius:var(--lp-radius);box-shadow:0 24px 60px -24px rgba(17,24,39,.35)}
.lp-btn{display:inline-block;padding:13px 24px;border-radius:12px;font-weight:650;font-size:15px;
transition:transform .15s ease,box-shadow .15s ease;border:1px solid transparent;cursor:pointer}
.lp-btn:hover{transform:translateY(-1px)}
.lp-btn-primary{background:var(--lp-accent);color:#fff;box-shadow:0 10px 24px -12px rgba(37,99,235,.9)}
.lp-btn-primary:hover{background:var(--lp-accent-2)}
.lp-btn-ghost{border-color:var(--lp-line);color:var(--lp-ink);background:#fff}
.lp-btn-light{background:#fff;color:var(--lp-accent-2)}
.lp-btn-block{width:100%;text-align:center}
.lp-section{padding:72px 0}
.lp-section-alt{background:var(--lp-soft)}
.lp-section-plain{padding:20px 0}
.lp-head{max-width:640px;margin:0 auto 40px;text-align:center}
.lp-head p{color:var(--lp-muted);margin:0}
.lp-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px}
.lp-grid-2{grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}
.lp-card{background:#fff;border:1px solid var(--lp-line);border-radius:var(--lp-radius);padding:24px}
.lp-card h3{margin-bottom:.4em}
.lp-card p{color:var(--lp-muted);font-size:14.5px;margin:0}
.lp-card-icon{width:38px;height:38px;border-radius:10px;display:grid;place-items:center;
background:rgba(37,99,235,.10);color:var(--lp-accent);font-size:18px;margin-bottom:14px}
.lp-steps{list-style:none;padding:0;margin:0;display:grid;gap:18px}
.lp-steps li{display:flex;gap:16px;align-items:flex-start}
.lp-step-no{flex:0 0 30px;height:30px;border-radius:50%;background:var(--lp-accent);color:#fff;
display:grid;place-items:center;font-size:14px;font-weight:700}
.lp-steps h3{margin-bottom:.2em}
.lp-steps p{color:var(--lp-muted);font-size:14.5px;margin:0}
.lp-stats-band{background:var(--lp-ink);color:#fff;padding:44px 0}
.lp-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:24px;text-align:center}
.lp-stat strong{display:block;font-size:34px;font-weight:800;letter-spacing:-.02em}
.lp-stat span{font-size:13.5px;opacity:.75}
.lp-quote{margin:0;background:#fff;border:1px solid var(--lp-line);border-radius:var(--lp-radius);padding:24px}
.lp-quote blockquote{margin:0 0 12px;font-size:15.5px;color:var(--lp-ink)}
.lp-quote figcaption{font-size:13px;color:var(--lp-muted)}
.lp-faq details{border-bottom:1px solid var(--lp-line);padding:16px 0}
.lp-faq summary{cursor:pointer;font-weight:650;font-size:15.5px;list-style:none}
.lp-faq summary::-webkit-details-marker{display:none}
.lp-faq summary::after{content:"+";float:right;color:var(--lp-muted);font-weight:400}
.lp-faq details[open] summary::after{content:"–"}
.lp-faq p{color:var(--lp-muted);margin:10px 0 0;font-size:14.5px}
.lp-cta{background:linear-gradient(135deg,var(--lp-accent),var(--lp-accent-2));color:#fff;padding:64px 0}
.lp-cta-inner{text-align:center}
.lp-cta h2{color:#fff}
.lp-cta p{opacity:.85;max-width:36em;margin:0 auto 24px}
.lp-form{background:#fff;border:1px solid var(--lp-line);border-radius:var(--lp-radius);
padding:26px;display:grid;gap:14px;box-shadow:0 20px 50px -30px rgba(17,24,39,.4)}
.lp-field{display:grid;gap:6px}
.lp-field span{font-size:13px;font-weight:600;color:var(--lp-muted)}
.lp-field em{color:#dc2626;font-style:normal}
.lp-field input,.lp-field textarea,.lp-field select{width:100%;padding:11px 13px;border:1px solid var(--lp-line);
border-radius:10px;font-size:14.5px;font-family:inherit;color:var(--lp-ink);background:#fff}
.lp-field input:focus,.lp-field textarea:focus,.lp-field select:focus{outline:none;border-color:var(--lp-accent);
box-shadow:0 0 0 3px rgba(37,99,235,.14)}
.lp-hp{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}
.lp-form-note{font-size:12px;color:#9ca3af;margin:0;text-align:center}
.lp-form-msg{font-size:14px;margin:0;text-align:center;min-height:1.2em}
.lp-form-msg.ok{color:#059669}
.lp-form-msg.err{color:#dc2626}
.lp-footer{border-top:1px solid var(--lp-line);padding:36px 0;background:var(--lp-soft)}
.lp-footer-brand{font-weight:700;margin-bottom:8px}
.lp-footer-links{display:flex;gap:18px;flex-wrap:wrap;font-size:14px;color:var(--lp-muted);margin-bottom:10px}
.lp-footer-note{font-size:12.5px;color:#9ca3af;margin:0}
.lp-text{font-size:16px;color:var(--lp-muted);white-space:pre-wrap}
.lp-list{color:var(--lp-muted);font-size:15.5px}
.lp-img{border-radius:var(--lp-radius);margin:0 auto}
@media(max-width:820px){
.lp-hero-inner{grid-template-columns:1fr;gap:32px}
.lp-hero{padding:44px 0 48px}
.lp-section{padding:52px 0}
.lp-nav-links{display:none}
.lp-head{text-align:left;margin-bottom:28px}
}
@media print{.lp-nav,.lp-cta,.lp-footer{display:none}body{color:#000}}
"""

_FORM_JS = """
(function(){
  var f=document.querySelector('form.lp-form');if(!f)return;
  var msg=f.querySelector('.lp-form-msg');
  f.addEventListener('submit',function(e){
    e.preventDefault();
    var values={},fd=new FormData(f);
    fd.forEach(function(v,k){if(k!=='_hp')values[k]=v;});
    // 蜜罐命中：假装成功，不打扰真人（机器人填了就写不进库）
    if(fd.get('_hp')){msg.className='lp-form-msg ok';msg.textContent=f.dataset.success;return;}
    var btn=f.querySelector('button[type=submit]');btn.disabled=true;
    fetch('/api/v1/public/forms/'+encodeURIComponent(f.dataset.key)+'/submit',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({values:values,_hp:''})
    }).then(function(r){return r.json().then(function(j){return {ok:r.ok,body:j};});})
    .then(function(res){
      if(res.ok){msg.className='lp-form-msg ok';msg.textContent=res.body.message||f.dataset.success;f.reset();}
      else{msg.className='lp-form-msg err';msg.textContent=(res.body&&res.body.detail)||'提交失败，请稍后重试';}
    }).catch(function(){msg.className='lp-form-msg err';msg.textContent='网络异常，请稍后重试';})
    .finally(function(){btn.disabled=false;});
  });
})();
"""


def _jsonld(page: dict, ctx: dict) -> str:
    graph: list[dict] = []
    seo = page.get("seo") or {}
    if ctx.get("site_name"):
        graph.append({
            "@type": "Organization",
            "name": ctx["site_name"],
            "url": ctx.get("site_url") or "",
        })
    faqs = [f for f in (ctx.get("faqs") or []) if f.get("q") and f.get("a")]
    if faqs:
        graph.append({
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": f["q"],
                    "acceptedAnswer": {"@type": "Answer", "text": f["a"]},
                }
                for f in faqs[:10]
            ],
        })
    if seo.get("title"):
        graph.append({"@type": "WebPage", "name": seo["title"], "description": seo.get("description") or ""})
    if not graph:
        return ""
    # 内联 JSON 必须转义 `</`，否则 FAQ 里出现 </script> 就能提前闭合标签
    payload = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)
    return '<script type="application/ld+json">' + payload.replace("</", "<\\/") + "</script>"


def render_page(
    page: dict,
    *,
    forms: dict[str, dict] | None = None,
    ctx: dict | None = None,
    canonical: str = "",
    track: bool = True,
    noindex: bool = False,
) -> str:
    """整页 HTML。page: {key,title,schema,seo,nav,kind,site_key}"""
    seo = page.get("seo") or {}
    title = str(seo.get("title") or page.get("title") or "")
    desc = str(seo.get("description") or "")
    keywords = str(seo.get("keywords") or "")
    og_image = str(seo.get("og_image") or "")
    accent = str(seo.get("accent") or "")

    ctx = dict(ctx or {})
    ctx["forms"] = forms or {}
    nav = page.get("nav") or []
    if isinstance(nav, list) and nav:
        ctx.setdefault("nav_items", nav)

    body = render_blocks(page.get("schema") or [], ctx)
    ld = _jsonld(page, ctx)

    css = _CSS + (f":root{{--lp-accent:{_esc(accent)};}}" if accent and accent.startswith("#") else "")

    head_extra = "".join([
        f'<meta name="description" content="{_txt(desc, 300)}" />' if desc else "",
        f'<meta name="keywords" content="{_txt(keywords, 200)}" />' if keywords else "",
        '<meta name="robots" content="noindex" />' if noindex else "",
        f'<link rel="canonical" href="{_href(canonical)}" />' if canonical else "",
        '<meta property="og:type" content="website" />',
        f'<meta property="og:title" content="{_txt(title, 80)}" />',
        f'<meta property="og:description" content="{_txt(desc, 300)}" />' if desc else "",
        f'<meta property="og:image" content="{_href(og_image)}" />' if og_image else "",
        f'<meta property="og:url" content="{_href(canonical)}" />' if canonical else "",
        '<meta name="twitter:card" content="summary_large_image" />',
        ld,
    ])

    track_js = '<script src="/api/v1/public/track.js" defer></script>' if track else ""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_txt(title, 120)}</title>
{head_extra}
<style>{css}</style>
</head>
<body>
{body}
{track_js}
<script>{_FORM_JS}</script>
</body>
</html>"""


def page_html(page_key: str, title: str, blocks: list[dict]) -> str:
    """兼容旧调用（builder/public_router 早期版本）。"""
    return render_page({"key": page_key, "title": title, "schema": blocks})
