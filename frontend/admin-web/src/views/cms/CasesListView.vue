<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { api } from '@/lib/api'
import SearchInput from '@/components/SearchInput.vue'
import CsvExportButton from '@/components/CsvExportButton.vue'

interface Case {
  id: number
  industry: string
  name: string
  desc: string
  tag: string
  href: string | null
  sort: number
  status: string
}

const cases = ref<Case[]>([])
const loading = ref(true)
const error = ref('')
const search = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/api/v1/cms/cases', { params: { search: search.value || undefined } })
    cases.value = data.items ?? data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

watch(search, () => { load() })
onMounted(load)
</script>

<template>
  <div>
    <div v-if="loading && cases.length === 0" class="card text-ink-500">加载中…</div>
    <div v-else-if="error" class="card text-red-600">⚠️ {{ error }}</div>
    <div v-else>
      <div class="flex flex-wrap items-center justify-between gap-3 mb-6">
        <h1 class="text-2xl font-semibold tracking-tight">客户案例（{{ cases.length }}）</h1>
        <div class="flex items-center gap-3">
          <SearchInput v-model="search" placeholder="按名称/行业/标签搜索…" />
          <CsvExportButton endpoint="/api/v1/cms/cases/export" filename="cases.csv" :params="{ search: search || undefined }" />
          <router-link to="/cms/cases/new" class="btn-primary">+ 新建案例</router-link>
        </div>
      </div>
      <div class="grid md:grid-cols-2 gap-4">
        <div v-for="c in cases" :key="c.id" class="card">
          <div class="flex items-center justify-between mb-3">
            <span class="text-xs px-2 py-0.5 rounded bg-ink-100 text-ink-700">{{ c.industry }}</span>
            <span class="text-xs text-ink-400">{{ c.tag }}</span>
          </div>
          <h3 class="font-semibold">{{ c.name }}</h3>
          <p class="mt-2 text-sm text-ink-600">{{ c.desc }}</p>
          <div class="mt-4 flex items-center gap-2">
            <router-link :to="`/cms/cases/${c.id}`" class="text-sm text-ink-600 hover:text-ink-900">编辑</router-link>
            <a v-if="c.href" :href="c.href" target="_blank" rel="noopener" class="text-sm text-ink-600 hover:text-ink-900">查看 →</a>
          </div>
        </div>
        <div v-if="cases.length === 0" class="col-span-full text-center text-ink-400 py-12">暂无案例</div>
      </div>
    </div>
  </div>
</template>
