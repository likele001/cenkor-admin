"""AI 工作流 · 执行引擎

## 一个 run 的生命周期

    start_run()  → 建 run（pending）+ 立刻排后台任务
    execute()    → 拓扑序逐节点执行，每步单独提交
    …            → succeeded / failed / halted / cancelled

## 四个必须自己实现、不能省的机制

1. **拓扑序 + 环检测**。画布允许任意连线，用户画出 A→B→A 是常事。不检测的话
   执行器会死循环，而前端只是画面上多了条线。保存时就拒，执行前再兜一次。
2. **变量插值**。`{{n1.topic}}` 取上游节点输出，`{{input.x}}` 取本次输入。
   整串就是一个变量时必须**保留原类型** —— `{{n3.draft}}` 要拿到 dict，
   一旦被转成字符串，落库步骤就得靠 json.loads 猜回来。
3. **重试按步骤声明的能力决定**。起草失败重试是省钱（省一次人工重写），
   落库失败重试是造脏数据（多一条重复条目）。所以 `retryable=False` 的步骤
   无论配置多少次都只跑一次。
4. **可恢复**。重跑失败的 run 时，已成功的节点直接复用 `cms_workflow_steps.output`
   里存的输出，不再花模型钱。

## 一个必须记住的坑：rollback 会让 ORM 对象过期

某一步的 SQL 失败后，整个事务被标成 aborted，不 rollback 后面 commit 必炸。
但 rollback 之后**所有 ORM 对象都过期了**，此时访问 `run.site_id` 会触发惰性
加载 —— 在 async session 里直接抛 MissingGreenlet。所以每个循环开头都把要用
的标量抠成局部变量，rollback 之后重新 `get` 一遍对象，不复用旧引用。

## 为什么不用 Celery

见 batch_runner.py 的同类取舍：任务「长但不密集」（每步 10~60s 纯等 LLM），
进程内 asyncio 足够；状态全落 DB，宝塔自愈重启后 pending 的 run 由调度器钩子
接手续跑，不会静默消失。
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm.exc import StaleDataError

from cenkor_admin.apps.cms.ai import workflow_steps as ws
from cenkor_admin.apps.cms.ai.workflow_models import (
    CmsWorkflow,
    CmsWorkflowRun,
    CmsWorkflowStep,
)
from cenkor_admin.core.db import AsyncSessionLocal

log = structlog.get_logger()

_BG: set[asyncio.Task] = set()

# 本进程启动时刻。用来区分「上次遗留的 run」和「本进程刚起的 run」，
# 见 recover_stale()。
_PROC_START = datetime.now(UTC)

RUN_ACTIVE = ("pending", "running")


# ---------------------------------------------------------------------------
# 图
# ---------------------------------------------------------------------------
class GraphError(ValueError):
    pass


def normalize_graph(graph: Any) -> dict[str, Any]:
    """把画布传来的图收成 {nodes:[...], edges:[...], inputs:[...]}，并保证 id 唯一。

    `inputs` 是这条流水线要人填的变量（主题方向、内容类型 key …）。
    它存在图里而不是独立字段，因为输入项和参数面板是同一件事的两面：
    「运行时要填什么」和「节点里怎么引用它」必须同源，否则对不上。
    """
    if not isinstance(graph, dict):
        return {"nodes": [], "edges": [], "inputs": []}
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for n in graph.get("nodes") or []:
        if not isinstance(n, dict):
            continue
        nid = str(n.get("id") or "").strip()
        if not nid or nid in seen:
            continue
        seen.add(nid)
        nodes.append(
            {
                "id": nid,
                "type": str(n.get("type") or "").strip(),
                "title": str(n.get("title") or "")[:120],
                "x": n.get("x"),
                "y": n.get("y"),
                "params": n.get("params") if isinstance(n.get("params"), dict) else {},
                "retries": int(n.get("retries") or 0),
            }
        )
    edges: list[dict[str, str]] = []
    for e in graph.get("edges") or []:
        if not isinstance(e, dict):
            continue
        src = str(e.get("from") or "").strip()
        dst = str(e.get("to") or "").strip()
        if src in seen and dst in seen and src != dst:
            edges.append({"from": src, "to": dst})
    inputs: list[dict[str, Any]] = []
    for it in graph.get("inputs") or []:
        if not isinstance(it, dict):
            continue
        key = str(it.get("key") or "").strip()
        if not key:
            continue
        inputs.append(
            {
                "key": key,
                "label": str(it.get("label") or key)[:60],
                "required": bool(it.get("required")),
                "help": str(it.get("help") or "")[:300],
                "default": it.get("default"),
            }
        )
    return {"nodes": nodes, "edges": edges, "inputs": inputs}


def topo_order(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Kahn 拓扑排序。无连线的节点按声明顺序排在前面。

    为什么「无连线的节点也要跑」：用户拖了节点还没连线就想试跑看看效果。
    直接跳过会让人以为节点没生效；跑一遍反而能立刻看到输出对不对。
    """
    g = normalize_graph(graph)
    nodes = g["nodes"]
    by_id = {n["id"]: n for n in nodes}
    indeg = {n["id"]: 0 for n in nodes}
    out: dict[str, list[str]] = {n["id"]: [] for n in nodes}
    for e in g["edges"]:
        out[e["from"]].append(e["to"])
        indeg[e["to"]] += 1

    ready = [n["id"] for n in nodes if indeg[n["id"]] == 0]
    order: list[str] = []
    while ready:
        nid = ready.pop(0)
        order.append(nid)
        for nxt in out[nid]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                ready.append(nxt)

    if len(order) != len(nodes):
        stuck = [n["id"] for n in nodes if n["id"] not in order]
        raise GraphError(f"连线存在环：{'、'.join(stuck)}")
    return [by_id[i] for i in order]


def first_node(graph: dict[str, Any]) -> str | None:
    try:
        order = topo_order(graph)
    except GraphError:
        return None
    return order[0]["id"] if order else None


# ---------------------------------------------------------------------------
# 变量插值
# ---------------------------------------------------------------------------
_VAR_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.\-]+)\s*\}\}")
_MISSING = "\u0000missing"


def _walk(path: str, scope: dict[str, Any]) -> Any:
    cur: Any = scope
    for part in path.split("."):
        if isinstance(cur, dict):
            if part not in cur:
                return _MISSING
            cur = cur[part]
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return _MISSING
        else:
            return _MISSING
    return cur


def _to_text(v: Any) -> str:
    if v is _MISSING or v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float, bool)):
        return str(v)
    return json.dumps(v, ensure_ascii=False)


def interpolate(value: Any, scope: dict[str, Any]) -> Any:
    """递归插值。整串只有一个变量时保留原类型，这是 entry.save 能拿到 dict 的前提。"""
    if isinstance(value, str):
        whole = _VAR_RE.fullmatch(value.strip())
        if whole:
            got = _walk(whole.group(1), scope)
            return "" if got is _MISSING else got
        return _VAR_RE.sub(lambda m: _to_text(_walk(m.group(1), scope)), value)
    if isinstance(value, list):
        return [interpolate(v, scope) for v in value]
    if isinstance(value, dict):
        return {k: interpolate(v, scope) for k, v in value.items()}
    return value


def missing_refs(value: Any, scope: dict[str, Any]) -> list[str]:
    """找出引用了但上游没有的变量。执行前预检，比跑到一半报错友好。"""
    bad: list[str] = []
    if isinstance(value, str):
        for m in _VAR_RE.finditer(value):
            if _walk(m.group(1), scope) is _MISSING:
                bad.append(m.group(1))
    elif isinstance(value, list):
        for v in value:
            bad.extend(missing_refs(v, scope))
    elif isinstance(value, dict):
        for v in value.values():
            bad.extend(missing_refs(v, scope))
    return bad


# ---------------------------------------------------------------------------
# run 创建
# ---------------------------------------------------------------------------
async def active_run_id(db, workflow_id: int) -> int | None:
    return (
        await db.execute(
            select(CmsWorkflowRun.id)
            .where(
                CmsWorkflowRun.workflow_id == workflow_id,
                CmsWorkflowRun.status.in_(RUN_ACTIVE),
            )
            .order_by(CmsWorkflowRun.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def create_run(
    db,
    workflow: CmsWorkflow,
    *,
    payload: dict[str, Any] | None = None,
    trigger: str = "manual",
    user_id: int | None = None,
) -> CmsWorkflowRun:
    if await active_run_id(db, workflow.id):
        raise GraphError("这个工作流还有一次执行没结束，等它跑完再试")
    run = CmsWorkflowRun(
        workflow_id=workflow.id,
        site_id=workflow.site_id,
        status="pending",
        trigger=trigger,
        input=payload or {},
        vars={},
        created_by=user_id,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


def spawn(run_id: int, *, resume: bool = False) -> asyncio.Task:
    """排后台任务。

    这里必须吃掉异常：asyncio 后台任务抛出的异常没人 await，
    日志里只会留下一句 "Task exception was never retrieved"，run 永远卡在 running。
    所以兜底把 run 标失败，前端才能看到真实状态。
    """

    async def _runner() -> None:
        try:
            await execute(run_id, resume=resume)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("cms.workflow.run_crashed", run=run_id, error=str(exc))
            try:
                async with AsyncSessionLocal() as db:
                    run = await db.get(CmsWorkflowRun, run_id)
                    if run is not None and run.status in RUN_ACTIVE:
                        run.status = "failed"
                        run.error = f"执行异常：{exc}"[:500]
                        run.finished_at = datetime.now(UTC)
                        await db.commit()
            except Exception:
                pass

    task = asyncio.create_task(_runner())
    _BG.add(task)
    task.add_done_callback(_BG.discard)
    return task


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------
async def _upsert_step(db, run_id: int, node: dict[str, Any], seq: int) -> CmsWorkflowStep:
    await db.execute(
        pg_insert(CmsWorkflowStep)
        .values(
            run_id=run_id,
            node_id=node["id"],
            node_type=node["type"],
            seq=seq,
            title=node.get("title") or node["type"],
            status="pending",
            input={},
            output={},
        )
        .on_conflict_do_nothing(index_elements=["run_id", "node_id"])
    )
    await db.commit()
    return (
        await db.execute(
            select(CmsWorkflowStep).where(
                CmsWorkflowStep.run_id == run_id, CmsWorkflowStep.node_id == node["id"]
            )
        )
    ).scalar_one()


async def _finish(db, run_id: int, wf_id: int, status: str, error: str | None) -> None:
    """统一收尾。rollback 之后对象可能已过期，所以按 id 重新取。"""
    run = await db.get(CmsWorkflowRun, run_id)
    if run is not None:
        run.status = status
        run.error = error
        run.finished_at = datetime.now(UTC)
    wf = await db.get(CmsWorkflow, wf_id)
    if wf is not None:
        wf.last_run_status = status
    await db.commit()


async def execute(run_id: int, *, resume: bool = False) -> dict[str, Any]:
    """跑一次工作流。resume=True 时复用已成功节点的输出。"""
    started = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        run = await db.get(CmsWorkflowRun, run_id)
        if run is None:
            return {"ok": False, "error": "run 不存在"}

        # 先把要反复用的标量抠出来：rollback 会让 ORM 对象过期，之后不能再碰它们
        wf_id = int(run.workflow_id)
        site_id = int(run.site_id)
        user_id = run.created_by
        run_input = dict(run.input or {})
        prev_vars = dict(run.vars or {})

        wf = await db.get(CmsWorkflow, wf_id)
        if wf is None:
            await _finish(db, run_id, wf_id, "failed", "工作流已被删除")
            return {"ok": False, "error": "工作流已被删除"}

        try:
            order = topo_order(wf.graph)
        except GraphError as exc:
            await _finish(db, run_id, wf_id, "failed", str(exc))
            return {"ok": False, "error": str(exc)}

        run.status = "running"
        run.started_at = started
        run.error = None
        wf.last_run_id = run.id
        wf.last_run_status = "running"
        wf.run_count = int(wf.run_count or 0) + (0 if resume else 1)
        await db.commit()

        outputs: dict[str, Any] = dict(prev_vars)
        scope_base: dict[str, Any] = {"input": run_input, **outputs}

        status = "succeeded"
        halt_reason: str | None = None

        for seq, node in enumerate(order):
            nid = node["id"]
            ntitle = node.get("title") or node["type"]

            # 协作式取消：每一步开始前查一次状态位。
            # 不 task.cancel() 是因为重启之后这个 run 可能是别的 worker 起的，
            # 拿不到句柄；强行杀还可能打断正在写库的那一步。
            cur = await db.get(CmsWorkflowRun, run_id)
            if cur is not None and cur.status == "cancelled":
                status = "cancelled"
                log.info("cms.workflow.cancelled_mid_run", run=run_id, at=nid)
                break

            step = await _upsert_step(db, run_id, node, seq)

            if resume and step.status == "succeeded" and isinstance(step.output, dict):
                outputs[nid] = step.output
                scope_base[nid] = step.output
                continue

            if not ws.has_step(node["type"]):
                msg = f"未知步骤类型：{node['type']}"
                await _finish(db, run_id, wf_id, "failed", f"[{ntitle}] {msg}")
                return {"ok": False, "status": "failed", "error": msg}

            node_params = node.get("params") or {}
            params = interpolate(node_params, scope_base)

            # 预检：引用了不存在的变量，直接告诉用户「缺哪个」，别跑到一半才炸
            bad = missing_refs(node_params, scope_base)
            if bad:
                msg = f"引用了上游不存在的变量：{'、'.join(sorted(set(bad)))}"
                step.status = "failed"
                step.error = msg
                step.finished_at = datetime.now(UTC)
                await _finish(db, run_id, wf_id, "failed", f"[{ntitle}] {msg}")
                return {"ok": False, "status": "failed", "error": msg}

            attempts = 1 + (int(node.get("retries") or 0) if ws.is_retryable(node["type"]) else 0)
            attempts = max(1, min(4, attempts))
            t0 = datetime.now(UTC)
            out: dict[str, Any] | None = None

            for attempt in range(1, attempts + 1):
                step.status = "running"
                step.attempts = attempt
                step.started_at = datetime.now(UTC)
                step.input = params if isinstance(params, dict) else {"_raw": params}
                await db.commit()
                try:
                    got = await ws.get_runner(node["type"])(
                        ws.StepCtx(
                            db=db,
                            site_id=site_id,
                            user_id=user_id,
                            params=params if isinstance(params, dict) else {},
                            outputs=outputs,
                        )
                    )
                    out = got if isinstance(got, dict) else {"value": got}
                except asyncio.CancelledError:
                    await db.rollback()
                    await _finish(db, run_id, wf_id, "cancelled", "执行被取消")
                    raise
                except Exception as exc:
                    last_err = f"{type(exc).__name__}: {exc}"[:1000]
                    log.warning(
                        "cms.workflow.step_failed",
                        run=run_id,
                        node=nid,
                        attempt=attempt,
                        error=last_err,
                    )
                    # 先回滚：失败的那条 SQL 已把事务标成 aborted
                    await db.rollback()
                    if attempt < attempts:
                        step = await _upsert_step(db, run_id, node, seq)
                        continue

                    step = await _upsert_step(db, run_id, node, seq)
                    step.status = "failed"
                    step.attempts = attempt
                    step.input = params if isinstance(params, dict) else {}
                    step.error = last_err
                    step.finished_at = datetime.now(UTC)
                    step.duration_ms = int((datetime.now(UTC) - t0).total_seconds() * 1000)
                    await _finish(db, run_id, wf_id, "failed", f"[{ntitle}] {last_err}")
                    return {"ok": False, "status": "failed", "error": last_err}
                else:
                    break

            assert out is not None
            halt = str(out.pop("_halt", "") or "").strip()
            step.status = "succeeded"
            step.output = out
            step.error = None
            step.finished_at = datetime.now(UTC)
            step.duration_ms = int((datetime.now(UTC) - t0).total_seconds() * 1000)
            outputs[nid] = out
            scope_base[nid] = out
            try:
                await db.commit()
            except StaleDataError:
                # 行被别人删了（用户删了工作流，级联删掉了 step 行）：
                # 这不是流水线出错，是并发删除，直接收工
                await db.rollback()
                log.info("cms.workflow.step_vanished", run=run_id, node=nid)
                return {"ok": False, "status": "cancelled", "error": "工作流已被删除"}

            if halt:
                halt_reason = halt
                await _finish(db, run_id, wf_id, "halted", f"[{ntitle}] {halt}")
                status = "halted"
                break

        run = await db.get(CmsWorkflowRun, run_id)
        if run is not None:
            run.vars = outputs
            if run.status == "running":
                run.status = status
                run.finished_at = datetime.now(UTC)
                wf2 = await db.get(CmsWorkflow, wf_id)
                if wf2 is not None:
                    wf2.last_run_status = status
            await db.commit()
            final_status = run.status
            final_error = run.error
        else:
            final_status, final_error = status, None

        log.info(
            "cms.workflow.finished",
            run=run_id,
            workflow=wf_id,
            status=final_status,
            halt=halt_reason,
        )
        return {"ok": final_status == "succeeded", "status": final_status, "error": final_error}


# ---------------------------------------------------------------------------
# 定时触发
# ---------------------------------------------------------------------------
_FIELD_RE = re.compile(r"^(\*|\*/\d{1,2}|\d{1,2}(-\d{1,2})?(/\d{1,2})?|\d{1,2}(,\d{1,2})*)$")


def _match_field(expr: str, value: int, lo: int, hi: int) -> bool:
    if expr == "*":
        return True
    for part in expr.split(","):
        if part.startswith("*/"):
            step = int(part[2:] or 1)
            if step > 0 and (value - lo) % step == 0:
                return True
        elif "/" in part:
            rng, step_s = part.split("/", 1)
            step = int(step_s or 1)
            a, _, b = rng.partition("-")
            start = int(a) if a else lo
            end = int(b) if b else hi
            if start <= value <= end and step > 0 and (value - start) % step == 0:
                return True
        elif "-" in part:
            a, _, b = part.partition("-")
            if int(a) <= value <= int(b):
                return True
        elif part.isdigit() and int(part) == value:
            return True
    return False


def cron_valid(expr: str) -> bool:
    fields = (expr or "").split()
    if len(fields) != 5:
        return False
    if any(not _FIELD_RE.match(f) for f in fields):
        return False
    try:
        _match_field(fields[0], 0, 0, 59)
        _match_field(fields[1], 0, 0, 23)
    except (ValueError, ZeroDivisionError):
        return False
    return True


def next_fire(expr: str, after: datetime | None = None) -> datetime | None:
    """下次触发时间。逐分钟向前扫，最多扫 370 天。

    为什么不手写 cron → 下次时间的数学：五段表达式的组合太碎（`*/7` 与
    `1-20/3` 混用、日与星期是「或」关系还是「且」关系各家实现都不一致），
    扫描实现短、能一眼验证对不对，成本只在保存和跑完之后各发生一次。
    """
    if not cron_valid(expr):
        return None
    now = (after or datetime.now(UTC)).replace(second=0, microsecond=0) + timedelta(minutes=1)
    m, h, dom, mon, dow = (expr or "").split()
    for _ in range(370 * 24 * 60):
        if (
            _match_field(m, now.minute, 0, 59)
            and _match_field(h, now.hour, 0, 23)
            and _match_field(dom, now.day, 1, 31)
            and _match_field(mon, now.month, 1, 12)
            and _match_field(dow, (now.weekday() + 1) % 7, 0, 6)
        ):
            return now
        now += timedelta(minutes=1)
    return None


async def fire_due_workflows() -> int:
    """扫描到点的工作流并起 run。返回本次触发数量。"""
    now = datetime.now(UTC)
    fired = 0
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(CmsWorkflow).where(
                    CmsWorkflow.status == "active",
                    CmsWorkflow.trigger_type == "schedule",
                    CmsWorkflow.next_run_at.is_not(None),
                    CmsWorkflow.next_run_at <= now,
                )
            )
        ).scalars().all()
        for wf in rows:
            wf_id = wf.id
            cron = wf.cron or ""
            if await active_run_id(db, wf_id):
                wf.next_run_at = next_fire(cron, now)
                await db.commit()
                continue
            try:
                run = await create_run(db, wf, payload={}, trigger="schedule")
                spawn(run.id)
                fired += 1
            except Exception as exc:
                log.warning("cms.workflow.schedule_failed", workflow=wf_id, error=str(exc))
            wf = await db.get(CmsWorkflow, wf_id)
            if wf is not None:
                wf.next_run_at = next_fire(cron, now)
                await db.commit()
    return fired


async def recover_stale() -> int:
    """卡住的 run 兜底。

    pending（还没开始跑就被重启打断）→ 直接接手继续跑；
    running（跑到一半被打断）→ 标 failed 让用户点「重跑」，**不能**自动重跑：
    落库、发布这类步骤已经产生了副作用，自动重跑会重复建条目、重复发渠道。

    只处理**本进程启动之前**创建的 run。少了这个条件，第一次 tick 会把本进程
    刚起的 run 误判成「上次遗留」，正在跑的被标失败、pending 的被执行两遍。
    """
    async with AsyncSessionLocal() as db:
        pending_ids = (
            await db.execute(
                select(CmsWorkflowRun.id).where(
                    CmsWorkflowRun.status == "pending",
                    CmsWorkflowRun.started_at.is_(None),
                    CmsWorkflowRun.created_at < _PROC_START,
                )
            )
        ).scalars().all()
        for rid in pending_ids:
            spawn(rid, resume=True)

        res = await db.execute(
            update(CmsWorkflowRun)
            .where(
                CmsWorkflowRun.status == "running",
                CmsWorkflowRun.started_at.is_not(None),
                CmsWorkflowRun.started_at < _PROC_START,
            )
            .values(status="failed", error="服务重启导致执行中断，请点重跑")
        )
        await db.commit()
        return len(pending_ids) + int(res.rowcount or 0)


async def fire_schedules() -> None:
    """调度器钩子的入口，异常自己吞掉，不影响核心定时任务。"""
    try:
        n = await fire_due_workflows()
        if n:
            log.info("cms.workflow.fired", count=n)
    except Exception as exc:
        log.warning("cms.workflow.fire_failed", error=str(exc))


# ---------------------------------------------------------------------------
# 调度器挂载
# ---------------------------------------------------------------------------
from cenkor_admin.core.hooks import hook

_RECOVERED = False


@hook("scheduler.tick")
async def _hook_workflow_tick() -> None:
    """第一跳做一次遗留恢复，之后每跳只看定时工作流。

    恢复只做一次：recover_stale() 会把「running 但属于上次进程」的 run 标失败，
    每 30 秒跑一次等于给长任务判死刑。
    """
    global _RECOVERED
    if not _RECOVERED:
        _RECOVERED = True
        try:
            n = await recover_stale()
            if n:
                log.info("cms.workflow.recovered", count=n)
        except Exception as exc:
            log.warning("cms.workflow.recover_failed", error=str(exc))
    await fire_schedules()
