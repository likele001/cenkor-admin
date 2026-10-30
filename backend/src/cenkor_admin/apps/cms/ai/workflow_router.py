"""AI 工作流编排 · HTTP 接口

    GET    /workflow/steps                 步骤清单（画布左栏 + 参数定义）
    POST   /workflow/validate              图校验（连线成环、必填参数、未知步骤）
    GET    /workflow/templates             内置模板（一键铺好整条内容生产链）

    GET    /workflow/flows                 工作流列表
    POST   /workflow/flows                 新建
    GET    /workflow/flows/{wf_id}         详情
    PUT    /workflow/flows/{wf_id}         保存定义
    DELETE /workflow/flows/{wf_id}         删除
    POST   /workflow/flows/{wf_id}/run     手动执行

    GET    /workflow/flows/{wf_id}/runs    执行历史
    GET    /workflow/runs/{run_id}          执行详情（含每个节点的输入/输出）
    POST   /workflow/runs/{run_id}/rerun    重跑失败的节点
    POST   /workflow/runs/{run_id}/cancel   取消

为什么「保存」和「执行」分开：画布上改一下就跑会烧模型钱（一条完整链约 3~5
次模型调用）。保存只是写库，用户想跑必须显式点执行，并且输入变量在弹窗里填。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.cms.ai import workflow_engine as eng
from cenkor_admin.apps.cms.ai import workflow_steps as ws
from cenkor_admin.apps.cms.ai.workflow_models import (
    CmsWorkflow,
    CmsWorkflowRun,
    CmsWorkflowStep,
)
from cenkor_admin.core.db import get_db
from cenkor_admin.core.site_scope import current_site_id

router = APIRouter(prefix="/workflow")


def _site() -> int:
    return current_site_id() or 1


# ---------------------------------------------------------------------------
# 内置模板：整条 AI 内容生产链
# ---------------------------------------------------------------------------
def _chain_template() -> dict[str, Any]:
    """选题 → 大纲 → 起草 → 查重 → 质检 → 落库 → SEO → 内链。

    刻意不带「配图」和「发布」：生图要花钱、发布直接对外，这两步由用户自己
    拖上画布再配参数，默认不替人做决定。
    """
    nodes = [
        {"id": "n1", "type": "topic.pick", "title": "选题生成", "x": 60, "y": 80,
         "params": {"direction": "{{input.direction}}", "count": 1, "lang": "zh-CN"}},
        {"id": "n2", "type": "outline.gen", "title": "大纲生成", "x": 270, "y": 80,
         "params": {"topic": "{{n1.topic}}", "sections": 5, "lang": "zh-CN"}},
        {"id": "n3", "type": "draft.write", "title": "起草正文", "x": 480, "y": 80,
         "params": {"outline": "{{n2.outline_text}}",
                    "content_type_key": "{{input.content_type_key}}",
                    "max_tokens": 20000, "lang": "zh-CN"}},
        {"id": "n4", "type": "dup.check", "title": "查重", "x": 690, "y": 80,
         "params": {"title": "{{n3.title}}", "content": "{{n3.draft.content}}",
                    "threshold": 0.8, "abort": True}},
        {"id": "n5", "type": "quality.check", "title": "质量质检", "x": 690, "y": 260,
         "params": {"title": "{{n3.title}}", "content": "{{n3.draft.content}}",
                    "min_score": 75, "abort": False, "lang": "zh-CN"}},
        {"id": "n6", "type": "entry.save", "title": "存为草稿", "x": 480, "y": 260,
         "params": {"draft": "{{n3.draft}}"}},
        {"id": "n7", "type": "seo.suggest", "title": "SEO 元数据", "x": 270, "y": 260,
         "params": {"entry_id": "{{n6.entry_id}}", "apply": True, "lang": "zh-CN"}},
        {"id": "n8", "type": "internal_link", "title": "内链建议", "x": 60, "y": 260,
         "params": {"entry_id": "{{n6.entry_id}}", "max_links": 4}},
    ]
    edges = [
        {"from": "n1", "to": "n2"},
        {"from": "n2", "to": "n3"},
        {"from": "n3", "to": "n4"},
        {"from": "n4", "to": "n5"},
        {"from": "n5", "to": "n6"},
        {"from": "n6", "to": "n7"},
        {"from": "n7", "to": "n8"},
    ]
    inputs = [
        {"key": "direction", "label": "主题方向", "required": True,
         "help": "越具体越好，如「MES 在注塑车间的落地」"},
        {"key": "content_type_key", "label": "内容类型 key", "required": True,
         "help": "目标写入哪个内容类型，如 article / news / case"},
    ]
    return {"nodes": nodes, "edges": edges, "inputs": inputs}


TEMPLATES: list[dict[str, Any]] = [
    {
        "key": "content_chain",
        "name": "AI 内容生产链",
        "desc": "选题 → 大纲 → 起草 → 查重 → 质检 → 落库 → SEO → 内链。输入一个方向就出一条草稿。",
        "input_schema": [
            {"key": "direction", "label": "主题方向", "required": True,
             "help": "越具体越好，如「MES 在注塑车间的落地」"},
            {"key": "content_type_key", "label": "内容类型 key", "required": True,
             "help": "目标写入哪个内容类型，如 news / product / case"},
        ],
        "graph": _chain_template(),
    }
]

# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------
def _wf_dict(wf: CmsWorkflow, *, with_graph: bool = False) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": wf.id,
        "name": wf.name,
        "description": wf.description or "",
        "status": wf.status,
        "trigger_type": wf.trigger_type,
        "cron": wf.cron or "",
        "next_run_at": wf.next_run_at.isoformat() if wf.next_run_at else None,
        "last_run_id": wf.last_run_id,
        "last_run_status": wf.last_run_status,
        "run_count": wf.run_count or 0,
        "updated_at": wf.updated_at.isoformat() if wf.updated_at else None,
    }
    if with_graph:
        d["graph"] = wf.graph or {"nodes": [], "edges": []}
    else:
        g = eng.normalize_graph(wf.graph)
        d["node_count"] = len(g["nodes"])
    return d


def _run_dict(run: CmsWorkflowRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "workflow_id": run.workflow_id,
        "status": run.status,
        "trigger": run.trigger,
        "input": run.input or {},
        "error": run.error or "",
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_ms": (
            int((run.finished_at - run.started_at).total_seconds() * 1000)
            if run.started_at and run.finished_at
            else None
        ),
    }


def _step_dict(s: CmsWorkflowStep) -> dict[str, Any]:
    return {
        "node_id": s.node_id,
        "node_type": s.node_type,
        "seq": s.seq,
        "title": s.title or s.node_type,
        "status": s.status,
        "input": s.input or {},
        "output": s.output or {},
        "error": s.error or "",
        "attempts": s.attempts,
        "duration_ms": s.duration_ms,
    }


async def _get_wf(db: AsyncSession, wf_id: int) -> CmsWorkflow:
    wf = await db.get(CmsWorkflow, wf_id)
    if wf is None or wf.site_id != _site():
        raise HTTPException(404, "工作流不存在")
    return wf


# ---------------------------------------------------------------------------
# 元信息
# ---------------------------------------------------------------------------
@router.get("/steps")
async def list_steps(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    return {"items": ws.all_specs()}


@router.get("/templates")
async def list_templates(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    return {"items": [{k: v for k, v in t.items() if k != "graph"} for t in TEMPLATES],
            "graphs": {t["key"]: t["graph"] for t in TEMPLATES}}


@router.post("/validate")
async def validate(
    graph: dict[str, Any] = Body(..., embed=True),
    _: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """保存前校验。一次把「未知步骤 / 缺必填 / 成环」全列出来，不要一次报一条。"""
    problems: list[str] = []
    try:
        order = eng.topo_order(graph)
    except eng.GraphError as exc:
        return {"ok": False, "problems": [str(exc)], "order": []}

    for node in order:
        label = node.get("title") or node["id"]
        if not ws.has_step(node["type"]):
            problems.append(f"「{label}」的步骤类型不存在：{node['type']}")
            continue
        problems.extend(f"「{label}」{p}" for p in ws.validate_node(node["type"], node["params"]))

    return {"ok": not problems, "problems": problems, "order": [n["id"] for n in order]}


# ---------------------------------------------------------------------------
# 工作流 CRUD
# ---------------------------------------------------------------------------
@router.get("/flows")
async def list_workflows(
    db: AsyncSession = Depends(get_db),
    _: Any = Depends(get_current_user),
) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(CmsWorkflow)
            .where(CmsWorkflow.site_id == _site())
            .order_by(CmsWorkflow.id.desc())
        )
    ).scalars().all()
    return {"items": [_wf_dict(w) for w in rows]}


@router.post("/flows")
async def create_workflow(
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    name = str(body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "请填写工作流名称")

    graph = eng.normalize_graph(body.get("graph") or {"nodes": [], "edges": []})
    if not graph["nodes"]:
        tpl_key = str(body.get("template") or "").strip()
        tpl = next((t for t in TEMPLATES if t["key"] == tpl_key), None)
        if tpl is not None:
            graph = eng.normalize_graph(tpl["graph"])

    trigger_type = str(body.get("trigger_type") or "manual")
    cron = str(body.get("cron") or "").strip()
    if trigger_type == "schedule" and not eng.cron_valid(cron):
        raise HTTPException(400, "定时表达式不合法，需要 5 段（分 时 日 月 周）")

    wf = CmsWorkflow(
        site_id=_site(),
        name=name[:120],
        description=str(body.get("description") or "")[:1000] or None,
        status="draft",
        graph=graph,
        trigger_type=trigger_type,
        cron=cron or None,
        next_run_at=eng.next_fire(cron) if trigger_type == "schedule" else None,
        created_by=getattr(user, "id", None),
    )
    db.add(wf)
    await db.commit()
    await db.refresh(wf)
    return {"item": _wf_dict(wf, with_graph=True)}


@router.get("/flows/{wf_id}")
async def get_workflow(
    wf_id: int,
    db: AsyncSession = Depends(get_db),
    _: Any = Depends(get_current_user),
) -> dict[str, Any]:
    wf = await _get_wf(db, wf_id)
    return {"item": _wf_dict(wf, with_graph=True)}


@router.put("/flows/{wf_id}")
async def update_workflow(
    wf_id: int,
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    _: Any = Depends(get_current_user),
) -> dict[str, Any]:
    wf = await _get_wf(db, wf_id)

    if "name" in body:
        name = str(body.get("name") or "").strip()
        if not name:
            raise HTTPException(400, "请填写工作流名称")
        wf.name = name[:120]
    if "description" in body:
        wf.description = str(body.get("description") or "")[:1000] or None
    if "status" in body:
        st = str(body.get("status") or "").strip()
        if st not in ("draft", "active", "archived"):
            raise HTTPException(400, "状态只能是 draft / active / archived")
        wf.status = st
    if "graph" in body:
        graph = eng.normalize_graph(body.get("graph"))
        # 保存就校验：连线成环的工作流进了库，只在执行时才炸，排查成本高得多
        try:
            eng.topo_order(graph)
        except eng.GraphError as exc:
            raise HTTPException(400, str(exc)) from None
        wf.graph = graph
    if "trigger_type" in body:
        tt = str(body.get("trigger_type") or "manual")
        if tt not in ("manual", "schedule"):
            raise HTTPException(400, "触发方式只能是 manual / schedule")
        wf.trigger_type = tt
    if "cron" in body or "trigger_type" in body:
        cron = str(body.get("cron") if "cron" in body else (wf.cron or "")).strip()
        if wf.trigger_type == "schedule":
            if not eng.cron_valid(cron):
                raise HTTPException(400, "定时表达式不合法，需要 5 段（分 时 日 月 周）")
            wf.next_run_at = eng.next_fire(cron)
        else:
            wf.next_run_at = None
        wf.cron = cron or None

    await db.commit()
    await db.refresh(wf)
    return {"item": _wf_dict(wf, with_graph=True)}


@router.delete("/flows/{wf_id}")
async def delete_workflow(
    wf_id: int,
    db: AsyncSession = Depends(get_db),
    _: Any = Depends(get_current_user),
) -> dict[str, Any]:
    wf = await _get_wf(db, wf_id)
    busy = await eng.active_run_id(db, wf_id)
    if busy:
        raise HTTPException(400, "这个工作流正在执行，等它结束再删")
    await db.delete(wf)
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------
@router.post("/flows/{wf_id}/run")
async def run_workflow(
    wf_id: int,
    body: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    wf = await _get_wf(db, wf_id)
    graph = eng.normalize_graph(wf.graph)
    if not graph["nodes"]:
        raise HTTPException(400, "画布上还没有节点")

    # 执行前把必填参数过一遍：缺了就在点执行时告诉用户，别等后台跑起来才失败
    try:
        order = eng.topo_order(graph)
    except eng.GraphError as exc:
        raise HTTPException(400, str(exc)) from None
    problems: list[str] = []
    for node in order:
        if not ws.has_step(node["type"]):
            problems.append(f"「{node.get('title') or node['id']}」步骤类型不存在")
    if problems:
        raise HTTPException(400, "；".join(problems))

    payload = body.get("input") if isinstance(body.get("input"), dict) else {}

    # 必填输入先查一遍：缺了就当场说「缺哪个」，别让用户等两分钟看引擎报错
    missing = [
        f"{it.get('label') or it.get('key')}"
        for it in (graph.get("inputs") or [])
        if it.get("required") and not str(payload.get(str(it.get("key"))) or "").strip()
    ]
    if missing:
        raise HTTPException(400, f"缺少必填输入：{'、'.join(missing)}")

    try:
        run = await eng.create_run(
            db, wf, payload=payload, trigger="manual", user_id=getattr(user, "id", None)
        )
    except eng.GraphError as exc:
        raise HTTPException(400, str(exc)) from None

    eng.spawn(run.id)
    return {"run_id": run.id, "status": "pending"}


@router.get("/flows/{wf_id}/runs")
async def list_runs(
    wf_id: int,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: Any = Depends(get_current_user),
) -> dict[str, Any]:
    await _get_wf(db, wf_id)
    rows = (
        await db.execute(
            select(CmsWorkflowRun)
            .where(CmsWorkflowRun.workflow_id == wf_id)
            .order_by(CmsWorkflowRun.id.desc())
            .limit(limit)
        )
    ).scalars().all()
    return {"items": [_run_dict(r) for r in rows]}


@router.get("/runs/{run_id}")
async def get_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    _: Any = Depends(get_current_user),
) -> dict[str, Any]:
    run = await db.get(CmsWorkflowRun, run_id)
    if run is None or run.site_id != _site():
        raise HTTPException(404, "执行记录不存在")
    steps = (
        await db.execute(
            select(CmsWorkflowStep)
            .where(CmsWorkflowStep.run_id == run_id)
            .order_by(CmsWorkflowStep.seq)
        )
    ).scalars().all()
    return {"run": _run_dict(run), "steps": [_step_dict(s) for s in steps]}


@router.post("/runs/{run_id}/rerun")
async def rerun(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    _: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """重跑。已成功的节点直接复用输出，不重复烧模型钱。"""
    run = await db.get(CmsWorkflowRun, run_id)
    if run is None or run.site_id != _site():
        raise HTTPException(404, "执行记录不存在")
    if run.status in ("pending", "running"):
        raise HTTPException(400, "这次执行还在跑")

    # 有副作用的步骤成功后不能再跑一遍；把它们的状态保留，靠 resume 跳过
    run.status = "pending"
    run.error = None
    run.finished_at = None
    await db.commit()
    eng.spawn(run.id, resume=True)
    return {"run_id": run.id, "status": "pending"}


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    _: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """取消：把 DB 状态改掉，引擎在下一步之前会读到并停下。

    进程内的 asyncio.Task 拿不到句柄（重启后可能是别的 worker 起的），
    所以不做 task.cancel()，靠状态位协作式停止 —— 至少不会杀掉正在写库的那一步。
    """
    run = await db.get(CmsWorkflowRun, run_id)
    if run is None or run.site_id != _site():
        raise HTTPException(404, "执行记录不存在")
    if run.status not in ("pending", "running"):
        raise HTTPException(400, "这次执行已经结束了")
    run.status = "cancelled"
    run.error = "用户取消"
    run.finished_at = datetime.now(UTC)
    await db.commit()
    logger.info("cms.workflow.cancelled run={}", run_id)
    return {"ok": True}
