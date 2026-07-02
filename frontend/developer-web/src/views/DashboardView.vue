<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'

const stats = ref({ submissions: 0, installed: 0, downloads: 0 })
const recent = ref<any[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const subRes = await api.get('/api/v1/store/submissions?page_size=5')
    recent.value = subRes.data.items
    stats.value = {
      submissions: subRes.data.total,
      installed: subRes.data.items.filter((a: any) => a.status === 'installed').length,
      downloads: 0,
    }
  } catch { /* ignore */ } finally { loading.value = false }
})

const statusLabel: Record<string, string> = { pending: '待审核', approved: '已通过', rejected: '已拒绝', installed: '已安装' }
const statusClass: Record<string, string> = { pending: 'bg-amber-50 text-amber-600', approved: 'bg-blue-50 text-blue-600', rejected: 'bg-red-50 text-red-600', installed: 'bg-green-50 text-green-600' }
</script>

<template>
  <div>
    <div class="grid grid-cols-3 gap-4 mb-6">
      <div class="card p-4">
        <div class="text-sm text-ink-500">提交应用</div>
        <div class="text-2xl font-semibold">{{ stats.submissions }}</div>
      </div>
      <div class="card p-4">
        <div class="text-sm text-ink-500">已安装</div>
        <div class="text-2xl font-semibold text-green-600">{{ stats.installed }}</div>
      </div>
      <div class="card p-4">
        <div class="text-sm text-ink-500">总下载</div>
        <div class="text-2xl font-semibold text-blue-600">{{ stats.downloads }}</div>
      </div>
    </div>

    <div class="card">
      <h3 class="font-semibold p-4 border-b">最近提交</h3>
      <div v-if="loading" class="p-4 text-ink-500">加载中...</div>
      <div v-else-if="recent.length === 0" class="p-4 text-ink-500 text-center">暂无提交</div>
      <table v-else class="w-full text-sm">
        <thead class="bg-ink-50 text-left text-ink-500">
          <tr>
            <th class="px-4 py-2">应用</th>
            <th class="px-4 py-2">版本</th>
            <th class="px-4 py-2">状态</th>
            <th class="px-4 py-2">提交时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in recent" :key="s.id" class="border-t">
            <td class="px-4 py-2 font-medium">{{ s.icon }} {{ s.name }}</td>
            <td class="px-4 py-2 text-ink-500">{{ s.version }}</td>
            <td class="px-4 py-2">
              <span class="text-xs px-1.5 py-0.5 rounded" :class="statusClass[s.status]">{{ statusLabel[s.status] }}</span>
            </td>
            <td class="px-4 py-2 text-ink-500 text-xs">{{ s.created_at?.slice(0, 10) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
