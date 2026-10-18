<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from "vue"
import { useAuthStore } from "@/stores/auth"
import { api } from "@/lib/api"

interface RunItem {
  id: number
  source: string
  channel: string
  from_version: string | null
  to_version: string | null
  status: string
  backup_path: string | null
  duration_ms: number | null
  operator_id: number | null
  rollback_from_id: number | null
  notes: string | null
  created_at: string | null
  started_at: string | null
  finished_at: string | null
}

interface RunDetail extends RunItem {
  log: string | null
  error: string | null
}

const auth = useAuthStore()
const status = ref<any>(null)
const confirmText = ref("")
const source = ref<"resource" | "url" | "tar_upload">("resource")
const url = ref("")
const localPath = ref("")
const channel = ref("stable")
const notes = ref("")
const busy = ref<"" | "dry" | "run" | "rollback" | "delete" | "detail" | "loadRes" | "dlRes">("")
const error = ref("")
const ok = ref("")
const runs = ref<RunItem[]>([])
const runsLoading = ref(false)
const runsError = ref("")
const filterStatus = ref("")
const filterSource = ref("")
const detail = ref<RunDetail | null>(null)
const detailOpen = ref(false)
const rollbackConfirmOpen = ref(false)
const rollbackTarget = ref<RunItem | null>(null)
const liveRunId = ref<number | null>(null)
const liveLog = ref("")
let pollTimer: number | null = null

interface ResourceItem {
  version: string
  channel: string
  released_at: string
  pkg_url: string
  size: number
  notes: string
  source: string  // remote | local | local_file
  local_path?: string
  local_size?: number
  installed?: boolean
  downloaded?: boolean
}
const resources = ref<ResourceItem[]>([])
const resourcesInfo = ref<any>(null)
const resourcesError = ref("")
const selectedResource = ref<ResourceItem | null>(null)
const downloadBusy = ref<string | null>(null)  // version being downloaded

const canWrite = computed(() => auth.hasPermission("system:upgrade:write"))
const isSuper = computed(() => !!auth.user?.is_superuser)
const running = computed(() => status.value?.running || !!liveRunId.value)

const CONFIRM = "升级 cenkor-admin"

async function loadStatus() {
  try {
    const { data } = await api.get("/api/v1/system/upgrade/status")
    status.value = data
    if (data?.running_run_id) liveRunId.value = data.running_run_id
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "加载状态失败"
  }
}

async function loadRuns() {
  runsLoading.value = true
  runsError.value = ""
  try {
    const params: any = { limit: 20 }
    if (filterStatus.value) params.status = filterStatus.value
    if (filterSource.value) params.source = filterSource.value
    const { data } = await api.get("/api/v1/system/upgrade/runs", { params })
    runs.value = data.items || []
  } catch (e: any) {
    runsError.value = e?.response?.data?.detail || e?.message || "加载历史失败"
  } finally {
    runsLoading.value = false
  }
}

async function loadResources(forceRefresh = false) {
  busy.value = "loadRes"
  resourcesError.value = ""
  try {
    const { data } = await api.get("/api/v1/system/upgrade/resources", { params: { refresh: forceRefresh } })
    resourcesInfo.value = data
    resources.value = data.items || []
    if (resources.value.length && !selectedResource.value) {
      // 默认选中最新（列表已按 version 倒序）的「非当前」版本
      const next = resources.value.find((r) => !r.installed) || resources.value[0]
      selectResource(next)
    }
  } catch (e: any) {
    resourcesError.value = e?.response?.data?.detail || e?.message || "加载资源库失败"
  } finally {
    busy.value = busy.value === "loadRes" ? "" : busy.value
  }
}

function selectResource(r: ResourceItem) {
  selectedResource.value = r
  // 选中后自动同步到升级表单：
  // 1) 已有本地文件 → 切到本地路径模式
  if (r.local_path) {
    source.value = "tar_upload"
    localPath.value = r.local_path
    url.value = r.pkg_url || ""
  } else if (r.pkg_url) {
    // 2) 没下载但有 URL → 切到 URL 模式
    source.value = "url"
    url.value = r.pkg_url
    localPath.value = ""
  } else {
    // 3) 啥都没有 → URL 模式让用户自己填
    source.value = "url"
    url.value = ""
    localPath.value = ""
  }
  if (r.channel) channel.value = r.channel
}

async function doDownload(r: ResourceItem) {
  if (!isSuper.value) { error.value = "仅超级管理员可下载"; return }
  if (!r.pkg_url) { error.value = "该版本没有 pkg_url"; return }
  if (confirmText.value !== CONFIRM) {
    error.value = `下载资源前需要先输入「${CONFIRM}」确认`
    return
  }
  downloadBusy.value = r.version
  busy.value = "dlRes"
  error.value = ""
  try {
    const { data } = await api.post(
      "/api/v1/system/upgrade/resources/download",
      { version: r.version },
      { timeout: 180_000 },  // 慢源保险 3 分钟
    )
    if (data?.ok) {
      ok.value = "已下载到本地：" + (data.local_path || "")
      await loadResources(true)  // 刷新列表（更新 downloaded 标记）
      const updated = resources.value.find((x) => x.version === r.version)
      if (updated) selectResource(updated)
    } else {
      error.value = "下载失败：" + (data?.error || "未知错误")
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "下载失败"
  } finally {
    downloadBusy.value = null
    busy.value = busy.value === "dlRes" ? "" : busy.value
  }
}

async function doDryRun() {
  if (!isSuper.value) { error.value = "仅超级管理员可执行"; return }
  busy.value = "dry"
  error.value = ""
  ok.value = ""
  try {
    const { data } = await api.post("/api/v1/system/upgrade/dry-run", {
      source: mapSourceForApi(source.value),
      payload: source.value === "url" ? { url: url.value, channel: channel.value } : { local_path: localPath.value, channel: channel.value },
      confirm_text: CONFIRM,
      notes: notes.value || undefined,
    })
    ok.value = "预演完成（仅规划，未动文件/DB）。详见结果。"
    await loadStatus()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "预演失败"
  } finally {
    busy.value = ""
  }
}

function mapSourceForApi(s: "resource" | "url" | "tar_upload"): "url" | "tar_upload" {
  // 「资源库」只是前端选择层；后端只认 url / tar_upload。
  // resource 选中后 selectResource() 会自动切到 url 或 tar_upload；保险起见再 map 一次。
  if (s === "resource") return localPath.value ? "tar_upload" : "url"
  return s
}

async function doRun() {
  if (!isSuper.value) { error.value = "仅超级管理员可执行"; return }
  if (confirmText.value !== CONFIRM) {
    error.value = `确认文本错误（需输入「${CONFIRM}」）`
    return
  }
  if ((source.value === "url" || (source.value === "resource" && !localPath.value)) && !url.value) {
    error.value = "请先选择资源（已下载则用本地路径）或输入核心包 URL"
    return
  }
  if ((source.value === "tar_upload" || (source.value === "resource" && localPath.value)) && !localPath.value) {
    error.value = "请输入核心包本地路径"
    return
  }
  busy.value = "run"
  error.value = ""
  ok.value = ""
  try {
    await api.post("/api/v1/system/upgrade/run", {
      source: mapSourceForApi(source.value),
      payload: (source.value === "url" || (source.value === "resource" && !localPath.value)) ? { url: url.value, channel: channel.value } : { local_path: localPath.value, channel: channel.value },
      confirm_text: CONFIRM,
      notes: notes.value || undefined,
    })
    ok.value = "已启动后台升级，轮询日志查看进度..."
    // 轮询 status 拿 running_run_id
    setTimeout(async () => {
      await loadStatus()
      if (status.value?.running_run_id) {
        liveRunId.value = status.value.running_run_id
        liveLog.value = ""
        startPolling()
      } else {
        // 还没拿到 run_id，继续轮询
        setTimeout(async () => { await loadStatus(); if (status.value?.running_run_id) { liveRunId.value = status.value.running_run_id; startPolling() } }, 1000)
      }
    }, 500)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "启动升级失败"
    busy.value = ""
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = window.setInterval(async (): Promise<void> => {
    if (!liveRunId.value) return
    try {
      const { data } = await api.get(`/api/v1/system/upgrade/runs/${liveRunId.value}/log`)
      liveLog.value = (data.slice || "")
      // 终态：success / failed / rolled_back
      if (data.status && data.status !== "running" && data.status !== "pending") {
        stopPolling()
        busy.value = ""
        await loadStatus()
        await loadRuns()
        if (data.status === "success") ok.value = "✓ 升级成功"
        else if (data.status === "rolled_back") error.value = "✗ 升级失败，已自动回滚"
        else error.value = "✗ 升级失败（详见日志）"
      }
    } catch (e) {
      // ignore
    }
  }, 3000)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

async function openDetail(r: RunItem) {
  detail.value = null
  detailOpen.value = true
  busy.value = "detail"
  try {
    const { data } = await api.get(`/api/v1/system/upgrade/runs/${r.id}`)
    detail.value = data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "加载详情失败"
    detailOpen.value = false
  } finally {
    busy.value = ""
  }
}

function openRollback(r: RunItem) {
  rollbackTarget.value = r
  rollbackConfirmOpen.value = true
  confirmText.value = ""
}

async function doRollback() {
  if (!isSuper.value) { error.value = "仅超级管理员可执行"; return }
  if (confirmText.value !== CONFIRM) {
    error.value = `确认文本错误（需输入「${CONFIRM}」）`
    return
  }
  if (!rollbackTarget.value) return
  busy.value = "rollback"
  error.value = ""
  ok.value = ""
  try {
    await api.post(`/api/v1/system/upgrade/runs/${rollbackTarget.value.id}/rollback`, { confirm_text: CONFIRM })
    ok.value = "已启动手动回滚，轮询 status 查看进度"
    rollbackConfirmOpen.value = false
    setTimeout(async () => {
      await loadStatus()
      if (status.value?.running_run_id) { liveRunId.value = status.value.running_run_id; liveLog.value = ""; startPolling() }
    }, 500)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "启动回滚失败"
    busy.value = ""
  }
}

async function doDelete(r: RunItem) {
  if (!window.confirm(`删除执行记录 #${r.id}？只删留痕，不动已升级的项目。`)) return
  busy.value = "delete"
  error.value = ""
  try {
    await api.delete(`/api/v1/system/upgrade/runs/${r.id}`)
    ok.value = `已删除 #${r.id}`
    await loadRuns()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "删除失败"
  } finally {
    busy.value = ""
  }
}

function fmtTime(s: string | null) {
  if (!s) return "—"
  const d = new Date(s)
  return isNaN(d.getTime()) ? s : d.toLocaleString()
}

function statusColor(s: string) {
  switch (s) {
    case "success": return "text-green-600"
    case "failed": return "text-red-600"
    case "rolled_back": return "text-amber-600"
    case "running": return "text-blue-600"
    case "pending": return "text-ink-500"
    default: return ""
  }
}

function statusText(s: string) {
  return {
    pending: "等待中", running: "运行中", success: "成功",
    failed: "失败", rolled_back: "已回滚",
  }[s] || s
}

function truncateNotes(s: string, n: number) {
  if (!s) return "—"
  // 取首行（避免多行 notes 折行时把表格撑高）
  const first = s.split("\n")[0]
  return first.length > n ? first.slice(0, n) + "…" : first
}

onMounted(() => {
  loadStatus()
  loadRuns()
  loadResources()
  // 如果 status 已有 running_run_id，自动开启轮询
  status.value?.running_run_id && (liveRunId.value = status.value.running_run_id, startPolling())
})
onUnmounted(stopPolling)
</script>

<template>
  <div>
    <h1 class="text-3xl font-semibold tracking-tight">在线升级</h1>
    <p class="mt-2 text-ink-500">主架构自动升级（仅主架构 + 开源内置应用；商业应用 crm/erp/mes/workflow/payment 不参与）。失败自动回滚。</p>

    <div v-if="!isSuper" class="mt-4 p-3 rounded-lg border border-amber-300 bg-amber-50 text-amber-800 text-sm">
      ⚠ 仅超级管理员可执行升级。当前用户：{{ auth.user?.username || "—" }}
    </div>

    <div v-if="error" class="mt-3 p-3 rounded-lg border border-red-300 bg-red-50 text-red-700 text-sm break-all">{{ error }}</div>
    <div v-if="ok" class="mt-3 p-3 rounded-lg border border-green-300 bg-green-50 text-green-700 text-sm">{{ ok }}</div>

    <div class="mt-6 grid md:grid-cols-4 gap-3 text-sm">
      <div class="card"><div class="text-ink-500 text-xs">当前版本</div><div class="font-mono text-lg mt-1">{{ status?.current_version || "—" }}</div></div>
      <div class="card"><div class="text-ink-500 text-xs">alembic head</div><div class="font-mono text-xs mt-1 break-all">{{ status?.alembic_current || "—" }}</div></div>
      <div class="card"><div class="text-ink-500 text-xs">业务链（升级跳过）</div><div class="font-mono text-lg mt-1">{{ status?.business_revisions ?? "—" }} <span class="text-xs text-ink-400">个 revision</span></div></div>
      <div class="card"><div class="text-ink-500 text-xs">状态</div><div class="text-lg mt-1" :class="[running ? 'text-blue-600' : '']"">{{ running ? "升级中" : "空闲" }}</div></div>
    </div>

    <div class="mt-6 card">
      <div class="flex items-center justify-between mb-3">
        <h2 class="font-semibold">升级资源库</h2>
        <div class="flex items-center gap-2 text-xs">
          <span v-if="resourcesInfo?.remote_error" class="text-amber-600" :title="resourcesInfo.remote_error">⚠ 远程不可达，已用本地</span>
          <span v-else-if="resourcesInfo?.remote_cached_at" class="text-ink-400">远程 {{ resourcesInfo.remote_url }}</span>
          <button class="btn-ghost text-xs" :disabled="busy === 'loadRes'" @click="loadResources(true)">
            {{ busy === "loadRes" ? "刷新中..." : "刷新资源" }}
          </button>
        </div>
      </div>
      <div v-if="resourcesError" class="text-red-600 text-sm break-all mb-2">{{ resourcesError }}</div>
      <div v-else-if="!resources.length" class="text-ink-500 text-sm">暂无资源（先确保远程清单 URL 可达或本地 release.json 存在）</div>
      <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-2">
        <div
          v-for="r in resources"
          :key="r.version + '-' + r.source"
          class="border rounded-lg p-3 text-xs cursor-pointer hover:border-ink-400 transition-colors"
          :class="[
            selectedResource?.version === r.version && selectedResource?.source === r.source ? 'border-blue-500 bg-blue-50' : 'border-ink-200',
            r.installed ? 'opacity-60' : ''
          ]"
          @click="selectResource(r)"
        >
          <div class="flex items-center justify-between mb-1">
            <span class="font-mono font-semibold text-sm">v{{ r.version }}</span>
            <span class="text-ink-500 text-[10px]">
              <span v-if="r.source === 'remote'">远程</span>
              <span v-else-if="r.source === 'local'">本地</span>
              <span v-else>本地文件</span>
            </span>
          </div>
          <div class="text-ink-500 text-[11px] mb-1">
            <span v-if="r.released_at">{{ r.released_at }}</span>
            <span v-else>—</span>
            <span v-if="r.size"> · {{ (r.size / 1024 / 1024).toFixed(1) }} MB</span>
            <span v-if="r.local_size"> · 本地 {{ (r.local_size / 1024 / 1024).toFixed(1) }} MB</span>
            <span v-if="r.channel"> · {{ r.channel }}</span>
          </div>
          <div v-if="r.notes" class="text-ink-600 text-[11px] line-clamp-2">{{ r.notes }}</div>
          <div class="mt-2 flex items-center gap-2">
            <span v-if="r.installed" class="text-green-600">✓ 当前版本</span>
            <span v-else-if="r.downloaded" class="text-blue-600">✓ 已下载本地</span>
            <span v-else-if="r.pkg_url" class="text-ink-400">未下载</span>
            <span v-else class="text-ink-400">无下载链接</span>
            <button
              v-if="r.pkg_url && !r.downloaded && !r.installed"
              class="btn-ghost text-[10px] ml-auto"
              :disabled="downloadBusy === r.version || !isSuper"
              @click.stop="doDownload(r)"
            >
              {{ downloadBusy === r.version ? "下载中..." : "下载到本地" }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="mt-6 card">
      <h2 class="font-semibold mb-3">升级方式</h2>
      <div class="flex gap-4 mb-3 text-sm flex-wrap">
        <label class="flex items-center gap-2"><input type="radio" value="resource" v-model="source" /> 从资源库选择</label>
        <label class="flex items-center gap-2"><input type="radio" value="url" v-model="source" /> 手动 URL</label>
        <label class="flex items-center gap-2"><input type="radio" value="tar_upload" v-model="source" /> 手动本地路径</label>
        <label class="flex items-center gap-2 ml-auto">通道：<input v-model="channel" class="input w-24 text-xs" /></label>
      </div>
      <div v-if="source === 'resource'">
        <div v-if="!selectedResource" class="text-ink-500 text-sm">请先在「升级资源库」选择一个版本（点卡片即可）</div>
        <div v-else class="text-xs space-y-1">
          <div>已选：<span class="font-mono font-semibold">v{{ selectedResource.version }}</span>
            <span v-if="selectedResource.local_path" class="text-blue-600">（本地已下载，将走本地路径升级）</span>
            <span v-else-if="selectedResource.pkg_url" class="text-amber-600">（未下载，将现场下载）</span>
            <span v-else class="text-red-600">（无下载链接，请选其他资源或切手动模式）</span>
          </div>
          <div v-if="selectedResource.local_path" class="text-ink-500">本地路径：<code class="bg-ink-50 px-1 rounded">{{ selectedResource.local_path }}</code></div>
          <div v-else-if="selectedResource.pkg_url" class="text-ink-500 break-all">URL：<code class="bg-ink-50 px-1 rounded">{{ selectedResource.pkg_url }}</code></div>
        </div>
      </div>
      <div v-else-if="source === 'url'">
        <input v-model="url" placeholder="https://github.com/.../cenkor-admin-core-x.y.z-DATE.tar.gz" class="input w-full" />
      </div>
      <div v-else>
        <input v-model="localPath" placeholder="/tmp/cenkor-admin-core-x.y.z-DATE.tar.gz" class="input w-full" />
        <div class="text-xs text-ink-500 mt-1">提示：先把核心包 scp 到服务器本地，再填路径。</div>
      </div>

      <div class="mt-3 p-3 rounded-lg border border-amber-200 bg-amber-50 text-amber-800 text-xs">
        <b>⚠ 升级会：</b>先快照到 /www/backup/cenkor-admin/snapshot_&lt;时间&gt;/（项目文件 + pg_dump + env）→<br />
        覆盖主架构 + 开源内置应用代码（rsync 不删 crm/erp/mes/workflow/payment 这 5 个本地应用）→<br />
        跑 alembic upgrade head<b>（仅主架构链）</b>，业务链迁移自动 stamp 跳过 → 重启 8002 → 健康检查。<br />
        <b>失败自动回滚</b>到升级前版本，DB 不会留下半截状态。
      </div>

      <div class="mt-3">
        <label class="text-xs text-ink-500 mb-1 block">更新日志（notes，可选）— 升级成功后会自动存入「升级历史」+ 发布一条置顶公告（30 天后自动取消置顶）</label>
        <textarea
          v-model="notes"
          rows="3"
          maxlength="8000"
          placeholder="例如：修复 #123 数据导出 bug；新增 /api/v1/system/upgrade/status 接口；优化安装流程。"
          class="input w-full font-mono text-xs"
        />
        <div class="text-[10px] text-ink-400 mt-1 text-right">{{ notes.length }} / 8000</div>
      </div>

      <div class="mt-3 flex items-center gap-3">
        <button class="btn-ghost" :disabled="busy !== '' || !isSuper" @click="doDryRun">
          {{ busy === "dry" ? "规划中..." : "预演" }}
        </button>
        <input v-model="confirmText" :placeholder="'请输入「' + CONFIRM + '」确认'" class="input text-sm flex-1 max-w-md" />
        <button class="btn-primary" :disabled="busy !== '' || !isSuper || running" @click="doRun">
          {{ busy === "run" ? "启动中..." : "升级" }}
        </button>
      </div>
    </div>

    <div v-if="liveRunId" class="mt-4 card">
      <div class="flex items-center justify-between mb-2">
        <h2 class="font-semibold">实时日志 <span class="text-ink-400 text-xs">#{{ liveRunId }}</span></h2>
        <button class="btn-ghost text-xs" @click="() => { liveLog = '' }">清屏</button>
      </div>
      <pre class="bg-black text-green-300 p-3 rounded text-xs whitespace-pre-wrap break-all max-h-96 overflow-y-auto font-mono">{{ liveLog || "等待日志..." }}</pre>
    </div>

    <div class="mt-6 card">
      <div class="flex items-center justify-between mb-3">
        <h2 class="font-semibold">升级历史</h2>
        <div class="flex items-center gap-2">
          <select v-model="filterStatus" class="input text-xs" @change="loadRuns">
            <option value="">全部状态</option>
            <option value="success">成功</option>
            <option value="failed">失败</option>
            <option value="rolled_back">已回滚</option>
            <option value="running">运行中</option>
          </select>
          <select v-model="filterSource" class="input text-xs" @change="loadRuns">
            <option value="">全部来源</option>
            <option value="url">URL</option>
            <option value="tar_upload">上传</option>
          </select>
          <button class="btn-ghost text-xs" :disabled="runsLoading" @click="loadRuns">{{ runsLoading ? "刷新中..." : "刷新" }}</button>
        </div>
      </div>
      <div v-if="runsError" class="text-red-600 text-sm break-all">{{ runsError }}</div>
      <div v-else-if="!runs.length" class="text-ink-500 text-sm">还没有升级记录。</div>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-xs">
          <thead>
            <tr class="text-ink-500 text-left">
              <th class="font-normal py-1 pr-2">时间</th>
              <th class="font-normal py-1 pr-2">来源</th>
              <th class="font-normal py-1 pr-2">版本</th>
              <th class="font-normal py-1 pr-2">状态</th>
              <th class="font-normal py-1 pr-2">耗时</th>
              <th class="font-normal py-1 pr-2">更新日志</th>
              <th class="font-normal py-1"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in runs" :key="r.id" class="border-t border-ink-100">
              <td class="py-1.5 pr-2 whitespace-nowrap">{{ fmtTime(r.created_at) }}</td>
              <td class="py-1.5 pr-2">{{ r.source === "tar_upload" ? "上传" : "URL" }}</td>
              <td class="py-1.5 pr-2 font-mono text-xs">
                <span v-if="r.from_version">{{ r.from_version }}</span>
                <span v-else class="text-ink-400">—</span>
                →
                <span v-if="r.to_version">{{ r.to_version }}</span>
                <span v-else class="text-ink-400">—</span>
              </td>
              <td class="py-1.5 pr-2" :class="statusColor(r.status)">{{ statusText(r.status) }}</td>
              <td class="py-1.5 pr-2 whitespace-nowrap">{{ r.duration_ms === null ? "—" : r.duration_ms + " ms" }}</td>
              <td class="py-1.5 pr-2 max-w-xs">
                <span v-if="r.notes" class="text-ink-700" :title="r.notes">{{ truncateNotes(r.notes, 40) }}</span>
                <span v-else class="text-ink-400">—</span>
              </td>
              <td class="py-1.5 whitespace-nowrap">
                <button class="btn-ghost text-xs" @click="openDetail(r)">详情</button>
                <button class="btn-ghost text-xs" :disabled="!canWrite || !isSuper || running" @click="openRollback(r)">回滚</button>
                <button class="btn-ghost text-xs text-red-600" :disabled="!canWrite || r.status === 'running'" @click="doDelete(r)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="detailOpen" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="detailOpen = false">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-2xl p-6 max-h-[85vh] overflow-y-auto">
        <h2 class="text-lg font-semibold mb-3">升级详情</h2>
        <div v-if="!detail" class="text-ink-500 text-sm">加载中...</div>
        <template v-else>
          <div class="text-sm space-y-1 mb-3">
            <div>记录：#{{ detail.id }} · {{ detail.source === "tar_upload" ? "上传" : "URL" }} · <span :class="statusColor(detail.status)">{{ statusText(detail.status) }}</span></div>
            <div>版本：<span class="font-mono">{{ detail.from_version || "—" }} → {{ detail.to_version || "—" }}</span></div>
            <div>开始：{{ fmtTime(detail.started_at) }} · 结束：{{ fmtTime(detail.finished_at) }}<span v-if="detail.duration_ms !== null"> · {{ detail.duration_ms }} ms</span></div>
            <div v-if="detail.backup_path">备份：<code class="bg-ink-50 px-1 rounded text-xs">{{ detail.backup_path }}</code></div>
            <div v-if="detail.rollback_from_id">这是对 #{{ detail.rollback_from_id }} 的回滚</div>
          </div>
          <div v-if="detail.notes" class="mb-3">
            <div class="text-xs text-ink-500 mb-1">更新日志（本次升级填写）</div>
            <pre class="text-xs bg-blue-50 text-blue-900 p-3 rounded whitespace-pre-wrap break-all max-h-48 overflow-y-auto">{{ detail.notes }}</pre>
          </div>
          <div v-if="detail.error" class="mb-3">
            <div class="text-xs text-ink-500 mb-1">后端原始报错</div>
            <pre class="text-xs bg-red-50 text-red-700 p-3 rounded whitespace-pre-wrap break-all max-h-32 overflow-y-auto">{{ detail.error }}</pre>
          </div>
          <div>
            <div class="text-xs text-ink-500 mb-1">完整日志</div>
            <pre class="text-xs bg-black text-green-300 p-3 rounded whitespace-pre-wrap break-all max-h-96 overflow-y-auto font-mono">{{ detail.log || "（无）" }}</pre>
          </div>
          <div class="flex justify-end gap-2 mt-4">
            <button class="btn-ghost" :disabled="!isSuper || !canWrite || running" @click="openRollback(detail); detailOpen = false">回滚此次</button>
            <button class="btn-ghost" @click="detailOpen = false">关闭</button>
          </div>
        </template>
      </div>
    </div>

    <div v-if="rollbackConfirmOpen" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="rollbackConfirmOpen = false">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-lg p-6">
        <h2 class="text-lg font-semibold mb-3 text-red-600">确认手动回滚</h2>
        <div class="text-sm text-ink-700 space-y-2 mb-4">
          <p>将按记录 <b>#{{ rollbackTarget?.id }}</b> 的 backup_path 恢复 <code class="bg-ink-50 px-1 rounded">{{ rollbackTarget?.backup_path }}</code> 下的项目文件，</p>
          <p>然后重启 8002 + 健康检查。不会动 DB schema。</p>
        </div>
        <input v-model="confirmText" :placeholder="'请输入「' + CONFIRM + '」确认'" class="input w-full text-sm mb-3" />
        <div class="flex justify-end gap-2">
          <button class="btn-ghost" @click="rollbackConfirmOpen = false">取消</button>
          <button class="btn-primary" :disabled="busy !== '' || !isSuper" @click="doRollback">{{ busy === "rollback" ? "执行中..." : "确认回滚" }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
