<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import RichTextEditor from '@/components/RichTextEditor.vue'
const { t } = useI18n()
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/lib/api'
import DynamicFieldRenderer from '@/components/cms/DynamicFieldRenderer.vue'
import AiRewriteDialog from '@/components/cms/AiRewriteDialog.vue'
import EntryAiPanel from '@/components/cms/EntryAiPanel.vue'

interface FieldDef {
  id: number; field_key: string; label: string; field_type: string
  required: boolean; default_value: string | null
  options: Record<string, any> | null; validation: Record<string, any> | null
  group_id: number | null; sort: number; status: string
  field_options: { id: number; value: string; label: string; color: string | null; sort: number }[]
}
interface FieldGroup { id: number; key: string; label: string; sort: number; icon: string | null }
interface ContentType {
  id: number; key: string; name: string; icon: string | null
  supports_category: boolean; supports_tags: boolean
  translatable?: boolean
  field_groups: FieldGroup[]; field_definitions: FieldDef[]
}
interface Category { id: number; name: string; slug: string; parent_id: number | null }
interface Tag { id: number; name: string; slug: string; color: string | null }

const route = useRoute()
const router = useRouter()
const isNew = computed(() => !route.params.id)

const contentTypes = ref<ContentType[]>([])
const selectedCtKey = ref((route.query.ct as string) || '')
const ct = ref<ContentType | null>(null)
const categories = ref<Category[]>([])
const allTags = ref<Tag[]>([])
const entry = ref<any>(null)
const form = ref({
  title: (route.query.title as string) || '', slug: '', content: {} as Record<string, any>,
  custom_fields: {} as Record<string, any>,
  category_id: null as number | null, status: 'draft', sort: 0,
  tag_ids: [] as number[],
})
const activeGroup = ref<number | null>(null)
const saving = ref(false)
const error = ref('')

// ---- M1·P0 多语言 i18n ----
const languages = ref<{ code: string; name: string; flag: string | null; is_default: boolean }[]>([])
const drafts = ref<Record<string, any>>({})       // lang -> 翻译草稿 {title,slug,content,custom_fields}
const activeLang = ref<'default' | string>('default') // 'default' 表示主语言
const canI18n = computed(() => !!ct.value?.translatable && languages.value.length > 0)

// 当前激活语言的编辑对象：主语言用 form，其它语言用草稿
const activeForm = computed(() => {
  if (activeLang.value === 'default') return form.value
  if (!drafts.value[activeLang.value]) {
    drafts.value[activeLang.value] = { title: '', slug: '', content: {}, custom_fields: {} }
  }
  return drafts.value[activeLang.value]
})

// ---- M1·P0 版本控制 ----
const versions = ref<any[]>([])
const previewVersion = ref<any>(null)
const showVersionPreview = ref(false)

async function loadLanguages() {
  try {
    const { data } = await api.get('/api/v1/cms/languages')
    languages.value = data.items || []
  } catch { languages.value = [] }
}

async function loadTranslations(id: number) {
  const { data } = await api.get(`/api/v1/cms/entries/${id}/translations`)
  for (const tr of data.items || []) {
    drafts.value[tr.lang] = tr.field_values || {}
  }
}

async function loadVersions(id: number) {
  try {
    const { data } = await api.get(`/api/v1/cms/entries/${id}/versions`)
    versions.value = data.items || []
  } catch { versions.value = [] }
}

async function previewVersionFn(v: any) {
  const { data } = await api.get(`/api/v1/cms/entries/${route.params.id}/versions/${v.version}`)
  previewVersion.value = data.data || {}
  showVersionPreview.value = true
}

async function restoreVersion(v: any) {
  if (!window.confirm(`确认回滚到 v${v.version}？回滚前当前内容会自动保存为新快照。`)) return
  await api.post(`/api/v1/cms/entries/${route.params.id}/restore/${v.version}`)
  await loadEntryDetail(Number(route.params.id))
  await loadVersions(Number(route.params.id))
  error.value = ''
}

// ---- AI 内嵌（标题/正文改写 + 侧栏助手） ----
// 只改表单，保存才落库；模型不直接写内容，人要过一眼。
const rewriteTarget = ref<'title' | 'content' | null>(null)
const rewriteOpen = computed({
  get: () => rewriteTarget.value !== null,
  set: (v: boolean) => {
    if (!v) rewriteTarget.value = null
  },
})
const rewriteValue = computed(() => {
  if (rewriteTarget.value === 'title') return activeForm.value.title || ''
  if (rewriteTarget.value === 'content') return activeForm.value.content?.text || ''
  return ''
})
const rewriteTitle = computed(() =>
  rewriteTarget.value === 'content' ? 'AI 改写正文' : 'AI 改写标题',
)
// 正文纯文本：给摘要与 SEO 当输入，避免把 HTML 标签喂给模型
const bodyText = computed(() => {
  const html = activeForm.value.content?.text || ''
  if (!html) return ''
  const el = document.createElement('div')
  el.innerHTML = html
  return (el.textContent || '').replace(/\s+/g, ' ').trim()
})
// 内容类型里有「摘要」类字段就填它，没有就让用户自己贴
const summaryFieldKey = computed(() => {
  const fields = ct.value?.field_definitions || []
  const hit = fields.find(
    (f) => /^(summary|excerpt|digest|abstract|description)$/i.test(f.field_key) || /摘要|简介|导语/.test(f.label),
  )
  return hit?.field_key || null
})
const rewriteContext = computed(() => {
  const parts: string[] = []
  if (ct.value?.name) parts.push(`内容类型：${ct.value.name}`)
  if (activeForm.value.title && rewriteTarget.value === 'content') {
    parts.push(`当前标题：${activeForm.value.title}`)
  }
  // 拟标题/改标题时把正文一起给模型。只送一句标题过去的话，模型没有任何素材，
  // 很容易把原标题原样返回（「改写结果」和「修改前」一模一样）。
  if (rewriteTarget.value === 'title' && bodyText.value) {
    parts.push(`正文（拟标题的依据）：${bodyText.value.slice(0, 800)}`)
  }
  return parts.join('；')
})
const translatableLangs = computed(() =>
  languages.value.filter((l) => !l.is_default).map((l) => ({ code: l.code, name: l.name, flag: l.flag })),
)
const savedEntryId = computed(() => {
  const id = Number(route.params.id)
  return Number.isFinite(id) && id > 0 ? id : null
})

const REWRITE_PRESETS = [
  { key: 'polish', label: '润色' },
  { key: 'shorten', label: '精简' },
  { key: 'expand', label: '扩写' },
  { key: 'formal', label: '正式' },
  { key: 'plain', label: '口语' },
  { key: 'custom', label: '自定义' },
]

const TITLE_PRESETS = [
  { key: 'title', label: '拟标题' },
  { key: 'polish', label: '润色' },
  { key: 'shorten', label: '缩短' },
  { key: 'formal', label: '正式' },
  { key: 'custom', label: '自定义' },
]

function applyRewrite(v: string) {
  const target = rewriteTarget.value
  if (!target) return
  if (target === 'title') activeForm.value.title = v
  else activeForm.value.content.text = v
  rewriteTarget.value = null
}

function applySummary(v: string) {
  if (summaryFieldKey.value) {
    form.value.custom_fields[summaryFieldKey.value] = v
    return
  }
  // 没有摘要字段时退化成正文导语，仍由用户保存决定
  const cur = activeForm.value.content?.text || ''
  const esc = v.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  activeForm.value.content.text = `<p>${esc}</p>${cur}`
}

function applySlug(v: string) {
  activeForm.value.slug = v
}

/** HTML 转义：AI 产出的锚文本/标题不能直接进正文（防存储型 XSS） */
function escHtml(s: string): string {
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/**
 * 插入内链：追加到正文末尾的「相关阅读」段落。
 *
 * 为什么不插到光标处 —— 机器猜的插入点经常落在句子中间，读起来别扭，
 * 而且撤销麻烦。追加到末尾是内容运营最常见也最可控的做法，
 * 位置不满意用户自己拖一下就行。
 */
function applyLink(v: { anchorText: string; url: string; title: string }) {
  const cur = activeForm.value.content?.text || ''
  const anchor = escHtml(v.anchorText)
  const url = escHtml(v.url)
  const title = escHtml(v.title)
  const block = `<p><strong>相关阅读：</strong><a href="${url}" title="${title}" rel="noopener noreferrer" target="_blank">${anchor}</a></p>`
  // 已有「相关阅读」段落就并进去，避免每次插入都多一段
  const re = /<p><strong>相关阅读：<\/strong>(.*?)<\/p>/s
  if (re.test(cur)) {
    activeForm.value.content.text = cur.replace(
      re,
      (_m: string, inner: string) =>
        `<p><strong>相关阅读：</strong>${inner} · <a href="${url}" title="${title}" rel="noopener noreferrer" target="_blank">${anchor}</a></p>`,
    )
    return
  }
  activeForm.value.content.text = `${cur}${cur ? '\n' : ''}${block}`
}

async function onAiTranslated() {
  if (isNew.value) return
  await loadTranslations(Number(route.params.id))
}

// ---- M2·P1 发布工作流 ----
async function submitReview() {
  await api.post(`/api/v1/cms/entries/${route.params.id}/submit-review`, { comment: '提交审核' })
  await loadEntryDetail(Number(route.params.id))
}
async function reviewEntry(action: 'approve' | 'reject') {
  if (action === 'reject' && !window.confirm('驳回后内容将退回草稿，确认？')) return
  await api.post(`/api/v1/cms/entries/${route.params.id}/review`, { action, comment: action === 'approve' ? '审核通过' : '审核驳回' })
  await loadEntryDetail(Number(route.params.id))
}
// ---- M4·P3 staging 暂存预览 ----
async function previewEntry() {
  try {
    const { data } = await api.post(`/api/v1/cms/entries/${route.params.id}/preview`)
    window.open(data.url, '_blank')
  } catch (e: any) {
    alert(e?.response?.data?.detail || '生成预览失败')
  }
}

const visibleFields = computed(() => {
  if (!ct.value) return []
  if (activeGroup.value === null) return ct.value.field_definitions
  return ct.value.field_definitions.filter(f => f.group_id === activeGroup.value || f.group_id === null)
})

const groups = computed(() => {
  if (!ct.value) return []
  return [...ct.value.field_groups].sort((a, b) => a.sort - b.sort)
})

async function loadContentTypes() {
  // 列表接口已返回完整的 field_groups / field_definitions（含选项），
  // 没必要再逐个拉详情。原来那套 N+1 要发 6 个请求，跨境网络下就是十几秒白屏。
  // 这里不设默认类型——由 onMounted 决定：有条目就按条目类型，没有才取第一个。
  const { data } = await api.get('/api/v1/cms/content-types?page=1&page_size=200')
  contentTypes.value = (data.items || []).filter((c: any) => c.status !== 'archived')
}

/** 只取条目原始数据，不写表单（类型还没定之前没法补默认字段） */
async function fetchEntry(id: number): Promise<any | null> {
  try {
    const { data } = await api.get(`/api/v1/cms/entries/${id}`)
    return data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '条目加载失败'
    return null
  }
}

/** 把条目数据写进表单，用当前内容类型的字段定义补默认值 */
function applyEntry(data: any) {
  if (!data) return
  const defaults: Record<string, any> = {
    text: '', longtext: '', richtext: '', markdown: '', url: '', email: '', phone: '',
    image: '', file: '', select: '', color: '#000000', json: null,
    number: null, boolean: false, date: null, datetime: null,
    images: [], files: [], multiselect: [], repeater: [], relation: null,
  }
  const cf = { ...(data.custom_fields || {}) }
  if (ct.value) {
    for (const fd of ct.value.field_definitions) {
      if (!(fd.field_key in cf)) {
        cf[fd.field_key] = fd.default_value ?? defaults[fd.field_type] ?? ''
      }
    }
  }
  form.value = {
    title: data.title || '',
    slug: data.slug || '',
    content: data.content || {},
    custom_fields: cf,
    category_id: data.category_id,
    status: data.status || 'draft',
    sort: data.sort || 0,
    tag_ids: (data.tag_ids as number[]) || [],
  }
  entry.value = data
}

async function loadEntryDetail(id: number) {
  applyEntry(await fetchEntry(id))
}

async function loadCtAndOptions() {
  if (!selectedCtKey.value) return
  const found = contentTypes.value.find((c) => c.key === selectedCtKey.value)
  if (!found) {
    error.value = `内容类型 ${selectedCtKey.value} 不存在或已归档`
    return
  }
  ct.value = found

  // 分类与标签互不依赖，并行拉
  const [catRes, tagRes] = await Promise.all([
    api.get('/api/v1/cms/categories', { params: { content_type_key: selectedCtKey.value } }).catch(() => null),
    api.get('/api/v1/cms/tags', { params: { content_type_key: selectedCtKey.value } }).catch(() => null),
  ])
  categories.value = catRes?.data?.items || []
  allTags.value = tagRes?.data?.items || []

  // 初始化 custom_fields：确保所有字段 key 存在，方便 v-model 绑定
  const defaults: Record<string, any> = {
    text: '', longtext: '', richtext: '', markdown: '', url: '', email: '', phone: '',
    image: '', file: '', select: '', color: '#000000', json: null,
    number: null, boolean: false, date: null, datetime: null,
    images: [], files: [], multiselect: [], repeater: [], relation: null,
  }
  const cf = { ...form.value.custom_fields }
  for (const fd of ct.value.field_definitions) {
    if (!(fd.field_key in cf)) {
      cf[fd.field_key] = fd.default_value ?? defaults[fd.field_type] ?? ''
    }
  }
  form.value.custom_fields = cf

  if (groups.value.length) activeGroup.value = groups.value[0].id
}

async function save() {
  saving.value = true
  error.value = ''
  try {
    const payload: Record<string, any> = {
      title: form.value.title,
      slug: form.value.slug || null,
      content: form.value.content,
      custom_fields: form.value.custom_fields,
      category_id: form.value.category_id,
      status: form.value.status,
      sort: form.value.sort,
      tag_ids: form.value.tag_ids,
    }
    let savedId: number | null = null
    if (isNew.value) {
      const { data } = await api.post('/api/v1/cms/entries', {
        content_type_key: selectedCtKey.value,
        ...payload,
      })
      savedId = data.id
      router.replace({ name: 'cms-entry-edit', params: { id: data.id }, query: { ct: selectedCtKey.value } })
    } else {
      savedId = Number(route.params.id)
      await api.patch(`/api/v1/cms/entries/${route.params.id}`, payload)
    }

    // 多语言：保存各语言草稿（主语言以外）
    if (canI18n.value && savedId) {
      for (const lang of Object.keys(drafts.value)) {
        if (lang === 'default') continue
        const d = drafts.value[lang] || {}
        await api.put(`/api/v1/cms/entries/${savedId}/translations/${lang}`, {
          field_values: { title: d.title || '', slug: d.slug || '', content: d.content || {}, custom_fields: d.custom_fields || {} },
          status: form.value.status === 'published' ? 'published' : 'draft',
        })
      }
    }
    await router.push({ name: 'cms-entries' })
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 't("caseEdit.saveFailed")'
  } finally { saving.value = false }
}

function toggleTag(tid: number) {
  const idx = form.value.tag_ids.indexOf(tid)
  if (idx >= 0) form.value.tag_ids.splice(idx, 1)
  else form.value.tag_ids.push(tid)
}

// 启动阶段会自己设一次 selectedCtKey，别让 watch 再跑一遍（会重复拉分类/标签）
let bootstrapping = true

watch(selectedCtKey, async () => {
  if (bootstrapping) return
  // 切换内容类型时重置多语言草稿
  drafts.value = {}
  activeLang.value = 'default'
  await loadCtAndOptions()
  // 新建模式下重置表单
  if (isNew.value) {
    form.value = {
      title: '', slug: '', content: {}, custom_fields: {},
      category_id: null, status: 'draft', sort: 0, tag_ids: [],
    }
    // 重新初始化 custom_fields（loadCtAndOptions 已加载 ct）
    if (ct.value) {
      const defaults: Record<string, any> = {
        text: '', longtext: '', richtext: '', markdown: '', url: '', email: '', phone: '',
        image: '', file: '', select: '', color: '#000000', json: null,
        number: null, boolean: false, date: null, datetime: null,
        images: [], files: [], multiselect: [], repeater: [], relation: null,
      }
      const cf: Record<string, any> = {}
      for (const fd of ct.value.field_definitions) {
        cf[fd.field_key] = fd.default_value ?? defaults[fd.field_type] ?? ''
      }
      form.value.custom_fields = cf
    }
  }
})

onMounted(async () => {
  try {
    await loadLanguages()

    // 条目数据先拿到手（同时用于反查内容类型），类型定了之后才补默认字段
    const rawEntry = isNew.value ? null : await fetchEntry(Number(route.params.id))

    await loadContentTypes()

    // URL 没带 ?ct= 时（直接访问、刷新、从工作台跳来），用条目自己的类型；
    // 都没有才退回第一个类型。
    if (!selectedCtKey.value && rawEntry?.content_type_id) {
      const hit = contentTypes.value.find((c) => c.id === rawEntry.content_type_id)
      if (hit) selectedCtKey.value = hit.key
    }
    if (!selectedCtKey.value && contentTypes.value.length) {
      selectedCtKey.value = contentTypes.value[0].key
    }

    await loadCtAndOptions()
    if (rawEntry) applyEntry(rawEntry)

    if (!isNew.value) {
      await loadTranslations(Number(route.params.id))
      await loadVersions(Number(route.params.id))
    }
  } catch (e: any) {
    // 初始化任何一步挂了都要让人看见原因，而不是永远转圈
    console.error('[cms.entry_edit.init_failed]', e)
    error.value = `页面初始化失败：${e?.message || e}`
  } finally {
    bootstrapping = false
  }
})
</script>

<template>
  <div>
    <div class="flex items-center gap-2 mb-6">
      <router-link to="/cms/entries" class="text-ink-400 hover:text-ink-600 text-sm">{{ t('fieldDefinitions.text_1aztzu') }}</router-link>
      <h1 class="text-2xl font-semibold tracking-tight">
        {{ isNew ? '新建' : '编辑' }} {{ ct?.icon }} {{ ct?.name || '内容' }}
      </h1>
    </div>

    <div v-if="!ct" class="card text-ink-500">{{ t('usersList.加载中_b0k5km') }}</div>
    <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <!-- Main column: dynamic fields -->
      <div class="col-span-2 space-y-4">
        <div class="card space-y-3">
          <!-- 多语言 Tab（内容类型开启翻译且存在≥1语言时显示） -->
          <div v-if="canI18n" class="flex flex-wrap items-center gap-1 mb-1 border-b pb-2">
            <button
              class="px-3 py-1 text-sm border-b-2"
              :class="activeLang === 'default' ? 'border-blue-500 text-blue-600 font-medium' : 'border-transparent text-ink-400'"
              @click="activeLang = 'default'"
            >🌐 主语言</button>
            <button
              v-for="l in languages"
              :key="l.code"
              class="px-3 py-1 text-sm border-b-2"
              :class="activeLang === l.code ? 'border-blue-500 text-blue-600 font-medium' : 'border-transparent text-ink-400'"
              @click="activeLang = l.code"
            >{{ l.flag || '🌍' }} {{ l.name }}<span v-if="l.is_default" class="text-xs text-ink-400 ml-1">(默认)</span></button>
          </div>
          <div>
            <div class="flex items-center justify-between mb-1">
              <label class="text-sm font-medium">{{ t('newsList.标题_ij5d') }} <span class="text-red-500">*</span></label>
              <button
                type="button"
                class="text-xs text-violet-600 hover:text-violet-800 disabled:text-ink-300"
                :disabled="!activeForm.title?.trim()"
                title="用 AI 改写标题"
                @click="rewriteTarget = 'title'"
              >✨ AI</button>
            </div>
            <input v-model="activeForm.title" type="text" class="input" :placeholder="t('newsList.标题_ij5d')" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('entryEdit.text_k755t5') }}</label>
            <input v-model="activeForm.slug" type="text" class="input" placeholder="url-friendly-key" />
          </div>
          <div>
            <div class="flex items-center justify-between mb-1">
              <label class="text-sm font-medium">{{ t('entryEdit.内容_aduoyw') }}</label>
              <button
                type="button"
                class="text-xs text-violet-600 hover:text-violet-800 disabled:text-ink-300"
                :disabled="!activeForm.content?.text?.trim()"
                title="用 AI 改写正文（保留排版格式）"
                @click="rewriteTarget = 'content'"
              >✨ AI</button>
            </div>
            <RichTextEditor v-model="activeForm.content.text" :placeholder="t('entryEdit.富文本内_72xjm1')" />
          </div>
        </div>

        <!-- Dynamic field groups -->
        <div v-if="ct.field_definitions.length > 0" class="card">
          <div v-if="groups.length > 0" class="flex gap-1 border-b mb-3">
            <button
              class="px-3 py-1 text-sm border-b-2"
              :class="activeGroup === null ? 'border-blue-500 text-blue-600' : 'border-transparent text-ink-400'"
              @click="activeGroup = null"
            >{{ t('media.全部_en40') }}</button>
            <button
              v-for="g in groups"
              :key="g.id"
              class="px-3 py-1 text-sm border-b-2"
              :class="activeGroup === g.id ? 'border-blue-500 text-blue-600' : 'border-transparent text-ink-400'"
              @click="activeGroup = g.id"
            >{{ g.label }}</button>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <DynamicFieldRenderer
              v-for="fd in visibleFields"
              :key="fd.id"
              :definition="fd"
              v-model="form.custom_fields[fd.field_key]"
            />
          </div>
        </div>
      </div>

      <!-- Side column: meta -->
      <div class="space-y-4">
        <div class="card space-y-3">
          <h3 class="font-medium text-sm">{{ t('entryList.发布_erte') }}</h3>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('usersList.状态_k1e3') }}</label>
            <select v-model="form.status" class="input">
              <option value="draft">{{ t('productEdit.草稿_n02e') }}</option>
              <option value="published">{{ t('entryList.发布_erte') }}</option>
              <option value="archived">{{ t('entryList.归档_gsb5') }}</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('productEdit.排序_hge5') }}</label>
            <input v-model.number="form.sort" type="number" class="input" />
          </div>
        </div>

        <!-- AI 助手：摘要 / SEO / 翻译 / 内链建议 -->
        <EntryAiPanel
          :entry-id="savedEntryId"
          :title="activeForm.title || ''"
          :body-text="bodyText"
          :slug="activeForm.slug || ''"
          :summary-key="summaryFieldKey"
          :translatable-langs="translatableLangs"
          @apply-slug="applySlug"
          @apply-summary="applySummary"
          @apply-link="applyLink"
          @translated="onAiTranslated"
        />

        <!-- 版本历史（M1·P0） -->
        <div v-if="!isNew" class="card space-y-2">
          <h3 class="font-medium text-sm">📜 版本历史</h3>
          <div v-if="!versions.length" class="text-xs text-ink-400">暂无版本快照</div>
          <div v-for="v in versions" :key="v.version" class="flex items-center justify-between gap-2 text-xs border-b pb-1.5 last:border-0">
            <div class="min-w-0">
              <span class="font-mono font-semibold text-blue-600">v{{ v.version }}</span>
              <span class="text-ink-500 ml-1">{{ v.note || '' }}</span>
              <div class="text-ink-400">{{ new Date(v.created_at).toLocaleString() }}</div>
            </div>
            <div class="flex gap-1 shrink-0">
              <button class="btn-ghost px-2 py-0.5 text-xs" @click="previewVersionFn(v)">查看</button>
              <button class="text-red-500 hover:underline px-1" @click="restoreVersion(v)">回滚</button>
            </div>
          </div>
        </div>

        <div v-if="ct.supports_category && categories.length" class="card space-y-3">
          <h3 class="font-medium text-sm">{{ t('entryList.分类_emut') }}</h3>
          <select v-model.number="form.category_id" class="input">
            <option :value="null">{{ t('entryEdit.text_1qwl48') }}</option>
            <option v-for="c in categories" :key="c.id" :value="c.id">
              {{ c.parent_id ? '  └ ' : '' }}{{ c.name }}
            </option>
          </select>
        </div>

        <div v-if="ct.supports_tags && allTags.length" class="card space-y-3">
          <h3 class="font-medium text-sm">{{ t('productsList.标签_idef') }}</h3>
          <div class="flex flex-wrap gap-1.5">
            <label
              v-for="t in allTags"
              :key="t.id"
              class="flex items-center gap-1 px-2 py-1 rounded text-xs cursor-pointer border"
              :class="form.tag_ids.includes(t.id) ? 'bg-blue-50 border-blue-300' : 'bg-white border-ink-200'"
            >
              <input type="checkbox" :checked="form.tag_ids.includes(t.id)" @change="toggleTag(t.id)" class="w-3 h-3" />
              <span v-if="t.color" class="w-2 h-2 rounded-full" :style="{ backgroundColor: t.color }"></span>
              {{ t.name }}
            </label>
          </div>
        </div>

        <!-- 发布工作流（M2·P1）+ 暂存预览（M4·P3） -->
        <div v-if="!isNew && (form.status === 'draft' || form.status === 'approved' || form.status === 'pending_review')" class="card space-y-2">
          <h3 class="font-medium text-sm">🚦 发布工作流</h3>
          <button class="btn-ghost text-sm text-blue-600 w-full" @click="previewEntry">🖥 暂存预览（未发布）</button>
          <div v-if="form.status === 'draft' || form.status === 'approved'" class="flex gap-2">
            <button class="btn-ghost text-sm text-purple-600 w-full" @click="submitReview">提交审核</button>
          </div>
          <div v-if="form.status === 'pending_review'" class="flex gap-2">
            <button class="btn-ghost text-sm text-green-600 flex-1" @click="reviewEntry('approve')">通过并发布</button>
            <button class="btn-ghost text-sm text-red-600 flex-1" @click="reviewEntry('reject')">驳回</button>
          </div>
          <div class="text-xs text-ink-400">
            当前状态：{{ { draft: '草稿', published: '已发布', archived: '已归档', pending_review: '待审核', approved: '已通过' }[form.status] || form.status }}
          </div>
        </div>

        <div v-if="error" class="card text-red-600 text-sm">{{ error }}</div>

        <div class="card">
          <button class="btn-primary w-full" :disabled="saving" @click="save">
            {{ saving ? '保存中…' : (isNew ? '创建' : '保存') }}
          </button>
          <router-link to="/cms/entries" class="btn-ghost w-full mt-2 text-center">{{ t('usersList.取消_ev02') }}</router-link>
        </div>
      </div>
    </div>

    <!-- 版本快照预览弹层 -->
    <div v-if="showVersionPreview" class="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" @click.self="showVersionPreview = false">
      <div class="bg-white rounded-lg shadow-xl max-w-lg w-full max-h-[80vh] overflow-auto p-5">
        <div class="flex items-center justify-between mb-3">
          <h3 class="font-medium">版本快照预览</h3>
          <button @click="showVersionPreview = false" class="text-ink-400 hover:text-ink-600 text-lg leading-none">✕</button>
        </div>
        <div class="space-y-2 text-sm">
          <div><span class="text-ink-400">标题：</span><span class="font-medium">{{ previewVersion.title }}</span></div>
          <div><span class="text-ink-400">Slug：</span>{{ previewVersion.slug || '-' }}</div>
          <div>
            <span class="text-ink-400">正文：</span>
            <div class="whitespace-pre-wrap border rounded p-2 mt-1 bg-ink-50/50">{{ previewVersion.content?.text || '(无正文)' }}</div>
          </div>
        </div>
      </div>
    </div>
    <!-- AI 改写弹层：标题用纯文本模式，正文用 HTML 分块模式 -->
    <AiRewriteDialog
      v-model:open="rewriteOpen"
      :value="rewriteValue"
      :html="rewriteTarget === 'content'"
      :title="rewriteTitle"
      :context="rewriteContext"
      :presets="rewriteTarget === 'title' ? TITLE_PRESETS : REWRITE_PRESETS"
      @apply="applyRewrite"
    />
  </div>
</template>
