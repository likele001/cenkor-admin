"""区块校验：把模型输出的 blocks 收敛成渲染器认识的形状。

放在这里而不是塞进 landing.py，是因为两个消费者都要用：
AI 生成时校验一次，保存/编辑时再校验一次（人可以手改，改坏了也别存进去）。
"""

from __future__ import annotations

from typing import Any

from cenkor_admin.apps.builder.renderer import AI_BLOCK_TYPES

# 每种区块的条数上限：都是版式决定的，不是随便拍的
_ITEM_CAPS = {
    "navbar": ("links", 6),
    "hero": ("bullets", 4),
    "features": ("items", 6),
    "steps": ("items", 5),
    "stats": ("items", 4),
    "testimonial": ("items", 3),
    "faq": ("items", 6),
    "footer": ("links", 6),
}


def _s(v: Any, n: int) -> str:
    return str(v if v is not None else "").strip()[:n]


def _rows(v: Any, n: int) -> list[dict]:
    if not isinstance(v, list):
        return []
    return [x for x in v[:n] if isinstance(x, dict)]


def _norm(t: str, d: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(d, dict):
        d = {}
    out: dict[str, Any] = {}
    if t == "navbar":
        out = {"brand": _s(d.get("brand"), 40), "links": [
            {"label": _s(x.get("label"), 20), "href": _s(x.get("href"), 200)}
            for x in _rows(d.get("links"), 6)
        ]}
        if isinstance(d.get("cta"), dict):
            out["cta"] = {"label": _s(d["cta"].get("label"), 20), "href": _s(d["cta"].get("href"), 200)}
    elif t == "hero":
        out = {
            "eyebrow": _s(d.get("eyebrow"), 40),
            "title": _s(d.get("title"), 80),
            "subtitle": _s(d.get("subtitle"), 300),
            "bullets": [_s(x, 60) for x in (d.get("bullets") or [])[:4] if isinstance(x, str)],
        }
        for k in ("primary", "secondary"):
            if isinstance(d.get(k), dict):
                out[k] = {"label": _s(d[k].get("label"), 24), "href": _s(d[k].get("href"), 200)}
        if d.get("image"):
            out["image"] = _s(d.get("image"), 400)
            out["image_alt"] = _s(d.get("image_alt"), 80)
    elif t in ("features", "testimonial"):
        out = {"title": _s(d.get("title"), 80), "desc": _s(d.get("desc"), 300)}
        cap = _ITEM_CAPS[t][1]
        if t == "features":
            out["items"] = [
                {"icon": _s(x.get("icon"), 4) or "◆", "title": _s(x.get("title"), 40), "desc": _s(x.get("desc"), 300)}
                for x in _rows(d.get("items"), cap)
            ]
        else:
            out["items"] = [
                {"quote": _s(x.get("quote"), 300), "name": _s(x.get("name"), 30), "company": _s(x.get("company"), 40)}
                for x in _rows(d.get("items"), cap)
            ]
    elif t == "steps":
        out = {"title": _s(d.get("title"), 80), "items": [
            {"title": _s(x.get("title"), 40), "desc": _s(x.get("desc"), 300)}
            for x in _rows(d.get("items"), 5)
        ]}
    elif t == "stats":
        out = {"title": _s(d.get("title"), 80), "items": [
            {"value": _s(x.get("value"), 16), "label": _s(x.get("label"), 30)}
            for x in _rows(d.get("items"), 4)
        ]}
    elif t == "faq":
        out = {"title": _s(d.get("title"), 80), "items": [
            {"q": _s(x.get("q") or x.get("title"), 120), "a": _s(x.get("a") or x.get("desc"), 600)}
            for x in _rows(d.get("items"), 6)
        ]}
    elif t == "cta":
        out = {"title": _s(d.get("title"), 80), "desc": _s(d.get("desc"), 200)}
        if isinstance(d.get("primary"), dict):
            out["primary"] = {"label": _s(d["primary"].get("label"), 24), "href": _s(d["primary"].get("href"), 200)}
    elif t == "form":
        out = {
            "title": _s(d.get("title"), 80),
            "desc": _s(d.get("desc"), 200),
            "submit_label": _s(d.get("submit_label"), 20) or "提交",
            "form_key": _s(d.get("form_key"), 60),
        }
        if isinstance(d.get("fields"), list):
            out["fields"] = [
                {"key": _s(x.get("key"), 30), "label": _s(x.get("label"), 30),
                 "type": _s(x.get("type"), 12) or "text", "required": bool(x.get("required"))}
                for x in _rows(d.get("fields"), 8)
            ]
    elif t == "footer":
        out = {"brand": _s(d.get("brand"), 40), "note": _s(d.get("note"), 200), "links": [
            {"label": _s(x.get("label"), 20), "href": _s(x.get("href"), 200)}
            for x in _rows(d.get("links"), 6)
        ]}
    return out


def clean_blocks(raw: Any, *, limit: int = 12) -> tuple[list[dict], list[str]]:
    """返回 (干净区块, 被丢弃的 type 列表)。

    丢弃而不是报错：模型偶尔会多给一两个自创区块，整页 500 是最差的选择，
    用户看到的是「AI 挂了」。
    """
    if not isinstance(raw, list):
        return [], ["<not-list>"]
    out: list[dict] = []
    dropped: list[str] = []
    for b in raw:
        if not isinstance(b, dict):
            continue
        t = str(b.get("type") or "").strip()
        if t not in AI_BLOCK_TYPES:
            dropped.append(t or "<empty>")
            continue
        d = b.get("data")
        if not isinstance(d, dict) or not d:
            # 字段平铺在区块上时，把 type/data 之外的键当成 data
            d = {k: v for k, v in b.items() if k not in ("type", "data")}
        out.append({"type": t, "data": _norm(t, d)})
        if len(out) >= limit:
            break
    return out, dropped
