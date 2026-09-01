<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
import { api } from '@/lib/api'

interface Block { __id: string; type: string; data: any }
interface PaletteItem { type: string; label: string; icon: string; defaultData: any }

const PALETTE: PaletteItem[] = [
  { type: 'hero', label: '主视觉 Hero', icon: '🖼', defaultData: { title: '大标题', subtitle: '副标题文案' } },
  { type: 'heading', label: '标题', icon: '🔤', defaultData: { text: '小标题', level: 2 } },
  { type: 'text', label: '文本', icon: '📝', defaultData: { text: '正文内容…' } },
  { type: 'image', label: '图片', icon: '🏞', defaultData: { src: '', alt: '' } },
  { type: 'list', label: '列表', icon: '☑', defaultData: { items: ['条目一', '条目二'] } },
  { type: 'html', label: '自定义 HTML', icon: '🧩', defaultData: { html: '<div>自定义代码</div>' } },
]
const BLOCK_LABEL: Record<string, string> = Object.fromEntries(PALETTE.map((p) => [p.type, p.label]))

interface Page { id: number; key: string; title: string; schema: any[]; status: string; published_at: string | null }

const pages = ref<Page[]>([])

// ---- 编辑器状态 ----
const editorOpen = ref(false)
const editing = ref<Page | null>(null)
const formKey = ref('')
const formTitle = ref('')
const blocks = ref<Block[]>([])
const selectedId = ref<string | null>(null)

let _seq = 0
const uid = () => `b_${Date.now().toString(36)}_${(_seq++).toString(36)}`

function esc(v: any): string {
  return String(v == null ? '' : v).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] as string),
  )
}

function normalizeData(type: string, data: any): any {
  const d = data || {}
  switch (type) {
    case 'hero': return { title: d.title ?? '', subtitle: d.subtitle ?? '' }
    case 'heading': return { text: d.text ?? '', level: [1, 2, 3, 4, 5, 6].includes(d.level) ? d.level : 2 }
    case 'text': return { text: d.text ?? '' }
    case 'image': return { src: d.src ?? '', alt: d.alt ?? '' }
    case 'list': return { items: Array.isArray(d.items) ? d.items.map((x: any) => String(x)) : [] }
    case 'html': return { html: d.html ?? '' }
    default: return {}
  }
}

function previewHtml(b: Block): string {
  const d = b.data || {}
  switch (b.type) {
    case 'hero':
      return `<div class="pv-hero"><h2>${esc(d.title)}</h2><p>${esc(d.subtitle)}</p></div>`
    case 'heading': {
      const lvl = [1, 2, 3, 4, 5, 6].includes(d.level) ? d.level : 2
      return `<h${lvl} class="pv-h">${esc(d.text)}</h${lvl}>`
    }
    case 'text':
      return `<p class="pv-p">${esc(d.text)}</p>`
    case 'image':
      return d.src
        ? `<img class="pv-img" src="${esc(d.src)}" alt="${esc(d.alt)}" />`
        : `<div class="pv-empty">🏞 图片（未设置 src）</div>`
    case 'list': {
      const lis = (d.items || []).map((i: any) => `<li>${esc(i)}</li>`).join('')
      return `<ul class="pv-ul">${lis}</ul>`
    }
    case 'html':
      return d.html || ''
    default:
      return ''
  }
}

// ---- 拖拽：组件库克隆 -> 画布 ----
function clonePalette(orig: any): Block {
  return { __id: uid(), type: orig.type, data: JSON.parse(JSON.stringify(orig.defaultData)) }
}

function onCanvasChange(e: any) {
  if (e && e.added) {
    const el = e.added.element
    if (!el.__id) el.__id = uid()
    const tpl = PALETTE.find((p) => p.type === el.type)
    if (tpl && el.data === tpl.defaultData) el.data = JSON.parse(JSON.stringify(tpl.defaultData))
  }
}

// ---- 操作 ----
function addBlock(type: string) {
  const p = PALETTE.find((x) => x.type === type)
  if (!p) return
  const b: Block = { __id: uid(), type, data: JSON.parse(JSON.stringify(p.defaultData)) }
  blocks.value.push(b)
  selectedId.value = b.__id
}
function selectBlock(id: string) { selectedId.value = id }
const selected = computed(() => blocks.value.find((b) => b.__id === selectedId.value) || null)
function removeBlock(id: string) {
  blocks.value = blocks.value.filter((b) => b.__id !== id)
  if (selectedId.value === id) selectedId.value = null
}
function duplicateBlock(id: string) {
  const b = blocks.value.find((x) => x.__id === id)
  if (!b) return
  const copy: Block = { __id: uid(), type: b.type, data: JSON.parse(JSON.stringify(b.data)) }
  const idx = blocks.value.findIndex((x) => x.__id === id)
  blocks.value.splice(idx + 1, 0, copy)
  selectedId.value = copy.__id
}

// ---- 页面列表 ----
async function loadPages() {
  try {
    const { data } = await api.get('/api/v1/builder/pages')
    pages.value = data.items || []
  } catch (e: any) { alert(e?.response?.data?.detail || '加载失败') }
}
function openCreate() {
  editing.value = null
  formKey.value = ''
  formTitle.value = ''
  blocks.value = []
  selectedId.value = null
  editorOpen.value = true
}
function openEdit(p: Page) {
  editing.value = p
  formKey.value = p.key
  formTitle.value = p.title
  blocks.value = (p.schema || []).map((b: any) => ({
    __id: uid(),
    type: b.type,
    data: normalizeData(b.type, b.data),
  }))
  selectedId.value = null
  editorOpen.value = true
}
async function save() {
  const schema = blocks.value.map((b) => ({ type: b.type, data: b.data }))
  try {
    if (editing.value) {
      await api.patch(`/api/v1/builder/pages/${editing.value.id}`, { title: formTitle.value, schema })
    } else {
      if (!formKey.value.trim()) return alert('请填写页面 Key')
      await api.post('/api/v1/builder/pages', { key: formKey.value.trim(), title: formTitle.value, schema })
    }
    editorOpen.value = false
    await loadPages()
  } catch (e: any) { alert(e?.response?.data?.detail || '保存失败') }
}
async function publish(p: Page) {
  await api.post(`/api/v1/builder/pages/${p.id}/publish`)
  await loadPages()
}
async function remove(p: Page) {
  if (!window.confirm('确认删除该页面？')) return
  await api.delete(`/api/v1/builder/pages/${p.id}`)
  await loadPages()
}

onMounted(loadPages)
</script>

<template>
  <div>
    <!-- 列表页 -->
    <div v-if="!editorOpen">
      <div class="flex items-center justify-between mb-6">
        <div class="flex items-center gap-2">
          <h1 class="text-2xl font-semibold tracking-tight">🧩 页面构建器</h1>
          <span class="text-sm text-ink-400">M3·P2 · 可视化拖拽</span>
        </div>
        <button class="btn-primary" @click="openCreate">新建页面</button>
      </div>

      <div class="card overflow-hidden">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-ink-400 border-b">
              <th class="p-3">页面</th><th class="p-3">Key</th><th class="p-3">区块数</th><th class="p-3">状态</th><th class="p-3 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in pages" :key="p.id" class="border-b last:border-0">
              <td class="p-3 font-medium">{{ p.title }}</td>
              <td class="p-3"><code class="text-xs text-ink-400">{{ p.key }}</code></td>
              <td class="p-3">{{ p.schema?.length || 0 }}</td>
              <td class="p-3">
                <span :class="p.status === 'published' ? 'text-green-600' : 'text-ink-400'">{{ p.status === 'published' ? '已发布' : '草稿' }}</span>
              </td>
              <td class="p-3 text-right space-x-2 whitespace-nowrap">
                <a v-if="p.status === 'published'" :href="`/api/v1/public/pages/${p.key}/render`" target="_blank" class="btn-ghost text-sm">预览</a>
                <button v-if="p.status !== 'published'" class="btn-ghost text-sm text-green-600" @click="publish(p)">发布</button>
                <button class="btn-ghost text-sm" @click="openEdit(p)">编辑</button>
                <button class="btn-ghost text-sm text-red-600" @click="remove(p)">删除</button>
              </td>
            </tr>
            <tr v-if="!pages.length"><td colspan="5" class="p-6 text-center text-ink-400">暂无页面</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 可视化拖拽编辑器 -->
    <div v-else class="editor-modal">
      <div class="editor-head">
        <div class="flex items-center gap-3">
          <button class="btn-ghost text-sm" @click="editorOpen = false">← 返回</button>
          <div>
            <input v-if="!editing" v-model="formKey" class="input input-sm w-32 font-mono" placeholder="key" />
            <input v-model="formTitle" class="input input-sm w-56" placeholder="页面标题" />
          </div>
          <span class="text-xs text-ink-400">{{ editing ? '编辑：' + editing.key : '新建页面' }}</span>
        </div>
        <button class="btn-primary" @click="save">💾 保存</button>
      </div>

      <div class="editor-body">
        <!-- 左：组件库 -->
        <aside class="panel palette">
          <div class="panel-title">组件库</div>
          <p class="panel-hint">拖到画布，或点击添加</p>
          <VueDraggable
            :model-value="PALETTE"
            :group="{ name: 'builder', pull: 'clone', put: false }"
            :sort="false"
            :clone="clonePalette"
            class="palette-list"
          >
            <div v-for="p in PALETTE" :key="p.type" class="palette-item" @click="addBlock(p.type)">
              <span class="palette-icon">{{ p.icon }}</span>
              <span class="palette-label">{{ p.label }}</span>
            </div>
          </VueDraggable>
        </aside>

        <!-- 中：画布 -->
        <main class="panel canvas" @click.self="selectedId = null">
          <div class="panel-title">
            画布
            <span class="text-xs text-ink-400">（{{ blocks.length }} 个区块）</span>
          </div>
          <VueDraggable
            v-model="blocks"
            :group="{ name: 'builder', pull: false, put: true }"
            :animation="160"
            handle=".drag-handle"
            class="canvas-space"
            @change="onCanvasChange"
          >
            <div
              v-for="b in blocks"
              :key="b.__id"
              class="block-card"
              :class="{ selected: b.__id === selectedId }"
              @click="selectBlock(b.__id)"
            >
              <div class="block-bar">
                <span class="drag-handle" title="拖拽排序">⠿</span>
                <span class="block-type">{{ BLOCK_LABEL[b.type] }}</span>
                <span class="block-actions">
                  <button class="mini" @click.stop="duplicateBlock(b.__id)">复制</button>
                  <button class="mini danger" @click.stop="removeBlock(b.__id)">删除</button>
                </span>
              </div>
              <div class="block-preview" v-html="previewHtml(b)"></div>
            </div>
          </VueDraggable>
          <div v-if="!blocks.length" class="canvas-empty">
            从左侧拖入或点击组件，开始搭建页面
          </div>
        </main>

        <!-- 右：属性面板 -->
        <aside class="panel prop">
          <div class="panel-title">属性</div>
          <div v-if="selected" class="prop-form">
            <div class="prop-head">编辑 · {{ BLOCK_LABEL[selected.type] }}</div>

            <template v-if="selected.type === 'hero'">
              <label class="field-label">主标题</label>
              <input v-model="selected.data.title" class="input" />
              <label class="field-label">副标题</label>
              <input v-model="selected.data.subtitle" class="input" />
            </template>

            <template v-else-if="selected.type === 'heading'">
              <label class="field-label">标题文字</label>
              <input v-model="selected.data.text" class="input" />
              <label class="field-label">级别</label>
              <select v-model.number="selected.data.level" class="input">
                <option v-for="n in 6" :key="n" :value="n">H{{ n }}</option>
              </select>
            </template>

            <template v-else-if="selected.type === 'text'">
              <label class="field-label">正文</label>
              <textarea v-model="selected.data.text" rows="6" class="input"></textarea>
            </template>

            <template v-else-if="selected.type === 'image'">
              <label class="field-label">图片地址 (src)</label>
              <input v-model="selected.data.src" class="input" placeholder="https://..." />
              <label class="field-label">替代文本 (alt)</label>
              <input v-model="selected.data.alt" class="input" />
            </template>

            <template v-else-if="selected.type === 'list'">
              <label class="field-label">列表项</label>
              <div v-for="(it, i) in selected.data.items" :key="i" class="flex gap-2 mb-2">
                <input v-model="selected.data.items[i]" class="input" />
                <button class="mini danger" @click="selected.data.items.splice(i, 1)">×</button>
              </div>
              <button class="btn-ghost text-sm" @click="selected.data.items.push('新条目')">+ 添加条目</button>
            </template>

            <template v-else-if="selected.type === 'html'">
              <label class="field-label">自定义 HTML</label>
              <textarea v-model="selected.data.html" rows="8" class="input font-mono text-xs"></textarea>
            </template>

            <button class="btn-ghost text-red-600 text-sm mt-4" @click="removeBlock(selected.__id)">删除此区块</button>
          </div>
          <div v-else class="prop-empty">在画布中点击一个区块以编辑属性</div>
        </aside>
      </div>
    </div>
  </div>
</template>

<style scoped>
.editor-modal { position: fixed; inset: 0; background: #f5f6f8; z-index: 50; display: flex; flex-direction: column; }
.editor-head { display: flex; align-items: center; justify-content: space-between; padding: 12px 20px; background: #fff; border-bottom: 1px solid #e5e7eb; }
.editor-body { flex: 1; display: grid; grid-template-columns: 220px 1fr 300px; gap: 1px; background: #e5e7eb; min-height: 0; }
.panel { background: #fff; overflow-y: auto; padding: 14px; }
.panel-title { font-weight: 600; font-size: 13px; margin-bottom: 10px; }
.panel-hint { font-size: 12px; color: #9ca3af; margin: -6px 0 10px; }

/* 组件库 */
.palette-list { display: flex; flex-direction: column; gap: 8px; }
.palette-item { display: flex; align-items: center; gap: 8px; padding: 10px; border: 1px solid #e5e7eb; border-radius: 8px; cursor: grab; background: #fafafa; transition: all .15s; user-select: none; }
.palette-item:hover { border-color: #6366f1; background: #eef2ff; }
.palette-icon { font-size: 18px; }
.palette-label { font-size: 13px; }

/* 画布 */
.canvas-space { display: flex; flex-direction: column; gap: 12px; min-height: 60vh; }
.canvas-empty { color: #9ca3af; text-align: center; padding: 80px 20px; border: 2px dashed #d1d5db; border-radius: 12px; }
.block-card { border: 1px solid #e5e7eb; border-radius: 10px; background: #fff; overflow: hidden; transition: box-shadow .15s, border-color .15s; }
.block-card.selected { border-color: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,.15); }
.block-bar { display: flex; align-items: center; gap: 8px; padding: 6px 10px; background: #f9fafb; border-bottom: 1px solid #f0f0f0; }
.drag-handle { cursor: grab; color: #9ca3af; font-size: 16px; line-height: 1; }
.block-type { font-size: 12px; font-weight: 600; color: #4b5563; }
.block-actions { margin-left: auto; display: flex; gap: 6px; }
.mini { font-size: 11px; padding: 2px 8px; border: 1px solid #e5e7eb; border-radius: 6px; background: #fff; cursor: pointer; color: #4b5563; }
.mini:hover { background: #f3f4f6; }
.mini.danger { color: #dc2626; border-color: #fecaca; }
.block-preview { padding: 16px; font-size: 14px; }

/* 属性面板 */
.prop-form { display: flex; flex-direction: column; gap: 8px; }
.prop-head { font-size: 12px; color: #6b7280; margin-bottom: 4px; }
.field-label { font-size: 12px; color: #4b5563; margin-top: 6px; }
.prop-empty, .canvas-empty { color: #9ca3af; font-size: 13px; }

/* 预览样式（与后端渲染近似） */
:deep(.pv-hero) { background: #f3f4f6; padding: 28px; border-radius: 8px; text-align: center; }
:deep(.pv-hero h2) { font-size: 24px; margin: 0 0 6px; }
:deep(.pv-hero p) { font-size: 14px; color: #6b7280; margin: 0; }
:deep(.pv-h) { margin: 4px 0; }
:deep(.pv-p) { line-height: 1.7; color: #374151; }
:deep(.pv-img) { max-width: 100%; border-radius: 8px; display: block; }
:deep(.pv-ul) { padding-left: 20px; }
:deep(.pv-empty) { color: #9ca3af; font-size: 13px; text-align: center; padding: 16px; border: 1px dashed #d1d5db; border-radius: 8px; }
</style>
