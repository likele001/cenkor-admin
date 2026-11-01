<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { EditorView, basicSetup } from 'codemirror'
import { EditorState } from '@codemirror/state'
import { html as htmlLang } from '@codemirror/lang-html'
import { css as cssLang } from '@codemirror/lang-css'
import { setDiagnostics, lintGutter, type Diagnostic } from '@codemirror/lint'
import { api } from '@/lib/api'

const BASE = '/api/v1/cms/templates'

interface ThemeItem {
  theme: string
  name: string
  version: string | null
  source: 'builtin' | 'db'
  files: number
  custom_files: number
  editable: boolean
  deletable: boolean
  active: boolean
}

interface FileItem {
  path: string
  kind: string
  templatable: boolean
  overridden: boolean
  builtin: boolean
  inherited: boolean
  source: 'db' | 'builtin' | 'inherited'
}

const themes = ref<ThemeItem[]>([])
const activeTheme = ref('default')
const currentTheme = ref('default')
const files = ref<FileItem[]>([])
const currentPath = ref('')
const content = ref('')
const originContent = ref('')
const sourceKind = ref<'db' | 'builtin' | 'inherited'>('builtin')

const loadingFiles = ref(false)
const saving = ref(false)
const previewing = ref(false)
const notice = ref<{ type: 'ok' | 'err'; text: string } | null>(null)

const syntaxError = ref<{ message: string; line: number } | null>(null)
const previewHtml = ref('')
const previewKind = ref('article')
const previewSlug = ref('')

const showDiff = ref(false)
// 使用说明面板：第一次进来的人不知道「覆盖机制」「首页不归主题管」这些前提，
// 光给一个编辑器，改半天发现没变化，会以为坏了。
const showHelp = ref(false)
const diffText = ref('')
const diffStat = ref({ added: 0, removed: 0 })

const newTheme = ref('')

// ---------------------------------------------------------------- 标签速查
// 写模板最卡的是「不知道能调什么」——以前只能去翻 docs/template-guide.md。
// 后端 /templates/context-api 一直有这份清单，前端没接，等于白写一份接口。
interface TagItem {
  name: string
  desc: string
  insert: string
  sign?: string
  usage?: string
  group?: string
  type?: string
  aliases?: string[]
}

interface CtxApi {
  apis: TagItem[]
  filters: TagItem[]
  variables: TagItem[]
  sandbox: { autoescape: boolean; rules: string[] }
  macro: { how: string; then: string; hint: string }
  app_tags: { functions: string[]; filters: string[]; hint: string }
}

const showTags = ref(false)
const tagQuery = ref('')
const tagTab = ref<'api' | 'filter' | 'var'>('api')
const TABS = [
  { key: 'api' as const, label: '数据 API' },
  { key: 'filter' as const, label: '过滤器' },
  { key: 'var' as const, label: '变量' },
]
const ctxApi = ref<CtxApi | null>(null)
const loadingTags = ref(false)

async function loadCtxApi() {
  if (ctxApi.value || loadingTags.value) return
  loadingTags.value = true
  try {
    const { data } = await api.get(`${BASE}/context-api`)
    ctxApi.value = data
  } catch (e: any) {
    flash('err', errText(e, '标签列表加载失败'))
  } finally {
    loadingTags.value = false
  }
}

function toggleTags() {
  showTags.value = !showTags.value
  if (showTags.value) loadCtxApi()
}

const tagSource = computed<TagItem[]>(() => {
  const d = ctxApi.value
  if (!d) return []
  return tagTab.value === 'api' ? d.apis : tagTab.value === 'filter' ? d.filters : d.variables
})

const filteredTags = computed<TagItem[]>(() => {
  const q = tagQuery.value.trim().toLowerCase()
  if (!q) return tagSource.value
  return tagSource.value.filter((x) =>
    `${x.name} ${x.desc || ''} ${x.sign || ''} ${x.usage || ''} ${(x.aliases || []).join(' ')}`
      .toLowerCase()
      .includes(q),
  )
})

const tagGroups = computed<[string, TagItem[]][]>(() => {
  const list = filteredTags.value
  if (tagTab.value !== 'api') return [['', list]]
  const order = ['内容', '结构', '站点', '其他']
  const map = new Map<string, TagItem[]>()
  for (const it of list) {
    const k = it.group || '其他'
    if (!map.has(k)) map.set(k, [])
    map.get(k)!.push(it)
  }
  return order.filter((k) => map.has(k)).map((k) => [k, map.get(k)!])
})

// $0 是光标落点标记：for 骨架插进去后光标停在循环体，不用再手动跳
function insertTag(item: TagItem) {
  if (!view) {
    flash('err', '先在左侧选一个模板文件')
    return
  }
  const raw = item.insert || ''
  const marker = raw.indexOf('$0')
  const payload = marker >= 0 ? raw.replace('$0', '') : raw
  const caret = marker >= 0 ? marker : payload.length
  const { from, to } = view.state.selection.main
  view.dispatch({
    changes: { from, to, insert: payload },
    selection: { anchor: from + caret },
    scrollIntoView: true,
  })
  view.focus()
}
const importInput = ref<HTMLInputElement | null>(null)

const dirty = computed(() => content.value !== originContent.value)
const isActiveTheme = computed(() => currentTheme.value === activeTheme.value)

const groups = computed(() => {
  const pageLevel = ['layout.html', 'list.html', 'detail.html', 'page.html', '404.html']
  const buckets = new Map<string, FileItem[]>()
  for (const f of files.value) {
    const dir = f.path.includes('/') ? f.path.slice(0, f.path.lastIndexOf('/')) : (pageLevel.includes(f.path) ? '页面模板' : '其他')
    if (!buckets.has(dir)) buckets.set(dir, [])
    buckets.get(dir)!.push(f)
  }
  const order = ['页面模板', 'partials', 'macros', 'assets', '其他']
  return [...buckets.entries()].sort((a, b) => {
    const ia = order.indexOf(a[0]); const ib = order.indexOf(b[0])
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib)
  })
})

function flash(type: 'ok' | 'err', text: string) {
  notice.value = { type, text }
  window.setTimeout(() => {
    if (notice.value?.text === text) notice.value = null
  }, 4000)
}

function errText(e: any, fallback = '操作失败'): string {
  const d = e?.response?.data?.detail
  if (typeof d === 'string') return d
  if (d?.message) return d.message
  if (Array.isArray(d?.errors) && d.errors.length) {
    return `${d.message || '校验未通过'}：${d.errors.map((x: any) => `${x.path} ${x.message}`).join('；')}`
  }
  return e?.message || fallback
}

async function loadThemes() {
  const { data } = await api.get(`${BASE}/themes`)
  themes.value = data.items
  activeTheme.value = data.active
  if (!themes.value.find((t) => t.theme === currentTheme.value)) currentTheme.value = data.active
}

async function loadFiles() {
  loadingFiles.value = true
  try {
    const { data } = await api.get(`${BASE}/files`, { params: { theme: currentTheme.value } })
    files.value = data.items
    if (!files.value.find((f) => f.path === currentPath.value)) {
      currentPath.value = files.value.find((f) => f.path === 'detail.html')?.path || files.value[0]?.path || ''
    }
  } finally {
    loadingFiles.value = false
  }
}

async function loadFile(path: string) {
  if (!path) return
  const { data } = await api.get(`${BASE}/file`, { params: { theme: currentTheme.value, path } })
  currentPath.value = path
  originContent.value = data.content || ''
  sourceKind.value = data.source
  showDiff.value = false
  applyToEditor(originContent.value)
  scheduleValidate(0)
  schedulePreview(120)
}

// ---------------------------------------------------------------- 编辑器

function switchFile(path: string) {
  if (path === currentPath.value) return
  if (dirty.value && !window.confirm(`${currentPath.value} 的改动还没保存，切走会丢弃，继续？`)) return
  currentPath.value = path
}

const host = ref<HTMLElement | null>(null)
let view: EditorView | null = null
let applyingRemote = false
let validateTimer = 0
let previewTimer = 0

const cmTheme = EditorView.theme({
  '&': { height: '100%', fontSize: '12.5px' },
  '.cm-scroller': { overflow: 'auto', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' },
  '.cm-content': { paddingBottom: '40vh' },
  '&.cm-focused': { outline: 'none' },
})

const extensions = [
  basicSetup,
  htmlLang(),
  cssLang(),
  lintGutter(),
  cmTheme,
  EditorView.updateListener.of((u) => {
    if (!u.docChanged || applyingRemote) return
    content.value = u.state.doc.toString()
    scheduleValidate()
    schedulePreview()
  }),
]

function applyToEditor(text: string) {
  if (!view) return
  applyingRemote = true
  view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text } })
  applyingRemote = false
}

function markLine(line: number, message: string) {
  if (!view) return
  const doc = view.state.doc
  const ln = Math.min(Math.max(line, 1), doc.lines)
  const lineInfo = doc.line(ln)
  const diag: Diagnostic = { from: lineInfo.from, to: lineInfo.to, severity: 'error', message }
  view.dispatch(setDiagnostics(view.state, [diag]))
  view.dispatch({ effects: EditorView.scrollIntoView(lineInfo.from, { y: 'center' }) })
}

function clearMarks() {
  if (!view) return
  view.dispatch(setDiagnostics(view.state, []))
}

function scheduleValidate(delay = 450) {
  window.clearTimeout(validateTimer)
  if (!currentPath.value.endsWith('.html') && !currentPath.value.endsWith('.xml')) {
    syntaxError.value = null
    clearMarks()
    return
  }
  validateTimer = window.setTimeout(validateNow, delay)
}

async function validateNow() {
  try {
    const { data } = await api.post(`${BASE}/validate`, { source: content.value })
    if (data.valid) {
      syntaxError.value = null
      clearMarks()
    } else {
      const err = data.error || {}
      syntaxError.value = { message: err.message || '语法错误', line: err.line || 1 }
      markLine(err.line || 1, err.message || '语法错误')
    }
  } catch {
    /* 校验失败不阻塞编辑 */
  }
}

function schedulePreview(delay = 800) {
  window.clearTimeout(previewTimer)
  previewTimer = window.setTimeout(runPreview, delay)
}

async function runPreview() {
  if (!currentPath.value) return
  previewing.value = true
  try {
    const { data } = await api.post(`${BASE}/preview-page`, {
      source: content.value,
      path: currentPath.value,
      kind: previewKind.value,
      slug: previewSlug.value || null,
      theme: currentTheme.value,
    })
    if (data.ok) previewHtml.value = data.html
    else previewHtml.value = `<pre style="padding:24px;color:#b91c1c;font:13px/1.6 monospace;white-space:pre-wrap">${escapeHtml(data.error || '渲染失败')}</pre>`
  } catch (e: any) {
    previewHtml.value = `<pre style="padding:24px;color:#b91c1c;font:13px/1.6 monospace;white-space:pre-wrap">${escapeHtml(errText(e, '预览请求失败'))}</pre>`
  } finally {
    previewing.value = false
  }
}

function escapeHtml(s: string) {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] as string))
}

// ---------------------------------------------------------------- 保存 / 还原 / diff

async function save() {
  if (!currentPath.value || saving.value) return
  saving.value = true
  try {
    const { data } = await api.put(`${BASE}/file`, {
      theme: currentTheme.value,
      path: currentPath.value,
      content: content.value,
    })
    originContent.value = content.value
    sourceKind.value = 'db'
    const f = files.value.find((x) => x.path === currentPath.value)
    if (f) { f.overridden = true; f.inherited = false; f.source = 'db' }
    flash('ok', `已保存 ${currentPath.value}（${data.checksum?.slice(0, 8)}）`)
    schedulePreview(100)
  } catch (e: any) {
    const d = e?.response?.data?.detail
    if (d?.error?.line) {
      syntaxError.value = { message: d.error.message, line: d.error.line }
      markLine(d.error.line, d.error.message)
    }
    flash('err', errText(e, '保存失败'))
  } finally {
    saving.value = false
  }
}

async function revert() {
  if (!currentPath.value) return
  if (sourceKind.value !== 'db') {
    flash('err', '这个文件本来就没有覆盖，无需还原')
    return
  }
  if (!window.confirm(`确定放弃对 ${currentPath.value} 的修改，回落到内置版本？`)) return
  try {
    await api.delete(`${BASE}/file`, { params: { theme: currentTheme.value, path: currentPath.value } })
    await loadFiles()
    await loadFile(currentPath.value)
    flash('ok', '已回落到内置版本')
    schedulePreview(100)
  } catch (e: any) {
    flash('err', errText(e, '还原失败'))
  }
}

async function openDiff() {
  if (!currentPath.value) return
  if (sourceKind.value !== 'db') {
    flash('err', '没有覆盖版本，无差异可看')
    return
  }
  try {
    const { data } = await api.get(`${BASE}/diff`, { params: { theme: currentTheme.value, path: currentPath.value } })
    diffText.value = data.diff || '（与内置版本一致）'
    diffStat.value = { added: data.added, removed: data.removed }
    showDiff.value = true
  } catch (e: any) {
    flash('err', errText(e, '读取差异失败'))
  }
}

function diffLines() {
  return diffText.value.split('\n').map((text) => {
    let cls = 'text-ink-500'
    if (text.startsWith('+++') || text.startsWith('---')) cls = 'font-medium'
    else if (text.startsWith('+')) cls = 'bg-green-50 text-green-700'
    else if (text.startsWith('-')) cls = 'bg-red-50 text-red-700'
    else if (text.startsWith('@@')) cls = 'text-blue-600'
    return { text, cls }
  })
}

// ---------------------------------------------------------------- 主题操作

async function switchTheme(name: string, el?: HTMLSelectElement) {
  if (name === currentTheme.value) return
  if (dirty.value && !window.confirm('当前改动未保存，切换主题会丢弃，继续？')) {
    if (el) el.value = currentTheme.value
    return
  }
  currentTheme.value = name
  currentPath.value = ''
  await loadFiles()
  if (currentPath.value) await loadFile(currentPath.value)
}

function onThemeChange(ev: Event) {
  const el = ev.target as HTMLSelectElement
  switchTheme(el.value, el)
}

async function createTheme() {
  const name = newTheme.value.trim()
  if (!name) return
  try {
    const { data } = await api.post(`${BASE}/themes`, { theme: name, from_theme: currentTheme.value })
    flash('ok', `已从 ${data.from_theme} 复制 ${data.files} 个文件创建主题 ${data.theme}`)
    newTheme.value = ''
    await loadThemes()
    await switchTheme(name)
  } catch (e: any) {
    flash('err', errText(e, '创建主题失败'))
  }
}

async function activateTheme() {
  try {
    await api.put(`${BASE}/themes/active`, { theme: currentTheme.value })
    await loadThemes()
    flash('ok', `站点已切换到主题「${currentTheme.value}」`)
  } catch (e: any) {
    flash('err', errText(e, '切换生效主题失败'))
  }
}

async function deleteTheme() {
  if (!window.confirm(`确定删除主题「${currentTheme.value}」的全部文件？删除后不可恢复。`)) return
  try {
    const { data } = await api.delete(`${BASE}/themes/${currentTheme.value}`)
    flash('ok', `已删除 ${data.deleted} 个文件`)
    await loadThemes()
    await switchTheme(activeTheme.value)
  } catch (e: any) {
    flash('err', errText(e, '删除主题失败'))
  }
}

async function exportTheme() {
  try {
    const res = await api.get(`${BASE}/export`, { params: { theme: currentTheme.value }, responseType: 'blob' })
    const url = URL.createObjectURL(res.data as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${currentTheme.value}.zip`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    flash('ok', '主题包已导出')
  } catch (e: any) {
    flash('err', errText(e, '导出失败'))
  }
}

async function doImport(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const form = new FormData()
  form.append('file', file)
  form.append('theme', currentTheme.value.trim())
  form.append('overwrite', 'true')
  try {
    const { data } = await api.post(`${BASE}/import`, form)
    flash('ok', `已导入 ${data.written} 个文件到主题「${data.theme}」`)
    await loadThemes()
    if (data.theme !== currentTheme.value) await switchTheme(data.theme)
    else await loadFiles()
  } catch (e: any) {
    flash('err', errText(e, '导入失败'))
  } finally {
    input.value = ''
  }
}

// ---------------------------------------------------------------- 生命周期

function onKeydown(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
    e.preventDefault()
    save()
  }
}

onMounted(async () => {
  await loadThemes()
  await loadFiles()
  if (currentPath.value) await loadFile(currentPath.value)
  await nextTick()
  if (host.value) {
    view = new EditorView({
      state: EditorState.create({ doc: originContent.value, extensions }),
      parent: host.value,
    })
    scheduleValidate(0)
  }
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  window.clearTimeout(validateTimer)
  window.clearTimeout(previewTimer)
  view?.destroy()
  view = null
})

watch(previewKind, () => schedulePreview(0))
watch(currentPath, (p) => { if (p) loadFile(p) })
</script>

<template>
  <div class="flex h-[calc(100vh-64px)] flex-col">
    <div class="flex flex-wrap items-center gap-2 border-b border-ink-100 pb-3">
      <div>
        <h1 class="text-xl font-semibold tracking-tight">模板工作台</h1>
        <p class="text-xs text-ink-500">改完即存，右侧实时看效果；语法错误会在编辑器里标红</p>
      </div>

      <div class="ml-auto flex flex-wrap items-center gap-2">
        <button
          class="btn-ghost text-sm"
          :class="showTags ? 'text-blue-600' : ''"
          title="列出模板里能用的变量、数据 API 与过滤器，点一下插入"
          @click="toggleTags"
        >
          标签速查
        </button>
        <button class="btn-ghost text-sm" @click="showHelp = true">使用说明</button>
        <select :value="currentTheme" class="input w-44 text-sm" @change="onThemeChange">
          <option v-for="t in themes" :key="t.theme" :value="t.theme">
            {{ t.name }}（{{ t.theme }}）{{ t.active ? '· 生效中' : '' }}
          </option>
        </select>
        <button
          class="btn-ghost text-sm"
          :disabled="isActiveTheme"
          :title="isActiveTheme ? '已经是生效主题' : '把站点切到这个主题'"
          @click="activateTheme"
        >
          设为生效
        </button>
        <button class="btn-ghost text-sm" @click="exportTheme">导出 zip</button>
        <button class="btn-ghost text-sm" @click="importInput?.click()">导入 zip</button>
        <input ref="importInput" type="file" accept=".zip" class="hidden" @change="doImport" />
        <button
          class="btn-ghost text-sm text-red-600"
          :disabled="!themes.find((t) => t.theme === currentTheme)?.deletable"
          @click="deleteTheme"
        >
          删除主题
        </button>
      </div>
    </div>

    <div v-if="notice" class="mt-2 rounded px-3 py-1.5 text-sm"
         :class="notice.type === 'ok' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'">
      {{ notice.text }}
    </div>

    <div class="mt-3 grid min-h-0 flex-1 grid-cols-12 gap-3">
      <!-- 文件树 -->
      <aside class="col-span-2 flex min-h-0 flex-col overflow-hidden rounded-lg border border-ink-100">
        <div class="border-b border-ink-100 px-2 py-1.5 text-xs text-ink-500">
          {{ loadingFiles ? '加载中…' : `${files.length} 个文件` }}
        </div>
        <div class="min-h-0 flex-1 overflow-auto p-1.5">
          <div v-for="[dir, list] in groups" :key="dir" class="mb-2">
            <div class="px-1 py-0.5 text-[11px] font-medium uppercase tracking-wide text-ink-400">{{ dir }}</div>
            <button
              v-for="f in list"
              :key="f.path"
              class="flex w-full items-center gap-1 rounded px-1.5 py-1 text-left text-xs hover:bg-ink-50"
              :class="f.path === currentPath ? 'bg-ink-100 font-medium' : ''"
              @click="switchFile(f.path)"
            >
              <span class="w-1.5 shrink-0 rounded-full"
                    :class="f.source === 'db' ? 'h-1.5 bg-blue-500' : f.source === 'builtin' ? 'h-1.5 bg-ink-300' : 'h-1.5 bg-ink-200'"
                    :title="f.source === 'db' ? '已覆盖（DB）' : f.source === 'builtin' ? '内置' : '继承自 default'" />
              <span class="truncate">{{ f.path.includes('/') ? f.path.slice(f.path.lastIndexOf('/') + 1) : f.path }}</span>
              <span v-if="f.overridden" class="ml-auto text-[10px] text-blue-600">改</span>
            </button>
          </div>
        </div>
        <div class="border-t border-ink-100 p-2">
          <input v-model="newTheme" class="input mb-1 w-full text-xs" placeholder="新主题名，如 my-theme" />
          <button class="btn-ghost w-full text-xs" :disabled="!newTheme.trim()" @click="createTheme">
            从当前主题复制一份
          </button>
        </div>
      </aside>

      <!-- 编辑器 -->
      <section class="col-span-6 flex min-h-0 flex-col overflow-hidden rounded-lg border border-ink-100">
        <div class="flex items-center gap-2 border-b border-ink-100 px-2 py-1.5">
          <code class="text-xs font-medium">{{ currentPath || '未选择文件' }}</code>
          <span class="rounded px-1 text-[10px]"
                :class="sourceKind === 'db' ? 'bg-blue-50 text-blue-700' : 'bg-ink-50 text-ink-500'">
            {{ sourceKind === 'db' ? '已覆盖' : sourceKind === 'builtin' ? '内置' : '继承' }}
          </span>
          <span v-if="dirty" class="text-[10px] text-amber-600">未保存</span>
          <span v-if="syntaxError" class="text-[10px] text-red-600">第 {{ syntaxError.line }} 行：{{ syntaxError.message }}</span>
          <div class="ml-auto flex items-center gap-1">
            <button class="btn-ghost text-xs" :disabled="!dirty || saving" @click="save">
              {{ saving ? '保存中…' : '保存 ⌘S' }}
            </button>
            <button class="btn-ghost text-xs" :disabled="sourceKind !== 'db'" @click="openDiff">差异</button>
            <button class="btn-ghost text-xs" :disabled="sourceKind !== 'db'" @click="revert">还原</button>
          </div>
        </div>
        <div class="relative min-h-0 flex-1 overflow-hidden">
          <div ref="host" class="h-full" :class="showTags ? 'mr-[17rem]' : ''" />

          <!-- 标签速查：写模板时不用再切到文档去翻 -->
          <aside
            v-if="showTags"
            class="absolute inset-y-0 right-0 flex w-[17rem] flex-col border-l border-ink-100 bg-white"
          >
            <div class="flex items-center gap-1 border-b border-ink-100 px-2 py-1.5">
              <span class="text-xs font-medium">标签速查</span>
              <button class="ml-auto text-[11px] text-ink-400 hover:text-ink-700" @click="showTags = false">关闭</button>
            </div>

            <div class="flex gap-1 border-b border-ink-100 px-2 py-1.5">
              <button
                v-for="t in TABS"
                :key="t.key"
                class="rounded px-1.5 py-0.5 text-[11px]"
                :class="tagTab === t.key ? 'bg-blue-50 font-medium text-blue-700' : 'text-ink-500 hover:bg-ink-50'"
                @click="tagTab = t.key"
              >
                {{ t.label }}
              </button>
            </div>

            <div class="border-b border-ink-100 px-2 py-1.5">
              <input v-model="tagQuery" class="input h-7 w-full text-xs" placeholder="搜名字或用途，如 分页 / date" />
            </div>

            <div class="min-h-0 flex-1 overflow-auto p-1.5">
              <p v-if="loadingTags" class="p-2 text-[11px] text-ink-400">加载中…</p>
              <p v-else-if="!filteredTags.length" class="p-2 text-[11px] text-ink-400">没匹配的标签</p>
              <div v-for="[g, list] in tagGroups" :key="g" class="mb-2">
                <div v-if="g" class="px-1 py-0.5 text-[10px] font-medium uppercase tracking-wide text-ink-400">{{ g }}</div>
                <button
                  v-for="it in list"
                  :key="it.name"
                  class="block w-full rounded px-1.5 py-1 text-left hover:bg-ink-50"
                  :title="it.insert"
                  @click="insertTag(it)"
                >
                  <div class="flex items-baseline gap-1">
                    <code class="text-[11px] font-medium text-blue-700">{{ it.name }}</code>
                    <span v-if="it.aliases?.length" class="text-[10px] text-ink-400">/ {{ it.aliases.join(' ') }}</span>
                    <span v-if="it.type" class="ml-auto shrink-0 text-[10px] text-ink-400">{{ it.type }}</span>
                  </div>
                  <p class="mt-0.5 truncate text-[11px] leading-4 text-ink-500">{{ it.desc }}</p>
                </button>
              </div>
            </div>

            <div v-if="ctxApi" class="border-t border-ink-100 px-2 py-1.5 text-[10px] leading-4 text-ink-400">
              <p>自动转义开着，输出 HTML 要加 <code class="text-ink-600">|safe</code></p>
              <p class="mt-0.5">不能调 Python 内置，只能调上面这些和 {% macro %}</p>
              <p v-if="ctxApi.app_tags.functions.length || ctxApi.app_tags.filters.length" class="mt-1 text-ink-500">
                来自 App：{{ [...ctxApi.app_tags.functions, ...ctxApi.app_tags.filters].join('、') }}
              </p>
            </div>
          </aside>
        </div>
      </section>

      <!-- 预览 / 差异 -->
      <section class="col-span-4 flex min-h-0 flex-col overflow-hidden rounded-lg border border-ink-100">
        <div class="flex items-center gap-2 border-b border-ink-100 px-2 py-1.5">
          <template v-if="!showDiff">
            <select v-model="previewKind" class="input h-7 w-24 text-xs">
              <option value="article">文章</option>
              <option value="news">新闻</option>
              <option value="product">产品</option>
              <option value="case">案例</option>
              <option value="page">单页</option>
              <option value="list">列表</option>
            </select>
            <input v-model="previewSlug" class="input h-7 flex-1 text-xs" placeholder="slug（留空用示例数据）" />
            <button class="btn-ghost text-xs" :disabled="previewing" @click="runPreview">刷新</button>
          </template>
          <template v-else>
            <span class="text-xs font-medium">差异</span>
            <span class="text-[10px] text-green-600">+{{ diffStat.added }}</span>
            <span class="text-[10px] text-red-600">-{{ diffStat.removed }}</span>
            <button class="btn-ghost ml-auto text-xs" @click="showDiff = false">关闭</button>
          </template>
        </div>
        <div v-if="showDiff" class="min-h-0 flex-1 overflow-auto bg-ink-50/40 p-2 font-mono text-[11px] leading-5">
          <div v-for="(l, i) in diffLines()" :key="i" :class="l.cls" class="whitespace-pre-wrap">{{ l.text || ' ' }}</div>
        </div>
        <iframe
          v-else
          class="min-h-0 w-full flex-1 bg-white"
          sandbox=""
          :srcdoc="previewHtml || '<p style=&quot;padding:24px;color:#888;font:13px sans-serif&quot;>改一下左侧模板，这里会实时渲染</p>'"
        />
      </section>
    </div>

    <!-- 使用说明：把「第一次打开一定会踩的坑」摆在最前面 -->
    <div
      v-if="showHelp"
      class="fixed inset-0 z-50 flex items-start justify-center overflow-auto bg-black/40 p-6"
      @click.self="showHelp = false"
    >
      <div class="w-full max-w-3xl rounded-lg bg-white p-6 text-sm leading-relaxed shadow-xl">
        <div class="mb-4 flex items-start justify-between gap-4">
          <div>
            <h2 class="text-lg font-semibold">主题模板使用说明</h2>
            <p class="mt-1 text-xs text-ink-500">只需要会 HTML + 一点 Jinja 语法，不用懂框架</p>
          </div>
          <button class="btn-ghost text-xs" @click="showHelp = false">关闭</button>
        </div>

        <div class="mb-5 rounded border border-amber-200 bg-amber-50 p-3 text-[13px]">
          <p class="font-medium text-amber-800">动手前先知道这三件事</p>
          <ol class="mt-2 list-decimal space-y-1 pl-5 text-amber-900">
            <li>
              <b>首页不归主题管。</b>站点根地址返回的是静态站的
              <code class="rounded bg-amber-100 px-1">index.html</code>，不经过模板引擎。
              主题管的是内容页：详情页、列表页、分类页、标签页、搜索页、404。
            </li>
            <li>
              <b>主题是「覆盖」机制。</b>数据库里有的文件用你的，没有的自动回退到
              <code class="rounded bg-amber-100 px-1">default</code> 主题，
              所以只改 3 个文件也算一个完整主题。
            </li>
            <li>
              <b>保存即生效。</b>不用重启、不用清缓存，保存会同时清掉模板缓存。
              但要点<b>「设为生效」</b>才算上线 —— 只是保存并不会切换线上使用的主题。
            </li>
          </ol>
        </div>

        <div class="mb-5">
          <h3 class="mb-2 font-semibold">三步做第一个主题</h3>
          <ol class="list-decimal space-y-1 pl-5">
            <li>左下角输入主题名（小写字母数字，如 <code class="rounded bg-ink-100 px-1">magazine</code>），点「从当前主题复制一份」—— 12 个文件整体复制，不用从空白开始。</li>
            <li>改文件：先改 <code class="rounded bg-ink-100 px-1">assets/style.css</code> 顶部的配色变量，效果最直观。</li>
            <li>右上角点「设为生效」，线上全站换版式。回退就是把下拉切回 <code class="rounded bg-ink-100 px-1">default</code> 再点一次。</li>
          </ol>
        </div>

        <div class="mb-5">
          <h3 class="mb-2 font-semibold">文件对照</h3>
          <table class="w-full text-[13px]">
            <tbody class="[&_td]:border-b [&_td]:border-ink-100 [&_td]:py-1.5 [&_td]:align-top">
              <tr><td class="w-56 pr-3"><code>partials/header.html</code></td><td>站头、品牌、主菜单</td></tr>
              <tr><td class="pr-3"><code>partials/footer.html</code></td><td>页脚；想加「回到顶部」这类小组件也写这里</td></tr>
              <tr><td class="pr-3"><code>partials/card.html</code></td><td>列表卡片，循环变量固定叫 <code>r</code></td></tr>
              <tr><td class="pr-3"><code>partials/pagination.html</code></td><td>分页条，地址都是后端算好的，别自己拼 ?page=</td></tr>
              <tr><td class="pr-3"><code>detail.html</code></td><td>文章 / 产品 / 案例 / 新闻详情页</td></tr>
              <tr><td class="pr-3"><code>list.html</code></td><td>七种列表页共用（含分类、标签、搜索）</td></tr>
              <tr><td class="pr-3"><code>layout.html</code></td><td>全站 head、字体、脚本入口</td></tr>
              <tr><td class="pr-3"><code>assets/style.css</code></td><td>全站样式，整段内联进 &lt;style&gt;</td></tr>
            </tbody>
          </table>
        </div>

        <div class="mb-5">
          <h3 class="mb-2 font-semibold">最容易踩的五个坑</h3>
          <ul class="list-disc space-y-1 pl-5">
            <li>正文变量不加 <code class="rounded bg-ink-100 px-1">| safe</code>，页面会显示一堆 <code class="rounded bg-ink-100 px-1">&amp;lt;p&amp;gt;</code>。</li>
            <li><code class="rounded bg-ink-100 px-1">item.cover</code> 可能是空串，要用 <code class="rounded bg-ink-100 px-1">if</code> 包着，否则输出 <code class="rounded bg-ink-100 px-1">&lt;img src=""&gt;</code> 多一次 404 请求。</li>
            <li>列表数据用顶层 <code class="rounded bg-ink-100 px-1">items</code>，别用 <code class="rounded bg-ink-100 px-1">page.items</code>（会撞上 dict 的方法名）。</li>
            <li>别删 <code class="rounded bg-ink-100 px-1">partials/meta.html</code>，OG、Twitter Card、JSON-LD 全在里面，删了不影响人看但会掉搜索富摘要。</li>
            <li>预览区是禁用脚本的 iframe：<b>加了 JS 在预览里不会执行</b>，保存后线上才生效。</li>
          </ul>
        </div>

        <p class="border-t border-ink-100 pt-3 text-xs text-ink-500">
          完整教程（目录约定、16 个数据 API、过滤器、沙箱边界、导入导出、排错）见仓库
          <code class="rounded bg-ink-100 px-1">docs/template-guide.md</code>，
          其中「二·补、从零做一个自己的主题」是一份可以照着做的完整实战。
        </p>
      </div>
    </div>
  </div>
</template>
