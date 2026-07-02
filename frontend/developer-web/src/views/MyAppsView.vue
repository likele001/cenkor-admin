<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { api } from '@/lib/api'
import { useRouter } from 'vue-router'

const items = ref<any[]>([])
const loading = ref(true)
const acting = ref<number | null>(null)
const expanded = ref<Set<string>>(new Set())
const router = useRouter()

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/api/v1/store/submissions?page_size=200')
    items.value = data.items
  } catch { /* ignore */ } finally { loading.value = false }
}

onMounted(load)

const statusLabel: Record<string, string> = { pending: '待审核', approved: '已通过', rejected: '已拒绝', installed: '已安装' }
const statusClass: Record<string, string> = { pending: 'bg-amber-50 text-amber-600', approved: 'bg-blue-50 text-blue-600', rejected: 'bg-red-50 text-red-600', installed: 'bg-green-50 text-green-600' }

// 状态严重度：installed > approved > pending > rejected（用于"应用整体状态"展示）
const statusRank: Record<string, number> = { installed: 4, approved: 3, pending: 2, rejected: 1 }

// 按 app_key 分组；每组按状态严重度 + 创建时间排序，取最佳作为主条目
interface AppGroup {
  app_key: string
  name: string
  icon: string
  primary: any
  versions: any[]
}

const groups = computed<AppGroup[]>(() => {
  const map = new Map<string, AppGroup>()
  for (const s of items.value) {
    let g = map.get(s.app_key)
    if (!g) {
      g = { app_key: s.app_key, name: s.name, icon: s.icon, primary: s, versions: [] }
      map.set(s.app_key, g)
    }
    g.versions.push(s)
  }
  // 同一 key 的多个版本：按"严重度优先 + 时间新"排序，主条目取第一个
  const arr = Array.from(map.values())
  for (const g of arr) {
    g.versions.sort((a, b) => {
      const r = (statusRank[b.status] || 0) - (statusRank[a.status] || 0)
      if (r !== 0) return r
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    })
    g.primary = g.versions[0]
  }
  // 应用列表按主条目时间倒序
  arr.sort((a, b) => new Date(b.primary.created_at).getTime() - new Date(a.primary.created_at).getTime())
  return arr
})

function canWithdraw(s: any) {
  return s.status !== 'installed'
}

function isExpanded(key: string) {
  return expanded.value.has(key)
}

function toggle(key: string) {
  if (expanded.value.has(key)) expanded.value.delete(key)
  else expanded.value.add(key)
  // 触发响应式
  expanded.value = new Set(expanded.value)
}

async function withdraw(s: any) {
  if (!confirm(`确定撤回「${s.name} v${s.version}」？撤回后可以重新提交。`)) return
  acting.value = s.id
  try {
    await api.delete(`/api/v1/store/submissions/${s.id}`)
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || '撤回失败')
  } finally {
    acting.value = null
  }
}

function submitNewVersion(prefillKey?: string) {
  const query = prefillKey ? { app_key: prefillKey } : {}
  router.push({ path: '/dashboard/submit', query })
}
</script>

<template>
  <div class="card">
    <div class="flex items-center justify-between p-4 border-b">
      <h2 class="font-semibold">我的应用</h2>
    </div>
    <div v-if="loading" class="p-4 text-ink-500">加载中...</div>
    <div v-else-if="groups.length === 0" class="p-8 text-center text-ink-500">
      <p class="mb-4">还没有提交过应用</p>
      <router-link to="/dashboard/submit" class="btn-primary">提交第一个应用</router-link>
    </div>
    <table v-else class="w-full text-sm">
      <thead class="bg-ink-50 text-left text-ink-500">
        <tr>
          <th class="px-4 py-2 w-6"></th>
          <th class="px-4 py-2">应用</th>
          <th class="px-4 py-2">最新版本</th>
          <th class="px-4 py-2">状态</th>
          <th class="px-4 py-2">最近提交</th>
          <th class="px-4 py-2 text-right">操作</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="g in groups" :key="g.app_key">
          <tr class="border-t">
            <td class="px-4 py-2 text-ink-400">
              <button
                v-if="g.versions.length > 1"
                class="text-xs hover:text-ink-900"
                :title="isExpanded(g.app_key) ? '收起历史版本' : '展开历史版本'"
                @click="toggle(g.app_key)"
              >{{ isExpanded(g.app_key) ? '▼' : '▶' }}</button>
            </td>
            <td class="px-4 py-2 font-medium">
              <code class="text-xs text-ink-400 mr-1">{{ g.app_key }}</code>
              {{ g.icon }} {{ g.name }}
              <span v-if="g.versions.length > 1" class="text-xs text-ink-400 ml-1">({{ g.versions.length }} 个版本)</span>
            </td>
            <td class="px-4 py-2 text-ink-500">{{ g.primary.version }}</td>
            <td class="px-4 py-2">
              <span class="text-xs px-1.5 py-0.5 rounded" :class="statusClass[g.primary.status]">{{ statusLabel[g.primary.status] }}</span>
            </td>
            <td class="px-4 py-2 text-ink-500 text-xs">{{ g.primary.created_at?.slice(0, 10) }}</td>
            <td class="px-4 py-2 text-right">
              <div class="flex justify-end gap-2">
                <button
                  v-if="canWithdraw(g.primary)"
                  class="text-xs text-red-600 hover:text-red-800 disabled:opacity-50"
                  :disabled="acting === g.primary.id"
                  @click="withdraw(g.primary)"
                >{{ acting === g.primary.id ? '撤回中…' : '撤回' }}</button>
                <button
                  class="text-xs text-blue-600 hover:text-blue-800"
                  @click="submitNewVersion(g.app_key)"
                >{{ g.primary.status === 'installed' ? '更新版本' : '提交新版本' }}</button>
              </div>
            </td>
          </tr>
          <tr v-if="isExpanded(g.app_key) && g.versions.length > 1" class="bg-ink-50/50">
            <td></td>
            <td colspan="5" class="px-4 py-2">
              <table class="w-full text-xs">
                <thead class="text-ink-400">
                  <tr>
                    <th class="py-1 text-left font-normal">版本</th>
                    <th class="py-1 text-left font-normal">状态</th>
                    <th class="py-1 text-left font-normal">提交时间</th>
                    <th class="py-1 text-left font-normal">审核备注</th>
                    <th class="py-1 text-right font-normal">操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="v in g.versions" :key="v.id" class="border-t border-ink-100">
                    <td class="py-1.5">{{ v.version }}</td>
                    <td class="py-1.5">
                      <span class="px-1.5 py-0.5 rounded" :class="statusClass[v.status]">{{ statusLabel[v.status] }}</span>
                    </td>
                    <td class="py-1.5 text-ink-500">{{ v.created_at?.slice(0, 10) }}</td>
                    <td class="py-1.5 text-ink-500">{{ v.review_note || '-' }}</td>
                    <td class="py-1.5 text-right">
                      <button
                        v-if="canWithdraw(v)"
                        class="text-red-600 hover:text-red-800 disabled:opacity-50"
                        :disabled="acting === v.id"
                        @click="withdraw(v)"
                      >{{ acting === v.id ? '撤回中…' : '撤回' }}</button>
                      <span v-else class="text-ink-400">—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>
