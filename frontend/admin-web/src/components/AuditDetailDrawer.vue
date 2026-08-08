<script setup lang="ts">
import { ref, watch } from 'vue'
import { api } from '@/lib/api'

const props = defineProps<{ auditId: number | null }>()
const emit = defineEmits<{ close: [] }>()

interface Detail {
  id: number
  request_id: string
  user_id: number | null
  method: string
  path: string
  status_code: number
  duration_ms: number
  ip: string | null
  user_agent: string | null
  diff: any
  error: string | null
  created_at: string | null
}

const detail = ref<Detail | null>(null)
const loading = ref(false)
const error = ref('')

watch(() => props.auditId, async (id) => {
  if (id == null) {
    detail.value = null
    return
  }
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get(`/api/v1/system/audit/${id}`)
    detail.value = data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}, { immediate: true })

function formatJSON(v: any): string {
  if (v == null) return ''
  if (typeof v === 'string') return v
  try { return JSON.stringify(v, null, 2) } catch { return String(v) }
}

function diffKeys(diff: any): Array<{ key: string; before: any; after: any }> {
  // 接受 {key: {before, after}} 或 {key: [before, after]} 结构
  if (!diff || typeof diff !== 'object') return []
  const out: Array<{ key: string; before: any; after: any }> = []
  for (const [k, v] of Object.entries(diff)) {
    if (v && typeof v === 'object' && 'before' in v && 'after' in v) {
      out.push({ key: k, before: (v as any).before, after: (v as any).after })
    } else if (Array.isArray(v) && v.length === 2) {
      out.push({ key: k, before: v[0], after: v[1] })
    }
  }
  return out
}
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="auditId != null"
        class="fixed inset-0 z-50 flex"
        @click.self="emit('close')"
      >
        <div class="flex-1 bg-ink-900/40 backdrop-blur-sm" @click="emit('close')" />
        <div class="w-full max-w-2xl bg-white shadow-xl flex flex-col overflow-hidden">
          <div class="px-6 py-4 border-b border-ink-200 flex items-center justify-between">
            <h2 class="text-lg font-semibold">审计详情 #{{ auditId }}</h2>
            <button class="text-ink-500 hover:text-ink-900" @click="emit('close')">✕</button>
          </div>

          <div class="flex-1 overflow-y-auto px-6 py-4 space-y-4">
            <div v-if="loading" class="text-ink-400 text-sm">加载中…</div>
            <div v-else-if="error" class="text-red-600 text-sm">{{ error }}</div>
            <template v-else-if="detail">
              <section>
                <h3 class="text-xs font-semibold text-ink-500 uppercase mb-2">基本信息</h3>
                <dl class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
                  <div><dt class="text-ink-500">方法</dt><dd class="font-mono">{{ detail.method }}</dd></div>
                  <div><dt class="text-ink-500">状态</dt><dd>{{ detail.status_code }}</dd></div>
                  <div class="col-span-2"><dt class="text-ink-500">路径</dt><dd class="font-mono text-xs break-all">{{ detail.path }}</dd></div>
                  <div><dt class="text-ink-500">用户 ID</dt><dd>{{ detail.user_id ?? '-' }}</dd></div>
                  <div><dt class="text-ink-500">耗时</dt><dd>{{ detail.duration_ms }}ms</dd></div>
                  <div><dt class="text-ink-500">IP</dt><dd class="font-mono text-xs">{{ detail.ip || '-' }}</dd></div>
                  <div><dt class="text-ink-500">时间</dt><dd class="font-mono text-xs">{{ detail.created_at }}</dd></div>
                  <div class="col-span-2"><dt class="text-ink-500">请求 ID</dt><dd class="font-mono text-xs break-all">{{ detail.request_id }}</dd></div>
                  <div v-if="detail.user_agent" class="col-span-2"><dt class="text-ink-500">UA</dt><dd class="text-xs break-all">{{ detail.user_agent }}</dd></div>
                </dl>
              </section>

              <section v-if="diffKeys(detail.diff).length > 0">
                <h3 class="text-xs font-semibold text-ink-500 uppercase mb-2">变更对比</h3>
                <div class="border border-ink-200 rounded-lg overflow-hidden">
                  <div class="overflow-x-auto"><table class="w-full text-xs">
                    <thead class="bg-ink-50">
                      <tr class="text-ink-500 text-left">
                        <th class="px-3 py-2 w-full sm:w-32 font-medium">字段</th>
                        <th class="px-3 py-2 font-medium">变更前</th>
                        <th class="px-3 py-2 font-medium">变更后</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="d in diffKeys(detail.diff)" :key="d.key" class="border-t border-ink-200 align-top">
                        <td class="px-3 py-2 font-mono text-ink-700">{{ d.key }}</td>
                        <td class="px-3 py-2 font-mono text-red-700 bg-red-50/50 whitespace-pre-wrap break-all">
                          {{ formatJSON(d.before) || '∅' }}
                        </td>
                        <td class="px-3 py-2 font-mono text-emerald-700 bg-emerald-50/50 whitespace-pre-wrap break-all">
                          {{ formatJSON(d.after) || '∅' }}
                        </td>
                      </tr>
                    </tbody>
                  </table></div>
                </div>
              </section>

              <section v-else>
                <h3 class="text-xs font-semibold text-ink-500 uppercase mb-2">变更对比</h3>
                <p class="text-sm text-ink-400">该请求无 diff 数据（可能为查询操作或未启用 diff 记录）</p>
              </section>

              <section v-if="detail.error">
                <h3 class="text-xs font-semibold text-ink-500 uppercase mb-2">错误</h3>
                <pre class="text-xs text-red-700 bg-red-50 border border-red-200 rounded p-3 whitespace-pre-wrap break-all">{{ detail.error }}</pre>
              </section>
            </template>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
