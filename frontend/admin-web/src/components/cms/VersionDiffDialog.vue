<script setup lang="ts">
/**
 * 版本对比弹层（M1·P0 版本控制的续篇）
 *
 * 审核流的痛点是「看不到改了什么」，只能整篇重读 —— 这会让审批退化成
 * 走个流程。这个弹层把两版快照摊成左右对照：哪段是新增、哪段被删、
 * 哪段改了、哪些字段变了，一屏看完。
 *
 * 两个取舍：
 * 1. 不渲染 HTML，只显示纯文本。对比场景下要看的是「文字差异」，
 *    渲染 HTML 反而会因为标签层面的细微差别造成视觉误导；同时避开 v-html 的 XSS 面。
 *    但会从首标签判断段落类型（标题加粗、列表加符号），保住层次感。
 * 2. 左右两栏放进同一个 grid 行里，而不是两个独立滚动容器。
 *    两栏各自滚动的话，滚动同步一定会飘；同一行两格天然对齐。
 */
import { computed, ref, watch } from 'vue'
import { api } from '@/lib/api'

interface VersionMeta {
  version: number
  note?: string | null
  created_at?: string | null
  created_by?: number | null
}

interface DiffSide {
  no: number | null
  html: string
  text: string
  empty: boolean
}

interface DiffRow {
  type: 'equal' | 'insert' | 'delete' | 'replace'
  left: DiffSide | null
  right: DiffSide | null
}

interface FieldItem {
  key: string
  type: string
  from: string
  to: string
}

interface FieldDiff {
  field: string
  label: string
  type: string
  from?: string
  to?: string
  items?: FieldItem[]
}

interface DiffPayload {
  left: VersionMeta
  right: VersionMeta
  text: { rows: DiffRow[]; stats: Record<string, number>; left_lines: number; right_lines: number }
  fields: FieldDiff[]
  has_changes: boolean
  summary: Record<string, number>
}

const props = defineProps<{
  open: boolean
  entryId: number
  versions: VersionMeta[]
  /** 从「某一版」的对比按钮进来时，以它为右侧（新版），左侧自动取它的上一版 */
  initialTo?: number | null
}>()

const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()

const fromVersion = ref<number | null>(null)
const toVersion = ref<number | null>(null)
const loading = ref(false)
const error = ref('')
const data = ref<DiffPayload | null>(null)
const tab = ref<'text' | 'fields'>('text')

const canCompare = computed(() => props.versions.length >= 2)

const statLine = computed(() => {
  const s = data.value?.summary
  if (!s) return ''
  const parts: string[] = []
  if (s.changed) parts.push(`修改 ${s.changed} 段`)
  if (s.added) parts.push(`新增 ${s.added} 段`)
  if (s.removed) parts.push(`删除 ${s.removed} 段`)
  if (s.fields_changed) parts.push(`${s.fields_changed} 个字段`)
  return parts.length ? parts.join(' · ') : '两版内容一致'
})

async function load() {
  if (!canCompare.value || fromVersion.value == null || toVersion.value == null) return
  if (fromVersion.value === toVersion.value) {
    error.value = '请选择两个不同的版本'
    data.value = null
    return
  }
  loading.value = true
  error.value = ''
  try {
    const { data: res } = await api.get(
      `/api/v1/cms/entries/${props.entryId}/versions/diff`,
      { params: { from: fromVersion.value, to: toVersion.value } },
    )
    data.value = res
    // 只有字段变化时自动切到「字段变化」，不然用户会以为没差别
    if (res?.text?.stats) {
      const t = res.text.stats
      const textChanged = (t.added || 0) + (t.removed || 0) + (t.changed || 0) > 0
      tab.value = textChanged ? 'text' : 'fields'
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
    data.value = null
  } finally {
    loading.value = false
  }
}

function initSelectors() {
  // versions 是倒序（最新在前）
  if (!props.versions.length) return
  const asc = [...props.versions].sort((a, b) => a.version - b.version)
  const target = props.initialTo ?? asc[asc.length - 1].version
  const idx = asc.findIndex((v) => v.version === target)
  if (idx > 0) {
    toVersion.value = asc[idx].version
    fromVersion.value = asc[idx - 1].version
  } else if (idx === 0 && asc.length >= 2) {
    // 选的是最早一版，没有更早的，往后退一格
    toVersion.value = asc[1].version
    fromVersion.value = asc[0].version
  } else {
    toVersion.value = asc[asc.length - 1].version
    fromVersion.value = asc.length >= 2 ? asc[asc.length - 2].version : null
  }
  tab.value = 'text'
}

watch(
  () => props.open,
  (v) => {
    if (!v) return
    initSelectors()
    load()
  },
)

function close() {
  emit('update:open', false)
}

/** 从首个块级标签判断行的视觉类型，用来还原层次（不渲染 HTML）。 */
function lineKind(side: DiffSide | null): string {
  if (!side?.html) return 'normal'
  const m = /^\s*<(h[1-6]|li|pre|blockquote|td|th)\b/i.exec(side.html)
  if (!m) return 'normal'
  const tag = m[1].toLowerCase()
  if (tag.startsWith('h')) return 'heading'
  if (tag === 'li') return 'list'
  if (tag === 'pre') return 'code'
  return 'normal'
}

function cellClass(row: DiffRow, side: 'left' | 'right'): string {
  const own = row[side]
  const base = 'px-2 py-1 border-b border-ink-100 align-top whitespace-pre-wrap break-words'
  if (!own) return `${base} bg-ink-50/60`
  if (row.type === 'equal') return `${base} text-ink-600`
  if (row.type === 'delete') return `${base} bg-red-50 text-red-800`
  if (row.type === 'insert') return `${base} bg-green-50 text-green-800`
  // replace：左侧表示被替换掉的，右侧表示新内容
  return side === 'left' ? `${base} bg-amber-50 text-amber-900` : `${base} bg-green-50 text-green-800`
}

function kindClass(kind: string): string {
  if (kind === 'heading') return 'font-medium text-[13px]'
  if (kind === 'code') return 'font-mono'
  if (kind === 'list') return 'pl-3'
  return ''
}

function fmtTime(s?: string | null) {
  return s ? new Date(s).toLocaleString() : ''
}
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
    @click.self="close"
  >
    <div class="bg-white rounded-lg shadow-xl w-full max-w-5xl max-h-[88vh] flex flex-col">
      <!-- 头部 -->
      <div class="flex items-center justify-between gap-3 px-5 py-3 border-b">
        <h3 class="font-medium text-sm">版本对比</h3>
        <div class="flex items-center gap-2 text-xs">
          <template v-if="canCompare">
            <select v-model.number="fromVersion" class="input py-1 text-xs w-28" @change="load">
              <option v-for="v in versions" :key="v.version" :value="v.version">
                v{{ v.version }} {{ v.note || '' }}
              </option>
            </select>
            <span class="text-ink-400">→</span>
            <select v-model.number="toVersion" class="input py-1 text-xs w-28" @change="load">
              <option v-for="v in versions" :key="v.version" :value="v.version">
                v{{ v.version }} {{ v.note || '' }}
              </option>
            </select>
          </template>
          <button class="text-ink-400 hover:text-ink-600 text-lg leading-none px-1" @click="close">✕</button>
        </div>
      </div>

      <!-- 摘要 -->
      <div v-if="canCompare" class="px-5 py-2 border-b bg-ink-50/50 text-xs text-ink-600">
        <template v-if="loading">加载中…</template>
        <template v-else-if="error">
          <span class="text-red-600">{{ error }}</span>
        </template>
        <template v-else-if="data">
          <span :class="data.has_changes ? 'text-ink-700 font-medium' : 'text-ink-400'">{{ statLine }}</span>
          <span class="text-ink-400 ml-3">
            v{{ data.left.version }} {{ fmtTime(data.left.created_at) }}
            → v{{ data.right.version }} {{ fmtTime(data.right.created_at) }}
          </span>
        </template>
      </div>

      <!-- 版本不足 -->
      <div v-if="!canCompare" class="flex-1 flex items-center justify-center text-xs text-ink-400 p-10">
        该条目只有 1 个版本快照，没有可比对的上一版。再保存一次就会出现对比。
      </div>

      <template v-else>
        <!-- Tab -->
        <div class="flex gap-1 px-5 pt-2 border-b text-xs">
          <button
            class="px-3 py-1.5 rounded-t"
            :class="tab === 'text' ? 'bg-white border border-b-white -mb-px text-ink-800' : 'text-ink-400 hover:text-ink-600'"
            @click="tab = 'text'"
          >
            正文对比
          </button>
          <button
            class="px-3 py-1.5 rounded-t"
            :class="tab === 'fields' ? 'bg-white border border-b-white -mb-px text-ink-800' : 'text-ink-400 hover:text-ink-600'"
            @click="tab = 'fields'"
          >
            字段变化
            <span v-if="data?.fields?.length" class="ml-1 text-amber-600">{{ data.fields.length }}</span>
          </button>
        </div>

        <!-- 正文对比 -->
        <div v-if="tab === 'text'" class="flex-1 overflow-auto">
          <div v-if="loading" class="p-8 text-center text-xs text-ink-400">加载中…</div>
          <div v-else-if="!data" class="p-8 text-center text-xs text-ink-400">{{ error || '暂无数据' }}</div>
          <div v-else-if="!data.text.rows.length" class="p-8 text-center text-xs text-ink-400">
            两版正文都为空
          </div>
          <div v-else>
            <div class="grid grid-cols-2 sticky top-0 bg-ink-50 border-b text-[11px] text-ink-500 z-10">
              <div class="px-2 py-1">v{{ data.left.version }}</div>
              <div class="px-2 py-1">v{{ data.right.version }}</div>
            </div>
            <div class="grid grid-cols-2 text-xs leading-relaxed">
              <template v-for="(row, i) in data.text.rows" :key="i">
                <div :class="cellClass(row, 'left')" class="flex gap-2">
                  <span class="text-ink-300 select-none w-6 shrink-0 text-right">{{ row.left?.no ?? '' }}</span>
                  <span :class="kindClass(lineKind(row.left))" class="min-w-0 flex-1">
                    {{ row.left ? (row.left.empty ? '（空行）' : row.left.text) : '' }}
                  </span>
                </div>
                <div :class="cellClass(row, 'right')" class="flex gap-2">
                  <span class="text-ink-300 select-none w-6 shrink-0 text-right">{{ row.right?.no ?? '' }}</span>
                  <span :class="kindClass(lineKind(row.right))" class="min-w-0 flex-1">
                    {{ row.right ? (row.right.empty ? '（空行）' : row.right.text) : '' }}
                  </span>
                </div>
              </template>
            </div>
          </div>
        </div>

        <!-- 字段变化 -->
        <div v-else class="flex-1 overflow-auto p-4 space-y-3">
          <div v-if="loading" class="text-center text-xs text-ink-400 py-8">加载中…</div>
          <div v-else-if="!data" class="text-center text-xs text-ink-400 py-8">{{ error || '暂无数据' }}</div>
          <div v-else-if="!data.fields.length" class="text-center text-xs text-ink-400 py-8">
            两个版本的字段完全一致
          </div>
          <template v-else>
          <div v-for="f in data.fields" :key="f.field" class="border rounded p-3">
            <div class="text-xs text-ink-500 mb-2">{{ f.label }}</div>

            <!-- 结构化字段：逐 key -->
            <div v-if="f.items" class="space-y-1">
              <div
                v-for="it in f.items"
                :key="it.key"
                class="grid grid-cols-[110px_1fr_1fr] gap-2 text-xs items-start"
              >
                <span class="font-mono text-ink-500 truncate" :title="it.key">{{ it.key }}</span>
                <span class="bg-red-50 text-red-800 rounded px-1.5 py-0.5 whitespace-pre-wrap break-words">
                  {{ it.from || '（空）' }}
                </span>
                <span class="bg-green-50 text-green-800 rounded px-1.5 py-0.5 whitespace-pre-wrap break-words">
                  {{ it.to || '（空）' }}
                </span>
              </div>
            </div>

            <!-- 标量字段 -->
            <div v-else class="grid grid-cols-2 gap-2 text-xs">
              <span class="bg-red-50 text-red-800 rounded px-2 py-1 whitespace-pre-wrap break-words">
                {{ f.from || '（空）' }}
              </span>
              <span class="bg-green-50 text-green-800 rounded px-2 py-1 whitespace-pre-wrap break-words">
                {{ f.to || '（空）' }}
              </span>
            </div>
          </div>
          </template>
        </div>
      </template>
    </div>
  </div>
</template>
