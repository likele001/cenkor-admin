"""修正版慢端点复测。

上一轮 smoke_slow.py 的两个 FAIL 都是脚本调用方式错，不是功能缺陷：
  1) 知识库检索端点是 POST /kb/search + JSON body{"query":...}，
     上一轮用 GET + 中文 query string → urllib 未做 URL 编码，抛 UnicodeEncodeError
     （HTTP 0 / 0.0s 立即返回的特征就是编码异常，不是超时）
  2) 落地页草稿返回体是 {brand, form, pages:[{blocks:[...]}]}，
     上一轮读顶层 body["blocks"]，恒为 0
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8002/api/v1"
TOKEN = sys.argv[1]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def call(method, path, body=None, timeout=420):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=H, method=method)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw), time.time() - t0
            except json.JSONDecodeError:
                return r.status, raw, time.time() - t0
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw), time.time() - t0
        except json.JSONDecodeError:
            return e.code, raw, time.time() - t0
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}", time.time() - t0


print("=== 1) 知识库：建档 → 分块 → POST /kb/search 检索 ===")
st, body, dt = call("POST", "/cms/ai/kb/docs/paste",
                    {"title": "【慢测2】MES 验收流程",
                     "text": "设备验收分三步：到货检验、安装调试、试运行验收。验收需客户签字确认。"})
print(f"  建档 HTTP {st}  {dt:.1f}s")
doc_id = (body.get("doc") or {}).get("id") if st == 200 and isinstance(body, dict) else None
if doc_id:
    status = "?"
    chunks = "?"
    for i in range(12):
        time.sleep(8)
        st2, b2, _ = call("GET", f"/cms/ai/kb/docs/{doc_id}")
        doc = (b2.get("doc") or b2) if isinstance(b2, dict) else {}
        status = doc.get("status")
        chunks = doc.get("chunk_count")
        print(f"    轮询 {i+1}: status={status} chunks={chunks}")
        if status in ("ready", "indexed", "failed"):
            break
    st3, b3, dt3 = call("POST", "/cms/ai/kb/search",
                        {"query": "设备验收需要哪几步", "limit": 6})
    print(f"  检索 HTTP {st3}  {dt3:.1f}s")
    if st3 == 200 and isinstance(b3, dict):
        hits = b3.get("hits") or []
        print(f"  hits={len(hits)}")
        for h in hits[:3]:
            txt = (h.get("text") or h.get("content") or h.get("chunk") or "")
            print(f"    - score={h.get('score')} passed={h.get('passed')} :: {str(txt)[:90]}")
    else:
        print(f"  失败体: {str(b3)[:300]}")
    call("DELETE", f"/cms/ai/kb/docs/{doc_id}")
    print("  已清理文档")
else:
    print(f"  建档失败: {str(body)[:300]}")

print("\n=== 2) 落地页草稿（按 pages[].blocks 解析）===")
st, body, dt = call("POST", "/cms/ai/landing/draft",
                    {"brief": "MES 注塑车间设备联网落地页", "mode": "page"}, timeout=420)
print(f"  HTTP {st}  {dt:.1f}s")
if st == 200 and isinstance(body, dict):
    pages = body.get("pages") or []
    total_blocks = sum(len(p.get("blocks") or []) for p in pages)
    print(f"  页面数: {len(pages)}  总区块数: {total_blocks}  dropped={body.get('dropped')}")
    print(f"  brand={body.get('brand')} accent={body.get('accent')}")
    print(f"  form={json.dumps(body.get('form'), ensure_ascii=False)[:160]}")
    for p in pages:
        print(f"  ── page {p.get('key')} / {p.get('name')} (blocks={len(p.get('blocks') or [])})")
        for b in (p.get("blocks") or [])[:10]:
            d = b.get("data") if isinstance(b.get("data"), dict) else b
            title = (d.get("title") or d.get("heading") or d.get("text") or "")[:44]
            print(f"      {b.get('type'):14s} {title}")
else:
    print(f"  失败: {str(body)[:400]}")
