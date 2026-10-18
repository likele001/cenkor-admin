<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue"
import { useAuthStore } from "@/stores/auth"
import { api } from "@/lib/api"

const auth = useAuthStore()
const status = ref<any>(null)
const resources = ref<any>(null)       // /resources 返回的 git commits
const confirmText = ref("")
const notes = ref("")
const busy = ref<"" | "check" | "dry" | "run" | "rollback" | "delete" | "detail">("")
const error = ref("")
const ok = ref("")
const runs = ref<any[]>([])
const runsLoading = ref(false)
const filterStatus = ref("")
const detail = ref<any>(null)
const detailOpen = ref(false)
const rollbackConfirmOpen = ref(false)
const rollbackTarget = ref<any>(null)
const liveRunId = ref<number | null>(null)
const liveLog = ref("")
let pollTimer: number | null = null

const CONFIRM = "升级 cenkor-admin"
const canWrite = computed(() => auth.hasPermission("system:upgrade:write"))
const isSuper = computed(() => !!auth.user?.is_superuser)
const running = computed(() => !!liveRunId.value)

async function loadStatus() {
  try {
    const { data } = await api.get("/api/v1/system/upgrade/status")
    status.value = data
    if (data?.running_run_id) {
      liveRunId.value = data.running_run_id
      startPolling()
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "加载状态失败"
  }
}

async function loadRuns() {
  runsLoading.value = true
  try {
    const params: any = { page: 1, page_size: 20 }
    if (filterStatus.value) params.status = filterStatus.value
    const { data } = await api.get("/api/v1/system/upgrade/runs", { params })
    runs.value = data.items || []
  } catch (e: any) {
    // ignore
  } finally {
    runsLoading.value = false
  }
}

async function checkUpdates() {
  busy.value = "check"
  error.value = ""
  try {
    const { data } = await api.get("/api/v1/system/upgrade/resources", { params: { refresh: true } })
    resources.value = data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "检查更新失败"
  } finally {
    busy.value = ""
  }
}

async function doDryRun() {
  if (!isSuper.value) { error.value = "仅超级管理员可执行"; return }
  if (confirmText.value !== CONFIRM) { error.value = `请输入「${CONFIRM}」确认`; return }
  busy.value = "dry"
  error.value = ""
  ok.value = ""
  try {
    const { data } = await api.post("/api/v1/system/upgrade/dry-run", {
      source: "git",
      payload: {},
      confirm_text: CONFIRM,
      notes: notes.value || undefined,
    })
    ok.value = "预演完成（仅检查，未执行升级）"
    if (data?.log) liveLog.value = data.log
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "预演失败"
  } finally {
    busy.value = ""
  }
}

async function doRun() {
  if (!isSuper.value) { error.value = "仅超级管理员可执行"; return }
  if (confirmText.value !== CONFIRM) { error.value = `请输入「${CONFIRM}」确认`; return }
  busy.value = "run"
  error.value = ""
  ok.value = ""
  try {
    await api.post("/api/v1/system/upgrade/run", {
      source: "git",
      payload: {},
      confirm_text: CONFIRM,
      notes: notes.value || undefined,
    })
    ok.value = "已启动升级，轮询日志查看进度..."
    setTimeout(async () => {
      await loadStatus()
      if (status.value?.running_run_id) {
        liveRunId.value = status.value.running_run_id
        liveLog.value = ""
        startPolling()
      }
    }, 500)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "启动升级失败"
    busy.value = ""
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = window.setInterval(async () => {
    if (!liveRunId.value) return
    try {
      const { data } = await api.get(`/api/v1/system/upgrade/runs/${liveRunId.value}/log`)
      liveLog.value = data.slice || ""
      if (data.status && data.status !== "running" && data.status !== "pending") {
        stopPolling()
        busy.value = ""
        await loadStatus()
        await loadRuns()
        if (data.status === "success") {
          ok.value = "✓ 代码已更新，请在宝塔面板手动重启后端服务！"
        } else if (data.status === "rolled_back") {
          error.value = "✗ 升级失败，已自动回滚代码"
        } else {
          error.value = "✗ 升级失败（详见日志）"
        }
      }
    } catch { /* ignore */ }
  }, 3000)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

async function openDetail(r: any) {
  detail.value = null
  detailOpen.value = true
  try {
    const { data } = await api.get(`/api/v1/system/upgrade/runs/${r.id}`)
    detail.value = data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "加载详情失败"
    detailOpen.value = false
  }
}

function openRollback(r: any) {
  rollbackTarget.value = r
  rollbackConfirmOpen.value = true
  confirmText.value = ""
}

async function doRollback() {
  if (!isSuper.value) { error.value = "仅超级管理员可执行"; return }
  if (confirmText.value !== CONFIRM) { error.value = `请输入「${CONFIRM}」确认`; return }
  busy.value = "rollback"
  try {
    await api.post(`/api/v1/system/upgrade/runs/${rollbackTarget.value.id}/rollback`, { confirm_text: CONFIRM })
    ok.value = "已启动回滚，轮询查看进度"
    rollbackConfirmOpen.value = false
    setTimeout(async () => {
      await loadStatus()
      if (status.value?.running_run_id) {
        liveRunId.value = status.value.running_run_id
        liveLog.value = ""
        startPolling()
      }
    }, 500)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "回滚失败"
    busy.value = ""
  }
}

async function doDelete(r: any) {
  if (!window.confirm(`删除记录 #${r.id}？`)) return
  try {
    await api.delete(`/api/v1/system/upgrade/runs/${r.id}`)
    ok.value = `已删除 #${r.id}`
    await loadRuns()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "删除失败"
  }
}

function fmtTime(s: string | null) {
  if (!s) return "—"
  const d = new Date(s)
  return isNaN(d.getTime()) ? s : d.toLocaleString()
}

function statusColor(s: string) {
  return { success: "text-green-600", failed: "text-red-600", rolled_back: "text-amber-600", running: "text-blue-600", pending: "text-ink-500" }[s] || ""
}
function statusText(s: string) {
  return { pending: "等待", running: "进行中", success: "成功", failed: "失败", rolled_back: "已回滚" }[s] || s
}

onMounted(() => {
  loadStatus()
  loadRuns()
  checkUpdates()
})
onUnmounted(stopPolling)
</script>

<template>
  <div>
    <h1 class="text-3xl font-semibold tracking-tight">在线升级</h1>
    <p class="mt-2 text-sm text-ink-500">通过 git pull 升级主程序，数据库自动迁移。升级后需手动在宝塔面板重启后端。</p>

    <div v-if="!isSuper" class="mt-4 p-3 rounded-lg border border-amber-300 bg-amber-50 text-amber-800 text-sm">
      ⚠ 仅超级管理员可执行升级。当前用户：{{ auth.user?.username || "—" }}
    </div>

    <div v-if="error" class="mt-3 p-3 rounded-lg border border-red-300 bg-red-50 text-red-700 text-sm break-all">{{ error }}</div>
    <div v-if="ok" class="mt-3 p-3 rounded-lg border border-green-300 bg-green-50 text-green-700 text-sm">{{ ok }}</div>

    <!-- 当前版本卡片 -->
    <div class="mt-6 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
      <div class="card"><div class="text-ink-500 text-xs">当前版本</div><div class="font-mono text-lg mt-1">{{ status?.current_version || "—" }}</div></div>
      <div class="card"><div class="text-ink-500 text-xs">当前 Commit</div><div class="font-mono text-sm mt-1">{{ status?.current_sha?.slice(0,8) || "—" }}</div></div>
      <div class="card"><div class="text-ink-500 text-xs">新提交数</div><div class="font-mono text-lg mt-1">{{ resources?.commits_count ?? "—" }}</div></div>
      <div class="card"><div class="text-ink-500 text-xs">状态</div><div class="text-lg mt-1" :class="running ? 'text-blue-600' : ''">{{ running ? "升级中" : "空闲" }}</div></div>
    </div>

    <!-- 检查更新 -->
    <div class="mt-6 card">
      <div class="flex items-center justify-between mb-3">
        <h2 class="font-semibold">检查更新</h2>
        <button class="btn-ghost text-xs" :disabled="busy === 'check'" @click="checkUpdates">
          {{ busy === "check" ? "检查中..." : "刷新检查" }}
        </button>
      </div>

      <div v-if="resources?.error" class="text-red-600 text-sm mb-2">{{ resources.error }}</div>

      <div v-if="resources && !resources.commits_count && !resources.error" class="text-green-600 text-sm">✓ 已是最新版本</div>

      <div v-if="resources?.commits?.length" class="space-y-1">
        <div class="text-sm text-ink-500 mb-2">远程有 {{ resources.commits_count }} 个新提交：</div>
        <div class="border rounded divide-y">
          <div v-for="c in resources.commits.slice(0, 20)" :key="c.sha" class="px-3 py-2 flex items-center gap-3 text-xs">
            <span class="font-mono text-ink-400">{{ c.sha }}</span>
            <span class="text-ink-400">{{ c.date }}</span>
            <span class="flex-1">{{ c.message }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 升级操作 -->
    <div class="mt-6 card">
      <h2 class="font-semibold mb-3">执行升级</h2>

      <div class="p-3 rounded-lg border border-blue-200 bg-blue-50 text-blue-900 text-xs mb-3">
        <b>升级流程：</b>git fetch → git pull --ff-only → 自动备份数据库 → alembic 迁移 → 提示重启<br/>
        <b>⚠ 升级完成后必须手动在宝塔面板重启后端服务才能生效！</b>
      </div>

      <div class="mb-3">
        <label class="text-xs text-ink-500 block mb-1">更新说明（可选）</label>
        <input v-model="notes" placeholder="本次升级的说明（可选）" class="input w-full text-sm" />
      </div>

      <div class="flex items-center gap-3">
        <button class="btn-ghost" :disabled="busy !== '' || !isSuper" @click="doDryRun">
          {{ busy === "dry" ? "检查中..." : "检查更新" }}
        </button>
        <input v-model="confirmText" :placeholder="'输入「' + CONFIRM + '」确认'" class="input text-sm flex-1 max-w-md" />
        <button class="btn-primary" :disabled="busy !== '' || !isSuper || running" @click="doRun">
          {{ busy === "run" ? "升级中..." : "开始升级" }}
        </button>
      </div>
    </div>

    <!-- 实时日志 -->
    <div v-if="liveRunId" class="mt-4 card">
      <div class="flex items-center justify-between mb-2">
        <h2 class="font-semibold">实时日志 <span class="text-ink-400 text-xs">#{{ liveRunId }}</span></h2>
      </div>
      <pre class="bg-black text-green-300 p-3 rounded text-xs whitespace-pre-wrap break-all max-h-96 overflow-y-auto font-mono">{{ liveLog || "等待日志..." }}</pre>
    </div>

    <!-- 升级历史 -->
    <div class="mt-6 card">
      <div class="flex items-center justify-between mb-3">
        <h2 class="font-semibold">升级历史</h2>
        <div class="flex items-center gap-2">
          <select v-model="filterStatus" class="input text-xs" @change="loadRuns">
            <option value="">全部状态</option>
            <option value="success">成功</option>
            <option value="failed">失败</option>
            <option value="rolled_back">已回滚</option>
          </select>
          <button class="btn-ghost text-xs" :disabled="runsLoading" @click="loadRuns">刷新</button>
        </div>
      </div>
      <div v-if="!runs.length" class="text-ink-500 text-sm">暂无记录</div>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-xs">
          <thead><tr class="text-ink-500 text-left">
            <th class="font-normal py-1 pr-2">时间</th>
            <th class="font-normal py-1 pr-2">版本</th>
            <th class="font-normal py-1 pr-2">状态</th>
            <th class="font-normal py-1 pr-2">耗时</th>
            <th class="font-normal py-1"></th>
          </tr></thead>
          <tbody>
            <tr v-for="r in runs" :key="r.id" class="border-t border-ink-100">
              <td class="py-1.5 pr-2 whitespace-nowrap">{{ fmtTime(r.created_at) }}</td>
              <td class="py-1.5 pr-2 font-mono text-xs">{{ r.from_version || "—" }} → {{ r.to_version || "—" }}</td>
              <td class="py-1.5 pr-2" :class="statusColor(r.status)">{{ statusText(r.status) }}</td>
              <td class="py-1.5 pr-2">{{ r.duration_ms ? r.duration_ms + "ms" : "—" }}</td>
              <td class="py-1.5 whitespace-nowrap">
                <button class="btn-ghost text-xs" @click="openDetail(r)">详情</button>
                <button class="btn-ghost text-xs" :disabled="!isSuper || running" @click="openRollback(r)">回滚</button>
                <button class="btn-ghost text-xs text-red-600" :disabled="r.status === 'running'" @click="doDelete(r)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 详情弹窗 -->
    <div v-if="detailOpen" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="detailOpen = false">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-2xl p-6 max-h-[85vh] overflow-y-auto">
        <h2 class="text-lg font-semibold mb-3">升级详情 #{{ detail?.id }}</h2>
        <div v-if="detail" class="text-sm space-y-1 mb-3">
          <div>版本：<span class="font-mono">{{ detail.from_version }} → {{ detail.to_version }}</span></div>
          <div>状态：<span :class="statusColor(detail.status)">{{ statusText(detail.status) }}</span></div>
          <div v-if="detail.backup_path">数据库备份：<code class="bg-ink-50 px-1 rounded text-xs">{{ detail.backup_path }}</code></div>
        </div>
        <div v-if="detail?.error" class="mb-3">
          <div class="text-xs text-ink-500 mb-1">错误</div>
          <pre class="text-xs bg-red-50 text-red-700 p-3 rounded">{{ detail.error }}</pre>
        </div>
        <div>
          <div class="text-xs text-ink-500 mb-1">完整日志</div>
          <pre class="text-xs bg-black text-green-300 p-3 rounded whitespace-pre-wrap break-all max-h-96 overflow-y-auto font-mono">{{ detail?.log || "（无）" }}</pre>
        </div>
        <div class="flex justify-end gap-2 mt-4">
          <button class="btn-ghost" @click="detailOpen = false">关闭</button>
        </div>
      </div>
    </div>

    <!-- 回滚确认弹窗 -->
    <div v-if="rollbackConfirmOpen" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="rollbackConfirmOpen = false">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-lg p-6">
        <h2 class="text-lg font-semibold mb-3 text-red-600">确认回滚</h2>
        <p class="text-sm text-ink-700 mb-3">将 git reset 到升级前的 commit。回滚后需在宝塔手动重启后端。</p>
        <input v-model="confirmText" :placeholder="'输入「' + CONFIRM + '」确认'" class="input w-full text-sm mb-3" />
        <div class="flex justify-end gap-2">
          <button class="btn-ghost" @click="rollbackConfirmOpen = false">取消</button>
          <button class="btn-primary" :disabled="busy !== ''" @click="doRollback">{{ busy === "rollback" ? "回滚中..." : "确认回滚" }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
