<script setup lang="ts">
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { ref } from 'vue'

const props = defineProps<{ endpoint: string; filename: string; params?: Record<string, any> }>()
const auth = useAuthStore()
const loading = ref(false)

async function download() {
  loading.value = true
  try {
    const res = await api.get(props.endpoint, {
      params: props.params,
      responseType: 'blob',
      headers: { Authorization: `Bearer ${auth.token}` },
    })
    const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = props.filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch (e) {
    alert('导出失败：' + (e as any)?.message)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <button
    type="button"
    class="px-3 py-1.5 rounded-lg border border-ink-200 bg-white text-sm text-ink-700 hover:bg-ink-50 disabled:opacity-50"
    :disabled="loading"
    @click="download"
  >
    {{ loading ? '导出中…' : '导出 CSV' }}
  </button>
</template>
