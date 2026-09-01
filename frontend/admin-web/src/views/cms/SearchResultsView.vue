<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/lib/api'

const route = useRoute()
const q = ref(String(route.query.q || ''))
const items = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const ctFilter = ref('')

async function search() {
  loading.value = true
  try {
    const params: any = { q: q.value, page_size: 50 }
    if (ctFilter.value) params.content_type_key = ctFilter.value
    const { data } = await api.get('/api/v1/cms/search', { params })
    items.value = data.items || []
    total.value = data.total || 0
  } catch { items.value = [] } finally { loading.value = false }
}
function statusLabel(s: string) {
  return ({ draft: '草稿', published: '已发布', archived: '归档', pending_review: '待审核', approved: '已通过' } as Record<string, string>)[s] || s
}
watch(ctFilter, search)
watch(() => route.query.q, v => { q.value = String(v || ''); search() })
onMounted(search)
</script>

<template>
  <div>
    <div class="flex items-center gap-3 mb-6">
      <h1 class="text-2xl font-semibold tracking-tight">🔍 内容搜索</h1>
      <input v-model="q" class="input flex-1 max-w-md" placeholder="关键词：标题 / 正文 / 自定义字段…" @keyup.enter="search" />
      <select v-model="ctFilter" class="input w-36">
        <option value="">全部类型</option>
        <option value="article">文章</option>
        <option value="news">新闻</option>
        <option value="product">产品</option>
        <option value="case">案例</option>
      </select>
      <button class="btn-primary" @click="search">搜索</button>
    </div>

    <div class="card overflow-hidden">
      <div v-if="loading" class="text-ink-500 p-6">搜索中…</div>
      <template v-else>
        <div class="text-sm text-ink-400 px-3 pt-3">共 {{ total }} 条结果</div>
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-ink-400 border-b">
              <th class="p-3">标题</th><th class="p-3">Slug</th><th class="p-3">状态</th><th class="p-3">更新时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="it in items" :key="it.id" class="border-b last:border-0">
              <td class="p-3">
                <router-link :to="`/cms/entries/${it.id}?ct=${it.content_type_id}`" class="text-blue-600 hover:underline">{{ it.title }}</router-link>
              </td>
              <td class="p-3 text-xs text-ink-400">{{ it.slug || '-' }}</td>
              <td class="p-3"><span class="text-xs px-1.5 py-0.5 bg-ink-50 rounded">{{ statusLabel(it.status) }}</span></td>
              <td class="p-3 text-xs text-ink-400">{{ it.updated_at ? new Date(it.updated_at).toLocaleString() : '' }}</td>
            </tr>
            <tr v-if="!items.length"><td colspan="4" class="p-6 text-center text-ink-400">{{ q ? '无匹配结果' : '输入关键词开始搜索' }}</td></tr>
          </tbody>
        </table>
      </template>
    </div>
  </div>
</template>
