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
const diffText = ref('')
const diffStat = ref({ added: 0, removed: 0 })

const newTheme = ref('')
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
        <div ref="host" class="min-h-0 flex-1 overflow-hidden" />
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
  </div>
</template>
