<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'

interface Comment {
  id: number; content_type_key: string; object_id: number; parent_id: number | null
  author_name: string; author_email: string | null; content: string; status: string; ip: string | null; created_at: string | null
}

const items = ref<Comment[]>([])
const statusFilter = ref('')
const stats = ref<Record<string, number>>({})
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/api/v1/comments', { params: statusFilter.value ? { status: statusFilter.value } : {} })
    items.value = data.items || []
    const s = await api.get('/api/v1/comments/stats')
    stats.value = s.data.by_status || {}
  } catch (e: any) { alert(e?.response?.data?.detail || t("dashboard.loadFailed")) } finally { loading.value = false }
}
async function act(c: Comment, status: string) {
  await api.patch(`/api/v1/comments/${c.id}`, { status })
  await load()
}
async function remove(c: Comment) {
  if (!window.confirm(t("comments.确认删除_1hy5af"))) return
  await api.delete(`/api/v1/comments/${c.id}`)
  await load()
}
function statusLabel(s: string) {
  return ({ pending: t("comments.待审核_eftvg"), approved: t("comments.已通过_ego67"), spam: t("comments.垃圾_fd3v"), deleted: t("comments.已删除_e65yu") } as Record<string, string>)[s] || s
}
function statusColor(s: string) {
  return ({ pending: 'bg-yellow-50 text-yellow-600', approved: 'bg-green-50 text-green-600', spam: 'bg-red-50 text-red-600', deleted: 'bg-ink-50 text-ink-400' } as Record<string, string>)[s] || 'bg-ink-50'
}
onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <div class="flex items-center gap-3">
        <h1 class="text-2xl font-semibold tracking-tight">{{ t("comments.text_1ct9fq") }}</h1>
        <span class="text-sm text-ink-400">M4·P3</span>
        <span v-if="stats.pending" class="text-xs px-2 py-1 bg-yellow-50 text-yellow-600 rounded">{{ stats.pending }} 条待审核</span>
      </div>
      <select v-model="statusFilter" class="input w-40" @change="load">
        <option value="">{{ t("entryList.全部状态_avez63") }}</option>
        <option value="pending">{{ t("comments.待审核_eftvg") }}</option>
        <option value="approved">{{ t("comments.已通过_ego67") }}</option>
        <option value="spam">{{ t("comments.垃圾_fd3v") }}</option>
        <option value="deleted">{{ t("comments.已删除_e65yu") }}</option>
      </select>
    </div>

    <div class="card overflow-hidden">
      <div v-if="loading" class="text-ink-500 p-6">{{ t("apiKeys.加载中_b0k5km") }}</div>
      <table v-else class="w-full text-sm">
        <thead>
          <tr class="text-left text-ink-400 border-b">
            <th class="p-3">{{ t("comments.content") }}</th><th class="p-3">{{ t("comments.作者_e78p") }}</th><th class="p-3">{{ t("comments.status") }}</th><th class="p-3">{{ t("comments.time") }}</th><th class="p-3 text-right">{{ t("comments.actions") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in items" :key="c.id" class="border-b last:border-0 align-top">
            <td class="p-3">
              <div class="text-ink-500 text-xs mb-1">{{ c.content_type_key }} / #{{ c.object_id }}<span v-if="c.parent_id" class="ml-1 text-ink-400">回复 #{{ c.parent_id }}</span></div>
              <div class="line-clamp-2">{{ c.content }}</div>
            </td>
            <td class="p-3">
              <div class="font-medium">{{ c.author_name }}</div>
              <div v-if="c.author_email" class="text-xs text-ink-400">{{ c.author_email }}</div>
            </td>
            <td class="p-3"><span class="text-xs px-1.5 py-0.5 rounded" :class="statusColor(c.status)">{{ statusLabel(c.status) }}</span></td>
            <td class="p-3 text-xs text-ink-400">{{ c.created_at ? new Date(c.created_at).toLocaleString() : '' }}</td>
            <td class="p-3 text-right space-x-2 whitespace-nowrap">
              <template v-if="c.status === 'pending'">
                <button class="btn-ghost text-sm text-green-600" @click="act(c, 'approved')">{{ t("comments.通过_past") }}</button>
                <button class="btn-ghost text-sm text-red-600" @click="act(c, 'reject')">{{ t("comments.驳回_qqx7") }}</button>
              </template>
              <button v-if="c.status === 'approved'" class="btn-ghost text-sm text-red-600" @click="act(c, 'spam')">{{ t("comments.垃圾_fd3v") }}</button>
              <button class="btn-ghost text-sm text-ink-500" @click="remove(c)">{{ t("comments.delete") }}</button>
            </td>
          </tr>
          <tr v-if="!items.length"><td colspan="5" class="p-6 text-center text-ink-400">{{ t("comments.暂无评论_dd1vv8") }}</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
