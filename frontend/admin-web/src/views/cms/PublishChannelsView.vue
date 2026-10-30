<script setup lang="ts">
/**
 * 分发渠道配置。
 *
 * 每个渠道单独开关、单独测试、单独失败。公众号 Secret 填错不该让官网发布
 * 跟着一起挂 —— 一个渠道配错了，其他渠道照常发。
 *
 * 凭据只显示尾 4 位。改的时候留空或保持掩码表示「不修改」，避免点一次保存
 * 就把密钥覆盖成星号。
 */
import { computed, onMounted, ref } from 'vue'
import { api } from '@/lib/api'

interface Channel {
  id: number
  key: string
  name: string
  type: string
  enabled: boolean
  is_default: boolean
  config: Record<string, unknown>
}

interface JobRow {
  id: number
  entry_id: number
  channel: string
  channel_name: string
  status: string
  attempts: number
  external_url: string | null
  error: string | null
  created_at: string | null
}

interface SetupInfo {
  title: string
  need: string[]
  steps: string[]
}

interface FieldDef {
  key: string
  label: string
  placeholder?: string
  hint?: string
}

const FIELDS: Record<string, FieldDef[]> = {
  builtin: [{ key: 'site_base', label: '站点域名', placeholder: 'https://blog.cenkor.cn', hint: '用于拼原文链接' }],
  webhook: [],
  wechat: [
    { key: 'appid', label: 'AppID' },
    { key: 'secret', label: 'AppSecret' },
    { key: 'thumb_media_id', label: '封面素材 ID', hint: '公众号永久素材的 media_id，必填' },
    { key: 'author', label: '作者名（可选）' },
    { key: 'source_url', label: '原文链接（可选）' },
  ],
  export: [],
}

const channels = ref<Channel[]>([])
const setup = ref<Record<string, SetupInfo>>({})
const jobs = ref<JobRow[]>([])
const loading = ref(false)
const error = ref('')
const saving = ref<string | null>(null)
const testing = ref<string | null>(null)
const testResult = ref<Record<string, { ok: boolean; detail: string }>>({})
const editing = ref<Record<string, Record<string, string>>>({})
const openSetup = ref<string | null>(null)

const orderedChannels = computed(() =>
  [...channels.value].sort((a, b) => (a.is_default === b.is_default ? a.id - b.id : a.is_default ? -1 : 1)),
)

function fieldsOf(c: Channel): FieldDef[] {
  return FIELDS[c.type] || []
}

function draft(c: Channel, key: string): string {
  const d = editing.value[c.key]
  if (d && key in d) return d[key]
  const v = c.config?.[key]
  return typeof v === 'string' ? v : ''
}

function setDraft(c: Channel, key: string, value: string) {
  if (!editing.value[c.key]) editing.value[c.key] = {}
  editing.value[c.key][key] = value
}

function statusText(s: string) {
  return (
    { success: '成功', failed: '失败', pending: '待执行', running: '执行中', skipped: '已跳过' }[s] || s
  )
}

function statusClass(s: string) {
  if (s === 'success') return 'text-emerald-600'
  if (s === 'failed') return 'text-red-600'
  if (s === 'running') return 'text-blue-600'
  return 'text-ink-500'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [ch, st, jb] = await Promise.all([
      api.get('/api/v1/cms/ai/publish/channels'),
      api.get('/api/v1/cms/ai/publish/setup'),
      api.get('/api/v1/cms/ai/publish/jobs', { params: { limit: 30 } }),
    ])
    channels.value = ch.data.items || []
    setup.value = st.data || {}
    jobs.value = jb.data.items || []
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function toggle(c: Channel) {
  const { data } = await api.patch(`/api/v1/cms/ai/publish/channels/${c.key}`, { enabled: !c.enabled })
  Object.assign(c, data)
}

async function save(c: Channel) {
  const patch = editing.value[c.key]
  if (!patch || !Object.keys(patch).length) return
  saving.value = c.key
  try {
    const { data } = await api.patch(`/api/v1/cms/ai/publish/channels/${c.key}`, { config: patch })
    Object.assign(c, data)
    delete editing.value[c.key]
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '保存失败'
  } finally {
    saving.value = null
  }
}

async function test(c: Channel) {
  testing.value = c.key
  try {
    const { data } = await api.post(`/api/v1/cms/ai/publish/channels/${c.key}/test`)
    testResult.value[c.key] = { ok: !!data.ok, detail: data.detail || '' }
  } catch (e: unknown) {
    testResult.value[c.key] = { ok: false, detail: e instanceof Error ? e.message : '测试失败' }
  } finally {
    testing.value = null
  }
}

async function runPending() {
  loading.value = true
  try {
    await api.post('/api/v1/cms/ai/publish/jobs/run-pending', null, { params: { limit: 10 } })
    await load()
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-5">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-lg font-medium text-ink-900">分发渠道</h1>
        <p class="mt-1 text-[13px] text-ink-500">
          内容审核通过后往哪些出口发。每个渠道独立执行、独立重试，一个失败不影响其他。
        </p>
      </div>
      <button class="btn btn-ghost" :disabled="loading" @click="runPending">执行待处理任务</button>
    </div>

    <div v-if="error" class="card border-red-200 bg-red-50 text-[13px] text-red-700">{{ error }}</div>

    <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <div v-for="c in orderedChannels" :key="c.key" class="card space-y-3">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="flex items-center gap-2">
              <span class="text-[15px] font-medium text-ink-900">{{ c.name }}</span>
              <span
                class="rounded px-1.5 py-0.5 text-[11px]"
                :class="c.enabled ? 'bg-emerald-50 text-emerald-700' : 'bg-ink-100 text-ink-500'"
              >
                {{ c.enabled ? '已启用' : '未启用' }}
              </span>
              <span v-if="c.is_default" class="rounded bg-ink-900 px-1.5 py-0.5 text-[11px] text-white">默认</span>
            </div>
            <div class="mt-1 text-[12px] text-ink-400">标识 {{ c.key }} · 类型 {{ c.type }}</div>
          </div>
          <button
            class="rounded-lg border px-2.5 py-1 text-[12px] transition"
            :class="c.enabled ? 'border-ink-200 text-ink-600 hover:bg-ink-50' : 'border-emerald-300 text-emerald-700 hover:bg-emerald-50'"
            @click="toggle(c)"
          >
            {{ c.enabled ? '停用' : '启用' }}
          </button>
        </div>

        <div v-if="fieldsOf(c).length" class="space-y-2">
          <div v-for="f in fieldsOf(c)" :key="f.key">
            <label class="block text-[12px] text-ink-500">{{ f.label }}</label>
            <input
              class="input mt-1 w-full text-[13px]"
              :value="draft(c, f.key)"
              :placeholder="f.placeholder || ''"
              @input="setDraft(c, f.key, ($event.target as HTMLInputElement).value)"
            />
            <div v-if="f.hint" class="mt-0.5 text-[11px] text-ink-400">{{ f.hint }}</div>
          </div>
          <button class="btn btn-primary text-[13px]" :disabled="saving === c.key" @click="save(c)">
            {{ saving === c.key ? '保存中…' : '保存配置' }}
          </button>
        </div>
        <div v-else class="rounded-lg bg-ink-50 px-3 py-2 text-[12px] text-ink-500">
          {{ c.type === 'export' ? '无需配置。发布时直接产出可粘贴的 HTML / 纯文本 / 封面清单。' : '无需在此配置，依赖「系统 / Webhook」里已有的订阅。' }}
        </div>

        <div class="flex flex-wrap items-center gap-2 border-t border-ink-100 pt-3">
          <button class="btn btn-ghost text-[13px]" :disabled="testing === c.key" @click="test(c)">
            {{ testing === c.key ? '测试中…' : '连通性测试' }}
          </button>
          <button class="text-[12px] text-ink-500 hover:text-ink-900" @click="openSetup = openSetup === c.key ? null : c.key">
            {{ openSetup === c.key ? '收起说明' : '怎么配' }}
          </button>
          <span
            v-if="testResult[c.key]"
            class="text-[12px]"
            :class="testResult[c.key].ok ? 'text-emerald-600' : 'text-red-600'"
          >
            {{ testResult[c.key].detail }}
          </span>
        </div>

        <div v-if="openSetup === c.key && setup[c.type]" class="rounded-lg bg-ink-50 p-3 text-[12px] leading-relaxed text-ink-600">
          <div class="mb-1 font-medium text-ink-800">需要准备</div>
          <ul class="mb-2 list-disc pl-4">
            <li v-for="(n, i) in setup[c.type].need" :key="i">{{ n }}</li>
          </ul>
          <div class="mb-1 font-medium text-ink-800">步骤</div>
          <ol class="list-decimal pl-4">
            <li v-for="(s, i) in setup[c.type].steps" :key="i" class="mb-0.5">{{ s }}</li>
          </ol>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="mb-3 flex items-center justify-between">
        <div class="text-[14px] font-medium text-ink-900">最近发布任务</div>
        <button class="text-[12px] text-ink-500 hover:text-ink-900" @click="load">刷新</button>
      </div>
      <div v-if="!jobs.length" class="py-6 text-center text-[13px] text-ink-400">
        还没有发布记录。在内容编辑页点「发布」后会出现在这里。
      </div>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-[13px]">
          <thead>
            <tr class="border-b border-ink-100 text-left text-[12px] text-ink-500">
              <th class="py-2 pr-3 font-normal">条目</th>
              <th class="px-2 py-2 font-normal">渠道</th>
              <th class="px-2 py-2 font-normal">状态</th>
              <th class="px-2 py-2 text-right font-normal">尝试</th>
              <th class="px-2 py-2 font-normal">结果 / 原因</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="j in jobs" :key="j.id" class="border-b border-ink-50 last:border-0">
              <td class="py-2 pr-3 text-ink-700">#{{ j.entry_id }}</td>
              <td class="px-2 py-2 text-ink-700">{{ j.channel_name }}</td>
              <td class="px-2 py-2" :class="statusClass(j.status)">{{ statusText(j.status) }}</td>
              <td class="px-2 py-2 text-right tabular-nums text-ink-500">{{ j.attempts }}</td>
              <td class="max-w-[380px] px-2 py-2">
                <a v-if="j.external_url" :href="j.external_url" target="_blank" class="truncate text-blue-600 hover:underline">
                  {{ j.external_url }}
                </a>
                <span v-else-if="j.error" class="text-[12px] text-red-600">{{ j.error }}</span>
                <span v-else class="text-[12px] text-ink-400">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
