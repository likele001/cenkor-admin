<script setup lang="ts">
/**
 * 内链管理：分析建议 → 保存待审 → 审核（通过/拒绝）→ 标记已插入 → 删除
 *
 * 内链是「文章 → 文章」的有向关系，和标签（文章 → 主题词）是两套互补体系：
 * 内链管「读到这，顺手点过去」，标签管「同主题归档」。这里只管关系本身的生命周期，
 * 真正把 <a> 写进正文由编辑页负责（emit apply-link 向上抛）。
 *
 * 状态机：pending → approved → inserted / rejected
 * 拒绝（rejected）后允许对同一条重新建议 —— 后端唯一索引已排除该状态。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/lib/api'

interface LinkSuggestion {
  entry_id: number
  title: string
  slug?: string | null
  anchor_text: string
  reason: string
  insert_after: string
  source_url: string
}

interface SavedLink {
  id: number
  target_entry_id: number
  target_title: string | null
  target_slug: string | null
  target_url: string | null
  anchor_text: string
  insert_after: string | null
  status: string
  created_at: string | null
}

const props = withDefaults(
  defineProps<{
    entryId: number | null
    disabled?: boolean
  }>(),
  { disabled: false },
)

const emit = defineEmits<{
  (e: 'apply-link', v: { anchorText: string; url: string; title: string }): void
}>()

const STATUS_META: Record<string, { label: string; cls: string }> = {
  pending: { label: '待审', cls: 'bg-amber-50 text-amber-700 border-amber-200' },
  approved: { label: '已通过', cls: 'bg-blue-50 text-blue-700 border-blue-200' },
  inserted: { label: '已插入', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  rejected: { label: '已拒绝', cls: 'bg-ink-100 text-ink-500 border-ink-200' },
}

const FILTERS = [
  { key: '', label: '全部' },
  { key: 'pending', label: '待审' },
  { key: 'approved', label: '已通过' },
  { key: 'inserted', label: '已插入' },
  { key: 'rejected', label: '已拒绝' },
] as const

const busy = ref('')
const errMsg = ref('')
const tip = ref('')
const suggestions = ref<LinkSuggestion[]>([])
const saved = ref<SavedLink[]>([])
const counts = ref<Record<string, number>>({})
const filter = ref<string>('')
/** 已保存过的目标条目：避免同一条建议被重复存 */
const savedTargetIds = ref<Set<number>>(new Set())
const didApply = ref<Record<string, boolean>>({})

const canOperate = computed(() => !!props.entryId && !props.disabled && !busy.value)

const visibleSaved = computed(() =>
  filter.value ? saved.value.filter((l) => l.status === filter.value) : saved.value,
)

function errText(e: any): string {
  const d = e?.response?.data?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) {
    return d.map((x: any) => x?.msg || x?.error).filter(Boolean).join('; ')
  }
  return e?.message || '请求失败'
}

async function loadSaved() {
  if (!props.entryId) {
    saved.value = []
    counts.value = {}
    savedTargetIds.value = new Set()
    return
  }
  try {
    const { data } = await api.get(
      `/api/v1/cms/ai/entries/${props.entryId}/internal-links`,
    )
    saved.value = (data.items || []) as SavedLink[]
    counts.value = (data.counts || {}) as Record<string, number>
    savedTargetIds.value = new Set(
      saved.value.filter((l) => l.status !== 'rejected').map((l) => l.target_entry_id),
    )
  } catch (e: any) {
    errMsg.value = errText(e)
  }
}

async function analyze() {
  if (!canOperate.value) return
  busy.value = 'analyze'
  errMsg.value = ''
  tip.value = ''
  suggestions.value = []
  try {
    // 召回 + LLM 精选在后端完成，这一步要调模型，给到 2 分钟
    const { data } = await api.get(
      `/api/v1/cms/ai/entries/${props.entryId}/link-suggestions`,
      { params: { max_links: 3, candidates: 8 }, timeout: 120_000 },
    )
    suggestions.value = (data.links || []) as LinkSuggestion[]
    if (data.warning) tip.value = data.warning
    else if (!suggestions.value.length) tip.value = '没有找到值得互链的内容'
  } catch (e: any) {
    errMsg.value = errText(e)
  } finally {
    busy.value = ''
  }
}

async function saveSuggestion(s: LinkSuggestion) {
  if (!canOperate.value) return
  busy.value = `save-${s.entry_id}`
  errMsg.value = ''
  try {
    await api.post(`/api/v1/cms/ai/entries/${props.entryId}/internal-links`, {
      target_entry_id: s.entry_id,
      anchor_text: s.anchor_text,
      insert_after: s.insert_after || null,
    })
    tip.value = `已保存「${s.anchor_text}」为待审`
    await loadSaved()
  } catch (e: any) {
    errMsg.value = errText(e)
  } finally {
    busy.value = ''
  }
}

async function saveAll() {
  if (!canOperate.value) return
  busy.value = 'save-all'
  errMsg.value = ''
  let ok = 0
  try {
    for (const s of suggestions.value) {
      if (savedTargetIds.value.has(s.entry_id)) continue
      await api.post(`/api/v1/cms/ai/entries/${props.entryId}/internal-links`, {
        target_entry_id: s.entry_id,
        anchor_text: s.anchor_text,
        insert_after: s.insert_after || null,
      })
      ok += 1
    }
    tip.value = ok ? `已保存 ${ok} 条待审` : '这些建议都已保存过'
    await loadSaved()
  } catch (e: any) {
    errMsg.value = errText(e)
  } finally {
    busy.value = ''
  }
}

async function review(link: SavedLink, status: string) {
  if (!canOperate.value) return
  busy.value = `review-${link.id}`
  errMsg.value = ''
  try {
    await api.patch(`/api/v1/cms/ai/internal-links/${link.id}`, { status })
    await loadSaved()
  } catch (e: any) {
    errMsg.value = errText(e)
  } finally {
    busy.value = ''
  }
}

async function removeLink(link: SavedLink) {
  if (!canOperate.value) return
  const name = link.target_title || `#${link.target_entry_id}`
  if (!window.confirm(`删除这条内链？\n《${name}》锚文本：${link.anchor_text}`)) return
  busy.value = `del-${link.id}`
  errMsg.value = ''
  try {
    await api.delete(`/api/v1/cms/ai/internal-links/${link.id}`)
    tip.value = '已删除'
    await loadSaved()
  } catch (e: any) {
    errMsg.value = errText(e)
  } finally {
    busy.value = ''
  }
}

function insert(anchorText: string, url: string, title: string, key: string) {
  if (!url) {
    errMsg.value = '拿不到目标地址，无法插入'
    return
  }
  emit('apply-link', { anchorText, url, title })
  didApply.value = { ...didApply.value, [key]: true }
  tip.value = `已在正文追加「${anchorText}」，位置可再调整`
}

onMounted(loadSaved)
watch(
  () => props.entryId,
  () => {
    suggestions.value = []
    filter.value = ''
    errMsg.value = ''
    tip.value = ''
    didApply.value = {}
    loadSaved()
  },
)
</script>

<template>
  <div class="space-y-2">
    <div class="flex items-center justify-between">
      <span class="text-xs font-medium text-ink-700">内链管理</span>
      <button
        class="text-xs text-violet-600 hover:text-violet-800 disabled:text-ink-300"
        :disabled="!canOperate"
        title="用向量召回候选，再由模型精选该不该链"
        @click="analyze"
      >
        {{ busy === 'analyze' ? '分析中…' : '分析建议' }}
      </button>
    </div>

    <p v-if="!entryId" class="text-xs text-ink-400">先保存一次，再管内链</p>

    <template v-else>
      <!-- 状态统计兼筛选 -->
      <div v-if="saved.length" class="flex flex-wrap gap-1">
        <button
          v-for="f in FILTERS"
          :key="f.key"
          class="px-1.5 py-0.5 text-xs rounded border transition-colors"
          :class="filter === f.key
            ? 'bg-ink-900 text-white border-ink-900'
            : 'bg-white text-ink-600 border-ink-200 hover:border-ink-400'"
          @click="filter = f.key"
        >
          {{ f.label }}<span v-if="f.key && counts[f.key]" class="ml-0.5">{{ counts[f.key] }}</span>
        </button>
      </div>

      <p v-if="errMsg" class="text-xs text-red-600 leading-relaxed">{{ errMsg }}</p>
      <p v-if="tip" class="text-xs text-ink-500 leading-relaxed">{{ tip }}</p>

      <!-- AI 建议 -->
      <div v-if="suggestions.length" class="space-y-1.5">
        <div class="flex items-center justify-between">
          <span class="text-xs text-ink-400">AI 建议（{{ suggestions.length }}）</span>
          <button
            class="text-xs text-violet-600 hover:text-violet-800 disabled:text-ink-300"
            :disabled="!canOperate"
            @click="saveAll"
          >
            {{ busy === 'save-all' ? '保存中…' : '全部保存' }}
          </button>
        </div>
        <div
          v-for="s in suggestions"
          :key="s.entry_id"
          class="border border-violet-200 rounded-lg px-2.5 py-2 bg-violet-50"
        >
          <div class="text-xs text-ink-800 font-medium truncate">《{{ s.title }}》</div>
          <div class="text-xs text-ink-500 mt-0.5">
            锚文本：<span class="text-violet-700">{{ s.anchor_text }}</span>
          </div>
          <div v-if="s.reason" class="text-xs text-ink-500 mt-1 leading-relaxed">{{ s.reason }}</div>
          <div class="flex gap-1 mt-1.5">
            <button
              class="btn-ghost text-xs px-2 py-0.5"
              @click="insert(s.anchor_text, s.source_url, s.title, `s-${s.entry_id}`)"
            >
              {{ didApply[`s-${s.entry_id}`] ? '再插入' : '插入正文' }}
            </button>
            <button
              class="btn-ghost text-xs px-2 py-0.5 disabled:text-ink-300"
              :disabled="savedTargetIds.has(s.entry_id) || busy === `save-${s.entry_id}`"
              @click="saveSuggestion(s)"
            >
              {{ savedTargetIds.has(s.entry_id)
                ? '已保存'
                : busy === `save-${s.entry_id}` ? '保存中…' : '保存待审' }}
            </button>
          </div>
        </div>
      </div>

      <!-- 已保存的内链 -->
      <div v-if="visibleSaved.length" class="space-y-1.5">
        <div class="text-xs text-ink-400">已保存（{{ visibleSaved.length }}）</div>
        <div
          v-for="l in visibleSaved"
          :key="l.id"
          class="border border-ink-200 rounded-lg px-2.5 py-2 bg-ink-50"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="text-xs text-ink-800 font-medium truncate">
                《{{ l.target_title || `#${l.target_entry_id}` }}》
              </div>
              <div class="text-xs text-ink-500 mt-0.5">
                锚文本：<span class="text-ink-700">{{ l.anchor_text }}</span>
              </div>
            </div>
            <span
              class="text-xs px-1.5 py-0.5 rounded border shrink-0"
              :class="STATUS_META[l.status]?.cls || 'bg-ink-100 text-ink-500 border-ink-200'"
            >
              {{ STATUS_META[l.status]?.label || l.status }}
            </span>
          </div>
          <div class="flex flex-wrap gap-1 mt-1.5">
            <button
              v-if="l.target_url"
              class="btn-ghost text-xs px-2 py-0.5"
              @click="insert(l.anchor_text, l.target_url, l.target_title || '', `l-${l.id}`)"
            >
              {{ didApply[`l-${l.id}`] ? '再插入' : '插入正文' }}
            </button>
            <button
              v-if="l.status === 'pending'"
              class="btn-ghost text-xs px-2 py-0.5 disabled:text-ink-300"
              :disabled="!canOperate"
              @click="review(l, 'approved')"
            >通过</button>
            <button
              v-if="l.status !== 'inserted'"
              class="btn-ghost text-xs px-2 py-0.5 disabled:text-ink-300"
              :disabled="!canOperate"
              @click="review(l, 'inserted')"
            >标记已插入</button>
            <button
              v-if="l.status !== 'rejected'"
              class="btn-ghost text-xs px-2 py-0.5 text-ink-500 disabled:text-ink-300"
              :disabled="!canOperate"
              @click="review(l, 'rejected')"
            >拒绝</button>
            <button
              class="btn-ghost text-xs px-2 py-0.5 text-red-600 disabled:text-ink-300"
              :disabled="!canOperate"
              @click="removeLink(l)"
            >删除</button>
          </div>
        </div>
      </div>

      <p v-else-if="saved.length" class="text-xs text-ink-400">该状态下没有内链</p>
      <p v-else-if="!suggestions.length && !busy" class="text-xs text-ink-400">
        还没有内链。点「分析建议」找出该互链的内容，保存后可审核管理。
      </p>
      <p v-if="suggestions.length" class="text-xs text-ink-400">
        插入会追加到正文「相关阅读」段落，位置保存后仍可调整
      </p>
    </template>
  </div>
</template>
