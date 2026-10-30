<script setup lang="ts">
/**
 * 知识库管理。
 *
 * 定位：不是「又一个文件柜」，而是**让 AI 有据可依**的语料入口。
 *
 * 所以页面上有三件事必须有，缺一件这个功能就不可信：
 *   1. 索引状态 —— 传完显示「排队中」再也不动的功能，第二次就没人用了
 *   2. 分片预览 —— 得能看见「这篇文档被切成了什么」，否则不知道 AI 读到的是什么
 *   3. 检索测试 —— 上传 20 份手册后，问一句能不能召回对的段落，比看统计有用得多
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '@/lib/api'

interface KbDoc {
  id: number
  title: string
  source_type: string
  file_name: string
  mime: string
  size_bytes: number
  category: string
  note: string
  status: 'pending' | 'indexing' | 'ready' | 'failed'
  error: string
  chars: number
  chunk_count: number
  indexed_chunks: number
  embed_model: string
  created_at: string
  updated_at: string
}

interface KbChunk {
  seq: number
  heading: string
  heading_path: string
  chars: number
  text: string
  has_vector: boolean
  model: string
}

interface KbStats {
  docs: number
  ready_docs: number
  chunks: number
  indexed_chunks: number
  chars: number
  embed_model: string
  by_status: Record<string, number>
  categories: { name: string; count: number }[]
  limits: { max_chunks_per_doc: number; max_chars_per_doc: number; min_score: number }
}

interface Hit {
  chunk_id: number
  doc_id: number
  doc_title: string
  heading_path: string
  text: string
  chars: number
  score: number
  passed: boolean
}

const loading = ref(false)
const errorMsg = ref('')
const okMsg = ref('')

const docs = ref<KbDoc[]>([])
const total = ref(0)
const stats = ref<KbStats | null>(null)

const q = ref('')
const categoryFilter = ref('')
const statusFilter = ref('')
const page = ref(1)
const pageSize = 20

// ---------- 上传 ----------
const uploading = ref(false)
const uploadCategory = ref('')
const pasteTitle = ref('')
const pasteCategory = ref('')
const pasteText = ref('')
const activeTab = ref<'upload' | 'paste'>('upload')
const fileInput = ref<HTMLInputElement | null>(null)
const dragging = ref(false)

let pollTimer: number | null = null

const pendingCount = computed(
  () => docs.value.filter((d) => d.status === 'pending' || d.status === 'indexing').length,
)

const statusMeta: Record<string, { label: string; cls: string }> = {
  pending: { label: '排队中', cls: 'bg-ink-100 text-ink-600' },
  indexing: { label: '索引中', cls: 'bg-sky-50 text-sky-700' },
  ready: { label: '已就绪', cls: 'bg-emerald-50 text-emerald-700' },
  failed: { label: '失败', cls: 'bg-red-50 text-red-700' },
}

async function loadStats() {
  try {
    const { data } = await api.get('/api/v1/cms/ai/kb/stats')
    stats.value = data
  } catch {
    /* 统计失败不影响列表 */
  }
}

async function loadDocs() {
  loading.value = true
  errorMsg.value = ''
  try {
    const { data } = await api.get('/api/v1/cms/ai/kb/docs', {
      params: {
        q: q.value,
        category: categoryFilter.value,
        status: statusFilter.value,
        page: page.value,
        page_size: pageSize,
      },
    })
    docs.value = data.items
    total.value = data.total
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

// 有文档在索引中就轮询。等到全部结束自动停 —— 常驻轮询会在后台一直打接口
function syncPolling() {
  if (pollTimer) {
    window.clearTimeout(pollTimer)
    pollTimer = null
  }
  if (pendingCount.value > 0) {
    pollTimer = window.setTimeout(async () => {
      await loadDocs()
      await loadStats()
      syncPolling()
    }, 4000)
  }
}

async function refresh() {
  await Promise.all([loadDocs(), loadStats()])
  syncPolling()
}

async function doUpload(file: File) {
  uploading.value = true
  errorMsg.value = ''
  okMsg.value = ''
  try {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('category', uploadCategory.value)
    const { data } = await api.post('/api/v1/cms/ai/kb/docs/upload', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 180000,
    })
    okMsg.value = data.message || '已入库'
    await refresh()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || '上传失败'
  } finally {
    uploading.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

function onPick(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) doUpload(f)
}

function onDrop(e: DragEvent) {
  dragging.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f) doUpload(f)
}

async function doPaste() {
  if (!pasteTitle.value.trim() || !pasteText.value.trim()) {
    errorMsg.value = '标题和正文都要填'
    return
  }
  uploading.value = true
  errorMsg.value = ''
  okMsg.value = ''
  try {
    const { data } = await api.post('/api/v1/cms/ai/kb/docs/paste', {
      title: pasteTitle.value.trim(),
      text: pasteText.value,
      category: pasteCategory.value,
    })
    okMsg.value = data.message || '已入库'
    pasteTitle.value = ''
    pasteText.value = ''
    await refresh()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || '入库失败'
  } finally {
    uploading.value = false
  }
}

// ---------- 详情 ----------
const detailOpen = ref(false)
const detailDoc = ref<KbDoc | null>(null)
const detailChunks = ref<KbChunk[]>([])
const detailText = ref('')
const detailLoading = ref(false)

async function openDetail(doc: KbDoc) {
  detailOpen.value = true
  detailLoading.value = true
  detailDoc.value = doc
  detailChunks.value = []
  detailText.value = ''
  try {
    const { data } = await api.get(`/api/v1/cms/ai/kb/docs/${doc.id}`)
    detailDoc.value = data.doc
    detailChunks.value = data.chunks
    detailText.value = data.text_preview
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || '加载详情失败'
  } finally {
    detailLoading.value = false
  }
}

async function reindex(doc: KbDoc, force = false) {
  try {
    const { data } = await api.post(`/api/v1/cms/ai/kb/docs/${doc.id}/reindex`, null, {
      params: { force },
    })
    okMsg.value = data.queued ? '已加入重建队列' : data.message || '正在索引中'
    await refresh()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || '重建失败'
  }
}

async function removeDoc(doc: KbDoc) {
  if (!window.confirm(`删除《${doc.title}》？删除后 AI 不再引用这份资料。`)) return
  try {
    await api.delete(`/api/v1/cms/ai/kb/docs/${doc.id}`)
    okMsg.value = '已删除'
    if (detailDoc.value?.id === doc.id) detailOpen.value = false
    await refresh()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || '删除失败'
  }
}

// ---------- 检索测试 ----------
const searchQ = ref('')
const searching = ref(false)
const hits = ref<Hit[]>([])
const threshold = ref(0)
const effectiveCount = ref(0)
const searched = ref(false)

async function runSearch() {
  const query = searchQ.value.trim()
  if (!query) return
  searching.value = true
  searched.value = true
  try {
    const { data } = await api.post('/api/v1/cms/ai/kb/search', { query, limit: 8 })
    hits.value = data.hits
    threshold.value = data.threshold
    effectiveCount.value = data.effective_count
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || '检索失败'
    hits.value = []
  } finally {
    searching.value = false
  }
}

function fmtSize(n: number) {
  if (!n) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

function fmtTime(s: string) {
  if (!s) return ''
  return new Date(s).toLocaleString('zh-CN', { hour12: false })
}

onMounted(refresh)
onUnmounted(() => {
  if (pollTimer) window.clearTimeout(pollTimer)
})
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/cms/ai" class="text-sm text-ink-500 hover:text-ink-900">← AI 驾驶舱</router-link>
        <span class="font-semibold">知识库</span>
        <span class="text-xs text-ink-400">产品手册 · FAQ · 历史方案 —— 让 AI 有据可依</span>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-8">
      <p v-if="errorMsg" class="mb-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl px-4 py-2.5">
        {{ errorMsg }}
      </p>
      <p v-if="okMsg" class="mb-4 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-2.5">
        {{ okMsg }}
      </p>

      <!-- 概览 -->
      <div v-if="stats" class="grid gap-4 md:grid-cols-4 mb-6">
        <div class="card">
          <p class="text-xs text-ink-400 mb-1">文档</p>
          <p class="text-3xl font-semibold leading-none">{{ stats.docs }}</p>
          <p class="mt-2 text-[11px] text-ink-400">
            就绪 {{ stats.ready_docs }}
            <span v-if="stats.by_status?.failed"> · 失败 {{ stats.by_status.failed }}</span>
            <span v-if="stats.by_status?.pending || stats.by_status?.indexing">
              · 处理中 {{ (stats.by_status.pending || 0) + (stats.by_status.indexing || 0) }}
            </span>
          </p>
        </div>
        <div class="card">
          <p class="text-xs text-ink-400 mb-1">可检索分片</p>
          <p class="text-3xl font-semibold leading-none">{{ stats.indexed_chunks }}</p>
          <p class="mt-2 text-[11px] text-ink-400">共切出 {{ stats.chunks }} 段</p>
        </div>
        <div class="card">
          <p class="text-xs text-ink-400 mb-1">语料字数</p>
          <p class="text-3xl font-semibold leading-none">{{ stats.chars.toLocaleString() }}</p>
          <p class="mt-2 text-[11px] text-ink-400">抽取后的纯文本量</p>
        </div>
        <div class="card">
          <p class="text-xs text-ink-400 mb-1">向量模型</p>
          <p class="text-sm font-medium leading-tight mt-1 truncate" :title="stats.embed_model">
            {{ stats.embed_model || '未建立索引' }}
          </p>
          <p class="mt-2 text-[11px] text-ink-400">召回门槛 {{ stats.limits?.min_score }}</p>
        </div>
      </div>

      <!-- 入库 -->
      <div class="card mb-6">
        <div class="flex items-center gap-3 mb-4">
          <button
            class="px-3 py-1.5 text-sm rounded-lg border"
            :class="activeTab === 'upload' ? 'bg-ink-900 text-white border-ink-900' : 'border-ink-200 hover:bg-ink-50'"
            @click="activeTab = 'upload'"
          >上传文件</button>
          <button
            class="px-3 py-1.5 text-sm rounded-lg border"
            :class="activeTab === 'paste' ? 'bg-ink-900 text-white border-ink-900' : 'border-ink-200 hover:bg-ink-50'"
            @click="activeTab = 'paste'"
          >粘贴文本</button>
          <span class="text-xs text-ink-400 ml-auto">
            支持 PDF / Word / Excel / 图片 / 视频 / 文本，单文件 ≤ 20MB
          </span>
        </div>

        <div v-if="activeTab === 'upload'" class="flex flex-wrap items-end gap-3">
          <label class="text-sm text-ink-600">
            分类
            <input
              v-model="uploadCategory"
              placeholder="如：产品手册"
              class="ml-2 w-40 px-2 py-1.5 border border-ink-200 rounded-lg text-sm"
            />
          </label>
          <div
            class="flex-1 min-w-[280px] border-2 border-dashed rounded-xl px-4 py-6 text-center cursor-pointer transition-colors"
            :class="dragging ? 'border-ink-900 bg-ink-50' : 'border-ink-200 hover:border-ink-300'"
            @click="fileInput?.click()"
            @dragover.prevent="dragging = true"
            @dragleave.prevent="dragging = false"
            @drop.prevent="onDrop"
          >
            <p class="text-sm text-ink-600">
              {{ uploading ? '正在抽取文本…' : '把文件拖到这里，或点击选择' }}
            </p>
            <p class="mt-1 text-xs text-ink-400">扫描件 PDF 无法提取文字，会直接报错说明原因</p>
          </div>
          <input ref="fileInput" type="file" class="hidden" @change="onPick" />
        </div>

        <div v-else class="space-y-3">
          <div class="flex flex-wrap gap-3">
            <input
              v-model="pasteTitle"
              placeholder="文档标题（如：MES 排产规则说明）"
              class="flex-1 min-w-[240px] px-3 py-2 border border-ink-200 rounded-lg text-sm"
            />
            <input
              v-model="pasteCategory"
              placeholder="分类（如：产品手册）"
              class="w-48 px-3 py-2 border border-ink-200 rounded-lg text-sm"
            />
          </div>
          <textarea
            v-model="pasteText"
            rows="7"
            placeholder="粘贴正文。支持 markdown，用 # 标题分节能让切片更准 —— 每节会被切独立分片，检索命中更精确。"
            class="w-full px-3 py-2 border border-ink-200 rounded-lg text-sm font-mono leading-relaxed"
          />
          <div class="flex items-center gap-3">
            <span class="text-xs text-ink-400">{{ pasteText.length }} 字</span>
            <button
              class="ml-auto px-4 py-2 text-sm rounded-lg bg-ink-900 text-white hover:bg-ink-800 disabled:opacity-50"
              :disabled="uploading"
              @click="doPaste"
            >{{ uploading ? '入库中…' : '入库并索引' }}</button>
          </div>
        </div>
      </div>

      <!-- 检索测试 -->
      <div class="card mb-6">
        <div class="flex items-center justify-between mb-3">
          <h2 class="font-semibold">检索测试</h2>
          <span class="text-xs text-ink-400">问一句，看会召回哪几段 —— 知识库到底有没有用，这里最直接</span>
        </div>
        <div class="flex gap-3">
          <input
            v-model="searchQ"
            placeholder="如：客户交期倒排怎么算？"
            class="flex-1 px-3 py-2 border border-ink-200 rounded-lg text-sm"
            @keyup.enter="runSearch"
          />
          <button
            class="px-4 py-2 text-sm rounded-lg bg-ink-900 text-white hover:bg-ink-800 disabled:opacity-50"
            :disabled="searching"
            @click="runSearch"
          >{{ searching ? '检索中…' : '测试' }}</button>
        </div>

        <div v-if="searched" class="mt-4">
          <p class="text-xs text-ink-500 mb-2">
            召回 {{ hits.length }} 段，其中
            <span :class="effectiveCount > 0 ? 'text-emerald-600 font-medium' : 'text-amber-600 font-medium'">
              {{ effectiveCount }} 段达标
            </span>
            （门槛 {{ threshold }}，未达标的只展示、不会用于 AI 生成）
          </p>
          <div v-if="!hits.length" class="py-6 text-center text-sm text-ink-400">
            没有召回任何内容 —— 检查知识库是否已建立索引。
          </div>
          <ul v-else class="space-y-2">
            <li
              v-for="h in hits"
              :key="h.chunk_id"
              class="rounded-lg border px-3 py-2"
              :class="h.passed ? 'border-ink-200 bg-white' : 'border-ink-100 bg-ink-50/60'"
            >
              <div class="flex items-center gap-2 flex-wrap">
                <span
                  class="text-xs font-mono px-1.5 py-0.5 rounded"
                  :class="h.passed ? 'bg-emerald-50 text-emerald-700' : 'bg-ink-100 text-ink-400'"
                >{{ h.score.toFixed(3) }}</span>
                <span class="text-sm font-medium">{{ h.doc_title }}</span>
                <span class="text-xs text-ink-400">{{ h.heading_path }}</span>
                <span v-if="!h.passed" class="text-[11px] text-ink-400">（低于门槛）</span>
              </div>
              <p class="mt-1 text-xs text-ink-600 leading-relaxed line-clamp-3">{{ h.text }}</p>
            </li>
          </ul>
        </div>
      </div>

      <!-- 文档列表 -->
      <div class="card">
        <div class="flex flex-wrap items-center gap-3 mb-4">
          <h2 class="font-semibold">文档</h2>
          <input
            v-model="q"
            placeholder="搜索标题/文件名"
            class="w-56 px-3 py-1.5 border border-ink-200 rounded-lg text-sm"
            @keyup.enter="page = 1; refresh()"
          />
          <select
            v-model="categoryFilter"
            class="px-2 py-1.5 border border-ink-200 rounded-lg text-sm"
            @change="page = 1; refresh()"
          >
            <option value="">全部分类</option>
            <option v-for="c in stats?.categories || []" :key="c.name" :value="c.name">
              {{ c.name }}（{{ c.count }}）
            </option>
          </select>
          <select
            v-model="statusFilter"
            class="px-2 py-1.5 border border-ink-200 rounded-lg text-sm"
            @change="page = 1; refresh()"
          >
            <option value="">全部状态</option>
            <option value="pending">排队中</option>
            <option value="indexing">索引中</option>
            <option value="ready">已就绪</option>
            <option value="failed">失败</option>
          </select>
          <button
            class="px-3 py-1.5 text-xs rounded-lg border border-ink-200 hover:bg-ink-50"
            @click="refresh"
          >刷新</button>
          <span v-if="pendingCount" class="text-xs text-sky-600">
            {{ pendingCount }} 份处理中，每 4 秒自动刷新
          </span>
          <span class="ml-auto text-xs text-ink-400">共 {{ total }} 份</span>
        </div>

        <div v-if="loading && !docs.length" class="py-16 text-center text-sm text-ink-400">
          加载中…
        </div>
        <div v-else-if="!docs.length" class="py-16 text-center text-sm text-ink-400">
          还没有任何资料。上传一份产品手册或 FAQ，AI 起草时就能引用它。
        </div>

        <table v-else class="w-full text-sm">
          <thead>
            <tr class="text-xs text-ink-400 border-b border-ink-100">
              <th class="text-left font-normal py-2">标题</th>
              <th class="text-left font-normal py-2 w-24">分类</th>
              <th class="text-left font-normal py-2 w-28">状态</th>
              <th class="text-right font-normal py-2 w-20">分片</th>
              <th class="text-right font-normal py-2 w-20 pr-4">字数</th>
              <th class="text-left font-normal py-2 w-40">时间</th>
              <th class="text-right font-normal py-2 w-40">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in docs" :key="d.id" class="border-b border-ink-50 last:border-0">
              <td class="py-2.5 pr-3">
                <button class="text-left hover:underline font-medium" @click="openDetail(d)">
                  {{ d.title }}
                </button>
                <div v-if="d.file_name && d.file_name !== d.title" class="text-xs text-ink-400 truncate max-w-xs">
                  {{ d.file_name }} · {{ fmtSize(d.size_bytes) }}
                </div>
                <div v-if="d.status === 'failed' && d.error" class="text-xs text-red-500 mt-0.5">
                  {{ d.error }}
                </div>
              </td>
              <td class="py-2.5 text-xs text-ink-500">{{ d.category || '—' }}</td>
              <td class="py-2.5">
                <span class="text-xs px-2 py-0.5 rounded-full" :class="statusMeta[d.status]?.cls">
                  {{ statusMeta[d.status]?.label || d.status }}
                </span>
              </td>
              <td class="py-2.5 text-right text-xs text-ink-500">
                {{ d.indexed_chunks }}/{{ d.chunk_count }}
              </td>
              <td class="py-2.5 text-right text-xs text-ink-500 pr-4 tabular-nums">{{ d.chars }}</td>
              <td class="py-2.5 text-xs text-ink-400 tabular-nums">{{ fmtTime(d.created_at) }}</td>
              <td class="py-2.5 text-right whitespace-nowrap">
                <button
                  class="px-2 py-1 text-xs rounded border border-ink-200 hover:bg-ink-50"
                  @click="openDetail(d)"
                >分片</button>
                <button
                  class="ml-1.5 px-2 py-1 text-xs rounded border border-ink-200 hover:bg-ink-50"
                  @click="reindex(d)"
                >重建</button>
                <button
                  class="ml-1.5 px-2 py-1 text-xs rounded border border-red-200 text-red-600 hover:bg-red-50"
                  @click="removeDoc(d)"
                >删除</button>
              </td>
            </tr>
          </tbody>
        </table>

        <div v-if="total > pageSize" class="flex items-center justify-end gap-2 mt-4">
          <button
            class="px-3 py-1.5 text-xs rounded-lg border border-ink-200 disabled:opacity-40"
            :disabled="page <= 1"
            @click="page--; refresh()"
          >上一页</button>
          <span class="text-xs text-ink-400">{{ page }} / {{ Math.ceil(total / pageSize) }}</span>
          <button
            class="px-3 py-1.5 text-xs rounded-lg border border-ink-200 disabled:opacity-40"
            :disabled="page >= Math.ceil(total / pageSize)"
            @click="page++; refresh()"
          >下一页</button>
        </div>
      </div>
    </main>

    <!-- 详情抽屉 -->
    <div v-if="detailOpen" class="fixed inset-0 z-40 flex justify-end">
      <div class="absolute inset-0 bg-black/30" @click="detailOpen = false" />
      <div class="relative w-full max-w-2xl h-full bg-white shadow-xl overflow-y-auto">
        <div class="sticky top-0 bg-white border-b border-ink-200 px-5 py-3 flex items-center gap-3">
          <div class="min-w-0">
            <p class="font-semibold truncate">{{ detailDoc?.title }}</p>
            <p class="text-xs text-ink-400">
              {{ detailDoc?.category || '未分类' }} ·
              {{ detailDoc?.chars }} 字 · {{ detailChunks.length }} 段
              <span v-if="detailDoc?.embed_model"> · {{ detailDoc.embed_model }}</span>
            </p>
          </div>
          <button class="ml-auto text-sm text-ink-500 hover:text-ink-900" @click="detailOpen = false">
            关闭
          </button>
        </div>

        <div v-if="detailLoading" class="p-5 text-sm text-ink-400">加载中…</div>
        <div v-else class="p-5 space-y-5">
          <p
            v-if="detailDoc?.error"
            class="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2"
          >{{ detailDoc.error }}</p>

          <div v-if="detailDoc?.note" class="text-xs text-ink-500 bg-ink-50 rounded-lg px-3 py-2">
            {{ detailDoc.note }}
          </div>

          <section>
            <h3 class="text-sm font-semibold mb-2">检索分片（{{ detailChunks.length }}）</h3>
            <p class="text-xs text-ink-400 mb-3">
              AI 真正读到的是这些片段，不是整篇文档。分片过碎会丢上下文，过长会稀释语义。
            </p>
            <ul class="space-y-2">
              <li
                v-for="c in detailChunks"
                :key="c.seq"
                class="rounded-lg border border-ink-100 px-3 py-2"
              >
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="text-[11px] font-mono text-ink-400">#{{ c.seq + 1 }}</span>
                  <span class="text-xs font-medium text-ink-700">{{ c.heading || '（无小节）' }}</span>
                  <span class="text-[11px] text-ink-400">{{ c.chars }} 字</span>
                  <span
                    class="text-[11px] px-1.5 py-0.5 rounded"
                    :class="c.has_vector ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'"
                  >{{ c.has_vector ? '已向量化' : '缺向量' }}</span>
                </div>
                <p class="mt-1 text-xs text-ink-600 leading-relaxed whitespace-pre-wrap">{{ c.text }}</p>
              </li>
            </ul>
          </section>

          <section v-if="detailText">
            <h3 class="text-sm font-semibold mb-2">抽取文本（前 4000 字）</h3>
            <pre class="text-xs text-ink-600 bg-ink-50 rounded-lg p-3 whitespace-pre-wrap leading-relaxed max-h-96 overflow-y-auto">{{ detailText }}</pre>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>
