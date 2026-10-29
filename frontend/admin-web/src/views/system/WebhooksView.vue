<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/lib/api'

interface Delivery {
  id: number
  event_id: string
  webhook_id: number | null
  event: string
  url: string
  status: 'pending' | 'success' | 'failed' | 'dropped'
  attempts: number
  http_status: number | null
  response_snippet: string | null
  error: string | null
  duration_ms: number | null
  next_retry_at: string | null
  delivered_at: string | null
  created_at: string | null
  payload?: any
}

interface Webhook {
  id: number; url: string; events: string[]; secret: string | null
  description: string | null; enabled: boolean
  last_delivery?: Delivery | null
}

const EVENTS = ref<{ key: string; label: string }[]>([])
const items = ref<Webhook[]>([])
const loading = ref(false)
const showModal = ref(false)
const editing = ref<Webhook | null>(null)
const form = ref({ url: '', events: [] as string[], secret: '', description: '', enabled: true })

const tab = ref<'subs' | 'logs'>('subs')

// ---- 投递日志 ----
const logs = ref<Delivery[]>([])
const logsLoading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = 20
const fStatus = ref('')
const fEvent = ref('')
const fWebhook = ref<number | ''>('')
const stats = ref<any>(null)
const detail = ref<Delivery | null>(null)
const detailOpen = ref(false)
const replaying = ref<number | null>(null)

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

const STATUS_STYLE: Record<string, string> = {
  success: 'bg-green-50 text-green-700',
  failed: 'bg-red-50 text-red-700',
  pending: 'bg-amber-50 text-amber-700',
  dropped: 'bg-ink-100 text-ink-500',
}
const STATUS_LABEL: Record<string, string> = {
  success: '已送达', failed: '失败', pending: '待重试', dropped: '已丢弃',
}

function fmt(ts: string | null) {
  if (!ts) return '—'
  const d = new Date(ts)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}
function eventLabel(key: string) {
  if (key === 'webhook.test') return '测试投递'
  return EVENTS.value.find((e) => e.key === key)?.label || ''
}

async function loadEvents() {
  try {
    const { data } = await api.get('/api/v1/system/webhook-events')
    EVENTS.value = data.items || []
  } catch { /* 事件目录拉不到不阻塞页面 */ }
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/api/v1/system/webhooks')
    items.value = data.items || []
  } catch (e: any) { alert(e?.response?.data?.detail || '加载失败') } finally { loading.value = false }
}

async function loadStats() {
  try {
    const { data } = await api.get('/api/v1/system/webhook-deliveries/stats', { params: { hours: 24 } })
    stats.value = data
  } catch { stats.value = null }
}

async function loadLogs() {
  logsLoading.value = true
  try {
    const params: any = { page: page.value, page_size: pageSize }
    if (fStatus.value) params.status = fStatus.value
    if (fEvent.value) params.event = fEvent.value
    if (fWebhook.value !== '') params.webhook_id = fWebhook.value
    const { data } = await api.get('/api/v1/system/webhook-deliveries', { params })
    logs.value = data.items || []
    total.value = data.total || 0
  } catch (e: any) {
    alert(e?.response?.data?.detail || '加载投递日志失败')
  } finally { logsLoading.value = false }
}

function openCreate() {
  editing.value = null
  form.value = { url: '', events: ['entry.published'], secret: '', description: '', enabled: true }
  showModal.value = true
}
function openEdit(w: Webhook) {
  editing.value = w
  form.value = {
    url: w.url, events: [...w.events], secret: w.secret || '',
    description: w.description || '', enabled: w.enabled,
  }
  showModal.value = true
}
async function save() {
  if (!form.value.url) return alert('URL 必填')
  try {
    const body = { ...form.value, secret: form.value.secret || null }
    if (editing.value) await api.patch(`/api/v1/system/webhooks/${editing.value.id}`, body)
    else await api.post('/api/v1/system/webhooks', body)
    showModal.value = false
    await load()
  } catch (e: any) { alert(e?.response?.data?.detail || '保存失败') }
}
async function remove(w: Webhook) {
  if (!window.confirm('确认删除该 Webhook？' + '\n投递日志会保留（id 置空），但不会再投递。')) return
  try {
    await api.delete(`/api/v1/system/webhooks/${w.id}`)
    await load()
  } catch (e: any) { alert(e?.response?.data?.detail || '删除失败') }
}
function toggleEvent(ev: string) {
  const i = form.value.events.indexOf(ev)
  if (i >= 0) form.value.events.splice(i, 1)
  else form.value.events.push(ev)
}

async function sendTest(w: Webhook) {
  try {
    const { data } = await api.post(`/api/v1/system/webhooks/${w.id}/test`)
    await new Promise((r) => setTimeout(r, 900))
    const did = (data.delivery_ids || [])[0]
    if (did) {
      const { data: d } = await api.get(`/api/v1/system/webhook-deliveries/${did}`)
      const st = STATUS_LABEL[d.status] || d.status
      alert(`测试投递：${st}${d.http_status ? `（HTTP ${d.http_status}）` : ''}${d.error ? `\n${d.error}` : ''}`)
    }
    await Promise.all([load(), loadStats(), loadLogs()])
  } catch (e: any) { alert(e?.response?.data?.detail || '测试发送失败') }
}

async function openDetail(d: Delivery) {
  try {
    const { data } = await api.get(`/api/v1/system/webhook-deliveries/${d.id}`)
    detail.value = data
    detailOpen.value = true
  } catch (e: any) { alert(e?.response?.data?.detail || '读取详情失败') }
}

async function replay(d: Delivery) {
  replaying.value = d.id
  try {
    const { data } = await api.post(`/api/v1/system/webhook-deliveries/${d.id}/replay`)
    const st = data?.delivery?.status
    alert(`重放结果：${STATUS_LABEL[st] || st}${data?.delivery?.error ? `\n${data.delivery.error}` : ''}`)
    await Promise.all([loadStats(), loadLogs(), load()])
  } catch (e: any) { alert(e?.response?.data?.detail || '重放失败') } finally { replaying.value = null }
}

watch([fStatus, fEvent, fWebhook], () => { page.value = 1; loadLogs() })
watch(page, loadLogs)
watch(tab, (t) => { if (t === 'logs') { loadLogs(); loadStats() } })

onMounted(async () => {
  await loadEvents()
  await load()
  await loadStats()
})
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <div class="flex items-center gap-2">
        <h1 class="text-2xl font-semibold tracking-tight">⚡ Webhook → Agent</h1>
        <span class="text-sm text-ink-400">发布即触发下游</span>
      </div>
      <button class="btn-primary" @click="openCreate">新增订阅</button>
    </div>

    <!-- 24h 概览 -->
    <div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
      <div class="card p-4">
        <div class="text-xs text-ink-400">近 24h 投递</div>
        <div class="text-2xl font-semibold mt-1">{{ stats?.total ?? '—' }}</div>
      </div>
      <div class="card p-4">
        <div class="text-xs text-ink-400">已送达</div>
        <div class="text-2xl font-semibold mt-1 text-green-600">{{ stats?.by_status?.success ?? 0 }}</div>
      </div>
      <div class="card p-4">
        <div class="text-xs text-ink-400">失败</div>
        <div class="text-2xl font-semibold mt-1 text-red-600">{{ stats?.by_status?.failed ?? 0 }}</div>
      </div>
      <div class="card p-4">
        <div class="text-xs text-ink-400">待重试</div>
        <div class="text-2xl font-semibold mt-1 text-amber-600">{{ stats?.by_status?.pending ?? 0 }}</div>
      </div>
      <div class="card p-4">
        <div class="text-xs text-ink-400">成功率</div>
        <div class="text-2xl font-semibold mt-1">
          {{ stats?.success_rate == null ? '—' : (stats.success_rate * 100).toFixed(1) + '%' }}
        </div>
      </div>
    </div>

    <div class="flex items-center gap-1 mb-3 border-b">
      <button class="px-4 py-2 text-sm -mb-px border-b-2"
        :class="tab === 'subs' ? 'border-ink-900 text-ink-900 font-medium' : 'border-transparent text-ink-400'"
        @click="tab = 'subs'">订阅（{{ items.length }}）</button>
      <button class="px-4 py-2 text-sm -mb-px border-b-2"
        :class="tab === 'logs' ? 'border-ink-900 text-ink-900 font-medium' : 'border-transparent text-ink-400'"
        @click="tab = 'logs'">投递日志</button>
    </div>

    <!-- 订阅 -->
    <div v-if="tab === 'subs'" class="card overflow-hidden">
      <div v-if="loading" class="text-ink-500 p-6">加载中…</div>
      <table v-else class="w-full text-sm">
        <thead>
          <tr class="text-left text-ink-400 border-b">
            <th class="p-3">URL</th>
            <th class="p-3">事件</th>
            <th class="p-3">状态</th>
            <th class="p-3">最近投递</th>
            <th class="p-3 text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="w in items" :key="w.id" class="border-b last:border-0">
            <td class="p-3">
              <div class="font-mono text-xs truncate max-w-xs">{{ w.url }}</div>
              <div v-if="w.description" class="text-xs text-ink-400">{{ w.description }}</div>
              <div v-if="w.secret" class="text-xs text-ink-300">已配置签名密钥</div>
            </td>
            <td class="p-3">
              <span v-for="ev in w.events" :key="ev"
                class="text-xs px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded mr-1 mb-1 inline-block">{{ ev }}</span>
            </td>
            <td class="p-3">
              <span :class="w.enabled ? 'text-green-600' : 'text-ink-300'">{{ w.enabled ? '启用' : '停用' }}</span>
            </td>
            <td class="p-3 text-xs">
              <template v-if="w.last_delivery">
                <span class="px-1.5 py-0.5 rounded" :class="STATUS_STYLE[w.last_delivery.status]">
                  {{ STATUS_LABEL[w.last_delivery.status] }}
                </span>
                <span class="text-ink-400 ml-1">{{ fmt(w.last_delivery.created_at) }}</span>
              </template>
              <span v-else class="text-ink-300">从未投递</span>
            </td>
            <td class="p-3 text-right space-x-2 whitespace-nowrap">
              <button class="btn-ghost text-sm" :disabled="!w.enabled" @click="sendTest(w)">测试</button>
              <button class="btn-ghost text-sm" @click="openEdit(w)">编辑</button>
              <button class="btn-ghost text-sm text-red-600" @click="remove(w)">删除</button>
            </td>
          </tr>
          <tr v-if="!items.length">
            <td colspan="5" class="p-6 text-center text-ink-400">
              暂无订阅 —— 点右上角新增，填下游 Agent 的接收地址
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 投递日志 -->
    <div v-else>
      <div class="flex flex-wrap items-center gap-2 mb-3">
        <select v-model="fWebhook" class="input w-48">
          <option value="">全部订阅</option>
          <option v-for="w in items" :key="w.id" :value="w.id">#{{ w.id }} {{ w.url.slice(0, 28) }}</option>
        </select>
        <select v-model="fEvent" class="input w-52">
          <option value="">全部事件</option>
          <option v-for="e in EVENTS" :key="e.key" :value="e.key">{{ e.key }}</option>
        </select>
        <select v-model="fStatus" class="input w-36">
          <option value="">全部状态</option>
          <option value="success">已送达</option>
          <option value="pending">待重试</option>
          <option value="failed">失败</option>
          <option value="dropped">已丢弃</option>
        </select>
        <button class="btn-ghost text-sm" @click="loadLogs">刷新</button>
        <span class="text-xs text-ink-400 ml-auto">共 {{ total }} 条</span>
      </div>

      <div class="card overflow-hidden">
        <div v-if="logsLoading" class="text-ink-500 p-6">加载中…</div>
        <table v-else class="w-full text-sm">
          <thead>
            <tr class="text-left text-ink-400 border-b">
              <th class="p-3">时间</th>
              <th class="p-3">事件</th>
              <th class="p-3">状态</th>
              <th class="p-3">尝试</th>
              <th class="p-3">HTTP</th>
              <th class="p-3">耗时</th>
              <th class="p-3">说明</th>
              <th class="p-3 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in logs" :key="d.id" class="border-b last:border-0 hover:bg-ink-50">
              <td class="p-3 text-xs whitespace-nowrap">{{ fmt(d.created_at) }}</td>
              <td class="p-3">
                <div class="text-xs">{{ d.event }}</div>
                <div v-if="eventLabel(d.event)" class="text-ink-300 text-[10px] truncate max-w-[160px]">
                  {{ eventLabel(d.event) }}
                </div>
              </td>
              <td class="p-3">
                <span class="px-1.5 py-0.5 rounded text-xs" :class="STATUS_STYLE[d.status]">
                  {{ STATUS_LABEL[d.status] || d.status }}
                </span>
              </td>
              <td class="p-3 text-xs">{{ d.attempts }}</td>
              <td class="p-3 text-xs">{{ d.http_status ?? '—' }}</td>
              <td class="p-3 text-xs">{{ d.duration_ms == null ? '—' : d.duration_ms + 'ms' }}</td>
              <td class="p-3 text-xs text-ink-500 max-w-[220px] truncate" :title="d.error || ''">
                {{ d.error || (d.next_retry_at ? '下次重试 ' + fmt(d.next_retry_at) : '') }}
              </td>
              <td class="p-3 text-right space-x-2 whitespace-nowrap">
                <button class="btn-ghost text-sm" @click="openDetail(d)">详情</button>
                <button class="btn-ghost text-sm" :disabled="replaying === d.id" @click="replay(d)">
                  {{ replaying === d.id ? '投递中…' : '重放' }}
                </button>
              </td>
            </tr>
            <tr v-if="!logs.length">
              <td colspan="8" class="p-6 text-center text-ink-400">暂无投递记录</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="flex items-center justify-end gap-2 mt-3 text-sm">
        <button class="btn-ghost" :disabled="page <= 1" @click="page--">上一页</button>
        <span class="text-ink-500">{{ page }} / {{ pageCount }}</span>
        <button class="btn-ghost" :disabled="page >= pageCount" @click="page++">下一页</button>
      </div>
    </div>

    <!-- 新建/编辑 -->
    <div v-if="showModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showModal = false">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h2 class="text-lg font-semibold mb-4">{{ editing ? '编辑订阅' : '新增订阅' }}</h2>
        <div class="space-y-3">
          <div>
            <label class="block text-sm font-medium mb-1">回调 URL</label>
            <input v-model="form.url" class="input" placeholder="https://agent.example.com/hooks/cenkor" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">订阅事件</label>
            <div class="flex flex-col gap-1.5">
              <label v-for="ev in EVENTS" :key="ev.key"
                class="flex items-start gap-2 px-2 py-1.5 rounded text-xs cursor-pointer border"
                :class="form.events.includes(ev.key) ? 'bg-blue-50 border-blue-300' : 'bg-white border-ink-200'">
                <input type="checkbox" :checked="form.events.includes(ev.key)" @change="toggleEvent(ev.key)" class="w-3 h-3 mt-0.5" />
                <span>
                  <span class="font-mono">{{ ev.key }}</span>
                  <span class="text-ink-400 ml-1">{{ ev.label }}</span>
                </span>
              </label>
            </div>
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">签名密钥（HMAC-SHA256，可选）</label>
            <input v-model="form.secret" class="input" placeholder="留空则不签名" />
            <p class="text-xs text-ink-400 mt-1">
              下游校验：<code>sha256=HMAC(secret, "{timestamp}\n{body}")</code>，配合
              <code>X-Cenkor-Timestamp</code> 防重放。
            </p>
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">描述</label>
            <input v-model="form.description" class="input" placeholder="例：小红书分发 Agent" />
          </div>
          <label class="flex items-center gap-2">
            <input type="checkbox" v-model="form.enabled" /><span class="text-sm">启用</span>
          </label>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button class="btn-ghost" @click="showModal = false">取消</button>
          <button class="btn-primary" @click="save">保存</button>
        </div>
      </div>
    </div>

    <!-- 详情 -->
    <div v-if="detailOpen && detail" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="detailOpen = false">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-2xl p-6 max-h-[85vh] overflow-auto">
        <div class="flex items-start justify-between mb-3">
          <div>
            <h2 class="text-lg font-semibold">投递 #{{ detail.id }}</h2>
            <div class="text-xs text-ink-400 mt-1">
              {{ detail.event }} · {{ fmt(detail.created_at) }} · 尝试 {{ detail.attempts }} 次
            </div>
          </div>
          <span class="px-2 py-0.5 rounded text-xs" :class="STATUS_STYLE[detail.status]">
            {{ STATUS_LABEL[detail.status] || detail.status }}
          </span>
        </div>
        <div class="text-xs space-y-1 mb-3">
          <div><span class="text-ink-400">目标：</span><span class="font-mono">{{ detail.url }}</span></div>
          <div><span class="text-ink-400">Event-Id：</span><span class="font-mono">{{ detail.event_id }}</span></div>
          <div v-if="detail.error"><span class="text-ink-400">错误：</span><span class="text-red-600">{{ detail.error }}</span></div>
          <div v-if="detail.response_snippet">
            <span class="text-ink-400">响应：</span><span class="font-mono">{{ detail.response_snippet }}</span>
          </div>
        </div>
        <div class="text-xs text-ink-400 mb-1">Payload</div>
        <pre class="bg-ink-50 rounded p-3 text-xs overflow-auto max-h-72">{{ JSON.stringify(detail.payload, null, 2) }}</pre>
        <div class="flex justify-end gap-2 mt-4">
          <button class="btn-ghost" @click="detailOpen = false">关闭</button>
          <button class="btn-primary" :disabled="replaying === detail.id" @click="replay(detail)">
            {{ replaying === detail.id ? '投递中…' : '重放这条' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
