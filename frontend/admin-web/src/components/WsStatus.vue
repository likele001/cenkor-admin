<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const status = ref<'connecting' | 'open' | 'closed'>('closed')
const lastMessage = ref<any>(null)
let ws: WebSocket | null = null
let reconnectTimer: number | undefined
let pingTimer: number | undefined

function url(): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const base = import.meta.env.VITE_WS_URL || `${proto}://${location.host}`
  return `${base}/api/v1/ws/notifications?token=${auth.token}`
}

function connect() {
  if (!auth.token) return
  status.value = 'connecting'
  try {
    ws = new WebSocket(url())
  } catch {
    status.value = 'closed'
    return
  }
  ws.onopen = () => {
    status.value = 'open'
    pingTimer = window.setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send('ping')
    }, 25_000)
  }
  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data)
      lastMessage.value = msg
      if (msg.type === 'notification' && msg.data) {
        window.dispatchEvent(new CustomEvent('notify:new', { detail: msg.data }))
      }
    } catch { lastMessage.value = e.data }
  }
  ws.onclose = () => {
    status.value = 'closed'
    if (pingTimer) window.clearInterval(pingTimer)
    // 5s 后重连
    reconnectTimer = window.setTimeout(connect, 5000)
  }
  ws.onerror = () => {
    ws?.close()
  }
}

onMounted(connect)
onBeforeUnmount(() => {
  if (reconnectTimer) window.clearTimeout(reconnectTimer)
  if (pingTimer) window.clearInterval(pingTimer)
  ws?.close()
})
</script>

<template>
  <div class="hidden">
    <span data-ws-status>{{ status }}</span>
    <span data-ws-last>{{ lastMessage ? JSON.stringify(lastMessage) : '' }}</span>
  </div>
</template>
