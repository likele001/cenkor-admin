<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, reactive, computed, onMounted } from 'vue'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

interface FieldRow {
  name: string
  label: string
  type: string
  len: number
  precision: number
  scale: number
  required: boolean
  unique: boolean
  list: boolean
  search: boolean
  filter: boolean
  /** enum 用：逗号分隔的选项 */
  choices: string
  /** fk 用：目标实体 key */
  entity: string
}

interface EntityRow {
  key: string
  title: string
  subtitle: string
  fields: FieldRow[]
}

interface AppForm {
  key: string
  name: string
  icon: string
  version: string
  category: string
  author: string
  description: string
  sort: number
}

interface TableColumn {
  name: string
  type: string
  suggested_type: string
  len: number | null
  precision: number | null
  scale: number | null
  nullable: boolean
  builtin: boolean
  default: string | null
}

interface TableItem {
  name: string
  columns: TableColumn[]
}

const auth = useAuthStore()

const meta = ref<any>(null)
const mode = ref<'visual' | 'yaml'>('visual')
const yamlText = ref('')
const loading = ref(true)
const busy = ref<'' | 'preview' | 'generate' | 'install' | 'apply'>('')
const error = ref('')
const ok = ref('')
const preview = ref<any>(null)
const confirmOpen = ref(false)
const confirmText = ref('')
const metaError = ref('')

const appForm = reactive<AppForm>({
  key: '',
  name: '',
  icon: '',
  version: '1.0.0',
  category: 'business',
  author: '',
  description: '',
  sort: 80,
})
const entities = ref<EntityRow[]>([])

const tablesOpen = ref(false)
const tables = ref<TableItem[]>([])
const tableQ = ref('')
const tablesLoading = ref(false)
const tablesError = ref('')

const canWrite = computed(() => auth.hasPermission('system:codegen:write'))
const pluginReady = computed(() => !!meta.value?.plugin_asset?.exists)
const alreadyInstalled = computed(() => {
  const key = preview.value?.spec?.key
  return !!key && (meta.value?.installed_keys || []).includes(key)
})
const fieldTypes = computed<string[]>(() => meta.value?.field_types || [])
const entityTitles = computed(() =>
  (preview.value?.spec?.entities || []).map((e: any) => e.title).join('、'),
)

const KEY_RE = /^[a-z][a-z0-9_]*$/

function hasDup(list: string[]) {
  return list.length !== new Set(list).size
}

/** 前端即时校验：把明显会在后端 400 的问题提前指出来。 */
const localIssues = computed<string[]>(() => {
  const out: string[] = []
  if (!KEY_RE.test(appForm.key)) out.push('应用 key 必须小写字母开头，且只含小写字母/数字/下划线')
  if (!appForm.name.trim()) out.push('应用名称不能为空')
  if (!entities.value.length) out.push('至少需要 1 个实体')
  if (hasDup(entities.value.map((e) => e.key))) out.push('实体 key 有重复')
  entities.value.forEach((e, i) => {
    const tag = e.key || `#${i + 1}`
    if (!KEY_RE.test(e.key)) out.push(`实体 ${tag} 的 key 不合法`)
    if (!e.fields.length) out.push(`实体 ${tag} 至少需要 1 个字段`)
    if (hasDup(e.fields.map((f) => f.name))) out.push(`实体 ${tag} 的字段名有重复`)
    e.fields.forEach((f) => {
      if (!f.name.trim()) out.push(`实体 ${tag} 有字段未填字段名`)
      if (f.type === 'enum' && !f.choices.trim()) out.push(`实体 ${tag} 的 ${f.name} 是 enum，必须填选项`)
      if (f.type === 'fk' && !f.entity) out.push(`实体 ${tag} 的 ${f.name} 是 fk，必须选择目标实体`)
    })
  })
  return out
})

/** 实时推算「将执行的清单」（表名/菜单路径由 key + 实体 key 决定，与后端规则一致）。 */
const planEntities = computed(() =>
  entities.value.map((e) => ({
    title: e.title || e.key,
    table: appForm.key ? `${appForm.key}_${e.key}` : `__${e.key}`,
    menuPath: appForm.key ? `/${appForm.key}/${e.key}` : `/__/${e.key}`,
    fieldCount: e.fields.length,
  })),
)

function newField(): FieldRow {
  return {
    name: '', label: '', type: 'string', len: 255, precision: 12, scale: 2,
    required: false, unique: false, list: true, search: false, filter: false,
    choices: '', entity: '',
  }
}

function addEntity() {
  entities.value.push({ key: '', title: '', subtitle: '', fields: [newField()] })
}

function removeEntity(i: number) {
  entities.value.splice(i, 1)
}

function moveEntity(i: number, d: number) {
  const j = i + d
  if (j < 0 || j >= entities.value.length) return
  const [row] = entities.value.splice(i, 1)
  entities.value.splice(j, 0, row)
}

function addField(e: EntityRow) {
  e.fields.push(newField())
}

function removeField(e: EntityRow, i: number) {
  e.fields.splice(i, 1)
}

function moveField(e: EntityRow, i: number, d: number) {
  const j = i + d
  if (j < 0 || j >= e.fields.length) return
  const [row] = e.fields.splice(i, 1)
  e.fields.splice(j, 0, row)
}

/** 可视化表单 → 后端 spec（只送后端需要的键，其余交给 norm_spec 推导）。 */
function buildSpec() {
  return {
    key: appForm.key,
    name: appForm.name,
    icon: appForm.icon,
    version: appForm.version,
    category: appForm.category,
    author: appForm.author,
    description: appForm.description,
    sort: appForm.sort,
    entities: entities.value.map((e) => ({
      key: e.key,
      title: e.title,
      subtitle: e.subtitle,
      fields: e.fields.map((f) => {
        const o: any = { name: f.name, label: f.label, type: f.type, list: f.list }
        if (f.required) o.required = true
        if (f.unique) o.unique = true
        if (f.search) o.search = true
        if (f.filter) o.filter = true
        if (f.type === 'string') o.len = Number(f.len) || 255
        if (f.type === 'decimal') {
          o.precision = Number(f.precision) || 12
          o.scale = Number(f.scale) || 2
        }
        if (f.type === 'enum') o.choices = f.choices.split(/[,，\s]+/).filter(Boolean)
        if (f.type === 'fk') o.entity = f.entity
        return o
      }),
    })),
  }
}

/** 规范化后的 spec → 可视化表单（只读 title，避免 "管理" 后缀被反复追加）。 */
function fillFromSpec(s: any) {
  appForm.key = s.key || ''
  appForm.name = s.name || ''
  appForm.icon = s.icon || ''
  appForm.version = s.version || '1.0.0'
  appForm.category = s.category || 'business'
  appForm.author = s.author || ''
  appForm.description = s.description || ''
  appForm.sort = Number(s.sort) || 80
  entities.value = (s.entities || []).map((e: any) => ({
    key: e.key || '',
    title: e.title || '',
    subtitle: e.subtitle || '',
    fields: (e.fields || []).map((f: any) => ({
      name: f.name || '',
      label: f.label || '',
      type: f.type || 'string',
      len: Number(f.len) || 255,
      precision: Number(f.precision) || 12,
      scale: Number(f.scale) || 2,
      required: !!f.required,
      unique: !!f.unique,
      list: f.list !== false,
      search: !!f.search,
      filter: !!f.filter,
      choices: (f.choices || []).join(', '),
      entity: f.fk_entity || '',
    })),
  }))
}

function payload() {
  return mode.value === 'yaml' ? { yaml: yamlText.value } : { spec: buildSpec() }
}

function fmtSize(n: number) {
  if (!n) return '0 B'
  if (n < 1024) return n + ' B'
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB'
  return (n / 1024 / 1024).toFixed(2) + ' MB'
}

function fmtTime(s: string | null) {
  if (!s) return '—'
  const d = new Date(s)
  return isNaN(d.getTime()) ? s : d.toLocaleString()
}

/** 把二进制响应存成文件，返回实际文件名（从 content-disposition 里取）。 */
function downloadBlob(res: any, fallback: string) {
  const m = /filename="?([^";]+)"?/.exec(res.headers?.['content-disposition'] || '')
  const filename = m ? m[1] : fallback
  const url = URL.createObjectURL(res.data as Blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
  return filename
}

async function errText(e: any): Promise<string> {
  const d = e?.response?.data
  if (d instanceof Blob) {
    try {
      const j = JSON.parse(await d.text())
      return j.detail || t("codegen.请求失败_i3trb3")
    } catch {
      return t("codegen.请求失败_i3trb3")
    }
  }
  return d?.detail || e?.message || t("codegen.请求失败_i3trb3")
}

async function loadMeta() {
  loading.value = true
  error.value = ''
  metaError.value = ''
  try {
    const { data } = await api.get('/api/v1/system/codegen/meta')
    meta.value = data
  } catch (e: any) {
    // meta 是页面唯一的前置依赖：失败时单独提示（404 多半是后端进程还没重启），
    // 不走通用的红色 error 卡，也避免把「插件资产缺失」的兜底告警误报出来。
    metaError.value = await errText(e)
  } finally {
    loading.value = false
  }
}

/** 载入样例：走后端解析，直接回填可视化表单。 */
async function loadSample() {
  if (!meta.value?.sample) return
  busy.value = 'preview'
  error.value = ''
  ok.value = ''
  try {
    const { data } = await api.post(
      '/api/v1/system/codegen/preview',
      { yaml: meta.value.sample },
      { timeout: 60_000 },
    )
    fillFromSpec(data.spec)
    yamlText.value = data.yaml
    preview.value = data
    mode.value = 'visual'
    ok.value = t("codegen.已载入样_6h5jn9")
  } catch (e: any) {
    error.value = await errText(e)
  } finally {
    busy.value = ''
  }
}

async function doPreview() {
  if (mode.value === 'visual' && localIssues.value.length) {
    error.value = localIssues.value.join('；')
    return
  }
  busy.value = 'preview'
  error.value = ''
  ok.value = ''
  preview.value = null
  try {
    const { data } = await api.post('/api/v1/system/codegen/preview', payload(), { timeout: 60_000 })
    preview.value = data
    if (mode.value === 'visual') yamlText.value = data.yaml
  } catch (e: any) {
    error.value = await errText(e)
  } finally {
    busy.value = ''
  }
}

async function doGenerate() {
  if (mode.value === 'visual' && localIssues.value.length) {
    error.value = localIssues.value.join('；')
    return
  }
  busy.value = 'generate'
  error.value = ''
  ok.value = ''
  try {
    const res = await api.post('/api/v1/system/codegen/generate', payload(), {
      responseType: 'blob',
      timeout: 120_000,
    })
    const filename = downloadBlob(res, 'app.zip')
    ok.value = `已生成源码包：${filename}（可上传开发者中心分发，或在本页直接「安装到本系统」）`
    await loadRuns()
  } catch (e: any) {
    error.value = await errText(e)
  } finally {
    busy.value = ''
  }
}

async function openConfirm() {
  if (!preview.value) {
    await doPreview()
    if (!preview.value) return
  }
  confirmText.value = ''
  confirmOpen.value = true
}

async function doInstall() {
  if (confirmText.value !== preview.value?.spec?.key) return
  busy.value = 'install'
  error.value = ''
  ok.value = ''
  try {
    const { data } = await api.post('/api/v1/system/codegen/install', payload(), { timeout: 180_000 })
    confirmOpen.value = false
    ok.value =
      `应用 ${data.key} 已安装：已建表、注册 ${data.permissions?.length || 0} 个权限与菜单（授予 super_admin）、` +
      `动态注册了 API 路由。现在去「应用中心」确认状态、或直接刷新页面在侧边栏看到「${data.name}」。`
    await loadMeta()
    await loadRuns()
  } catch (e: any) {
    error.value = await errText(e)
    confirmOpen.value = false
  } finally {
    busy.value = ''
  }
}

/** YAML（高级模式）→ 可视化：由后端解析，避免前端引入 YAML 依赖。 */
async function applyYaml() {
  busy.value = 'apply'
  error.value = ''
  ok.value = ''
  try {
    const { data } = await api.post(
      '/api/v1/system/codegen/preview',
      { yaml: yamlText.value },
      { timeout: 60_000 },
    )
    fillFromSpec(data.spec)
    yamlText.value = data.yaml
    preview.value = data
    mode.value = 'visual'
    ok.value = t("codegen.已按_96t9f7")
  } catch (e: any) {
    error.value = await errText(e)
  } finally {
    busy.value = ''
  }
}

/** 可视化 → YAML：同样走后端，拿到规范化后的 YAML 存档。 */
async function toYaml() {
  if (localIssues.value.length) {
    error.value = localIssues.value.join('；')
    return
  }
  busy.value = 'preview'
  error.value = ''
  try {
    const { data } = await api.post(
      '/api/v1/system/codegen/preview',
      { spec: buildSpec() },
      { timeout: 60_000 },
    )
    yamlText.value = data.yaml
    preview.value = data
    mode.value = 'yaml'
  } catch (e: any) {
    error.value = await errText(e)
  } finally {
    busy.value = ''
  }
}

async function openTables() {
  tablesOpen.value = true
  if (!tables.value.length) await loadTables()
}

async function loadTables() {
  tablesLoading.value = true
  tablesError.value = ''
  try {
    const params = tableQ.value ? { q: tableQ.value } : {}
    const { data } = await api.get('/api/v1/system/codegen/tables', { params, timeout: 30_000 })
    tables.value = data.items || []
  } catch (e: any) {
    tablesError.value = await errText(e)
  } finally {
    tablesLoading.value = false
  }
}

function importTable(t: TableItem) {
  const prefix = appForm.key ? appForm.key + '_' : ''
  let key = t.name
  if (prefix && key.startsWith(prefix)) key = key.slice(prefix.length)
  key = key.toLowerCase().replace(/[^a-z0-9_]/g, '_')
  if (!/^[a-z]/.test(key)) key = 'e_' + key
  entities.value.push({
    key,
    title: key,
    subtitle: '',
    fields: t.columns.map((c) => ({
      name: c.name,
      label: c.name,
      type: c.suggested_type,
      len: Number(c.len) || 255,
      precision: Number(c.precision) || 12,
      scale: Number(c.scale) || 2,
      required: !c.nullable,
      unique: false,
      list: true,
      search: false,
      filter: c.suggested_type === 'bool',
      choices: '',
      entity: '',
    })),
  })
  tablesOpen.value = false
  ok.value = `已按表 ${t.name} 导入实体 ${key}（${t.columns.length} 个字段），请核对后预览。`
}

/* ===================== 执行历史 ===================== */

interface RunItem {
  id: number
  app_key: string
  app_name: string | null
  action: string
  status: string
  summary: string | null
  duration_ms: number | null
  operator_id: number | null
  created_at: string | null
}

const runs = ref<RunItem[]>([])
const runsLoading = ref(false)
const runsBusy = ref(false)
const runsError = ref('')
const runsAction = ref('')
const runDetail = ref<any>(null)
const runDetailOpen = ref(false)
const rerunRun = ref<RunItem | null>(null)
const rerunOpen = ref(false)

async function loadRuns() {
  runsLoading.value = true
  runsError.value = ''
  try {
    const params: any = { limit: 30 }
    if (runsAction.value) params.action = runsAction.value
    const { data } = await api.get('/api/v1/system/codegen/runs', { params, timeout: 30_000 })
    runs.value = data.items || []
  } catch (e: any) {
    runsError.value = await errText(e)
  } finally {
    runsLoading.value = false
  }
}

async function openRunDetail(r: RunItem) {
  runDetail.value = null
  runDetailOpen.value = true
  try {
    const { data } = await api.get(`/api/v1/system/codegen/runs/${r.id}`, { timeout: 30_000 })
    runDetail.value = data
  } catch (e: any) {
    error.value = await errText(e)
    runDetailOpen.value = false
  }
}

async function doDeleteRun(r: RunItem) {
  if (!window.confirm(`删除执行记录 #${r.id}？只删留痕，不影响已安装的 App 与其数据表。`)) return
  runsBusy.value = true
  error.value = ''
  try {
    await api.delete(`/api/v1/system/codegen/runs/${r.id}`)
    ok.value = `已删除执行记录 #${r.id}。`
    await loadRuns()
  } catch (e: any) {
    error.value = await errText(e)
  } finally {
    runsBusy.value = false
  }
}

/** 再次执行：generate 直接下载；install 先弹强确认（会再次建表 / 覆盖同名 App）。 */
function openRerun(r: RunItem | null) {
  if (!r) return
  if (r.action === 'install') {
    rerunRun.value = r
    rerunOpen.value = true
  } else {
    void doRerun(r)
  }
}

async function doRerun(r: RunItem | null) {
  if (!r) return
  runsBusy.value = true
  error.value = ''
  ok.value = ''
  try {
    if (r.action === 'install') {
      const { data } = await api.post(
        `/api/v1/system/codegen/runs/${r.id}/rerun`,
        {},
        { timeout: 180_000 },
      )
      rerunOpen.value = false
      ok.value = `已按历史记录 #${r.id} 重新安装 ${data.key}。`
      await loadMeta()
    } else {
      const res = await api.post(`/api/v1/system/codegen/runs/${r.id}/rerun`, {}, {
        responseType: 'blob',
        timeout: 120_000,
      })
      const filename = downloadBlob(res, 'app.zip')
      ok.value = `已按历史记录 #${r.id} 重新生成：${filename}`
    }
    runDetailOpen.value = false
    await loadRuns()
  } catch (e: any) {
    error.value = await errText(e)
    rerunOpen.value = false
  } finally {
    runsBusy.value = false
  }
}

/** 把历史记录里的 spec 快照回填到可视化表单（先经后端规范化再填）。 */
async function loadSpecFromRun(r: any) {
  if (!r?.spec) return
  runsBusy.value = true
  error.value = ''
  ok.value = ''
  try {
    const { data } = await api.post(
      '/api/v1/system/codegen/preview',
      { spec: r.spec },
      { timeout: 60_000 },
    )
    fillFromSpec(data.spec)
    yamlText.value = data.yaml
    preview.value = data
    mode.value = 'visual'
    runDetailOpen.value = false
    ok.value = `已把执行记录 #${r.id} 的 spec 回填到表单。`
  } catch (e: any) {
    error.value = await errText(e)
  } finally {
    runsBusy.value = false
  }
}

onMounted(() => {
  loadMeta()
  loadRuns()
})
</script>

<template>
  <div>
    <h1 class="text-2xl font-semibold tracking-tight mb-2">{{ $t('codegen.代码生成_agc8nj') }}</h1>
    <p class="text-ink-500 mb-6">
      {{ $t('codegen.用一张表_hdi7ru') }}
    </p>

    <div v-if="loading" class="card text-ink-500">{{ $t('codegen.加载中_b0k5km') }}</div>
    <template v-else>
      <div v-if="error" class="card text-red-600 mb-4 break-all whitespace-pre-wrap">{{ error }}</div>
      <div v-if="ok" class="card text-green-600 mb-4">{{ ok }}</div>
      <div v-if="metaError" class="card text-amber-600 mb-4">
        {{ $t('codegen.后端代码_602eo2') }}
        <code class="bg-ink-50 px-1 rounded">{{ metaError }}</code>{{ $t('codegen.text_3fcvre') }}
      </div>
      <div v-if="meta && !pluginReady" class="card text-amber-600 mb-4">
        {{ $t('codegen.未找到前_1bdrn6') }}
        <code class="bg-ink-50 px-1 rounded">codegen/assets/plugin_head.js</code>{{ $t('codegen.text_37n9p6') }}
        <code class="bg-ink-50 px-1 rounded">runtime_plugin/README.md</code> {{ $t('codegen.构建一次_1pwehc') }}
      </div>

      <!-- 模式切换 -->
      <div class="flex items-center gap-2 mb-4">
        <button
          class="text-sm px-3 py-1.5 rounded"
          :class="mode === 'visual' ? 'bg-ink-900 text-white' : 'btn-ghost'"
          @click="mode = 'visual'"
        >
          {{ $t('codegen.可视化配_1psfby') }}
        </button>
        <button
          class="text-sm px-3 py-1.5 rounded"
          :class="mode === 'yaml' ? 'bg-ink-900 text-white' : 'btn-ghost'"
          @click="mode = 'yaml'"
        >
          {{ $t('codegen.text_126ako') }}
        </button>
        <div class="flex-1"></div>
        <button class="btn-ghost text-xs" :disabled="!!busy" @click="loadSample">{{ $t('codegen.载入样例_ify9x8') }}</button>
      </div>

      <!-- ===================== 可视化 ===================== -->
      <template v-if="mode === 'visual'">
        <div class="card mb-6">
          <h2 class="font-semibold mb-3">{{ $t('codegen.应用信息_cezu0y') }}</h2>
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
            <label class="block">
              <span class="text-xs text-ink-500">{{ $t('codegen.应用_13i9zn') }}</span>
              <input v-model.trim="appForm.key" class="input w-full font-mono" placeholder="inventory" />
            </label>
            <label class="block">
              <span class="text-xs text-ink-500">{{ $t('codegen.应用名称_cf0olz') }}</span>
              <input v-model.trim="appForm.name" class="input w-full" :placeholder="$t('codegen.库存管理_cbemwa')" />
            </label>
            <label class="block">
              <span class="text-xs text-ink-500">{{ $t('codegen.图标_717gde') }}</span>
              <input v-model.trim="appForm.icon" class="input w-full" :placeholder="$t('codegen.留空用默_1cl4vt')" />
            </label>
            <label class="block">
              <span class="text-xs text-ink-500">{{ $t('codegen.版本_k06c') }}</span>
              <input v-model.trim="appForm.version" class="input w-full" placeholder="1.0.0" />
            </label>
            <label class="block">
              <span class="text-xs text-ink-500">{{ $t('codegen.分类_emut') }}</span>
              <input v-model.trim="appForm.category" class="input w-full" placeholder="business" />
            </label>
            <label class="block">
              <span class="text-xs text-ink-500">{{ $t('codegen.作者_e78p') }}</span>
              <input v-model.trim="appForm.author" class="input w-full" placeholder="Cenkor Team" />
            </label>
            <label class="block">
              <span class="text-xs text-ink-500">{{ $t('codegen.菜单排序_gzewae') }}</span>
              <input v-model.number="appForm.sort" type="number" class="input w-full" />
            </label>
            <label class="block">
              <span class="text-xs text-ink-500">{{ $t('codegen.描述_hrlt') }}</span>
              <input v-model.trim="appForm.description" class="input w-full" :placeholder="$t('codegen.库存基础_14wf5v')" />
            </label>
          </div>
          <p class="text-xs text-ink-400 mt-3">
            {{ $t('codegen.表名与菜_1m35ch') }} <code class="bg-ink-50 px-1 rounded">warehouse</code>
            {{ $t('codegen.text_4xs9m') }} <code class="bg-ink-50 px-1 rounded">{{ appForm.key || 'key' }}_warehouse</code>
            {{ $t('codegen.text_3we82') }} <code class="bg-ink-50 px-1 rounded">/{{ appForm.key || 'key' }}/warehouse</code>
          </p>
        </div>

        <div class="card mb-6">
          <div class="flex items-center justify-between mb-3">
            <h2 class="font-semibold">{{ $t('codegen.实体_dtzjn') }}{{ entities.length }}）</h2>
            <div class="flex gap-2">
              <button class="btn-ghost text-xs" :disabled="!!busy" @click="openTables">{{ $t('codegen.从已有表_1ng9k7') }}</button>
              <button class="btn-ghost text-xs" @click="addEntity">{{ $t('codegen.text_z2girz') }}</button>
            </div>
          </div>

          <div v-if="!entities.length" class="text-ink-500 text-sm py-4">
            {{ $t('codegen.还没有实_1f3od6') }}
          </div>

          <div v-for="(e, ei) in entities" :key="ei" class="border border-ink-100 rounded-lg p-3 mb-3">
            <div class="flex flex-wrap items-end gap-2 mb-3 text-sm">
              <label class="block">
                <span class="text-xs text-ink-500">{{ $t('codegen.实体_1e2zui') }}</span>
                <input v-model.trim="e.key" class="input font-mono w-40" placeholder="warehouse" />
              </label>
              <label class="block">
                <span class="text-xs text-ink-500">{{ $t('codegen.显示名称_deexj3') }}</span>
                <input v-model.trim="e.title" class="input w-40" :placeholder="$t('codegen.仓库_dxcw')" />
              </label>
              <label class="block flex-1 min-w-[12rem]">
                <span class="text-xs text-ink-500">{{ $t('codegen.副标题_cl7a8') }}</span>
                <input v-model.trim="e.subtitle" class="input w-full" :placeholder="$t('codegen.仓库基础_1qbic5')" />
              </label>
              <div class="flex gap-1">
                <button class="btn-ghost text-xs" :disabled="ei === 0" @click="moveEntity(ei, -1)">{{ $t('codegen.上移_dxyp') }}</button>
                <button
                  class="btn-ghost text-xs"
                  :disabled="ei === entities.length - 1"
                  @click="moveEntity(ei, 1)"
                >{{ $t('codegen.下移_dxzk') }}</button>
                <button class="btn-ghost text-xs text-red-600" @click="removeEntity(ei)">{{ $t('codegen.删除_eslg') }}</button>
              </div>
            </div>

            <div class="overflow-x-auto">
              <table class="w-full text-xs">
                <thead>
                  <tr class="text-ink-500 text-left">
                    <th class="font-normal py-1 pr-2">{{ $t('codegen.字段名_dwexb') }}</th>
                    <th class="font-normal py-1 pr-2">{{ $t('codegen.标签_idef') }}</th>
                    <th class="font-normal py-1 pr-2">{{ $t('codegen.类型_lnjk') }}</th>
                    <th class="font-normal py-1 pr-2">{{ $t('codegen.参数_esxa') }}</th>
                    <th class="font-normal py-1 pr-2">{{ $t('codegen.必填_grwm') }}</th>
                    <th class="font-normal py-1 pr-2">{{ $t('codegen.唯一_ex0x') }}</th>
                    <th class="font-normal py-1 pr-2">{{ $t('codegen.列表_epm9') }}</th>
                    <th class="font-normal py-1 pr-2">{{ $t('codegen.搜索_hpqe') }}</th>
                    <th class="font-normal py-1 pr-2">{{ $t('codegen.筛选_lrta') }}</th>
                    <th class="font-normal py-1"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(f, fi) in e.fields" :key="fi" class="border-t border-ink-100">
                    <td class="py-1.5 pr-2">
                      <input v-model.trim="f.name" class="input font-mono w-32" placeholder="code" />
                    </td>
                    <td class="py-1.5 pr-2">
                      <input v-model.trim="f.label" class="input w-32" :placeholder="$t('codegen.仓库编码_acdqyz')" />
                    </td>
                    <td class="py-1.5 pr-2">
                      <select v-model="f.type" class="input w-24">
                        <option v-for="t in fieldTypes" :key="t" :value="t">{{ t }}</option>
                      </select>
                    </td>
                    <td class="py-1.5 pr-2">
                      <input
                        v-if="f.type === 'string'"
                        v-model.number="f.len"
                        type="number"
                        class="input w-24"
                        :placeholder="$t('codegen.长度_py4n')"
                      />
                      <div v-else-if="f.type === 'decimal'" class="flex gap-1">
                        <input v-model.number="f.precision" type="number" class="input w-16" :placeholder="$t('codegen.精度_lqjs')" />
                        <input v-model.number="f.scale" type="number" class="input w-16" :placeholder="$t('codegen.小数_g7r5')" />
                      </div>
                      <input
                        v-else-if="f.type === 'enum'"
                        v-model.trim="f.choices"
                        class="input w-40"
                        :placeholder="$t('codegen.成品仓_19ixve')"
                      />
                      <select v-else-if="f.type === 'fk'" v-model="f.entity" class="input w-32">
                        <option value="">{{ $t('codegen.选择目标_vtc3ym') }}</option>
                        <option v-for="o in entities" :key="o.key" :value="o.key">{{ o.key }}</option>
                      </select>
                      <span v-else class="text-ink-400">—</span>
                    </td>
                    <td class="py-1.5 pr-2"><input type="checkbox" v-model="f.required" /></td>
                    <td class="py-1.5 pr-2"><input type="checkbox" v-model="f.unique" /></td>
                    <td class="py-1.5 pr-2"><input type="checkbox" v-model="f.list" /></td>
                    <td class="py-1.5 pr-2"><input type="checkbox" v-model="f.search" /></td>
                    <td class="py-1.5 pr-2"><input type="checkbox" v-model="f.filter" /></td>
                    <td class="py-1.5 whitespace-nowrap">
                      <button class="text-ink-400 px-1" :disabled="fi === 0" @click="moveField(e, fi, -1)">↑</button>
                      <button
                        class="text-ink-400 px-1"
                        :disabled="fi === e.fields.length - 1"
                        @click="moveField(e, fi, 1)"
                      >↓</button>
                      <button class="text-red-500 px-1" @click="removeField(e, fi)">✕</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <button class="btn-ghost text-xs mt-2" @click="addField(e)">{{ $t('codegen.text_z2gmoo') }}</button>
          </div>
        </div>

        <div class="card mb-6">
          <h2 class="font-semibold mb-3">{{ $t('codegen.将执行的_1dj0e2') }}</h2>
          <div v-if="!planEntities.length" class="text-ink-500 text-sm">{{ $t('codegen.先定义实_1r1gz2') }}</div>
          <table v-else class="w-full text-xs">
            <thead>
              <tr class="text-ink-500 text-left">
                <th class="font-normal py-1">{{ $t('codegen.实体_g0ol') }}</th>
                <th class="font-normal py-1">{{ $t('codegen.数据表_fcje2') }}</th>
                <th class="font-normal py-1">{{ $t('codegen.菜单路径_gzm3vy') }}</th>
                <th class="font-normal py-1">{{ $t('codegen.字段数_dwicy') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(p, i) in planEntities" :key="i" class="border-t border-ink-100">
                <td class="py-1.5">{{ p.title }}</td>
                <td class="py-1.5 font-mono">{{ p.table }}</td>
                <td class="py-1.5 font-mono">{{ p.menuPath }}</td>
                <td class="py-1.5">{{ p.fieldCount }}</td>
              </tr>
            </tbody>
          </table>
          <p class="text-xs text-ink-400 mt-3">
            {{ $t('codegen.生成的每_1ss2mj') }}
          </p>
        </div>
      </template>

      <!-- ===================== YAML ===================== -->
      <template v-else>
        <div class="card mb-6">
          <div class="flex items-center justify-between mb-3">
            <h2 class="font-semibold">{{ $t('codegen.应用规格_179emm') }}</h2>
            <div class="flex gap-2">
              <button class="btn-ghost text-xs" :disabled="!!busy" @click="applyYaml">
                {{ busy === 'apply' ? $t('codegen.解析中_htmu06') : $t('codegen.解析到可_8lqxs9') }}
              </button>
              <button class="btn-ghost text-xs" :disabled="!!busy" @click="toYaml">{{ $t('codegen.由可视化_1oaixm') }}</button>
            </div>
          </div>
          <textarea
            v-model="yamlText"
            class="input font-mono text-xs leading-5 w-full"
            style="height: 460px"
            spellcheck="false"
            :placeholder="$t('codegen.text_12kgau')"
            @input="preview = null"
          ></textarea>
        </div>
      </template>

      <!-- ===================== 操作条 ===================== -->
      <div class="card mb-6">
        <div class="flex flex-wrap items-center gap-2">
          <button class="btn-primary text-sm" :disabled="!!busy" @click="doPreview">
            {{ busy === 'preview' ? $t('codegen.校验中_drtjl0') : $t('codegen.校验预览_ds6rnz') }}
          </button>
          <button class="btn-ghost text-sm" :disabled="!!busy" @click="doGenerate">
            {{ busy === 'generate' ? $t('codegen.生成中_f6jfoq') : $t('codegen.下载源码_13l433') }}
          </button>
          <button
            class="btn-ghost text-sm text-red-600"
            :disabled="!!busy || !canWrite"
            @click="openConfirm"
          >
            {{ busy === 'install' ? $t('codegen.安装中_c41791') : $t('codegen.安装到本_1qfxu3') }}
          </button>
          <span v-if="!canWrite" class="text-xs text-ink-400">{{ $t('codegen.text_14xgl0') }}</span>
        </div>
        <div v-if="mode === 'visual' && localIssues.length" class="text-xs text-amber-600 mt-3">
          {{ $t('codegen.待修正_cdyz1c') }}{{ localIssues.join('；') }}
        </div>
        <p v-if="meta" class="text-xs text-ink-400 mt-3">
          {{ $t('codegen.字段类型_g33mb0') }}{{ fieldTypes.join(' / ') }}
        </p>
        <p v-if="meta" class="text-xs text-ink-400 mt-1">
          {{ $t('codegen.迁移挂载_nhqbbp') }}
          <code class="bg-ink-50 px-1 rounded">{{ meta?.migration_head || '—' }}</code>
          <span v-if="meta?.migration_head_error" class="text-red-500">（{{ meta.migration_head_error }}）</span>
        </p>
        <p v-if="meta?.installed_keys?.length" class="text-xs text-ink-400 mt-1">
          {{ $t('codegen.已安装_1674rj') }}{{ meta.installed_keys.join('、') }}
        </p>
      </div>

      <!-- ===================== 预览 ===================== -->
      <div class="card">
        <div class="flex items-center justify-between mb-3">
          <h2 class="font-semibold">{{ $t('codegen.生成预览_f6wnrp') }}</h2>
          <span v-if="preview" class="text-xs text-ink-400">{{ $t('codegen.已通过自_yet6h4') }}</span>
        </div>
        <div v-if="!preview" class="text-ink-500 text-sm">
          {{ $t('codegen.点_1tweqt') }}
        </div>
        <template v-else>
          <div class="text-sm mb-3 space-y-0.5">
            <div>
              <span class="text-ink-500">{{ $t('codegen.应用_eg1ae') }}</span>
              {{ preview.spec.key }} · {{ preview.spec.name }} · v{{ preview.spec.version }}
              <span v-if="alreadyInstalled" class="text-amber-600 text-xs">
                {{ $t('codegen.text_1xtvf8') }}
              </span>
            </div>
            <div>
              <span class="text-ink-500">{{ $t('codegen.实体_dtzjn') }}{{ preview.spec.entities.length }}）：</span>
              {{ entityTitles }}
            </div>
            <div>
              <span class="text-ink-500">{{ $t('codegen.文件_fa6jv') }}</span>
              {{ preview.files.length }} {{ $t('codegen.个_bg6kh') }} {{ fmtSize(preview.total_size) }}
            </div>
          </div>

          <div class="mb-3">
            <div class="text-xs text-ink-500 mb-1">{{ $t('codegen.菜单路径_gzm3vy') }}</div>
            <code
              v-for="p in preview.menu_paths"
              :key="p"
              class="text-xs bg-ink-50 px-1 rounded mr-1"
            >{{ p }}</code>
          </div>

          <div class="mb-3">
            <div class="text-xs text-ink-500 mb-1">{{ $t('codegen.自动注册_13xj7g') }}</div>
            <div class="flex flex-wrap gap-1">
              <code
                v-for="p in preview.permissions"
                :key="p"
                class="text-xs px-1.5 py-0.5 bg-purple-50 text-purple-600 rounded"
              >{{ p }}</code>
            </div>
          </div>

          <div>
            <div class="text-xs text-ink-500 mb-1">{{ $t('codegen.文件清单_d53f5r') }}</div>
            <div class="max-h-64 overflow-y-auto text-xs font-mono">
              <div
                v-for="f in (preview.files || [])"
                :key="f.path"
                class="flex justify-between border-b border-ink-100 py-0.5"
              >
                <span class="truncate">{{ f.path }}</span>
                <span class="text-ink-400 ml-2 shrink-0">{{ fmtSize(f.size) }}</span>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- ===================== 执行历史 ===================== -->
      <div class="card mt-6">
        <div class="flex items-center justify-between mb-3">
          <h2 class="font-semibold">{{ $t('codegen.执行历史_cz6fg1') }}</h2>
          <div class="flex items-center gap-2">
            <select v-model="runsAction" class="input text-xs" @change="loadRuns">
              <option value="">{{ $t('codegen.全部动作_av9flg') }}</option>
              <option value="generate">{{ $t('codegen.下载源码_13l433') }}</option>
              <option value="install">{{ $t('codegen.安装到本_1qfxu3') }}</option>
            </select>
            <button class="btn-ghost text-xs" :disabled="runsLoading" @click="loadRuns">
              {{ runsLoading ? $t('codegen.刷新中_askp0y') : $t('codegen.刷新_ejix') }}
            </button>
          </div>
        </div>
        <div v-if="runsError" class="text-red-600 text-sm break-all">{{ runsError }}</div>
        <div v-else-if="runsLoading && !runs.length" class="text-ink-500 text-sm">{{ $t('codegen.加载中_b0k5km') }}</div>
        <div v-else-if="!runs.length" class="text-ink-500 text-sm">
          {{ $t('codegen.还没有执_17yo36') }}
        </div>
        <div v-else class="overflow-x-auto">
          <table class="w-full text-xs">
            <thead>
              <tr class="text-ink-500 text-left">
                <th class="font-normal py-1 pr-2">{{ $t('codegen.时间_i5z2') }}</th>
                <th class="font-normal py-1 pr-2">{{ $t('codegen.动作_ehtg') }}</th>
                <th class="font-normal py-1 pr-2">{{ $t('codegen.应用_gqac') }}</th>
                <th class="font-normal py-1 pr-2">{{ $t('codegen.状态_k1e3') }}</th>
                <th class="font-normal py-1 pr-2">{{ $t('codegen.摘要_1ig6j3') }}</th>
                <th class="font-normal py-1 pr-2">{{ $t('codegen.耗时_mchr') }}</th>
                <th class="font-normal py-1"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in runs" :key="r.id" class="border-t border-ink-100">
                <td class="py-1.5 pr-2 whitespace-nowrap">{{ fmtTime(r.created_at) }}</td>
                <td class="py-1.5 pr-2">{{ r.action === 'install' ? $t('codegen.安装_gbj0') : $t('codegen.生成_kgk1') }}</td>
                <td class="py-1.5 pr-2">
                  <span class="font-mono">{{ r.app_key }}</span>
                  <span v-if="r.app_name" class="text-ink-400 ml-1">{{ r.app_name }}</span>
                </td>
                <td class="py-1.5 pr-2">
                  <span v-if="r.status === 'ok'" class="text-green-600">{{ $t('codegen.成功_h4sv') }}</span>
                  <span v-else class="text-red-600">{{ $t('codegen.失败_fy1g') }}</span>
                </td>
                <td
                  class="py-1.5 pr-2 max-w-[24rem] truncate"
                  :class="r.status === 'ok' ? '' : 'text-red-600'"
                >{{ r.summary || (r.status === 'ok' ? '' : $t('codegen.见详情_kup7k')) }}</td>
                <td class="py-1.5 pr-2 whitespace-nowrap">
                  {{ r.duration_ms === null ? '—' : r.duration_ms + ' ms' }}
                </td>
                <td class="py-1.5 whitespace-nowrap">
                  <button class="btn-ghost text-xs" @click="openRunDetail(r)">{{ $t('codegen.详情_obrz') }}</button>
                  <button
                    class="btn-ghost text-xs"
                    :disabled="runsBusy || !canWrite"
                    @click="openRerun(r)"
                  >{{ $t('codegen.再次执行_aqgum1') }}</button>
                  <button
                    class="btn-ghost text-xs text-red-600"
                    :disabled="runsBusy || !canWrite"
                    @click="doDeleteRun(r)"
                  >{{ $t('codegen.删除_eslg') }}</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- 从已有表导入 -->
    <div
      v-if="tablesOpen"
      class="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
      @click.self="tablesOpen = false"
    >
      <div class="bg-white rounded-lg shadow-xl w-full max-w-2xl p-6">
        <h2 class="text-lg font-semibold mb-2">{{ $t('codegen.从已有表_1ng9k7') }}</h2>
        <p class="text-xs text-ink-500 mb-3">
          {{ $t('codegen.只读_hhrtpk') }}
        </p>
        <div class="flex gap-2 mb-3">
          <input
            v-model.trim="tableQ"
            class="input flex-1"
            :placeholder="$t('codegen.按表名筛_1stqba')"
            @keyup.enter="loadTables"
          />
          <button class="btn-ghost" :disabled="tablesLoading" @click="loadTables">{{ $t('codegen.搜索_hpqe') }}</button>
        </div>
        <div v-if="tablesLoading" class="text-ink-500 text-sm py-3">{{ $t('codegen.加载中_b0k5km') }}</div>
        <div v-else-if="tablesError" class="text-red-600 text-sm break-all">{{ tablesError }}</div>
        <div v-else class="max-h-80 overflow-y-auto">
          <div
            v-for="t in tables"
            :key="t.name"
            class="flex items-start justify-between border-b border-ink-100 py-2 gap-2"
          >
            <div class="min-w-0">
              <code class="text-sm">{{ t.name }}</code>
              <span class="text-xs text-ink-400 ml-2">{{ t.columns.length }} {{ $t('codegen.列_g7r') }}</span>
              <div class="text-xs text-ink-400 truncate">
                {{ t.columns.map((c) => c.name + ':' + c.suggested_type).join(' · ') }}
              </div>
            </div>
            <button class="btn-ghost text-xs shrink-0" @click="importTable(t)">{{ $t('codegen.导入为实_f3kejq') }}</button>
          </div>
          <div v-if="!tables.length" class="text-ink-500 text-sm py-3">{{ $t('codegen.没有匹配_4oz8pu') }}</div>
        </div>
        <div class="flex justify-end mt-4">
          <button class="btn-ghost" @click="tablesOpen = false">{{ $t('codegen.关闭_eod6') }}</button>
        </div>
      </div>
    </div>

    <!-- 安装强确认 -->
    <div
      v-if="confirmOpen"
      class="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
      @click.self="confirmOpen = false"
    >
      <div class="bg-white rounded-lg shadow-xl w-full max-w-lg p-6">
        <h2 class="text-lg font-semibold mb-3 text-red-600">{{ $t('codegen.确认安装_1we8c9') }}</h2>
        <div class="text-sm text-ink-700 space-y-3 mb-4">
          <p>
            {{ $t('codegen.即将安装_1979ps') }}
            <code class="bg-ink-50 px-1 rounded">{{ preview?.spec?.key }}</code>{{ $t('codegen.text_wrjwi5') }}
          </p>
          <ul class="list-disc pl-5 space-y-1">
            <li>{{ $t('codegen.在数据库_bf32gd') }}<b>{{ $t('codegen.新建数据_1iuhj1') }}</b>{{ $t('codegen.并执行迁_r65emt') }} <code class="bg-ink-50 px-1 rounded">alembic upgrade</code></li>
            <li>
              {{ $t('codegen.注册菜单_1x1ow9') }}
              <code class="bg-ink-50 px-1 rounded">static/apps/&lt;key&gt;/</code>
            </li>
            <li>
              {{ $t('codegen.动态注册_1m5034') }} <code class="bg-ink-50 px-1 rounded">/api/v1/&lt;key&gt;</code>{{ $t('codegen.text_10hgpi') }}
            </li>
          </ul>
          <p class="text-amber-600">{{ $t('codegen.卸载请到_czgses') }}</p>
          <p>
            {{ $t('codegen.请输入应_e8vda4') }} <b>{{ preview?.spec?.key }}</b> {{ $t('codegen.以确认_agkgdb') }}
          </p>
          <input v-model="confirmText" class="input w-full" :placeholder="preview?.spec?.key" />
        </div>
        <div class="flex justify-end gap-2">
          <button class="btn-ghost" @click="confirmOpen = false">{{ $t('codegen.取消_ev02') }}</button>
          <button
            class="btn-primary"
            :disabled="confirmText !== preview?.spec?.key || busy === 'install'"
            @click="doInstall"
          >
            {{ busy === 'install' ? $t('codegen.安装中_c41791') : $t('codegen.确认安装_frqcpe') }}
          </button>
        </div>
      </div>
    </div>

    <!-- 执行详情 -->
    <div
      v-if="runDetailOpen"
      class="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
      @click.self="runDetailOpen = false"
    >
      <div class="bg-white rounded-lg shadow-xl w-full max-w-2xl p-6 max-h-[85vh] overflow-y-auto">
        <h2 class="text-lg font-semibold mb-3">{{ $t('codegen.执行详情_czg36s') }}</h2>
        <div v-if="!runDetail" class="text-ink-500 text-sm">{{ $t('codegen.加载中_b0k5km') }}</div>
        <template v-else>
          <div class="text-sm space-y-1 mb-3">
            <div>
              <span class="text-ink-500">{{ $t('codegen.记录_ky6mt') }}</span>
              #{{ runDetail.id }} · {{ runDetail.action === 'install' ? $t('codegen.安装到本_1qfxu3') : $t('codegen.下载源码_13l433') }} ·
              <span :class="runDetail.status === 'ok' ? 'text-green-600' : 'text-red-600'">
                {{ runDetail.status === 'ok' ? $t('codegen.成功_h4sv') : $t('codegen.失败_fy1g') }}
              </span>
            </div>
            <div>
              <span class="text-ink-500">{{ $t('codegen.应用_eg1ae') }}</span>
              <span class="font-mono">{{ runDetail.app_key }}</span>
              <span v-if="runDetail.app_name"> · {{ runDetail.app_name }}</span>
            </div>
            <div>
              <span class="text-ink-500">{{ $t('codegen.时间_fojks') }}</span>{{ fmtTime(runDetail.created_at) }}
              <span v-if="runDetail.duration_ms !== null"> · {{ runDetail.duration_ms }} ms</span>
            </div>
            <div v-if="runDetail.summary">
              <span class="text-ink-500">{{ $t('codegen.结果_j3rip') }}</span>{{ runDetail.summary }}
            </div>
          </div>

          <div v-if="runDetail.error" class="mb-3">
            <div class="text-xs text-ink-500 mb-1">{{ $t('codegen.后端原始_1ssfrl') }}</div>
            <pre
              class="text-xs bg-red-50 text-red-700 p-3 rounded whitespace-pre-wrap break-all max-h-48 overflow-y-auto"
            >{{ runDetail.error }}</pre>
          </div>

          <div class="mb-3">
            <div class="text-xs text-ink-500 mb-1">{{ $t('codegen.text_gsezq9') }}</div>
            <pre
              class="text-xs bg-ink-50 p-3 rounded whitespace-pre-wrap break-all max-h-64 overflow-y-auto"
            >{{ JSON.stringify(runDetail.spec, null, 2) }}</pre>
          </div>

          <div class="flex justify-end gap-2">
            <button class="btn-ghost" :disabled="!runDetail.spec" @click="loadSpecFromRun(runDetail)">
              {{ $t('codegen.回填到表_1v12kk') }}
            </button>
            <button
              class="btn-ghost text-red-600"
              :disabled="runsBusy || !canWrite"
              @click="openRerun(runDetail)"
            >{{ $t('codegen.再次执行_aqgum1') }}</button>
            <button class="btn-ghost" @click="runDetailOpen = false">{{ $t('codegen.关闭_eod6') }}</button>
          </div>
        </template>
      </div>
    </div>

    <!-- 再次执行安装的强确认 -->
    <div
      v-if="rerunOpen"
      class="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
      @click.self="rerunOpen = false"
    >
      <div class="bg-white rounded-lg shadow-xl w-full max-w-lg p-6">
        <h2 class="text-lg font-semibold mb-3 text-red-600">{{ $t('codegen.确认再次_n181aj') }}</h2>
        <div class="text-sm text-ink-700 space-y-2 mb-4">
          <p>
            {{ $t('codegen.将按历史_197jf2') }} <b>#{{ rerunRun?.id }}</b> {{ $t('codegen.的_p7r81k') }}
            <code class="bg-ink-50 px-1 rounded">{{ rerunRun?.app_key }}</code>：
          </p>
          <ul class="list-disc pl-5 space-y-1">
            <li>
              {{ $t('codegen.再次执行_aqgum1') }} <code class="bg-ink-50 px-1 rounded">alembic upgrade</code>
              {{ $t('codegen.text_htp6ou') }}
            </li>
            <li>{{ $t('codegen.覆盖同名_1ud46p') }}</li>
          </ul>
        </div>
        <div class="flex justify-end gap-2">
          <button class="btn-ghost" @click="rerunOpen = false">{{ $t('codegen.取消_ev02') }}</button>
          <button class="btn-primary" :disabled="runsBusy" @click="doRerun(rerunRun)">
            {{ runsBusy ? $t('codegen.执行中_cz58gu') : $t('codegen.确认执行_frrinv') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
