<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
/**
 * Agent 工作流编排 · 拖拽画布。
 *
 * 定位：**把已有的 AI 能力串成一条可复用、可定时跑的流水线**，不是通用
 * 流程编排器（审批流那套已经在系统里了，别再造一个）。
 *
 * 四个刻意的设计：
 *   1. 画布自己画，不用第三方图编辑器。
 *      需求就「拖节点 + 连线 + 改参数」，引一个图库要适配它的数据模型，
 *      还得把后端的图结构反向映射一遍，最后两头都得迁就它。
 *   2. 参数里写 `{{n1.topic}}` 引用上游产出，**不给变量面板做映射 UI**。
 *      画布上直接显示可引用的变量名，点一下就填进去：能看懂「这个节点
 *      吃的是上一个节点的什么」比「拖一根线做字段映射」更直观。
 *   3. 运行和保存彻底分开。跑一次要调 4~5 次模型，按「保存」就烧钱是不可接受的。
 *   4. 执行详情按节点列出「输入 / 输出 / 耗时 / 报错」。流水线出问题时，
 *      唯一的定位手段就是这一步到底拿到了什么。
 */
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { api } from '@/lib/api'

interface FieldSpec {
  key: string
  label: string
  kind: string
  required: boolean
  default: any
  help: string
  choices: { value: string; label: string }[]
}

interface StepSpec {
  key: string
  title: string
  group: string
  desc: string
  retryable: boolean
  inputs: FieldSpec[]
  outputs: string[]
}

interface WfNode {
  id: string
  type: string
  title: string
  x: number
  y: number
  params: Record<string, any>
  retries?: number
}

interface WfEdge {
  from: string
  to: string
}

interface WfInput {
  key: string
  label: string
  required: boolean
  help: string
  default?: any
}

interface Graph {
  nodes: WfNode[]
  edges: WfEdge[]
  inputs: WfInput[]
}

interface FlowRow {
  id: number
  name: string
  description: string
  status: string
  trigger_type: string
  cron: string
  next_run_at: string | null
  last_run_id: number | null
  last_run_status: string | null
  run_count: number
  node_count?: number
}

interface RunRow {
  id: number
  status: string
  trigger: string
  input: Record<string, any>
  error: string
  created_at: string
  finished_at: string | null
  duration_ms: number | null
}

interface StepLog {
  node_id: string
  node_type: string
  seq: number
  title: string
  status: string
  input: Record<string, any>
  output: Record<string, any>
  error: string
  attempts: number
  duration_ms: number
}

const NODE_W = 176
const NODE_H = 74

const specs = ref<StepSpec[]>([])
const specMap = computed(() => {
  const m: Record<string, StepSpec> = {}
  specs.value.forEach((s) => (m[s.key] = s))
  return m
})
const groups = computed(() => {
  const g: Record<string, StepSpec[]> = {}
  specs.value.forEach((s) => {
    ;(g[s.group] = g[s.group] || []).push(s)
  })
  return g
})

const flows = ref<FlowRow[]>([])
const currentId = ref<number | null>(null)
const flowName = ref('')
const flowDesc = ref('')
const triggerType = ref<'manual' | 'schedule'>('manual')
const cron = ref('')
const graph = ref<Graph>({ nodes: [], edges: [], inputs: [] })

const selectedId = ref<string | null>(null)
const dirty = ref(false)
const loading = ref(false)
const saving = ref(false)
const errorMsg = ref('')
const okMsg = ref('')

const rightTab = ref<'params' | 'runs'>('params')
const runs = ref<RunRow[]>([])
const runDetail = ref<{ run: RunRow; steps: StepLog[] } | null>(null)
const polling = ref(false)

const showRun = ref(false)
const runInputs = ref<Record<string, any>>({})
const running = ref(false)

const showVars = ref(false)
const varTarget = ref<string>('')

const canvasRef = ref<HTMLElement | null>(null)
const linking = ref<string | null>(null)
const mouse = ref({ x: 0, y: 0 })
const dragging = ref<{ id: string; dx: number; dy: number } | null>(null)

const selected = computed(() => graph.value.nodes.find((n) => n.id === selectedId.value) || null)
const selectedSpec = computed(() => (selected.value ? specMap.value[selected.value.type] : null))

const canvasSize = computed(() => {
  const maxX = Math.max(900, ...graph.value.nodes.map((n) => (n.x || 0) + NODE_W + 120))
  const maxY = Math.max(520, ...graph.value.nodes.map((n) => (n.y || 0) + NODE_H + 120))
  return { w: maxX, h: maxY }
})

const edgePaths = computed(() =>
  graph.value.edges
    .map((e) => {
      const a = graph.value.nodes.find((n) => n.id === e.from)
      const b = graph.value.nodes.find((n) => n.id === e.to)
      if (!a || !b) return null
      const x1 = (a.x || 0) + NODE_W
      const y1 = (a.y || 0) + NODE_H / 2
      const x2 = b.x || 0
      const y2 = (b.y || 0) + NODE_H / 2
      const dx = Math.max(40, Math.abs(x2 - x1) / 2)
      return { id: `${e.from}->${e.to}`, d: `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}` }
    })
    .filter(Boolean) as { id: string; d: string }[],
)

/** 当前节点能引用的变量：工作流输入 + 其它节点的产出。 */
const availableVars = computed(() => {
  const out: { label: string; value: string }[] = []
  graph.value.inputs.forEach((i) => out.push({ label: `输入 · ${i.label}`, value: `{{input.${i.key}}}` }))
  graph.value.nodes.forEach((n) => {
    if (n.id === selectedId.value) return
    const sp = specMap.value[n.type]
    const outs = sp?.outputs || []
    outs.forEach((o) => {
      out.push({ label: `${n.title || n.id} · ${o}`, value: `{{${n.id}.${o}}}` })
    })
  })
  return out
})

function fmtTime(s?: string | null) {
  if (!s) return '—'
  const d = new Date(s)
  return isNaN(d.getTime()) ? '—' : d.toLocaleString('zh-CN', { hour12: false })
}

function toast(msg: string, isErr = false) {
  if (isErr) errorMsg.value = msg
  else okMsg.value = msg
}

async function loadSpecs() {
  const { data } = await api.get('/api/v1/cms/ai/workflow/steps')
  specs.value = data.items || []
}

async function loadFlows() {
  const { data } = await api.get('/api/v1/cms/ai/workflow/flows')
  flows.value = data.items || []
}

async function openFlow(id: number) {
  loading.value = true
  try {
    const { data } = await api.get(`/api/v1/cms/ai/workflow/flows/${id}`)
    const it = data.item || {}
    currentId.value = id
    flowName.value = it.name || ''
    flowDesc.value = it.description || ''
    triggerType.value = it.trigger_type === 'schedule' ? 'schedule' : 'manual'
    cron.value = it.cron || ''
    const g = it.graph || {}
    graph.value = {
      nodes: (g.nodes || []).map((n: any) => ({ ...n, x: n.x || 60, y: n.y || 60 })),
      edges: g.edges || [],
      inputs: g.inputs || [],
    }
    selectedId.value = graph.value.nodes[0]?.id || null
    dirty.value = false
    await loadRuns()
  } catch (e: any) {
    toast(e?.response?.data?.detail || t("workflowStudio.打开失败_cst6g1"), true)
  } finally {
    loading.value = false
  }
}

async function createFlow(template?: string) {
  try {
    const { data } = await api.post('/api/v1/cms/ai/workflow/flows', {
      name: template ? 'AI 内容生产链' : '新建工作流',
      template: template || undefined,
      graph: template ? undefined : { nodes: [], edges: [], inputs: [] },
    })
    await loadFlows()
    await openFlow(data.item.id)
    toast(template ? '已按模板铺好整条内容生产链' : '已创建，右侧可以拖步骤进来')
  } catch (e: any) {
    toast(e?.response?.data?.detail || t("workflowStudio.创建失败_ar5wgj"), true)
  }
}

async function saveFlow() {
  if (!currentId.value) return
  saving.value = true
  try {
    await api.put(`/api/v1/cms/ai/workflow/flows/${currentId.value}`, {
      name: flowName.value,
      description: flowDesc.value,
      trigger_type: triggerType.value,
      cron: cron.value,
      graph: graph.value,
    })
    dirty.value = false
    await loadFlows()
    toast('已保存')
  } catch (e: any) {
    toast(e?.response?.data?.detail || t("aiMemory.saveFailed"), true)
  } finally {
    saving.value = false
  }
}

async function validateFlow() {
  try {
    const { data } = await api.post('/api/v1/cms/ai/workflow/validate', { graph: graph.value })
    if (data.ok) toast(`校验通过，执行顺序：${(data.order || []).join(' → ')}`)
    else toast(`发现 ${data.problems.length} 个问题：${data.problems.join('；')}`, true)
  } catch (e: any) {
    toast(e?.response?.data?.detail || t("workflowStudio.校验失败_drw0kf"), true)
  }
}

async function deleteFlow(id: number) {
  if (!window.confirm(t("workflowStudio.删除这个_1opxl5"))) return
  try {
    await api.delete(`/api/v1/cms/ai/workflow/flows/${id}`)
    if (currentId.value === id) {
      currentId.value = null
      graph.value = { nodes: [], edges: [], inputs: [] }
    }
    await loadFlows()
    toast('已删除')
  } catch (e: any) {
    toast(e?.response?.data?.detail || t("aiMemory.删除失败_azdahk"), true)
  }
}

// ---------------- 画布交互 ----------------
function addNode(spec: StepSpec) {
  const id = 'n' + Date.now().toString(36) + Math.floor(Math.random() * 90 + 10)
  const params: Record<string, any> = {}
  spec.inputs.forEach((f) => {
    if (f.default !== null && f.default !== undefined) params[f.key] = f.default
  })
  const count = graph.value.nodes.length
  graph.value.nodes.push({
    id,
    type: spec.key,
    title: spec.title,
    x: 60 + (count % 4) * 240,
    y: 60 + Math.floor(count / 4) * 130,
    params,
    retries: 1,
  })
  selectedId.value = id
  dirty.value = true
  rightTab.value = 'params'
}

function removeNode(id: string) {
  graph.value.nodes = graph.value.nodes.filter((n) => n.id !== id)
  graph.value.edges = graph.value.edges.filter((e) => e.from !== id && e.to !== id)
  if (selectedId.value === id) selectedId.value = null
  dirty.value = true
}

function onNodeMouseDown(n: WfNode, ev: MouseEvent) {
  ev.preventDefault()
  const rect = canvasRef.value!.getBoundingClientRect()
  dragging.value = {
    id: n.id,
    dx: ev.clientX - rect.left - (n.x || 0),
    dy: ev.clientY - rect.top - (n.y || 0),
  }
}

function startLink(n: WfNode, ev: MouseEvent) {
  ev.preventDefault()
  ev.stopPropagation()
  linking.value = n.id
  const rect = canvasRef.value!.getBoundingClientRect()
  mouse.value = { x: ev.clientX - rect.left, y: ev.clientY - rect.top }
}

function onMove(ev: MouseEvent) {
  const rect = canvasRef.value!.getBoundingClientRect()
  if (dragging.value) {
    const n = graph.value.nodes.find((x) => x.id === dragging.value!.id)
    if (n) {
      n.x = Math.max(0, Math.round(ev.clientX - rect.left - dragging.value.dx))
      n.y = Math.max(0, Math.round(ev.clientY - rect.top - dragging.value.dy))
      dirty.value = true
    }
  } else if (linking.value) {
    mouse.value = { x: ev.clientX - rect.left, y: ev.clientY - rect.top }
  }
}

function onUp(ev: MouseEvent) {
  if (linking.value) {
    const target = (ev.target as HTMLElement)?.closest('[data-node-id]') as HTMLElement | null
    const to = target?.getAttribute('data-node-id')
    if (to && to !== linking.value) {
      const exists = graph.value.edges.some((e) => e.from === linking.value && e.to === to)
      if (!exists) {
        graph.value.edges.push({ from: linking.value, to })
        dirty.value = true
      }
    }
    linking.value = null
  }
  dragging.value = null
}

function removeEdge(from: string, to: string) {
  graph.value.edges = graph.value.edges.filter((e) => !(e.from === from && e.to === to))
  dirty.value = true
}

/** 按拓扑层级自动排布：手摆位置容易重叠，自动排一遍省事。 */
function autoLayout() {
  const nodes = graph.value.nodes
  const depth: Record<string, number> = {}
  const visit = (id: string, seen: Set<string>): number => {
    if (depth[id] !== undefined) return depth[id]
    if (seen.has(id)) return 0
    seen.add(id)
    const incoming = graph.value.edges.filter((e) => e.to === id).map((e) => e.from)
    const d = incoming.length ? Math.max(...incoming.map((p) => visit(p, seen) + 1)) : 0
    depth[id] = d
    return d
  }
  nodes.forEach((n) => visit(n.id, new Set()))
  const byDepth: Record<number, WfNode[]> = {}
  nodes.forEach((n) => {
    const d = depth[n.id] || 0
    ;(byDepth[d] = byDepth[d] || []).push(n)
  })
  Object.keys(byDepth).forEach((d) => {
    byDepth[Number(d)].forEach((n: WfNode, i: number) => {
      n.x = 60 + Number(d) * 210
      n.y = 60 + i * 120
    })
  })
  dirty.value = true
  toast('已按执行顺序排好')
}

function insertVar(v: string) {
  const key = varTarget.value
  if (!key) {
    toast(t("workflowStudio.先在下面_1xew0v"), true)
    return
  }
  const n = selected.value
  if (!n) return
  const cur = String(n.params[key] ?? '')
  n.params[key] = cur ? `${cur} ${v}` : v
  dirty.value = true
  showVars.value = false
}

// ---------------- 运行 ----------------
function openRun() {
  const init: Record<string, any> = {}
  graph.value.inputs.forEach((i) => (init[i.key] = i.default ?? ''))
  runInputs.value = init
  showRun.value = true
}

async function triggerRun() {
  if (!currentId.value) return
  running.value = true
  try {
    const { data } = await api.post(`/api/v1/cms/ai/workflow/flows/${currentId.value}/run`, {
      input: runInputs.value,
    })
    showRun.value = false
    rightTab.value = 'runs'
    toast(`已触发，执行 #${data.run_id} 开始跑`)
    pollRun(data.run_id)
  } catch (e: any) {
    toast(e?.response?.data?.detail || t("workflowStudio.触发失败_hqv3lr"), true)
  } finally {
    running.value = false
  }
}

async function pollRun(runId: number) {
  if (polling.value) return
  polling.value = true
  try {
    for (let i = 0; i < 150; i++) {
      const { data } = await api.get(`/api/v1/cms/ai/workflow/runs/${runId}`)
      runDetail.value = data
      const st = data?.run?.status
      if (st && st !== 'pending' && st !== 'running') {
        await loadRuns()
        toast(`执行 ${st}${data.run.error ? '：' + data.run.error : ''}`, st !== 'succeeded')
        return
      }
      await new Promise((r) => setTimeout(r, 3000))
    }
  } finally {
    polling.value = false
  }
}

async function loadRuns() {
  if (!currentId.value) return
  try {
    const { data } = await api.get(`/api/v1/cms/ai/workflow/flows/${currentId.value}/runs`)
    runs.value = data.items || []
  } catch {
    runs.value = []
  }
}

async function openRunDetail(id: number) {
  try {
    const { data } = await api.get(`/api/v1/cms/ai/workflow/runs/${id}`)
    runDetail.value = data
  } catch (e: any) {
    toast(e?.response?.data?.detail || t("workflowStudio.读取失败_i0bjbj"), true)
  }
}

async function rerun(id: number) {
  try {
    await api.post(`/api/v1/cms/ai/workflow/runs/${id}/rerun`)
    toast(t("workflowStudio.已重跑_u6bpct"))
    pollRun(id)
  } catch (e: any) {
    toast(e?.response?.data?.detail || t("workflowStudio.重跑失败_iz8o1k"), true)
  }
}

async function cancelRun(id: number) {
  try {
    await api.post(`/api/v1/cms/ai/workflow/runs/${id}/cancel`)
    toast(t("workflowStudio.已取消_e68dg"))
    await loadRuns()
  } catch (e: any) {
    toast(e?.response?.data?.detail || t("workflowStudio.取消失败_b15iiu"), true)
  }
}

const STATUS_STYLE: Record<string, string> = {
  succeeded: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  failed: 'bg-red-50 text-red-700 border-red-200',
  halted: 'bg-amber-50 text-amber-700 border-amber-200',
  running: 'bg-blue-50 text-blue-700 border-blue-200',
  pending: 'bg-ink-50 text-ink-500 border-ink-200',
  cancelled: 'bg-ink-100 text-ink-500 border-ink-200',
}

onMounted(async () => {
  await loadSpecs()
  await loadFlows()
  if (flows.value.length) await openFlow(flows.value[0].id)
})

onUnmounted(() => {
  polling.value = false
})

nextTick(() => {})
</script>

<template>
  <div class="min-h-screen bg-ink-50 flex flex-col">
    <header class="bg-white border-b border-ink-200 flex-none">
      <div class="px-5 h-14 flex items-center gap-3">
        <router-link to="/cms/ai" class="text-sm text-ink-500 hover:text-ink-900">{{ t("contentHealth.text_11m1s0") }}</router-link>
        <span class="font-semibold">{{ t("workflowStudio.text_1fdqo5") }}</span>
        <span class="text-xs text-ink-400">{{ t("workflowStudio.把_q7oyhk") }}</span>
        <div class="ml-auto flex items-center gap-2">
          <select
            class="text-sm rounded-lg border border-ink-200 px-2 py-1.5 max-w-56"
            :value="currentId ?? ''"
            @change="openFlow(Number(($event.target as HTMLSelectElement).value))"
          >
            <option value="">{{ t("workflowStudio.选择工作_sk4h24") }}</option>
            <option v-for="f in flows" :key="f.id" :value="f.id">
              {{ f.name }}（{{ f.node_count ?? 0 }} {{ $t('workflowStudio.步_jo04') }}
            </option>
          </select>
          <button class="px-3 py-1.5 text-sm rounded-lg border border-ink-200 hover:bg-ink-50" @click="createFlow('content_chain')">
            {{ t("workflowStudio.按模板新_19w384") }}
          </button>
          <button class="px-3 py-1.5 text-sm rounded-lg border border-ink-200 hover:bg-ink-50" @click="createFlow()">
            {{ t("workflowStudio.空白新建_fxywgd") }}
          </button>
        </div>
      </div>
    </header>

    <p v-if="errorMsg" class="mx-5 mt-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl px-4 py-2.5 flex-none">
      {{ errorMsg }}
    </p>
    <p v-if="okMsg" class="mx-5 mt-3 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-2.5 flex-none">
      {{ okMsg }}
    </p>

    <div class="flex-1 flex overflow-hidden">
      <!-- 左：步骤面板 -->
      <aside class="w-60 bg-white border-r border-ink-200 overflow-y-auto flex-none">
        <div class="px-4 py-3 border-b border-ink-100">
          <h3 class="text-sm font-semibold">{{ t("workflowStudio.可用步骤_b2surc") }}</h3>
          <p class="text-[11px] text-ink-400 mt-0.5">{{ t("workflowStudio.点一下加_zrgny4") }}</p>
        </div>
        <div v-for="(list, gname) in groups" :key="gname" class="px-3 pt-3">
          <div class="text-[11px] text-ink-400 px-1 mb-1.5">{{ gname }}</div>
          <button
            v-for="s in list"
            :key="s.key"
            class="w-full text-left px-2.5 py-2 mb-1.5 rounded-lg border border-ink-200 hover:border-ink-400 hover:bg-ink-50 transition"
            @click="addNode(s)"
          >
            <div class="text-sm font-medium">{{ s.title }}</div>
            <div class="text-[11px] text-ink-400 line-clamp-2 mt-0.5">{{ s.desc }}</div>
          </button>
        </div>

        <div v-if="currentId" class="px-3 py-4 border-t border-ink-100 mt-3">
          <h3 class="text-sm font-semibold mb-2">{{ t("workflowStudio.运行输入_ipnh66") }}</h3>
          <div v-for="i in graph.inputs" :key="i.key" class="mb-2">
            <div class="text-[11px] text-ink-500">{{ i.label }}<span v-if="i.required" class="text-red-500">*</span></div>
            <div class="text-[11px] text-ink-400 truncate">{{ i.key }}</div>
          </div>
          <p v-if="!graph.inputs.length" class="text-[11px] text-ink-400">{{ t("workflowStudio.没有输入_1wjwdz") }}</p>
        </div>
      </aside>

      <!-- 中：画布 -->
      <main class="flex-1 overflow-auto relative">
        <div v-if="!currentId" class="h-full flex items-center justify-center text-ink-400 text-sm">
          {{ t("workflowStudio.左侧选一_um8ewm") }}
        </div>
        <div v-else class="p-5">
          <div class="bg-white border border-ink-200 rounded-xl mb-4 p-3">
            <div class="flex items-center gap-3 flex-wrap">
              <input v-model="flowName" class="text-sm rounded-lg border border-ink-200 px-3 py-1.5 w-56" :placeholder="t('workflowStudio.工作流名_mfpogd')" />
              <input v-model="flowDesc" class="text-sm rounded-lg border border-ink-200 px-3 py-1.5 w-72" :placeholder="t('workflowStudio.一句话说_nopzgo')" />
              <select v-model="triggerType" class="text-sm rounded-lg border border-ink-200 px-2 py-1.5">
                <option value="manual">{{ t("workflowStudio.手动触发_cr2yaw") }}</option>
                <option value="schedule">{{ t("workflowStudio.定时触发_bziybr") }}</option>
              </select>
              <input
                v-if="triggerType === 'schedule'"
                v-model="cron"
                class="text-sm rounded-lg border border-ink-200 px-3 py-1.5 w-44"
                :placeholder="t('workflowStudio.text_f3ja35')"
              />
              <button class="px-3 py-1.5 text-sm rounded-lg border border-ink-200 hover:bg-ink-50" @click="autoLayout">{{ t("workflowStudio.自动排列_gqha2r") }}</button>
              <button class="px-3 py-1.5 text-sm rounded-lg border border-ink-200 hover:bg-ink-50" @click="validateFlow">{{ t("workflowStudio.校验_ik5n") }}</button>
              <button class="px-3 py-1.5 text-sm rounded-lg border border-ink-200 hover:bg-ink-50" :disabled="saving" @click="saveFlow">
                {{ saving ? $t('workflowStudio.保存中_agdrec') : dirty ? $t('workflowStudio.保存_c4nlb') : $t('workflowStudio.已保存_e5ggd') }}
              </button>
              <button class="btn-primary" @click="openRun">{{ t("workflowStudio.运行_p7jw") }}</button>
              <button class="ml-auto px-3 py-1.5 text-sm rounded-lg border border-red-200 text-red-600 hover:bg-red-50" @click="deleteFlow(currentId)">
                {{ t("workflowStudio.delete") }}
              </button>
            </div>
          </div>

          <div
            ref="canvasRef"
            class="relative bg-white border border-ink-200 rounded-xl overflow-hidden"
            :style="{ height: canvasSize.h + 'px', minHeight: '520px' }"
            @mousemove="onMove"
            @mouseup="onUp"
            @mouseleave="onUp"
          >
            <svg class="absolute inset-0 pointer-events-none" :width="canvasSize.w" :height="canvasSize.h">
              <path
                v-for="p in edgePaths"
                :key="p.id"
                :d="p.d"
                fill="none"
                stroke="#c7d2fe"
                stroke-width="2"
              />
              <path
                v-if="linking"
                :d="`M ${(graph.nodes.find(n => n.id === linking)?.x || 0) + NODE_W} ${(graph.nodes.find(n => n.id === linking)?.y || 0) + NODE_H / 2} L ${mouse.x} ${mouse.y}`"
                fill="none"
                stroke="#6366f1"
                stroke-dasharray="4 4"
                stroke-width="2"
              />
            </svg>

            <div
              v-for="n in graph.nodes"
              :key="n.id"
              :data-node-id="n.id"
              class="absolute bg-white border rounded-xl shadow-sm select-none"
              :class="selectedId === n.id ? 'border-indigo-500 ring-2 ring-indigo-100' : 'border-ink-200'"
              :style="{ left: n.x + 'px', top: n.y + 'px', width: NODE_W + 'px' }"
              @mousedown="onNodeMouseDown(n, $event)"
              @click="selectedId = n.id; rightTab = 'params'"
            >
              <div class="px-3 py-2 border-b border-ink-100 flex items-center gap-2 cursor-move">
                <span class="text-[11px] px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-600">
                  {{ specMap[n.type]?.group }}
                </span>
                <span class="text-sm font-medium truncate">{{ n.title || specMap[n.type]?.title }}</span>
              </div>
              <div class="px-3 py-1.5 flex items-center gap-2">
                <span class="text-[11px] text-ink-400 truncate flex-1">{{ n.type }}</span>
                <span
                  class="w-2.5 h-2.5 rounded-full bg-ink-300 hover:bg-indigo-500 cursor-crosshair flex-none"
                  :title="t('workflowStudio.拖到另一_2m73j')"
                  @mousedown="startLink(n, $event)"
                />
              </div>
              <span
                class="absolute -left-1.5 top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-white border-2 border-ink-300"
              />
            </div>

            <div v-if="!graph.nodes.length" class="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div class="text-center text-ink-400 text-sm">
                <p>{{ t("workflowStudio.从左侧点_1kidif") }}</p>
                <p class="text-xs mt-1">{{ t("workflowStudio.节点的圆_1ku065") }}</p>
              </div>
            </div>
          </div>

          <!-- 连线列表（画布上不好点中，给一份可点的） -->
          <div v-if="graph.edges.length" class="mt-3 bg-white border border-ink-200 rounded-xl p-3">
            <div class="text-xs text-ink-500 mb-2">{{ $t('workflowStudio.连线_lpkef') }}{{ graph.edges.length }}）</div>
            <div class="flex flex-wrap gap-2">
              <span
                v-for="e in graph.edges"
                :key="e.from + e.to"
                class="text-[11px] px-2 py-1 rounded-lg border border-ink-200 flex items-center gap-1"
              >
                {{ graph.nodes.find(n => n.id === e.from)?.title || e.from }}
                <span class="text-ink-400">→</span>
                {{ graph.nodes.find(n => n.id === e.to)?.title || e.to }}
                <button class="text-red-500 hover:text-red-700" @click="removeEdge(e.from, e.to)">×</button>
              </span>
            </div>
          </div>
        </div>
      </main>

      <!-- 右：参数 / 执行记录 -->
      <aside class="w-80 bg-white border-l border-ink-200 overflow-y-auto flex-none">
        <div class="flex border-b border-ink-200 sticky top-0 bg-white">
          <button
            class="flex-1 px-3 py-2.5 text-sm border-b-2"
            :class="rightTab === 'params' ? 'border-indigo-500 text-ink-900 font-medium' : 'border-transparent text-ink-400'"
            @click="rightTab = 'params'"
          >
            {{ t("workflowStudio.参数_esxa") }}
          </button>
          <button
            class="flex-1 px-3 py-2.5 text-sm border-b-2"
            :class="rightTab === 'runs' ? 'border-indigo-500 text-ink-900 font-medium' : 'border-transparent text-ink-400'"
            @click="rightTab = 'runs'"
          >
            {{ t("workflowStudio.执行记录_czg1m2") }}
          </button>
        </div>

        <div v-if="rightTab === 'params'" class="p-4">
          <div v-if="!selected" class="text-sm text-ink-400">{{ t("workflowStudio.在画布上_1vjzx7") }}</div>
          <div v-else>
            <div class="flex items-center gap-2 mb-1">
              <span class="text-sm font-semibold">{{ selected.title || selectedSpec?.title }}</span>
              <span class="text-[11px] text-ink-400">{{ selected.type }}</span>
            </div>
            <p class="text-[11px] text-ink-400 mb-3">{{ selectedSpec?.desc }}</p>

            <div class="mb-3">
              <label class="text-[11px] text-ink-500">{{ t("workflowStudio.节点标题_gxm0q0") }}</label>
              <input
                v-model="selected.title"
                class="w-full text-sm rounded-lg border border-ink-200 px-2.5 py-1.5 mt-1"
                @input="dirty = true"
              />
            </div>

            <div v-for="f in selectedSpec?.inputs || []" :key="f.key" class="mb-3">
              <label class="text-[11px] text-ink-500 flex items-center gap-1">
                {{ f.label }}
                <span v-if="f.required" class="text-red-500">*</span>
                <button
                  class="ml-auto text-[11px] text-indigo-500 hover:text-indigo-700"
                  @click="varTarget = f.key; showVars = !showVars"
                >
                  {{ t("workflowStudio.引用变量_chb5d6") }}
                </button>
              </label>
              <textarea
                v-if="f.kind === 'textarea'"
                v-model="selected.params[f.key]"
                rows="3"
                class="w-full text-sm rounded-lg border border-ink-200 px-2.5 py-1.5 mt-1 focus:outline-none focus:ring-2 focus:ring-ink-300"
                :placeholder="f.help"
                @input="dirty = true"
              />
              <input
                v-else-if="f.kind === 'number'"
                type="number"
                v-model.number="selected.params[f.key]"
                class="w-full text-sm rounded-lg border border-ink-200 px-2.5 py-1.5 mt-1"
                @input="dirty = true"
              />
              <label v-else-if="f.kind === 'bool'" class="flex items-center gap-2 mt-1">
                <input v-model="selected.params[f.key]" type="checkbox" @change="dirty = true" />
                <span class="text-[11px] text-ink-500">{{ f.help || $t('workflowStudio.开启_gmcv') }}</span>
              </label>
              <select
                v-else-if="f.kind === 'select'"
                v-model="selected.params[f.key]"
                class="w-full text-sm rounded-lg border border-ink-200 px-2 py-1.5 mt-1"
                @change="dirty = true"
              >
                <option v-for="c in f.choices" :key="c.value" :value="c.value">{{ c.label }}</option>
              </select>
              <input
                v-else
                v-model="selected.params[f.key]"
                class="w-full text-sm rounded-lg border border-ink-200 px-2.5 py-1.5 mt-1"
                :placeholder="f.help"
                @input="dirty = true"
              />
              <p v-if="f.help && f.kind !== 'bool'" class="text-[11px] text-ink-400 mt-1">{{ f.help }}</p>
            </div>

            <div v-if="showVars" class="mb-3 rounded-lg border border-indigo-200 bg-indigo-50 p-2">
              <div class="text-[11px] text-indigo-700 mb-1.5">
                {{ $t('workflowStudio.点一下填_1k6cym') }}{{ varTarget || $t('workflowStudio.text_1tx4sc') }}」
              </div>
              <div class="max-h-40 overflow-y-auto flex flex-wrap gap-1">
                <button
                  v-for="v in availableVars"
                  :key="v.value"
                  class="text-[11px] px-1.5 py-0.5 rounded border border-indigo-200 bg-white hover:bg-indigo-100"
                  @click="insertVar(v.value)"
                >
                  {{ v.label }}
                </button>
              </div>
            </div>

            <div class="mb-3">
              <label class="text-[11px] text-ink-500">{{ t("workflowStudio.失败重试_gq6u5n") }}</label>
              <input
                v-model.number="selected.retries"
                type="number"
                min="0"
                max="3"
                class="w-full text-sm rounded-lg border border-ink-200 px-2.5 py-1.5 mt-1"
                @input="dirty = true"
              />
              <p v-if="selectedSpec && !selectedSpec.retryable" class="text-[11px] text-amber-600 mt-1">
                {{ t("workflowStudio.这步有副_c9m2co") }}
              </p>
            </div>

            <button
              class="px-3 py-1.5 text-sm rounded-lg border border-red-200 text-red-600 hover:bg-red-50"
              @click="removeNode(selected.id)"
            >
              {{ t("workflowStudio.删除节点_azk5vf") }}
            </button>
          </div>
        </div>

        <div v-else class="p-4">
          <div v-if="!runs.length" class="text-sm text-ink-400">{{ t("workflowStudio.还没有执_wsy7pm") }}</div>
          <div v-for="r in runs" :key="r.id" class="mb-2 border border-ink-200 rounded-lg p-2.5">
            <div class="flex items-center gap-2">
              <span class="text-xs px-1.5 py-0.5 rounded border" :class="STATUS_STYLE[r.status] || STATUS_STYLE.pending">
                {{ r.status }}
              </span>
              <span class="text-xs text-ink-400">#{{ r.id }}</span>
              <span class="text-[11px] text-ink-400 ml-auto">{{ fmtTime(r.created_at) }}</span>
            </div>
            <div class="text-[11px] text-ink-500 mt-1 line-clamp-2">
              {{ r.error || JSON.stringify(r.input).slice(0, 80) }}
            </div>
            <div class="flex gap-2 mt-2">
              <button class="text-[11px] text-indigo-600 hover:underline" @click="openRunDetail(r.id)">{{ t("workflowStudio.detail") }}</button>
              <button class="text-[11px] text-ink-500 hover:underline" @click="rerun(r.id)">{{ t("workflowStudio.重跑_pktg") }}</button>
              <button
                v-if="r.status === 'running' || r.status === 'pending'"
                class="text-[11px] text-ink-500 hover:underline"
                @click="cancelRun(r.id)"
              >
                {{ t("workflowStudio.cancel") }}
              </button>
            </div>
          </div>

          <div v-if="runDetail" class="mt-4 border-t border-ink-200 pt-3">
            <div class="text-xs font-semibold mb-2">{{ $t('workflowStudio.执行_cyrs7c') }}{{ runDetail.run.id }} {{ $t('workflowStudio.节点明细_gxljjj') }}</div>
            <div v-for="s in runDetail.steps" :key="s.node_id" class="mb-2 border border-ink-200 rounded-lg p-2">
              <div class="flex items-center gap-2">
                <span class="text-xs px-1.5 py-0.5 rounded border" :class="STATUS_STYLE[s.status] || STATUS_STYLE.pending">
                  {{ s.status }}
                </span>
                <span class="text-xs font-medium truncate">{{ s.title }}</span>
                <span class="text-[11px] text-ink-400 ml-auto">{{ s.duration_ms }}ms</span>
              </div>
              <p v-if="s.error" class="text-[11px] text-red-600 mt-1 break-all">{{ s.error }}</p>
              <details v-else-if="Object.keys(s.output || {}).length" class="mt-1">
                <summary class="text-[11px] text-ink-400 cursor-pointer">{{ t("workflowStudio.看输出_i4kya") }}</summary>
                <pre class="text-[10px] bg-ink-50 rounded p-2 mt-1 overflow-x-auto whitespace-pre-wrap break-all">{{
                  JSON.stringify(s.output, null, 1).slice(0, 1200)
                }}</pre>
              </details>
            </div>
          </div>
        </div>
      </aside>
    </div>

    <!-- 运行弹窗 -->
    <div v-if="showRun" class="fixed inset-0 bg-black/30 flex items-center justify-center z-50" @click.self="showRun = false">
      <div class="bg-white rounded-2xl shadow-xl w-[520px] max-w-[92vw] p-6">
        <h3 class="font-semibold mb-1">{{ t("workflowStudio.运行这条_jlqijs") }}</h3>
        <p class="text-xs text-ink-400 mb-4">
          {{ t("workflowStudio.一条完整_kd76r6") }}
        </p>
        <div v-for="i in graph.inputs" :key="i.key" class="mb-3">
          <label class="text-[11px] text-ink-500">{{ i.label }}<span v-if="i.required" class="text-red-500">*</span></label>
          <input
            v-model="runInputs[i.key]"
            class="w-full text-sm rounded-lg border border-ink-200 px-3 py-2 mt-1"
            :placeholder="i.help"
          />
        </div>
        <p v-if="!graph.inputs.length" class="text-sm text-ink-400 mb-4">{{ t("workflowStudio.这条流水_gx5hv") }}</p>
        <div class="flex justify-end gap-2 mt-5">
          <button class="px-4 py-2 text-sm rounded-lg border border-ink-200 hover:bg-ink-50" @click="showRun = false">{{ t("workflowStudio.cancel") }}</button>
          <button class="btn-primary" :disabled="running" @click="triggerRun">
            {{ running ? $t('workflowStudio.触发中_hqsmmc') : $t('workflowStudio.开始运行_cd7lon') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
