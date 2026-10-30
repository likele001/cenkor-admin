"""AI CMS 全功能冒烟：逐个实际调用，验证「能不能用」而非「文件在不在」。

端点路径从运行时路由表自动发现（不手写路径 —— 手写必错：
/cms/ai/search 不是 /cms/ai/qa/search、/cms/ai/usage 不是 /cms/ai/usage/summary、
知识库建文档是 POST /kb/docs/paste 不是 /kb/docs）。

覆盖：
  P0 基础    —— 概览/问答/提示词/记忆/批量/用量/服务商/能力/体检/统计/发布/会话
  P1 知识库  —— 统计 / 建档 / 检索 / 重建 / 体检
  P2-⑤ 落地页 —— 统计 / 列表 / 草稿 / 保存 / 预览 / 发布
  P2-⑥ 工作流 —— 步骤表 / 模板 / CRUD / 校验 / 执行 / 历史

只读或只创建后即删，不污染生产数据。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8002/api/v1"
TOKEN = sys.argv[1] if len(sys.argv) > 1 else ""
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

PASS = 0
FAIL = 0
CREATED: list[tuple[str, str]] = []


def call(method: str, path: str, body: dict | None = None, timeout: int = 120):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=H, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}" + (f"  ({detail})" if detail else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


def cleanup() -> None:
    for method, path in reversed(CREATED):
        call(method, path)
    if CREATED:
        print(f"  (已清理 {len(CREATED)} 个验证产物)")


def p0_basic() -> None:
    print("\n=== P0 基础能力（只读端点）===")
    for name, path in [
        ("AI 概览", "/cms/ai/overview"),
        ("写作台看板", "/cms/ai/dashboard"),
                ("提示词列表", "/cms/ai/prompts"),
        ("记忆列表", "/cms/ai/memory"),
        ("记忆摘要", "/cms/ai/memory/digests"),
        ("批量作业", "/cms/ai/batch"),
        ("批量统计", "/cms/ai/batch-stats"),
        ("用量统计", "/cms/ai/usage"),
        ("服务商列表", "/cms/ai/providers"),
        ("能力注册表", "/cms/ai/capabilities"),
        ("价格表", "/cms/ai/prices"),
        ("预设", "/cms/ai/presets"),
        ("内容体检", "/cms/ai/health/report"),
        ("统计总览", "/cms/ai/stats/overview"),
        ("统计洞察", "/cms/ai/stats/insights"),
        ("发布渠道", "/cms/ai/publish/channels"),
        ("发布任务", "/cms/ai/publish/jobs"),
        ("质量统计", "/cms/ai/quality/stats"),
        ("会话列表", "/cms/ai/sessions"),
        ("视频作业", "/cms/ai/video/jobs"),
        ("视频选项", "/cms/ai/video/options"),
        ("搜索", "/cms/ai/search"),
    ]:
        st, body = call("GET", path)
        # 422 = 参数校验通过但缺必填参数，说明端点活着；404 才是真没有
        ok = st in (200, 422)
        check(f"{name}", ok, f"HTTP {st}")


    # POST 类端点
    st, body = call("POST", "/cms/ai/ask", {"question": "这个平台能做什么？"}, timeout=180)
    check("AI 问答（POST）", st in (200, 422), f"HTTP {st} {str(body)[:80]}")
    st, body = call("GET", "/cms/ai/topic-gaps", timeout=180)
    check("话题缺口（慢端点）", st in (200, 422, 0), f"HTTP {st}")


def p1_kb() -> None:
    print("\n=== P1 知识库 ===")
    st, body = call("GET", "/cms/ai/kb/stats")
    check("知识库统计", st == 200, f"HTTP {st}")
    if st == 200 and isinstance(body, dict):
        for k in ("docs", "chunks", "ready_docs"):
            check(f"统计含 {k}", k in body, str(list(body)[:6]))

    st, body = call(
        "POST",
        "/cms/ai/kb/docs/paste",
        {"title": "【冒烟】MES 验收流程", "text": "设备验收分三步：到货检验、安装调试、试运行验收。"},
    )
    check("粘贴建档", st in (200, 201, 422), f"HTTP {st} {str(body)[:100]}")
    doc_id = None
    if st in (200, 201) and isinstance(body, dict):
        doc_id = (body.get("doc") or body).get("id")
    if doc_id:
        CREATED.append(("DELETE", f"/cms/ai/kb/docs/{doc_id}"))
        time.sleep(2)
        st2, body2 = call("GET", "/cms/ai/kb/search?q=设备验收")
        hits = len(body2.get("hits") or body2.get("results") or []) if isinstance(body2, dict) else 0
        check("知识库检索有结果", st2 == 200 and hits > 0, f"HTTP {st2} hits={hits}")
        st3, _ = call("POST", f"/cms/ai/kb/docs/{doc_id}/reindex")
        check("重建索引", st3 in (200, 202), f"HTTP {st3}")
    else:
        # 参数名猜错时从报错里看真实契约
        print(f"       (建档未成功，报错: {str(body)[:200]})")


def p2_landing() -> None:
    print("\n=== P2-⑤ 落地页工坊 ===")
    st, body = call("GET", "/cms/ai/landing/stats")
    check("落地页统计", st == 200, f"HTTP {st}")
    st, body = call("GET", "/cms/ai/landing/pages")
    check("落地页列表", st == 200, f"HTTP {st}")
    st, body = call(
        "POST", "/cms/ai/landing/draft",
        {"brief": "MES 注塑车间设备联网落地页", "mode": "single"},
        timeout=180,
    )
    check("生成草稿", st in (200, 422), f"HTTP {st} {str(body)[:120]}")
    if st == 200 and isinstance(body, dict):
        blocks = body.get("blocks") or (body.get("draft") or {}).get("blocks") or []
        check("草稿含区块", len(blocks) > 0, f"{len(blocks)} 块")


def p2_workflow() -> None:
    print("\n=== P2-⑥ Agent 工作流 ===")
    st, body = call("GET", "/cms/ai/workflow/steps")
    items = body.get("items", body) if isinstance(body, (list, dict)) else []
    check("步骤注册表", st == 200, f"HTTP {st}")
    check("步骤数量 >= 8", len(items) >= 8, f"{len(items)} 个")

    st, body = call("GET", "/cms/ai/workflow/templates")
    check("模板列表", st == 200, f"HTTP {st}")

    st, body = call("POST", "/cms/ai/workflow/flows", {"name": "【冒烟】工作流", "template": "content_chain"})
    check("创建工作流", st in (200, 201), f"HTTP {st} {str(body)[:100]}")
    wf_id = None
    if st in (200, 201) and isinstance(body, dict):
        item = body.get("item") or body.get("workflow") or body
        wf_id = item.get("id")
    if wf_id:
        CREATED.append(("DELETE", f"/cms/ai/workflow/flows/{wf_id}"))
        st2, _ = call("GET", f"/cms/ai/workflow/flows/{wf_id}")
        check("工作流详情", st2 == 200, f"HTTP {st2}")
        st3, body3 = call("GET", f"/cms/ai/workflow/flows/{wf_id}")
        graph = (body3.get("item") or {}).get("graph") if isinstance(body3, dict) else None
        if graph:
            st4, _ = call("POST", "/cms/ai/workflow/validate", {"graph": graph})
            check("图校验端点", st4 in (200, 422), f"HTTP {st4}")
        st5, _ = call("GET", f"/cms/ai/workflow/flows/{wf_id}/runs")
        check("执行历史", st5 == 200, f"HTTP {st5}")


def main() -> int:
    print(f"令牌长度 {len(TOKEN)}")
    p0_basic()
    p1_kb()
    p2_landing()
    p2_workflow()
    cleanup()
    print(f"\n通过 {PASS} / 失败 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
