<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { EditorView, basicSetup } from 'codemirror'
import { EditorState } from '@codemirror/state'
import { html as htmlLang } from '@codemirror/lang-html'
import { css as cssLang } from '@codemirror/lang-css'
import { setDiagnostics, lintGutter, type Diagnostic } from '@codemirror/lint'
import { api } from '@/lib/api'
import ThemeSettingsDialog from '@/components/cms/ThemeSettingsDialog.vue'

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
  disk?: boolean
  builtin: boolean
  inherited: boolean
  source: 'db' | 'builtin' | 'inherited' | 'disk'
}

const themes = ref<ThemeItem[]>([])
const activeTheme = ref('default')
const currentTheme = ref('default')
const files = ref<FileItem[]>([])
const currentPath = ref('')
const content = ref('')
const originContent = ref('')
const sourceKind = ref<'db' | 'builtin' | 'inherited' | 'disk'>('builtin')

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
// 主题配置弹窗：表单由主题自己的 theme.json settings 声明生成
const showThemeSettings = ref(false)

async function onThemeSaved(theme: string) {
  // 配置改完必须重载主题列表 —— 列表里的「已改 N 项」和图标都来自同一份数据
  await loadThemes()
  flash('ok', `「${theme}」的配置已保存，前台刷新即可看到新样式（已自动清理静态缓存）`)
}

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
    flash('err', errText(e, t("templateStudio.标签列表_1ez6qn")))
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
  const order = ['内容', t("templateStudio.结构_m51t"), t("templateStudio.站点_liio"), t("templateStudio.其他_eae8")]
  const map = new Map<string, TagItem[]>()
  for (const it of list) {
    const k = it.group || t("templateStudio.其他_eae8")
    if (!map.has(k)) map.set(k, [])
    map.get(k)!.push(it)
  }
  return order.filter((k) => map.has(k)).map((k) => [k, map.get(k)!])
})

// $0 是光标落点标记：for 骨架插进去后光标停在循环体，不用再手动跳
function insertTag(item: TagItem) {
  if (!view) {
    flash('err', t("templateStudio.先在左侧_1acoh1"))
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
    const dir = f.path.includes('/') ? f.path.slice(0, f.path.lastIndexOf('/')) : (pageLevel.includes(f.path) ? t("templateStudio.页面模板_juxtxn") : t("templateStudio.其他_eae8"))
    if (!buckets.has(dir)) buckets.set(dir, [])
    buckets.get(dir)!.push(f)
  }
  const order = ['页面模板', 'partials', 'macros', 'assets', t("templateStudio.其他_eae8")]
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
    // path 决定要不要跑 CSP 检查：css / js 里出现 <script> 字样是正常的，不能误报
    const { data } = await api.post(`${BASE}/validate`, {
      source: content.value,
      path: currentPath.value,
    })
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
    previewHtml.value = `<pre style="padding:24px;color:#b91c1c;font:13px/1.6 monospace;white-space:pre-wrap">${escapeHtml(errText(e, t("templateStudio.预览请求_6uu1qb")))}</pre>`
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
    // 磁盘同名文件优先于 DB：保存成功但前台仍用磁盘版，必须提醒
    if (data.disk_shadowed) {
      flash('ok', `已存入数据库，但磁盘目录里有同名文件正在生效，前台不会变。删除 var/themes/${currentTheme.value}/${currentPath.value} 后此版本才生效`)
    } else {
      const f = files.value.find((x) => x.path === currentPath.value)
      if (f) { f.overridden = true; f.inherited = false; f.source = 'db' }
      flash('ok', `已保存 ${currentPath.value}（${data.checksum?.slice(0, 8)}）`)
    }
    schedulePreview(100)
  } catch (e: any) {
    const d = e?.response?.data?.detail
    if (d?.error?.line) {
      syntaxError.value = { message: d.error.message, line: d.error.line }
      markLine(d.error.line, d.error.message)
    }
    flash('err', errText(e, t("aiMemory.saveFailed")))
  } finally {
    saving.value = false
  }
}

async function revert() {
  if (!currentPath.value) return
  if (sourceKind.value !== 'db') {
    flash('err', t("templateStudio.这个文件_1yrdao"))
    return
  }
  if (!window.confirm(`确定放弃对 ${currentPath.value} 的修改，回落到内置版本？`)) return
  try {
    await api.delete(`${BASE}/file`, { params: { theme: currentTheme.value, path: currentPath.value } })
    await loadFiles()
    await loadFile(currentPath.value)
    flash('ok', t("templateStudio.已回落到_1310od"))
    schedulePreview(100)
  } catch (e: any) {
    flash('err', errText(e, t("templateStudio.还原失败_ihtwkb")))
  }
}

async function openDiff() {
  if (!currentPath.value) return
  if (sourceKind.value !== 'db') {
    flash('err', t("templateStudio.没有覆盖_1s8inc"))
    return
  }
  try {
    const { data } = await api.get(`${BASE}/diff`, { params: { theme: currentTheme.value, path: currentPath.value } })
    diffText.value = data.diff || t("templateStudio.text_omnkhu")
    diffStat.value = { added: data.added, removed: data.removed }
    showDiff.value = true
  } catch (e: any) {
    flash('err', errText(e, t("templateStudio.读取差异_1agslu")))
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
  if (dirty.value && !window.confirm(t("templateStudio.当前改动_1rzh19"))) {
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
    flash('err', errText(e, t("templateStudio.创建主题_ybk500")))
  }
}

async function activateTheme() {
  try {
    await api.put(`${BASE}/themes/active`, { theme: currentTheme.value })
    await loadThemes()
    flash('ok', `站点已切换到主题「${currentTheme.value}」`)
  } catch (e: any) {
    flash('err', errText(e, t("templateStudio.切换生效_1n97j8")))
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
    flash('err', errText(e, t("templateStudio.删除主题_149hgi")))
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
    flash('ok', t("templateStudio.主题包已_3dia6g"))
  } catch (e: any) {
    flash('err', errText(e, t("templateStudio.导出失败_by46j6")))
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
    flash('err', errText(e, t("templateStudio.导入失败_by141p")))
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
        <h1 class="text-xl font-semibold tracking-tight">{{ $t('templateStudio.模板工作_280ozf') }}</h1>
        <p class="text-xs text-ink-500">{{ $t('templateStudio.改完即存_j0y4jm') }}</p>
      </div>

      <div class="ml-auto flex flex-wrap items-center gap-2">
        <button
          class="btn-ghost text-sm"
          :class="showTags ? 'text-blue-600' : ''"
          :title="$t('templateStudio.列出模板_1dvz73')"
          @click="toggleTags"
        >
          {{ $t('templateStudio.标签速查_dn4svx') }}
        </button>
        <button class="btn-ghost text-sm" @click="showHelp = true">{{ $t('templateStudio.使用说明_aisqn7') }}</button>
        <select :value="currentTheme" class="input w-44 text-sm" @change="onThemeChange">
          <option v-for="t in themes" :key="t.theme" :value="t.theme">
            {{ t.name }}（{{ t.theme }}）{{ t.active ? $t('templateStudio.text_3au0kb') : '' }}
          </option>
        </select>
        <button
          class="btn-ghost text-sm"
          :disabled="isActiveTheme"
          :title="isActiveTheme ? '已经是生效主题' : '把站点切到这个主题'"
          @click="activateTheme"
        >
          {{ $t('templateStudio.设为生效_hyjjgl') }}
        </button>
        <button
          class="btn-ghost text-sm"
          :title="$t('templateStudio.按主题声_1qxbzx')"
          @click="showThemeSettings = true"
        >
          {{ $t('templateStudio.主题配置_ai9rni') }}
        </button>
        <button class="btn-ghost text-sm" @click="exportTheme">{{ $t('templateStudio.导出_xxgvpb') }}</button>
        <button class="btn-ghost text-sm" @click="importInput?.click()">{{ $t('templateStudio.导入_vnjjai') }}</button>
        <input ref="importInput" type="file" accept=".zip" class="hidden" @change="doImport" />
        <button
          class="btn-ghost text-sm text-red-600"
          :disabled="!themes.find((t) => t.theme === currentTheme)?.deletable"
          @click="deleteTheme"
        >
          {{ $t('templateStudio.删除主题_azbhmp') }}
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
          {{ loadingFiles ? $t('templateStudio.加载中_b0k5km') : `${files.length} 个文件` }}
          <span v-if="files.some(f => f.disk)" class="ml-1 text-green-600" :title="$t('templateStudio.绿色_1v0mzo')">{{ $t('templateStudio.text_1qoxk9') }}</span>
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
                    :class="f.source === 'disk' ? 'h-1.5 bg-green-500' : f.source === 'db' ? 'h-1.5 bg-blue-500' : f.source === 'builtin' ? 'h-1.5 bg-ink-300' : 'h-1.5 bg-ink-200'"
                    :title="f.source === 'disk' ? '磁盘文件（优先于一切）' : f.source === 'db' ? '已覆盖（DB）' : f.source === 'builtin' ? '内置' : '继承自 default'" />
              <span class="truncate">{{ f.path.includes('/') ? f.path.slice(f.path.lastIndexOf('/') + 1) : f.path }}</span>
              <span v-if="f.disk" class="ml-auto text-[10px] text-green-600">{{ $t('templateStudio.盘_nh4') }}</span>
              <span v-else-if="f.overridden" class="ml-auto text-[10px] text-blue-600">{{ $t('templateStudio.改_jzt') }}</span>
            </button>
          </div>
        </div>
        <div class="border-t border-ink-100 p-2">
          <input v-model="newTheme" class="input mb-1 w-full text-xs" :placeholder="$t('templateStudio.新主题名_11j642')" />
          <button class="btn-ghost w-full text-xs" :disabled="!newTheme.trim()" @click="createTheme">
            {{ $t('templateStudio.从当前主_86p4yz') }}
          </button>
        </div>
      </aside>

      <!-- 编辑器 -->
      <section class="col-span-6 flex min-h-0 flex-col overflow-hidden rounded-lg border border-ink-100">
        <div class="flex items-center gap-2 border-b border-ink-100 px-2 py-1.5">
          <code class="text-xs font-medium">{{ currentPath || $t('templateStudio.未选择文_1usppb') }}</code>
          <span class="rounded px-1 text-[10px]"
                :class="sourceKind === 'disk' ? 'bg-green-50 text-green-700' : sourceKind === 'db' ? 'bg-blue-50 text-blue-700' : 'bg-ink-50 text-ink-500'">
            {{ sourceKind === 'disk' ? $t('templateStudio.磁盘文件_1o90d5') : sourceKind === 'db' ? $t('templateStudio.已覆盖_efeyq') : sourceKind === 'builtin' ? $t('templateStudio.内置_ekcp') : $t('templateStudio.继承_m4jc') }}
          </span>
          <span v-if="dirty" class="text-[10px] text-amber-600">{{ $t('templateStudio.未保存_fi2f9') }}</span>
          <span v-if="syntaxError" class="text-[10px] text-red-600">{{ $t('templateStudio.第_obw') }} {{ syntaxError.line }} {{ $t('templateStudio.行_okzy') }}{{ syntaxError.message }}</span>
          <div class="ml-auto flex items-center gap-1">
            <button class="btn-ghost text-xs" :disabled="!dirty || saving" @click="save">
              {{ saving ? $t('templateStudio.保存中_agdrec') : $t('templateStudio.保存_13nzbd') }}
            </button>
            <button class="btn-ghost text-xs" :disabled="sourceKind !== 'db'" @click="openDiff">{{ $t('templateStudio.差异_ghxw') }}</button>
            <button class="btn-ghost text-xs" :disabled="sourceKind !== 'db'" @click="revert">{{ $t('templateStudio.还原_oxc7') }}</button>
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
              <span class="text-xs font-medium">{{ $t('templateStudio.标签速查_dn4svx') }}</span>
              <button class="ml-auto text-[11px] text-ink-400 hover:text-ink-700" @click="showTags = false">{{ $t('templateStudio.关闭_eod6') }}</button>
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
              <input v-model="tagQuery" class="input h-7 w-full text-xs" :placeholder="$t('templateStudio.搜名字或_fqzoi')" />
            </div>

            <div class="min-h-0 flex-1 overflow-auto p-1.5">
              <p v-if="loadingTags" class="p-2 text-[11px] text-ink-400">{{ $t('templateStudio.加载中_b0k5km') }}</p>
              <p v-else-if="!filteredTags.length" class="p-2 text-[11px] text-ink-400">{{ $t('templateStudio.没匹配的_f6kr3a') }}</p>
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
              <p>{{ $t('templateStudio.自动转义_18o3qd') }} <code class="text-ink-600">|safe</code></p>
              <p class="mt-0.5">{{ $t('templateStudio.不能调_o3mog') }}</p>
              <p v-if="ctxApi.app_tags.functions.length || ctxApi.app_tags.filters.length" class="mt-1 text-ink-500">
                {{ $t('templateStudio.来自_e5nhhw') }}{{ [...ctxApi.app_tags.functions, ...ctxApi.app_tags.filters].join('、') }}
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
              <option value="article">{{ $t('templateStudio.文章_hxyx') }}</option>
              <option value="news">{{ $t('templateStudio.新闻_i4az') }}</option>
              <option value="product">{{ $t('templateStudio.产品_dud6') }}</option>
              <option value="case">{{ $t('templateStudio.案例_i69v') }}</option>
              <option value="page">{{ $t('templateStudio.单页_f0e8') }}</option>
              <option value="list">{{ $t('templateStudio.列表_epm9') }}</option>
            </select>
            <input v-model="previewSlug" class="input h-7 flex-1 text-xs" :placeholder="$t('templateStudio.text_fp9oz4')" />
            <button class="btn-ghost text-xs" :disabled="previewing" @click="runPreview">{{ $t('templateStudio.刷新_ejix') }}</button>
          </template>
          <template v-else>
            <span class="text-xs font-medium">{{ $t('templateStudio.差异_ghxw') }}</span>
            <span class="text-[10px] text-green-600">+{{ diffStat.added }}</span>
            <span class="text-[10px] text-red-600">-{{ diffStat.removed }}</span>
            <button class="btn-ghost ml-auto text-xs" @click="showDiff = false">{{ $t('templateStudio.关闭_eod6') }}</button>
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
            <h2 class="text-lg font-semibold">{{ $t('templateStudio.主题模板_16yino') }}</h2>
            <p class="mt-1 text-xs text-ink-500">{{ $t('templateStudio.只需要会_1jn0ti') }}</p>
          </div>
          <button class="btn-ghost text-xs" @click="showHelp = false">{{ $t('templateStudio.关闭_eod6') }}</button>
        </div>

        <div class="mb-5 rounded border border-amber-200 bg-amber-50 p-3 text-[13px]">
          <p class="font-medium text-amber-800">{{ $t('templateStudio.动手前先_pwzru9') }}</p>
          <ol class="mt-2 list-decimal space-y-1 pl-5 text-amber-900">
            <li>
              <b>{{ $t('templateStudio.首页不归_1s7sp8') }}</b>{{ $t('templateStudio.站点根地_eob3o1') }}
              <code class="rounded bg-amber-100 px-1">index.html</code>{{ $t('templateStudio.text_f9bxs2') }}
            </li>
            <li>
              <b>{{ $t('templateStudio.主题是_6a9omb') }}</b>{{ $t('templateStudio.数据库里_knu8r9') }}
              <code class="rounded bg-amber-100 px-1">default</code> {{ $t('templateStudio.主题_kcpze2') }}
            </li>
            <li>
              <b>{{ $t('templateStudio.保存即生_wzc76p') }}</b>{{ $t('templateStudio.不用重启_1g86m5') }}<b>{{ $t('templateStudio.text_1mq0iq') }}</b>{{ $t('templateStudio.才算上线_nov578') }}
            </li>
          </ol>
        </div>

        <div class="mb-5">
          <h3 class="mb-2 font-semibold">{{ $t('templateStudio.三步做第_s912wl') }}</h3>
          <ol class="list-decimal space-y-1 pl-5">
            <li>{{ $t('templateStudio.左下角输_vq1u9g') }} <code class="rounded bg-ink-100 px-1">magazine</code>{{ $t('templateStudio.text_1ldik8') }}</li>
            <li>{{ $t('templateStudio.改文件_xlq1j7') }} <code class="rounded bg-ink-100 px-1">assets/style.css</code> {{ $t('templateStudio.顶部的配_if572e') }}</li>
            <li>{{ $t('templateStudio.右上角点_8hm4m0') }} <code class="rounded bg-ink-100 px-1">default</code> {{ $t('templateStudio.再点一次_1dac88') }}</li>
          </ol>
        </div>

        <div class="mb-5">
          <h3 class="mb-2 font-semibold">{{ $t('templateStudio.文件对照_d50il9') }}</h3>
          <table class="w-full text-[13px]">
            <tbody class="[&_td]:border-b [&_td]:border-ink-100 [&_td]:py-1.5 [&_td]:align-top">
              <tr><td class="w-56 pr-3"><code>partials/header.html</code></td><td>{{ $t('templateStudio.站头_49et7o') }}</td></tr>
              <tr><td class="pr-3"><code>partials/footer.html</code></td><td>{{ $t('templateStudio.页脚_vfpuek') }}</td></tr>
              <tr><td class="pr-3"><code>partials/card.html</code></td><td>{{ $t('templateStudio.列表卡片_13xal1') }} <code>r</code></td></tr>
              <tr><td class="pr-3"><code>partials/pagination.html</code></td><td>{{ $t('templateStudio.分页条_6feh7e') }}</td></tr>
              <tr><td class="pr-3"><code>detail.html</code></td><td>{{ $t('templateStudio.文章_31omsc') }}</td></tr>
              <tr><td class="pr-3"><code>list.html</code></td><td>{{ $t('templateStudio.七种列表_y3ohtd') }}</td></tr>
              <tr><td class="pr-3"><code>layout.html</code></td><td>{{ $t('templateStudio.全站_1tqwi7') }}</td></tr>
              <tr><td class="pr-3"><code>assets/style.css</code></td><td>{{ $t('templateStudio.全站样式_1bc994') }}</td></tr>
            </tbody>
          </table>
        </div>

        <div class="mb-5">
          <h3 class="mb-2 font-semibold">{{ $t('templateStudio.最容易踩_1r5ahk') }}</h3>
          <ul class="list-disc space-y-1 pl-5">
            <li>{{ $t('templateStudio.正文变量_1ylubc') }} <code class="rounded bg-ink-100 px-1">| safe</code>{{ $t('templateStudio.text_1sjqcp') }} <code class="rounded bg-ink-100 px-1">&amp;lt;p&amp;gt;</code>。</li>
            <li><code class="rounded bg-ink-100 px-1">item.cover</code> {{ $t('templateStudio.可能是空_19z90f') }} <code class="rounded bg-ink-100 px-1">if</code> {{ $t('templateStudio.包着_pv2f2j') }} <code class="rounded bg-ink-100 px-1">&lt;img src=""&gt;</code> {{ $t('templateStudio.多一次_1kaq29') }}</li>
            <li>{{ $t('templateStudio.列表数据_2ebbs5') }} <code class="rounded bg-ink-100 px-1">items</code>{{ $t('templateStudio.text_11rh49') }} <code class="rounded bg-ink-100 px-1">page.items</code>{{ $t('templateStudio.text_1nakuw') }}</li>
            <li>{{ $t('templateStudio.别删_efdh') }} <code class="rounded bg-ink-100 px-1">partials/meta.html</code>{{ $t('templateStudio.text_12ahzc') }}</li>
            <li>{{ $t('templateStudio.预览区是_1p8s8g') }}<b>{{ $t('templateStudio.加了_1fo1iz') }}</b>{{ $t('templateStudio.text_1blkus') }}</li>
          </ul>
        </div>

        <p class="border-t border-ink-100 pt-3 text-xs text-ink-500">
          {{ $t('templateStudio.完整教程_idacqj') }}
          <code class="rounded bg-ink-100 px-1">docs/template-guide.md</code>{{ $t('templateStudio.text_1yrxt0') }}
        </p>
      </div>
    </div>
  </div>

  <ThemeSettingsDialog
    :open="showThemeSettings"
    :theme="currentTheme"
    @close="showThemeSettings = false"
    @saved="onThemeSaved"
  />
</template>
