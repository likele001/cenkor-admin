<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import RichTextEditor from '@/components/RichTextEditor.vue'
const { t } = useI18n()
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/lib/api'
import DynamicFieldRenderer from '@/components/cms/DynamicFieldRenderer.vue'

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
  title: '', slug: '', content: {} as Record<string, any>,
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
  const { data } = await api.get('/api/v1/cms/content-types')
  // 详情数据更全
  const items: ContentType[] = []
  for (const ct of data.items) {
    const { data: detail } = await api.get(`/api/v1/cms/content-types/${ct.id}`)
    items.push(detail)
  }
  contentTypes.value = items
  if (!selectedCtKey.value && items.length) selectedCtKey.value = items[0].key
}

async function loadEntryDetail(id: number) {
  const { data } = await api.get(`/api/v1/cms/entries/${id}`)
  // 合并历史 custom_fields + 新增字段定义的默认值
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
    tag_ids: [],
  }
  entry.value = data
}

async function loadCtAndOptions() {
  if (!selectedCtKey.value) return
  const { data } = await api.get(`/api/v1/cms/content-types?page=1&page_size=200`)
  const found = data.items.find((c: any) => c.key === selectedCtKey.value)
  if (!found) return
  const { data: detail } = await api.get(`/api/v1/cms/content-types/${found.id}`)
  ct.value = detail

  // 加载分类和标签
  const { data: catData } = await api.get(`/api/v1/cms/categories?content_type_key=${selectedCtKey.value}`)
  categories.value = catData.items || []
  const { data: tagData } = await api.get(`/api/v1/cms/tags?content_type_key=${selectedCtKey.value}`)
  allTags.value = tagData.items || []

  // 初始化 custom_fields：确保所有字段 key 存在，方便 v-model 绑定
  if (ct.value) {
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
  }

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

watch(selectedCtKey, async () => {
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
  await loadLanguages()
  await loadContentTypes()
  await loadCtAndOptions()
  if (!isNew.value) {
    await loadEntryDetail(Number(route.params.id))
    await loadTranslations(Number(route.params.id))
    await loadVersions(Number(route.params.id))
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
            <label class="block text-sm font-medium mb-1">{{ t('newsList.标题_ij5d') }} <span class="text-red-500">*</span></label>
            <input v-model="activeForm.title" type="text" class="input" :placeholder="t('newsList.标题_ij5d')" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('entryEdit.text_k755t5') }}</label>
            <input v-model="activeForm.slug" type="text" class="input" placeholder="url-friendly-key" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('entryEdit.内容_aduoyw') }}</label>
            <RichTextEditor v-model="activeForm.content.text" placeholder="t('entryEdit.富文本内_72xjm1')" />
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
  </div>
</template>
