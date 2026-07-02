<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, onMounted, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { api } from '@/lib/api'

interface Entry {
  id: number; content_type_id: number; slug: string | null
  title: string; content: Record<string, any>; custom_fields: Record<string, any>
  category_id: number | null; status: string; author_id: number | null
  published_at: string | null; sort: number; view_count: number
  created_at: string; updated_at: string
}
interface ContentType { id: number; key: string; name: string; icon: string | null; supports_category: boolean; supports_tags: boolean }
interface Category { id: number; name: string; slug: string; parent_id: number | null }
interface Tag { id: number; name: string; slug: string; color: string | null }

const router = useRouter()
const route = useRoute()
const contentTypes = ref<ContentType[]>([])
const selectedCtKey = ref('')
const categories = ref<Category[]>([])
const tags = ref<Tag[]>([])
const entries = ref<Entry[]>([])
const total = ref(0)
const loading = ref(true)
const search = ref('')
const statusFilter = ref('')
const categoryFilter = ref<number | null>(null)
const page = ref(1)
const pageSize = 20
const selected = ref<number[]>([])

const selectedCt = computed(() => contentTypes.value.find(c => c.key === selectedCtKey.value))

async function loadContentTypes() {
  const { data } = await api.get('/api/v1/cms/content-types')
  contentTypes.value = data.items
  if (data.items.length && !selectedCtKey.value) selectedCtKey.value = data.items[0].key
}

async function loadCategories() {
  if (!selectedCtKey.value || !selectedCt.value?.supports_category) {
    categories.value = []
    return
  }
  const { data } = await api.get(`/api/v1/cms/categories?content_type_key=${selectedCtKey.value}`)
  categories.value = data.items || []
}

async function loadTags() {
  if (!selectedCtKey.value || !selectedCt.value?.supports_tags) {
    tags.value = []
    return
  }
  const { data } = await api.get(`/api/v1/cms/tags?content_type_key=${selectedCtKey.value}`)
  tags.value = data.items || []
}

async function loadEntries() {
  if (!selectedCtKey.value) return
  loading.value = true
  try {
    const params = new URLSearchParams({
      content_type_key: selectedCtKey.value,
      page: String(page.value),
      page_size: String(pageSize),
    })
    if (search.value) params.set('search', search.value)
    if (statusFilter.value) params.set('status', statusFilter.value)
    if (categoryFilter.value) params.set('category_id', String(categoryFilter.value))
    const { data } = await api.get(`/api/v1/cms/entries?${params}`)
    entries.value = data.items || []
    total.value = data.total || 0
    selected.value = []
  } finally { loading.value = false }
}

async function onCtChange() {
  page.value = 1
  await loadCategories()
  await loadTags()
  await loadEntries()
}

function onSearch() {
  page.value = 1
  loadEntries()
}

function onStatusChange() {
  page.value = 1
  loadEntries()
}

function onPageChange(p: number) {
  page.value = p
  loadEntries()
}

function newEntry() {
  router.push({ name: 'cms-entry-new', query: { ct: selectedCtKey.value } })
}

function editEntry(e: Entry) {
  router.push({ name: 'cms-entry-edit', params: { id: e.id }, query: { ct: selectedCtKey.value } })
}

async function batchAction(action: 'delete' | 'publish' | 'draft' | 'archive') {
  if (!selected.value.length) return
  const statusMap: Record<string, string> = { publish: 'published', draft: 'draft', archive: 'archived' }
  try {
    if (action === 'delete') {
      await api.post('/api/v1/cms/entries/batch-delete', { ids: selected.value })
    } else {
      await api.post('/api/v1/cms/entries/batch-status', { ids: selected.value, status: statusMap[action] })
    }
    await loadEntries()
  } catch (e: any) {
    alert(e?.response?.data?.detail || 't("entryList.操作失败")')
  }
}

function toggleSelect(id: number) {
  const idx = selected.value.indexOf(id)
  if (idx >= 0) selected.value.splice(idx, 1)
  else selected.value.push(id)
}

function toggleSelectAll() {
  if (selected.value.length === entries.value.length) selected.value = []
  else selected.value = entries.value.map(e => e.id)
}

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

onMounted(async () => {
  // 从 URL 参数读取 content_type_key
  if (route.query.ct) {
    selectedCtKey.value = route.query.ct as string
  }
  await loadContentTypes()
  await loadCategories()
  await loadTags()
  await loadEntries()
})
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">{{ t('entryList.通用内容_invaua') }}</h1>
        <p class="text-ink-500">{{ t('entryList.管理各内_1vsukx') }}</p>
      </div>
      <div class="flex gap-2">
        <select v-model="selectedCtKey" class="input w-40" @change="onCtChange">
          <option v-for="ct in contentTypes" :key="ct.key" :value="ct.key">{{ ct.icon }} {{ ct.name }}</option>
        </select>
        <button class="btn-primary" @click="newEntry">{{ t('entryList.text_y2oa4s') }}</button>
      </div>
    </div>

    <!-- Filters -->
    <div class="card mb-4 flex flex-wrap gap-3 items-center">
      <input v-model="search" type="text" class="input w-60" :placeholder="t('entryList.按标题搜_1z0o89')" @keyup.enter="onSearch" />
      <select v-if="selectedCt?.supports_category" v-model.number="categoryFilter" class="input w-40" @change="onStatusChange">
        <option :value="null">{{ t('entryList.全部分类_av9kmt') }}</option>
        <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
      </select>
      <select v-model="statusFilter" class="input w-32" @change="onStatusChange">
        <option value="">{{ t('portalUsersList.全部状态_avez63') }}</option>
        <option value="draft">{{ t('productEdit.草稿_n02e') }}</option>
        <option value="published">{{ t('productEdit.已发布_e656s') }}</option>
        <option value="archived">{{ t('productEdit.已归档_e85oj') }}</option>
      </select>
      <button class="btn-ghost" @click="onSearch">{{ t('portalUsersList.搜索_hpqe') }}</button>
      <span class="text-ink-400 text-sm ml-auto">共 {{ total }} 条</span>
    </div>

    <!-- Batch actions -->
    <div v-if="selected.length" class="mb-2 p-2 bg-blue-50 rounded flex items-center gap-2 text-sm">
      已选 {{ selected.length }} 条
      <button class="btn-ghost text-xs" @click="batchAction('publish')">{{ t('entryList.发布_erte') }}</button>
      <button class="btn-ghost text-xs" @click="batchAction('draft')">{{ t('entryList.转草稿_ln9fm') }}</button>
      <button class="btn-ghost text-xs" @click="batchAction('archive')">{{ t('entryList.归档_gsb5') }}</button>
      <button class="btn-ghost text-xs text-red-600" @click="batchAction('delete')">{{ t('usersList.删除_eslg') }}</button>
      <button class="btn-ghost text-xs ml-auto" @click="selected = []">{{ t('entryList.取消选择_b1em0i') }}</button>
    </div>

    <!-- Table -->
    <div v-if="loading" class="card text-ink-500">{{ t('usersList.加载中_b0k5km') }}</div>
    <div v-else-if="entries.length === 0" class="card text-center text-ink-400 py-12">
      {{ t('entryList.暂无内容点击新建条目创建第一个') }}
    </div>
    <table v-else class="w-full text-sm">
      <thead class="text-left text-ink-500 border-b">
        <tr>
          <th class="py-2 px-2 w-8">
            <input type="checkbox" :checked="selected.length === entries.length" @change="toggleSelectAll" />
          </th>
          <th class="py-2 px-2">{{ t('newsList.标题_ij5d') }}</th>
          <th class="py-2 px-2">{{ t('entryList.分类_emut') }}</th>
          <th class="py-2 px-2">{{ t('usersList.状态_k1e3') }}</th>
          <th class="py-2 px-2">{{ t('entryList.浏览_jck9') }}</th>
          <th class="py-2 px-2">{{ t('entryList.更新时间_devbay') }}</th>
          <th class="py-2 px-2 w-20">{{ t('usersList.操作_hkxb') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="e in entries" :key="e.id" class="border-b hover:bg-ink-50">
          <td class="py-2 px-2">
            <input type="checkbox" :checked="selected.includes(e.id)" @change="toggleSelect(e.id)" />
          </td>
          <td class="py-2 px-2">
            <a href="#" class="text-blue-600 hover:underline" @click.prevent="editEntry(e)">{{ e.title }}</a>
            <code v-if="e.slug" class="text-xs text-ink-400 ml-2">{{ e.slug }}</code>
          </td>
          <td class="py-2 px-2 text-ink-500">
            {{ e.category_id ? categories.find(c => c.id === e.category_id)?.name : '—' }}
          </td>
          <td class="py-2 px-2">
            <span
              class="text-xs px-1.5 py-0.5 rounded"
              :class="{
                'bg-green-50 text-green-700': e.status === 'published',
                'bg-yellow-50 text-yellow-700': e.status === 'draft',
                'bg-ink-100 text-ink-500': e.status === 'archived',
              }"
            >{{ { draft: '草稿', published: '已发布', archived: '已归档' }[e.status] }}</span>
          </td>
          <td class="py-2 px-2 text-ink-500">{{ e.view_count }}</td>
          <td class="py-2 px-2 text-ink-500 text-xs">{{ e.updated_at?.slice(0, 16) }}</td>
          <td class="py-2 px-2">
            <button class="text-blue-600 text-xs" @click="editEntry(e)">{{ t('usersList.编辑_mekb') }}</button>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- Pagination -->
    <div v-if="totalPages > 1" class="mt-4 flex items-center gap-2 text-sm">
      <button class="btn-ghost" :disabled="page <= 1" @click="onPageChange(page - 1)">{{ t('portalUsersList.上一页_btlof') }}</button>
      <span>{{ page }} / {{ totalPages }}</span>
      <button class="btn-ghost" :disabled="page >= totalPages" @click="onPageChange(page + 1)">下一页</button>
    </div>
  </div>
</template>
