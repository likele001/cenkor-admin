"""版本快照对比（M1·P0 版本控制的续篇）。

## 为什么单独成模块

审核流有「通过 / 驳回」，但审核人看不到**这次改了什么**，只能整篇重读。
实际使用中这会退化成橡皮图章 —— 审批动作发生了，风险没有被看见。
这个模块只做一件事：把两份快照摊成「双栏行序列」，让改动一眼可见。

## 为什么按段落而不是按字符

中文按字符 diff 会切出大量无意义的单字差异（「的」→「了」也标一处），
审核人反而看不出真正改动。按块级标签切行、行内整体比对，符合人的阅读单位。

## 为什么左右两侧放在同一行里

前端双栏要同步滚动。若左右各返回一个列表，前端得自己做对齐计算，
滚动同步一定会飘。所以这里直接给出 ``rows``，每行 ``left``/``right`` 成对出现，
前端只负责渲染。缺失的一侧为 ``None``（新增行左边是空、删除行右边是空）。

## 纯函数

本模块不碰数据库、不依赖 FastAPI，全部输入输出都是普通 dict，
方便直接在 REPL 里拿真实快照跑一遍看结果。
"""

from __future__ import annotations

import difflib
import html as html_lib
import json
import re
from typing import Any

# 块级闭合标签：在这些标签结束处断行。
# 不追求完整的 HTML 解析 —— 正文由前端编辑器产出，结构稳定；
# 用正则切分比引一个解析器依赖更划算，也不会因为畸形 HTML 抛异常。
_BLOCK_CLOSE = re.compile(
    r"</(?:p|h[1-6]|li|blockquote|pre|td|th|div|section|article|figure|figcaption|dt|dd)>",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\u00a0]+")

# 快照里参与对比的标量字段 -> 中文标签（顺序即前端展示顺序）
SCALAR_FIELDS: list[tuple[str, str]] = [
    ("title", "标题"),
    ("slug", "Slug"),
    ("status", "状态"),
    ("category_id", "分类"),
    ("sort", "排序"),
    ("published_at", "发布时间"),
    ("scheduled_at", "定时发布"),
    ("expire_at", "过期下线"),
]

# 结构化字段 -> 中文标签（走 JSON 逐 key 比对，只回有变化的 key）
JSON_FIELDS: list[tuple[str, str]] = [
    ("custom_fields", "自定义字段"),
    ("seo", "SEO"),
]

STATUS_LABELS = {
    "draft": "草稿",
    "pending_review": "待审核",
    "approved": "已通过",
    "published": "已发布",
    "archived": "已下线",
    "rejected": "已驳回",
}

_MAX_TEXT = 4000  # 单行纯文本回传上限，防止超长段落把响应撑爆


def _plain(fragment: str) -> str:
    """HTML 片段 -> 纯文本（比对用）。"""
    text = _TAG_RE.sub("", fragment or "")
    text = html_lib.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return _WS_RE.sub(" ", text).strip()


def _split_blocks(raw: str) -> list[str]:
    """把正文切成「阅读单位」。

    优先按块级闭合标签切；没有块级标签时（纯文本正文）退化按换行切。
    两种都切不出来就整段当一行 —— 至少还能比对出「改了」。
    """
    if not raw:
        return []
    text = str(raw)

    if not _BLOCK_CLOSE.search(text):
        # 纯文本：一行一个单位，空行丢弃
        parts = [ln for ln in text.split("\n") if ln.strip()]
        if len(parts) > 1:
            return [p.strip() for p in parts]
        whole = _plain(text)
        return [text.strip()] if whole or text.strip() else []

    parts: list[str] = []
    cursor = 0
    for m in _BLOCK_CLOSE.finditer(text):
        chunk = text[cursor : m.end()]
        cursor = m.end()
        if chunk.strip():
            parts.append(chunk.strip())
    tail = text[cursor:]
    if tail.strip():
        parts.append(tail.strip())
    return parts


def _side(no: int | None, fragment: str | None) -> dict[str, Any] | None:
    if fragment is None:
        return None
    plain = _plain(fragment)
    return {
        "no": no,
        "html": fragment if len(fragment) <= _MAX_TEXT * 2 else fragment[: _MAX_TEXT * 2],
        "text": plain if len(plain) <= _MAX_TEXT else plain[:_MAX_TEXT] + "…",
        "empty": not plain,
    }


def diff_text(left_html: str, right_html: str) -> dict[str, Any]:
    """正文段落级对比，返回双栏行序列与增删改计数。"""
    left_lines = _split_blocks(left_html)
    right_lines = _split_blocks(right_html)
    left_keys = [_plain(x) for x in left_lines]
    right_keys = [_plain(x) for x in right_lines]

    # autojunk=False：内容重复度高（模板化正文）时默认启发式会漏判
    sm = difflib.SequenceMatcher(None, left_keys, right_keys, autojunk=False)
    rows: list[dict[str, Any]] = []
    stats = {"added": 0, "removed": 0, "changed": 0, "unchanged": 0}
    ln = 0
    rn = 0

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                ln += 1
                rn += 1
                rows.append(
                    {
                        "type": "equal",
                        "left": _side(ln, left_lines[i1 + k]),
                        "right": _side(rn, right_lines[j1 + k]),
                    }
                )
            stats["unchanged"] += i2 - i1
        elif tag == "delete":
            for k in range(i1, i2):
                ln += 1
                rows.append({"type": "delete", "left": _side(ln, left_lines[k]), "right": None})
            stats["removed"] += i2 - i1
        elif tag == "insert":
            for k in range(j1, j2):
                rn += 1
                rows.append({"type": "insert", "left": None, "right": _side(rn, right_lines[k])})
            stats["added"] += j2 - j1
        else:  # replace：能对上的算「改」，多出来的算增/删
            paired = min(i2 - i1, j2 - j1)
            for k in range(paired):
                ln += 1
                rn += 1
                rows.append(
                    {
                        "type": "replace",
                        "left": _side(ln, left_lines[i1 + k]),
                        "right": _side(rn, right_lines[j1 + k]),
                    }
                )
            for k in range(i1 + paired, i2):
                ln += 1
                rows.append({"type": "delete", "left": _side(ln, left_lines[k]), "right": None})
            for k in range(j1 + paired, j2):
                rn += 1
                rows.append({"type": "insert", "left": None, "right": _side(rn, right_lines[k])})
            stats["changed"] += paired
            stats["removed"] += (i2 - i1) - paired
            stats["added"] += (j2 - j1) - paired

    return {
        "rows": rows,
        "stats": stats,
        "left_lines": len(left_lines),
        "right_lines": len(right_lines),
    }


def _show_value(value: Any) -> tuple[str, str]:
    """把任意值转成「可展示文本 + 类型」，方便前端决定用文本还是 JSON 块渲染。"""
    if value is None:
        return "", "null"
    if isinstance(value, str):
        return value, "string"
    if isinstance(value, bool):
        return ("是" if value else "否"), "boolean"
    if isinstance(value, (int, float)):
        return str(value), "number"
    return json.dumps(value, ensure_ascii=False, indent=2), "json"


def diff_scalar_field(name: str, label: str, left: Any, right: Any) -> dict[str, Any] | None:
    """标量字段对比：无变化返回 None。"""
    if left == right:
        return None
    if name == "status":
        lv = STATUS_LABELS.get(str(left), "—" if left in (None, "") else str(left))
        rv = STATUS_LABELS.get(str(right), "—" if right in (None, "") else str(right))
        return {
            "field": name,
            "label": label,
            "type": "replace",
            "from": lv,
            "to": rv,
            "from_raw": left,
            "to_raw": right,
            "kind": "text",
        }
    ltext, lkind = _show_value(left)
    rtext, rkind = _show_value(right)
    if not ltext and rtext:
        ftype = "insert"
    elif ltext and not rtext:
        ftype = "delete"
    else:
        ftype = "replace"
    return {
        "field": name,
        "label": label,
        "type": ftype,
        "from": ltext,
        "to": rtext,
        "from_raw": left,
        "to_raw": right,
        "kind": "json" if "json" in (lkind, rkind) else "text",
    }


def diff_json_field(name: str, label: str, left: Any, right: Any) -> dict[str, Any] | None:
    """结构化字段对比：逐 key 比，只回有变化的 key。"""
    lmap = left if isinstance(left, dict) else {}
    rmap = right if isinstance(right, dict) else {}
    keys = sorted(set(lmap) | set(rmap))
    items: list[dict[str, Any]] = []
    for key in keys:
        lv = lmap.get(key)
        rv = rmap.get(key)
        if lv == rv:
            continue
        ltext, lkind = _show_value(lv)
        rtext, rkind = _show_value(rv)
        if key not in lmap:
            ftype = "insert"
        elif key not in rmap:
            ftype = "delete"
        else:
            ftype = "replace"
        items.append(
            {
                "key": key,
                "type": ftype,
                "from": ltext,
                "to": rtext,
                "kind": "json" if "json" in (lkind, rkind) else "text",
            }
        )
    if not items:
        return None
    return {"field": name, "label": label, "type": "replace", "items": items}


def build_payload(
    left_meta: dict[str, Any],
    left_data: dict[str, Any],
    right_meta: dict[str, Any],
    right_data: dict[str, Any],
) -> dict[str, Any]:
    """组装完整的对比结果。"""
    left_content = left_data.get("content") or {}
    right_content = right_data.get("content") or {}
    if not isinstance(left_content, dict):
        left_content = {"text": str(left_content)}
    if not isinstance(right_content, dict):
        right_content = {"text": str(right_content)}

    text = diff_text(left_content.get("text") or "", right_content.get("text") or "")

    fields: list[dict[str, Any]] = []
    for key, label in SCALAR_FIELDS:
        item = diff_scalar_field(key, label, left_data.get(key), right_data.get(key))
        if item:
            fields.append(item)
    for key, label in JSON_FIELDS:
        item = diff_json_field(key, label, left_data.get(key), right_data.get(key))
        if item:
            fields.append(item)

    # 正文 content 里 text 之外的结构化键（cover / gallery 等）
    extra_l_text = {k: v for k, v in left_content.items() if k != "text"}
    extra_r_text = {k: v for k, v in right_content.items() if k != "text"}
    extra = diff_json_field("content", "正文附加字段", extra_l_text, extra_r_text)
    if extra:
        fields.append(extra)

    s = text["stats"]
    has_text_change = s["added"] or s["removed"] or s["changed"]
    return {
        "left": left_meta,
        "right": right_meta,
        "text": text,
        "fields": fields,
        "has_changes": bool(has_text_change or fields),
        "summary": {
            "added": s["added"],
            "removed": s["removed"],
            "changed": s["changed"],
            "fields_changed": len(fields),
        },
    }
