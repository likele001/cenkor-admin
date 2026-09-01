"""Builder · 区块渲染（把 blocks schema 渲染成 HTML）"""
from __future__ import annotations

import html as _html
from typing import Any

BLOCK_TYPES = ("hero", "heading", "text", "image", "list", "html")


def _esc(v: Any) -> str:
    return _html.escape(str(v if v is not None else ""), quote=True)


def render_blocks(blocks: list[dict]) -> str:
    """将区块列表渲染为服务端 HTML（基础标签，安全转义）。"""
    parts: list[str] = []
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        d = b.get("data") or {}
        if t == "hero":
            parts.append(
                '<section class="builder-hero">'
                f'<h1 class="builder-hero-title">{_esc(d.get("title"))}</h1>'
                f'<p class="builder-hero-subtitle">{_esc(d.get("subtitle"))}</p>'
                "</section>"
            )
        elif t == "heading":
            lvl = d.get("level", 2)
            lvl = lvl if lvl in (1, 2, 3, 4, 5, 6) else 2
            parts.append(f"<h{lvl}>{_esc(d.get('text'))}</h{lvl}>")
        elif t == "text":
            parts.append(f'<p class="builder-text">{_esc(d.get("text"))}</p>')
        elif t == "image":
            src = d.get("src") or ""
            parts.append(f'<img class="builder-image" src="{_esc(src)}" alt="{_esc(d.get("alt"))}" />')
        elif t == "list":
            items = d.get("items") or []
            lis = "".join(f"<li>{_esc(i)}</li>" for i in items)
            parts.append(f'<ul class="builder-list">{lis}</ul>')
        elif t == "html":
            parts.append(f'<div class="builder-html">{d.get("html", "")}</div>')
        else:
            parts.append(f'<div class="builder-block" data-block="{_esc(t)}"></div>')
    return "\n".join(parts)


def page_html(page_key: str, title: str, blocks: list[dict]) -> str:
    """完整 HTML 文档（供 iframe / 快速预览）。"""
    body = render_blocks(blocks)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(title)}</title>
<style>
body{{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;margin:0;color:#1f2937;background:#fff;line-height:1.7}}
.builder-hero{{background:#f3f4f6;padding:64px 24px;text-align:center}}
.builder-hero-title{{font-size:40px;margin:0 0 12px}}
.builder-hero-subtitle{{font-size:18px;color:#6b7280;margin:0}}
.builder-block,.builder-text,.builder-image,.builder-list{{padding:0 24px;max-width:960px;margin:0 auto}}
img.builder-image{{display:block;max-width:100%;margin:16px auto}}
h1,h2,h3{{padding:0 24px}}
</style>
</head>
<body>
{body}
</body>
</html>"""
