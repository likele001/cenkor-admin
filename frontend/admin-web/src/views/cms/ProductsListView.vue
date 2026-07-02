<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/lib/api'
import { fromProductListItem } from '@/lib/transform'
import SearchInput from '@/components/SearchInput.vue'
import CsvExportButton from '@/components/CsvExportButton.vue'
import BatchActionBar from '@/components/BatchActionBar.vue'
import Skeleton from '@/components/Skeleton.vue'
import EmptyState from '@/components/EmptyState.vue'
import ConfirmModal, { confirm as confirmModal } from '@/components/ConfirmModal.vue'
import StatusFilterTabs from '@/components/StatusFilterTabs.vue'

interface Product {
  id: number
  key: string
  name: string
  chineseName: string | null
  tagline: string
  line: string
  desc: string
  isFlagship: boolean
  status: string
  sort: number
}

const { t } = useI18n()
const products = ref<Product[]>([])
const loading = ref(true)
const error = ref('')
const search = ref('')
const statusFilter = ref<'all' | 'published' | 'draft' | 'archived'>('all')
const includeDeleted = ref(false)
const selectedIds = ref<Set<number>>(new Set())
const confirmDel = ref(false)
const confirmBatch = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/api/v1/cms/products', {
      params: {
        page_size: 100,
        search: search.value || undefined,
        status: statusFilter.value === 'all' ? undefined : statusFilter.value,
        include_deleted: includeDeleted.value ? 'true' : undefined,
      },
    })
    products.value = (data.items as Record<string, unknown>[]).map(fromProductListItem)
    selectedIds.value = new Set()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('products.loadFailed', '加载失败（后端未启动？）')
  } finally {
    loading.value = false
  }
}

async function del(p: Product) {
  const ok = await confirmModal({
    title: t('products.deleteTitle', '删除产品'),
    message: t('products.deleteMessage', { name: p.name }),
    confirmText: t('app.delete'),
  })
  if (!ok) return
  try {
    await api.delete(`/api/v1/cms/products/${p.id}`)
    await load()
  } catch (e: any) {
    alert(t('products.deleteFailed', '删除失败') + '：' + (e?.response?.data?.detail || e.message))
  }
}

async function batchDelete() {
  confirmBatch.value = false
  if (selectedIds.value.size === 0) return
  try {
    await api.post('/api/v1/cms/products/batch-delete', { ids: Array.from(selectedIds.value) })
    await load()
  } catch (e: any) {
    alert(t('products.batchDeleteFailed', '批量删除失败') + '：' + (e?.response?.data?.detail || e.message))
  }
}

async function batchSetStatus(s: 'published' | 'draft' | 'archived') {
  if (selectedIds.value.size === 0) return
  try {
    await api.post('/api/v1/cms/products/batch-status', { ids: Array.from(selectedIds.value), status: s })
    await load()
  } catch (e: any) {
    alert(t('products.batchStatusFailed', '批量更新状态失败') + '：' + (e?.response?.data?.detail || e.message))
  }
}

function toggleAll(checked: boolean) {
  if (checked) {
    selectedIds.value = new Set(products.value.map((p) => p.id))
  } else {
    selectedIds.value = new Set()
  }
}

const allSelected = computed(() =>
  products.value.length > 0 && selectedIds.value.size === products.value.length,
)

watch([search, statusFilter, includeDeleted], () => { load() }, { deep: true })
onMounted(load)
</script>

<template>
  <div>
    <Skeleton v-if="loading && products.length === 0" :rows="6" />

    <div v-else-if="error" class="card">
      <div class="text-red-600 font-medium">⚠️ {{ error }}</div>
      <p class="mt-2 text-sm text-ink-500" v-html="t('products.errorHint', '请确认：<br>1. <code>docker compose up -d</code> 已运行<br>2. <code>alembic upgrade head</code> 已执行<br>3. <code>python -m cenkor_admin.scripts.seed</code> 已执行')"></p>
    </div>

    <div v-else>
      <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 class="text-2xl font-semibold tracking-tight">{{ t('products.title') }}（{{ products.length }}）</h1>
        <div class="flex items-center gap-3">
          <SearchInput v-model="search" :placeholder="t('products.searchPlaceholder', '按名称/中文名/标签搜索…')" />
          <CsvExportButton endpoint="/api/v1/cms/products/export" filename="products.csv" :params="{ search: search || undefined, status: statusFilter === 'all' ? undefined : statusFilter }" />
          <router-link to="/cms/products/new" class="btn-primary">+ {{ t('products.new', '新建产品') }}</router-link>
        </div>
      </div>

      <StatusFilterTabs
        v-model="statusFilter"
        :include-deleted="includeDeleted"
        @update:include-deleted="(v: boolean) => includeDeleted = v"
      />

      <BatchActionBar
        :selected-count="selectedIds.size"
        :total-count="products.length"
        :actions="[
          { label: t('products.batchPublish', '批量发布'), onAction: () => batchSetStatus('published') },
          { label: t('products.batchArchive', '批量下线'), onAction: () => batchSetStatus('archived') },
          { label: t('products.batchDelete', '批量删除'), danger: true, onAction: () => { confirmBatch = true } },
        ]"
        @select-all="toggleAll"
        @clear="selectedIds = new Set()"
      />

      <div class="card overflow-hidden p-0">
        <table class="w-full text-sm">
          <thead class="bg-ink-50 border-b border-ink-200">
            <tr class="text-left text-ink-500">
              <th class="px-4 py-3 w-10">
                <input
                  type="checkbox"
                  :checked="allSelected"
                  class="rounded"
                  @change="toggleAll(($event.target as HTMLInputElement).checked)"
                />
              </th>
              <th class="px-4 py-3 font-medium">{{ t('common.name', '名称') }}</th>
              <th class="px-4 py-3 font-medium">{{ t('products.line', '业务线') }}</th>
              <th class="px-4 py-3 font-medium">{{ t('products.tagline', '标签') }}</th>
              <th class="px-4 py-3 font-medium">{{ t('common.status') }}</th>
              <th class="px-4 py-3 font-medium">{{ t('products.flagship', '旗舰') }}</th>
              <th class="px-4 py-3 font-medium text-right">{{ t('common.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="products.length === 0">
              <td colspan="7" class="p-0">
                <EmptyState
                  :title="includeDeleted ? t('products.recycleEmpty', '回收站为空') : t('products.noProducts', '还没有产品')"
                  :description="includeDeleted ? t('products.recycleHint', '已删除的产品会显示在这里。') : t('products.noProductsHint', '创建第一个产品，开始填充你的产品矩阵。')"
                  :action-label="includeDeleted ? undefined : t('products.new', '新建产品')"
                  @action="$router.push('/cms/products/new')"
                />
              </td>
            </tr>
            <tr v-for="p in products" :key="p.id" class="border-b border-ink-100 last:border-0 hover:bg-ink-50">
              <td class="px-4 py-3">
                <input
                  type="checkbox"
                  :checked="selectedIds.has(p.id)"
                  class="rounded"
                  @change="(e) => {
                    const checked = (e.target as HTMLInputElement).checked
                    const next = new Set(selectedIds)
                    if (checked) next.add(p.id)
                    else next.delete(p.id)
                    selectedIds = next
                  }"
                />
              </td>
              <td class="px-4 py-3 font-medium">
                {{ p.name }}
                <span v-if="p.chineseName" class="text-ink-400 ml-1">{{ p.chineseName }}</span>
              </td>
              <td class="px-4 py-3 text-ink-600">{{ p.line }}</td>
              <td class="px-4 py-3 text-ink-600">{{ p.tagline }}</td>
              <td class="px-4 py-3">
                <span class="text-xs px-2 py-0.5 rounded-full"
                  :class="p.status === 'published' ? 'bg-emerald-100 text-emerald-700' : 'bg-ink-100 text-ink-600'">
                  {{ { draft: t('products.draft'), published: t('products.published'), archived: t('products.archived') }[p.status] || p.status }}
                </span>
              </td>
              <td class="px-4 py-3">
                <span v-if="p.isFlagship" class="text-xs px-2 py-0.5 rounded bg-ink-900 text-white">{{ t('products.flagship') }}</span>
              </td>
              <td class="px-4 py-3 text-right space-x-2">
                <router-link :to="`/cms/products/${p.id}`" class="text-sm text-ink-600 hover:text-ink-900">{{ t('app.edit') }}</router-link>
                <button @click="del(p)" class="text-sm text-red-600 hover:underline">{{ t('app.delete') }}</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <ConfirmModal
      :open="confirmBatch"
      :title="t('products.batchDeleteTitle', '批量删除产品')"
      :message="t('products.batchDeleteMessage', { count: selectedIds.size })"
      :confirm-text="t('products.batchDelete', '批量删除')"
      @confirm="batchDelete"
      @cancel="confirmBatch = false"
    />
  </div>
</template>