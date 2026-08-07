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
    if (isNew.value) {
      const { data } = await api.post('/api/v1/cms/entries', {
        content_type_key: selectedCtKey.value,
        ...payload,
      })
      router.replace({ name: 'cms-entry-edit', params: { id: data.id }, query: { ct: selectedCtKey.value } })
    } else {
      await api.patch(`/api/v1/cms/entries/${route.params.id}`, payload)
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
  await loadContentTypes()
  await loadCtAndOptions()
  if (!isNew.value) {
    await loadEntryDetail(Number(route.params.id))
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
    <div v-else class="grid grid-cols-3 gap-4">
      <!-- Main column: dynamic fields -->
      <div class="col-span-2 space-y-4">
        <div class="card space-y-3">
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('newsList.标题_ij5d') }} <span class="text-red-500">*</span></label>
            <input v-model="form.title" type="text" class="input" :placeholder="t('newsList.标题_ij5d')" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('entryEdit.text_k755t5') }}</label>
            <input v-model="form.slug" type="text" class="input" placeholder="url-friendly-key" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('entryEdit.内容_aduoyw') }}</label>
            <RichTextEditor v-model="form.content.text" placeholder="t('entryEdit.富文本内_72xjm1')" />
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
          <div class="grid grid-cols-2 gap-3">
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

        <div v-if="error" class="card text-red-600 text-sm">{{ error }}</div>

        <div class="card">
          <button class="btn-primary w-full" :disabled="saving" @click="save">
            {{ saving ? '保存中…' : (isNew ? '创建' : '保存') }}
          </button>
          <router-link to="/cms/entries" class="btn-ghost w-full mt-2 text-center">{{ t('usersList.取消_ev02') }}</router-link>
        </div>
      </div>
    </div>
  </div>
</template>
