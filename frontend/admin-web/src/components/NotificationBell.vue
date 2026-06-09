<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '@/lib/api'

interface Notification {
  id: number
  type: string
  title: string
  body: string | null
  link: string | null
  read: boolean
  read_at: string | null
  created_at: string
}

const open = ref(false)
const items = ref<Notification[]>([])
const unread = ref(0)
const loading = ref(false)
const error = ref('')
let pollTimer: number | undefined

async function fetchUnread() {
  try {
    const { data } = await api.get('/api/v1/notifications/unread-count')
    unread.value = data.unread ?? 0
  } catch {
    // 静默失败：用户可能无 notification:read 权限
  }
}

async function fetchList() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/api/v1/notifications', { params: { page_size: 20 } })
    items.value = data.items ?? []
  } catch (e: any) {
    error.value = e?.response?.data?.detail || ''
  } finally {
    loading.value = false
  }
}

async function toggle() {
  open.value = !open.value
  if (open.value) await fetchList()
}

async function markAll() {
  try {
    await api.post('/api/v1/notifications/read-all')
    items.value = items.value.map((n) => ({ ...n, read: true, read_at: new Date().toISOString() }))
    unread.value = 0
  } catch { /* ignore */ }
}

async function markOne(n: Notification) {
  if (n.read) return
  try {
    await api.post(`/api/v1/notifications/${n.id}/read`)
    n.read = true
    n.read_at = new Date().toISOString()
    unread.value = Math.max(0, unread.value - 1)
  } catch { /* ignore */ }
}

async function remove(n: Notification) {
  try {
    await api.delete(`/api/v1/notifications/${n.id}`)
    items.value = items.value.filter((x) => x.id !== n.id)
  } catch { /* ignore */ }
}

function timeAgo(iso: string | null): string {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60_000)
  if (m < 1) return '刚刚'
  if (m < 60) return `${m} 分钟前`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} 小时前`
  const d = Math.floor(h / 24)
  return `${d} 天前`
}

onMounted(() => {
  fetchUnread()
  pollTimer = window.setInterval(fetchUnread, 30_000)
})

onBeforeUnmount(() => {
  if (pollTimer) window.clearInterval(pollTimer)
})
</script>

<template>
  <div class="relative">
    <button
      type="button"
      class="relative p-1.5 rounded-md text-ink-600 hover:bg-ink-100"
      :aria-label="`通知 (${unread} 未读)`"
      @click="toggle"
    >
      <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
        <path d="M10 21a2 2 0 0 0 4 0" />
      </svg>
      <span
        v-if="unread > 0"
        class="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 text-[10px] font-medium rounded-full bg-red-500 text-white flex items-center justify-center"
      >
        {{ unread > 99 ? '99+' : unread }}
      </span>
    </button>

    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0 -translate-y-1"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition duration-100 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="open"
        class="absolute right-0 mt-2 w-96 max-h-[70vh] overflow-hidden flex flex-col rounded-xl border border-ink-200 bg-white shadow-lg z-50"
      >
        <div class="flex items-center justify-between px-4 py-3 border-b border-ink-200">
          <h3 class="font-semibold text-sm">通知</h3>
          <button
            v-if="unread > 0"
            type="button"
            class="text-xs text-brand-600 hover:underline"
            @click="markAll"
          >
            全部标为已读
          </button>
        </div>

        <div class="flex-1 overflow-y-auto">
          <div v-if="loading" class="p-6 text-center text-ink-400 text-sm">加载中…</div>
          <div v-else-if="error" class="p-4 text-sm text-red-600">{{ error }}</div>
          <div v-else-if="items.length === 0" class="p-8 text-center text-ink-400 text-sm">
            <div class="text-3xl mb-2">🔔</div>
            暂无通知
          </div>
          <ul v-else class="divide-y divide-ink-100">
            <li
              v-for="n in items"
              :key="n.id"
              class="px-4 py-3 hover:bg-ink-50 group"
              :class="{ 'bg-brand-50/40': !n.read }"
            >
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <span
                      v-if="!n.read"
                      class="w-1.5 h-1.5 rounded-full bg-brand-500 shrink-0"
                    />
                    <p class="text-sm font-medium text-ink-900 truncate">{{ n.title }}</p>
                  </div>
                  <p v-if="n.body" class="mt-1 text-xs text-ink-500 line-clamp-2">{{ n.body }}</p>
                  <p class="mt-1 text-[10px] text-ink-400">{{ timeAgo(n.created_at) }}</p>
                </div>
                <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100">
                  <button
                    v-if="!n.read"
                    type="button"
                    class="text-[10px] text-brand-600 hover:underline"
                    @click="markOne(n)"
                  >
                    已读
                  </button>
                  <button
                    type="button"
                    class="text-[10px] text-ink-400 hover:text-red-600"
                    @click="remove(n)"
                  >
                    删除
                  </button>
                </div>
              </div>
            </li>
          </ul>
        </div>
      </div>
    </Transition>
  </div>
</template>
