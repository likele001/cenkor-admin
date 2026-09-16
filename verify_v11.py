#!/usr/bin/env python3
"""MES v0.11.0 质量追溯 端到端验证

覆盖点：
1. 追溯事件表为共享真表 —— MES 能读到 ERP 写入的采购/出货事件
2. 工单追溯：开工/报工后产生 MES 侧事件，时间线分阶段聚合正确
3. 产品追溯：按产品编码跨工单汇总
4. 批次/序列号追溯：跨系统串联入口
5. 设备追溯：报停/恢复产生设备事件
6. 事件流水：类型筛选与时间窗过滤
7. 追溯概览：erp/mes 来源计数口径与明细一致
8. meta 字典接口返回事件中文名映射
9. 事件注入完整性：开工→报工→检验 三类事件按序产生
10. 必检工序报工：qty 记报工总数而非清零后的合格数（口径正确性）
11. 追溯事件不可增删改（只读共享表设计）
12. 回归：v0.8.0 质检 / v0.9.0 工资 / v0.10.0 设备 路由仍可用

用法：
    python3 verify_v11.py --password <admin密码> [--base http://127.0.0.1:8002]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime

BASE = "http://127.0.0.1:8002"
TOKEN = ""
PASSED = 0
FAILED = 0
FAILURES: list[str] = []


def call(method: str, path: str, body: dict | None = None, *, expect=(200, 201, 204)):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status, raw = resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read().decode()
    try:
        parsed = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        parsed = raw
    exp = expect if isinstance(expect, tuple) else (expect,)
    if status not in exp:
        raise AssertionError(f"{method} {path} 期望 {exp}，实际 {status}：{str(parsed)[:300]}")
    return status, parsed


def check(name: str, cond: bool, detail: str = ""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  [PASS] {name}")
    else:
        FAILED += 1
        FAILURES.append(f"{name} {detail}")
        print(f"  [FAIL] {name} {detail}")


def section(t: str):
    print(f"\n{'=' * 70}\n{t}\n{'=' * 70}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", required=True)
    a = ap.parse_args()
    global BASE, TOKEN
    BASE = a.base

    print(f"MES v0.11.0 质量追溯验证 — {BASE}")
    _, d = call("POST", "/api/v1/auth/login", {"username": a.user, "password": a.password}, expect=200)
    TOKEN = d.get("access_token") or d.get("token") or ""
    assert TOKEN, f"登录失败：{d}"
    print("登录成功")

    ts = datetime.now().strftime("%H%M%S")

    # ==================== 1. meta 字典 ====================
    section("1. 追溯元数据字典")
    _, meta = call("GET", "/api/v1/mes/trace/meta")
    check("meta 返回事件名映射", isinstance(meta.get("event_names"), dict), str(meta)[:200])
    check("覆盖 ERP 事件类型", "purchase_receipt" in meta["event_names"], "缺 purchase_receipt")
    check("覆盖 MES 事件类型", "work_report" in meta["event_names"], "缺 work_report")
    check("返回阶段字典", isinstance(meta.get("stage_names"), dict), str(meta)[:200])
    mes_events = meta.get("mes_events") or []
    check("MES 事件白名单非空", len(mes_events) >= 4, f"实际 {mes_events}")
    print(f"    MES 可写事件类型：{mes_events}")

    # ==================== 2. 读共享表：ERP 事件可见 ====================
    section("2. 共享真表读取（ERP 写入的事件应可见）")
    _, evts = call("GET", "/api/v1/mes/trace/events?limit=500")
    check("事件流水可读", isinstance(evts, list), f"got {type(evts)}")
    erp_evts = [e for e in evts if e.get("source") == "erp"]
    check("能读到 ERP 侧事件", len(erp_evts) > 0, f"erp 事件 {len(erp_evts)} 条 / 总 {len(evts)} 条")
    if erp_evts:
        e0 = erp_evts[0]
        check("ERP 事件带中文名", bool(e0.get("event_name")), str(e0)[:200])
        print(f"    ERP 事件样例：{e0.get('event_type')} / {e0.get('event_name')} / {e0.get('happen_date')}")

    # ==================== 3. 准备数据：工位/设备/产品/工序/计划 ====================
    section("3. 准备测试数据")
    _, wc = call("POST", "/api/v1/mes/work-centers", {
        "code": f"TWC{ts}", "name": f"追溯测试工位{ts}", "wc_type": "machine",
    }, expect=201)
    wc_id = wc.get("id")
    check("测试工位创建", wc_id is not None, str(wc)[:150])

    # 必检工序（用于验证报工数量口径）
    _, proc = call("POST", "/api/v1/mes/processes", {
        "code": f"TPC{ts}", "name": f"追溯测试工序{ts}",
        "piece_rate": 3.5, "need_inspection": True,
    }, expect=201)
    proc_id = proc.get("id")
    check("必检工序创建", proc_id is not None, str(proc)[:150])

    _, prod = call("POST", "/api/v1/mes/products", {
        "code": f"TPD{ts}", "name": f"追溯测试产品{ts}", "unit": "件",
    }, expect=201)
    prod_id = prod["id"]
    prod_code = prod["code"]

    # 建生产订单（追溯按工单维度聚合的载体）
    _, order = call("POST", "/api/v1/mes/orders", {
        "product_id": prod_id, "quantity": 20, "start_date": datetime.now().strftime("%Y-%m-%d"),
    }, expect=(200, 201))
    order_id = order["id"]
    order_code = order.get("code")
    check("生产订单创建", bool(order_code), str(order)[:200])

    # 计划挂订单
    _, plan = call("POST", "/api/v1/mes/plans", {
        "plan_date": datetime.now().strftime("%Y-%m-%d"),
        "work_order_id": order_id,
        "items": [{"product_id": prod_id, "product_name": prod["name"], "product_code": prod_code, "qty": 20}],
    }, expect=(200, 201))
    call("POST", f"/api/v1/mes/plans/{plan['id']}/confirm", expect=(200, 201, 404))
    _, detail = call("GET", f"/api/v1/mes/plans/{plan['id']}")
    item = (detail.get("items") or [None])[0]
    assert item, f"计划无明细：{detail}"

    # 派工
    _, task = call("POST", "/api/v1/mes/tasks", {
        "plan_item_id": item["id"], "process_id": proc_id,
        "work_center_id": wc_id, "qty_plan": 20,
    }, expect=201)
    task_id = task["id"]
    check("派工成功", task_id is not None, str(task)[:150])

    # ==================== 4. 开工留痕 ====================
    section("4. 开工 → 追溯留痕")
    _, r = call("POST", f"/api/v1/mes/tasks/{task_id}/start", expect=(200, 201))
    check("开工成功", r.get("status") == "in_progress", str(r)[:150])

    _, tl = call("GET", f"/api/v1/mes/trace/work-order/{order_id}")
    types = [e.get("event_type") for e in (tl.get("events") or [])]
    check("工单链路含开工事件", "work_start" in types, f"实际 {types}")
    check("开工事件带中文名", any(e.get("event_name") == "开工" for e in (tl.get("events") or [])), f"实际 {types}")
    check("事件来源标记为 mes", all(
        e.get("source") == "mes" for e in tl["events"] if e.get("event_type") == "work_start"
    ), "work_start 来源非 mes")

    # ==================== 5. 报工留痕（必检口径） ====================
    section("5. 报工 → 追溯留痕（必检工序数量口径）")
    _, rep = call("POST", "/api/v1/mes/reports", {
        "task_id": task_id, "qty_ok": 18, "qty_rework": 1, "qty_scrap": 1,
    }, expect=201)
    check("报工成功（必检挂起）", rep.get("inspect_status") == "pending", str(rep)[:200])
    report_id = rep["id"]

    _, tl = call("GET", f"/api/v1/mes/trace/work-order/{order_id}")
    work_reps = [e for e in tl["events"] if e.get("event_type") == "work_report"]
    check("工单链路含报工事件", len(work_reps) >= 1, f"实际 {len(work_reps)} 条")
    if work_reps:
        qty = float(work_reps[-1].get("quantity") or 0)
        # 必检时 qty_ok 被清零，留痕应记报工总数 20 而非 0
        check("报工留痕记报工总数而非清零后合格数", qty == 20, f"实际 quantity={qty}（期望 20）")
        check("报工备注标注待检", "待检" in (work_reps[-1].get("remark") or ""), str(work_reps[-1])[:200])

    # ==================== 6. 检验判定留痕 ====================
    section("6. 检验判定 → 追溯留痕")
    _, ins = call("POST", f"/api/v1/mes/quality/reports/{report_id}/inspect", {
        "qty_ok": 18, "qty_rework": 1, "qty_scrap": 1,
    }, expect=201)
    check("检验判定成功", ins.get("result") in ("passed", "partial"), str(ins)[:200])

    _, tl = call("GET", f"/api/v1/mes/trace/work-order/{order_id}")
    types = [e.get("event_type") for e in (tl.get("events") or [])]
    check("工单链路含检验事件", any(t in ("qc_pass", "qc_result") for t in types), f"实际 {types}")
    # 有返工/报废时应记 qc_result 而非 qc_pass，避免污染 ERP 的合格统计
    check("部分合格记 qc_result 而非 qc_pass", "qc_result" in types, f"实际 {types}")

    nodes = tl.get("nodes") or []
    stages = [n.get("stage") for n in nodes]
    check("时间线分阶段聚合", len(stages) >= 1, f"实际阶段 {stages}")
    check("制造段出现在时间线", "production" in stages, f"实际阶段 {stages}")
    check("时间线节点带事件明细", all(isinstance(n.get("events"), list) for n in nodes), "节点缺 events")
    print(f"    时间线阶段：{stages}")

    # 事件顺序：开工应在报工之前
    evt_seq = [(e.get("event_type"), e.get("id")) for e in tl["events"]]
    ws = [i for i, (t, _) in enumerate(evt_seq) if t == "work_start"]
    wr = [i for i, (t, _) in enumerate(evt_seq) if t == "work_report"]
    if ws and wr:
        check("开工事件排在报工之前", ws[0] < wr[0], f"开工 idx={ws} 报工 idx={wr}")

    # ==================== 7. 按产品追溯 ====================
    section("7. 按产品追溯")
    _, ptl = call("GET", f"/api/v1/mes/trace/product?product_code={prod_code}")
    check("产品追溯返回链路", ptl.get("ref_type") == "product", str(ptl)[:150])
    check("产品追溯有事件", ptl.get("total_events", 0) > 0, f"实际 {ptl.get('total_events')}")
    check("产品追溯带产品名", bool(ptl.get("product_name")), str(ptl)[:200])
    # 不存在的产品应 404
    call("GET", "/api/v1/mes/trace/product?product_code=__NOT_EXIST__", expect=404)
    check("不存在的产品返回 404", True)

    # ==================== 8. 按批次 / 序列号追溯 ====================
    section("8. 按批次 / 序列号追溯（跨系统入口）")
    if erp_evts:
        sample = next((e for e in erp_evts if e.get("batch_no")), None) or erp_evts[0]
        if sample.get("batch_no"):
            _, btl = call("GET", f"/api/v1/mes/trace/batch?batch_no={sample['batch_no']}")
            check("按批次追溯返回链路", btl.get("ref_type") in ("batch", "serial"), str(btl)[:150])
            check("批次追溯有事件", btl.get("total_events", 0) > 0, f"实际 {btl.get('total_events')}")
            print(f"    批次 {sample['batch_no']} → {btl.get('total_events')} 条事件")
        else:
            print("    （现有 ERP 事件无批次号，跳过批次查询）")
    # 参数缺失应 400
    call("GET", "/api/v1/mes/trace/batch", expect=400)
    check("批次查询缺参数返回 400", True)
    call("GET", "/api/v1/mes/trace/batch?batch_no=__NOPE__", expect=404)
    check("不存在的批次返回 404", True)

    # ==================== 9. 按设备追溯 ====================
    section("9. 按设备追溯（停机留痕）")
    _, eq = call("POST", "/api/v1/erp/equip/equipments", {
        "code": f"TEQ{ts}", "name": f"追溯测试机{ts}", "work_center_id": wc_id,
        "category": "加工", "status": "active",
    }, expect=(200, 201))
    eq_id = eq.get("id")
    check("测试设备创建（走 ERP 接口）", eq_id is not None, str(eq)[:200])

    _, dt = call("POST", "/api/v1/mes/equip/downtimes", {
        "equipment_id": eq_id, "reason": "breakdown", "affects_qty": 5,
    }, expect=201)
    dt_id = dt["id"]
    check("报停成功", dt.get("end_at") is None, str(dt)[:150])

    _, etl = call("GET", f"/api/v1/mes/trace/equipment/{eq_id}")
    e_types = [e.get("event_type") for e in (etl.get("events") or [])]
    check("设备链路含停机事件", "downtime_start" in e_types, f"实际 {e_types}")
    check("停机事件带影响产量", any(
        float(e.get("quantity") or 0) == 5 for e in etl["events"] if e.get("event_type") == "downtime_start"
    ), f"{etl.get('events')}")

    _, _c = call("POST", f"/api/v1/mes/equip/downtimes/{dt_id}/close", {"affects_qty": 5}, expect=(200, 201))
    _, etl = call("GET", f"/api/v1/mes/trace/equipment/{eq_id}")
    e_types = [e.get("event_type") for e in (etl.get("events") or [])]
    check("设备链路含恢复事件", "downtime_end" in e_types, f"实际 {e_types}")

    call("GET", "/api/v1/mes/trace/equipment/999999", expect=404)
    check("不存在的设备返回 404", True)

    # ==================== 10. 事件流水筛选 ====================
    section("10. 事件流水筛选")
    _, only_ws = call("GET", "/api/v1/mes/trace/events?event_type=work_start&limit=200")
    check("按事件类型筛选生效", all(e.get("event_type") == "work_start" for e in only_ws), f"实际 {len(only_ws)} 条")
    check("筛选结果非空", len(only_ws) > 0, "本应含刚写入的开工事件")

    # 流水按时间倒序
    if len(only_ws) >= 2:
        ids = [e.get("id") for e in only_ws]
        check("流水按时间倒序", ids == sorted(ids, reverse=True), f"ids={ids[:10]}")

    # 时间窗：远古区间应无数据
    _, ancient = call("GET", "/api/v1/mes/trace/events?date_from=2000-01-01&date_to=2000-01-02")
    check("时间窗过滤生效", len(ancient) == 0, f"实际 {len(ancient)} 条")

    # ==================== 11. 追溯概览 ====================
    section("11. 追溯概览统计")
    today = datetime.now().strftime("%Y-%m-%d")
    _, stat = call("GET", f"/api/v1/mes/trace/stat?date_from={today}&date_to={today}")
    check("概览返回总数", stat.get("total_events", 0) > 0, str(stat)[:200])
    check("概览分 erp/mes 来源", stat.get("mes_events", 0) > 0, f"mes_events={stat.get('mes_events')}")
    check("来源计数之和等于总数",
          stat["erp_events"] + stat["mes_events"] == stat["total_events"],
          f"{stat['erp_events']}+{stat['mes_events']} != {stat['total_events']}")
    rows = stat.get("by_event_type") or []
    check("按类型分布非空", len(rows) > 0, "by_event_type 为空")
    check("分布计数之和等于总数",
          sum(r["count"] for r in rows) == stat["total_events"],
          f"明细和 {sum(r['count'] for r in rows)} != {stat['total_events']}")
    check("类型带中文名", all(r.get("name") for r in rows), "存在无名类型")
    print(f"    今日事件：{stat['total_events']} 条（ERP {stat['erp_events']} / MES {stat['mes_events']}）")

    # ==================== 12. 工单追溯列表 ====================
    section("12. 可追溯工单列表")
    _, wos = call("GET", "/api/v1/mes/trace/work-orders")
    check("工单列表可读", isinstance(wos, list), f"got {type(wos)}")
    hit = [o for o in wos if o.get("id") == order_id]
    check("刚操作的工单在列表中", len(hit) == 1, f"实际 {len(hit)} 条匹配")
    if hit:
        check("列表带事件数", hit[0].get("event_count", 0) > 0, str(hit[0])[:200])
        check("列表带最近事件时间", bool(hit[0].get("last_event_at")), str(hit[0])[:200])

    # 关键字过滤
    _, kw = call("GET", f"/api/v1/mes/trace/work-orders?keyword={prod_code}")
    check("工单列表关键字过滤", all(
        prod_code in (o.get("product_code") or "") or prod_code in (o.get("code") or "")
        for o in kw
    ), f"实际 {len(kw)} 条")

    # ==================== 13. 只读边界 ====================
    section("13. 只读共享表边界（不可增删改）")
    # 追溯事件由业务动作自动产生，不提供写接口
    call("POST", "/api/v1/mes/trace/events", {"event_type": "hack"}, expect=(404, 405))
    check("追溯事件无新增接口（404/405）", True)
    call("DELETE", "/api/v1/mes/trace/events/1", expect=(404, 405))
    check("追溯事件无删除接口（404/405）", True)

    # ==================== 14. 权限点 ====================
    section("14. 权限与回归")
    _, h = call("GET", "/api/v1/mes/health")
    check("health 版本为 0.11.0", h.get("version") == "0.11.0", f"实际 {h.get('version')}")

    # v0.8.0 / v0.9.0 / v0.10.0 回归
    call("GET", "/api/v1/mes/quality/pending")
    check("回归 v0.8.0 质检路由可用", True)
    call("GET", "/api/v1/mes/wage/stat")
    check("回归 v0.9.0 计件工资路由可用", True)
    call("GET", "/api/v1/mes/equip/downtime-stat")
    check("回归 v0.10.0 设备统计路由可用", True)
    call("GET", "/api/v1/mes/trace/stat")
    check("v0.11.0 追溯统计路由可用", True)

    # ==================== 汇总 ====================
    print(f"\n{'=' * 70}")
    print(f"结果：通过 {PASSED} / 失败 {FAILED}")
    if FAILURES:
        print("\n失败明细：")
        for f in FAILURES:
            print(f"  - {f}")
    print("=" * 70)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
