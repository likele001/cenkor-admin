<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import RichTextEditor from '@/components/RichTextEditor.vue'
const { t } = useI18n()
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'

interface Notification {
  id: number; type: string; title: string; body: string
  link: string | null; read: boolean; created_at: string | null
}

const items = ref<Notification[]>([])
const loading = ref(true)
const error = ref('')
const total = ref(0)
const page = ref(1)
const pageSize = 20
const unreadOnly = ref(false)

const showSend = ref(false)
const sendForm = ref({ title: '', body: '', type: 'system', link: '' })
const sending = ref(false)

const typeLabel: Record<string, string> = { system: '系统', audit: '审计', mention: '提及', task: '任务' }
const typeClass: Record<string, string> = { system: 'bg-blue-50 text-blue-600', audit: 'bg-amber-50 text-amber-600', mention: 'bg-purple-50 text-purple-600', task: 'bg-green-50 text-green-600' }

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ page: String(page.value), page_size: String(pageSize) })
    if (unreadOnly.value) params.set('unread_only', 'true')
    const { data } = await api.get(`/api/v1/notifications?${params}`)
    items.value = data.items
    total.value = data.total
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t("dashboard.loadFailed")
  } finally { loading.value = false }
}

async function markRead(id: number) {
  try { await api.post(`/api/v1/notifications/${id}/read`); await load() } catch { /* ignore */ }
}

async function markAllRead() {
  try { await api.post('/api/v1/notifications/read-all'); await load() } catch { /* ignore */ }
}

async function del(id: number) {
  try { await api.delete(`/api/v1/notifications/${id}`); await load() } catch { /* ignore */ }
}

async function send() {
  if (!sendForm.value.title) return
  sending.value = true
  try {
    await api.post('/api/v1/notifications/send', {
      type: sendForm.value.type,
      title: sendForm.value.title,
      body: sendForm.value.body,
      link: sendForm.value.link || undefined,
    })
    showSend.value = false
    sendForm.value = { title: '', body: '', type: 'system', link: '' }
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || t("notifications.发送失败_b643fo"))
  } finally { sending.value = false }
}

const totalPages = Math.max(1, Math.ceil(total.value / pageSize))

onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">{{ t('nav.notifications') }}</h1>
        <p class="text-ink-500">{{ t("notifications.查看系统_nfi3i6") }}</p>
      </div>
      <div class="flex gap-2">
        <button class="btn-ghost text-sm" @click="unreadOnly = !unreadOnly; load()">
          {{ unreadOnly ? $t('notifications.查看全部_dll6ti') : $t('notifications.只看未读_b2yt6a') }}
        </button>
        <button class="btn-ghost text-sm" @click="markAllRead">{{ t("notifications.全部已读_avbop5") }}</button>
        <button class="btn-primary text-sm" @click="showSend = true">{{ t("notifications.发送通知_b6dbh7") }}</button>
      </div>
    </div>

    <div v-if="loading" class="card text-ink-500">{{ t("announcements.加载中_27k1ha") }}</div>
    <div v-else-if="error" class="card text-red-600">{{ error }}</div>
    <div v-else-if="items.length === 0" class="card text-ink-500 text-center py-12">{{ t("notifications.暂无通知_dd2ii1") }}</div>
    <div v-else class="space-y-2">
      <div v-for="n in items" :key="n.id" class="card flex items-start gap-3" :class="{ 'opacity-60': n.read }">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 mb-1">
            <h3 class="text-sm font-medium">{{ n.title }}</h3>
            <span v-if="!n.read" class="w-2 h-2 rounded-full bg-blue-500 shrink-0"></span>
            <span class="text-xs px-1.5 py-0.5 rounded" :class="typeClass[n.type]">{{ typeLabel[n.type] || n.type }}</span>
          </div>
          <p class="text-sm text-ink-600">{{ n.body }}</p>
          <div class="flex items-center gap-3 mt-1">
            <span class="text-xs text-ink-400">{{ n.created_at?.slice(0, 16) }}</span>
            <span v-if="n.link" class="text-xs text-blue-500 hover:underline cursor-pointer" @click="$router.push(n.link!)">{{ t("notifications.查看_ibpi") }}</span>
          </div>
        </div>
        <div class="flex gap-1 shrink-0">
          <button v-if="!n.read" class="text-xs text-ink-500 hover:text-ink-700" @click="markRead(n.id)">{{ t("notifications.已读_gqx5") }}</button>
          <button class="text-xs text-red-500 hover:text-red-700" @click="del(n.id)">{{ t("notifications.delete") }}</button>
        </div>
      </div>
    </div>

    <div v-if="totalPages > 1" class="mt-4 flex items-center justify-center gap-2 text-sm">
      <button class="btn-ghost" :disabled="page <= 1" @click="page--; load()">{{ t("notifications.上一页_btlof") }}</button>
      <span>{{ page }} / {{ totalPages }}</span>
      <button class="btn-ghost" :disabled="page >= totalPages" @click="page++; load()">{{ t("notifications.下一页_btmf4") }}</button>
    </div>

    <!-- Send Notification Modal -->
    <div v-if="showSend" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showSend = false">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h2 class="text-lg font-semibold mb-4">{{ t("notifications.发送系统_d0fhcv") }}</h2>
        <div class="space-y-3">
          <div>
            <label class="block text-sm font-medium mb-1">{{ t("notifications.type") }}</label>
            <select v-model="sendForm.type" class="input">
              <option value="system">{{ t("notifications.系统通知_garqz3") }}</option>
              <option value="task">{{ t("notifications.任务通知_abf72p") }}</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t("notifications.title") }}</label>
            <input v-model="sendForm.title" class="input" :placeholder="t('notifications.通知标题_iodwho')" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t("notifications.content") }}</label>
            <RichTextEditor v-model="sendForm.body" :placeholder="t('notifications.通知内容_bw7qw6')" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t("notifications.link") }}</label>
            <input v-model="sendForm.link" class="input" :placeholder="t('notifications.text_1m9n0q')" />
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button class="btn-ghost" @click="showSend = false">{{ t("notifications.cancel") }}</button>
          <button class="btn-primary" :disabled="sending || !sendForm.title" @click="send">
            {{ sending ? $t('notifications.发送中_6kni41') : $t('notifications.发送给所_d4ikfc') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
