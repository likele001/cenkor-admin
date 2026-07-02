<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, onMounted, watch } from 'vue'
import { api } from '@/lib/api'
import SearchInput from '@/components/SearchInput.vue'
import CsvExportButton from '@/components/CsvExportButton.vue'

interface NewsItem {
  id: number
  slug: string
  title: string
  excerpt: string
  status: string
  view_count: number
  published_at: string | null
  created_at: string
}

const news = ref<NewsItem[]>([])
const loading = ref(true)
const error = ref('')
const search = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/api/v1/cms/news', {
      params: { page_size: 100, search: search.value || undefined },
    })
    news.value = data.items
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 't("caseEdit.loadFailed")'
  } finally {
    loading.value = false
  }
}

async function del(n: NewsItem) {
  if (!confirm(`确定删除「${n.title}」吗？`)) return
  try {
    await api.delete(`/api/v1/cms/news/${n.id}`)
    await load()
  } catch (e: any) {
    alert('t("usersList.删除失败_1kc17l")' + (e?.response?.data?.detail || e.message))
  }
}

watch(search, () => { load() })
onMounted(load)
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/" class="text-sm text-ink-500 hover:text-ink-900">← Dashboard</router-link>
        <span class="font-semibold">{{ t('newsList.新闻管理_dgakuo') }}</span>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-10">
      <div v-if="loading" class="card text-ink-500">{{ t('usersList.加载中_b0k5km') }}</div>
      <div v-else-if="error" class="card text-red-600">⚠️ {{ error }}</div>
      <div v-else>
        <div class="flex flex-wrap items-center justify-between gap-3 mb-6">
          <h1 class="text-2xl font-semibold tracking-tight">新闻列表（{{ news.length }}）</h1>
          <div class="flex items-center gap-3">
            <SearchInput v-model="search" :placeholder="t('newsList.按标题_ve272g')" />
            <CsvExportButton endpoint="/api/v1/cms/news/export" filename="news.csv" :params="{ search: search || undefined }" />
            <router-link to="/cms/news/new" class="btn-primary">{{ t('newsList.text_y2o5wq') }}</router-link>
          </div>
        </div>
        <div class="card overflow-hidden p-0">
          <table class="w-full text-sm">
            <thead class="bg-ink-50 border-b border-ink-200">
              <tr class="text-left text-ink-500">
                <th class="px-4 py-3 font-medium">{{ t('newsList.标题_ij5d') }}</th>
                <th class="px-4 py-3 font-medium">Slug</th>
                <th class="px-4 py-3 font-medium">{{ t('usersList.状态_k1e3') }}</th>
                <th class="px-4 py-font-medium">{{ t('newsList.阅读_qaae') }}</th>
                <th class="px-4 py-3 font-medium text-right">{{ t('usersList.操作_hkxb') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="news.length === 0">
                <td colspan="5" class="px-4 py-12 text-center text-ink-400">{{ t('newsList.暂无新闻_dcvgq1') }}</td>
              </tr>
              <tr v-for="n in news" :key="n.id" class="border-b border-ink-100 last:border-0 hover:bg-ink-50">
                <td class="px-4 py-3 font-medium max-w-md truncate">{{ n.title }}</td>
                <td class="px-4 py-3 text-ink-500 font-mono text-xs">{{ n.slug }}</td>
                <td class="px-4 py-3">
                  <span class="text-xs px-2 py-0.5 rounded-full"
                    :class="n.status === 'published' ? 'bg-emerald-100 text-emerald-700' : 'bg-ink-100 text-ink-600'">
                    {{ n.status === 'published' ? '已发布' : n.status }}
                  </span>
                </td>
                <td class="px-4 py-3 text-ink-500">{{ n.view_count }}</td>
                <td class="px-4 py-3 text-right space-x-2">
                  <router-link :to="`/cms/news/${n.id}`" class="text-sm text-ink-600 hover:text-ink-900">{{ t('usersList.编辑_mekb') }}</router-link>
                  <button @click="del(n)" class="text-sm text-red-600 hover:underline">{{ t('usersList.删除_eslg') }}</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </main>
  </div>
</template>
