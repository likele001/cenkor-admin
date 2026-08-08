<script setup lang="ts">
import { onMounted, ref, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, PieChart, BarChart } from 'echarts/charts'
import {
  GridComponent,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
} from 'echarts/components'
import VChart, { THEME_KEY } from 'vue-echarts'
import { provide } from 'vue'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import RichTextContent from '@/components/RichTextContent.vue'

use([
  CanvasRenderer,
  LineChart,
  PieChart,
  BarChart,
  GridComponent,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
])

provide(THEME_KEY, 'light')

const auth = useAuthStore()
const { t } = useI18n()
const me = ref<{ username?: string; email?: string; nickname?: string; permissions?: string[]; is_superuser?: boolean } | null>(auth.user as any)
const overview = ref<Record<string, number> | null>(null)
const trend = ref<Array<{ date: string; count: number }>>([])
const byMethod = ref<Record<string, number>>({})
const byStatus = ref<Record<string, number>>({})
const loading = ref(true)
const error = ref<string | null>(null)

const lineOption = shallowRef({})
const methodOption = shallowRef({})
const statusOption = shallowRef({})

// 系统更新日志
const announcements = ref<any[]>([])
const annLoading = ref(false)
const annError = ref<string | null>(null)
const expandedAnnId = ref<number | null>(null)
const annDetail = ref<Record<number, string>>({})

function formatDate(s: string) {
  if (!s) return ''
  const d = new Date(s)
  if (isNaN(d.getTime())) return s
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

async function loadAnnouncements() {
  annLoading.value = true
  annError.value = null
  try {
    const res = await api.get('/api/v1/announcements', { params: { limit: 5 } })
    const items = (res.data?.items || [])
      .filter((x: any) => x.is_published !== false)
      .sort((a: any, b: any) => Number(b.is_pinned) - Number(a.is_pinned))
    announcements.value = items
    if (items.length) await toggleAnn(items[0], true)
  } catch (e: any) {
    annError.value = e?.message || '加载失败'
  } finally {
    annLoading.value = false
  }
}

async function toggleAnn(a: any, forceExpand = false) {
  if (!forceExpand && expandedAnnId.value === a.id) {
    expandedAnnId.value = null
    return
  }
  expandedAnnId.value = a.id
  if (annDetail.value[a.id] === undefined) {
    try {
      const res = await api.get(`/api/v1/announcements/${a.id}`)
      annDetail.value = { ...annDetail.value, [a.id]: res.data?.content || '' }
    } catch {
      annDetail.value = { ...annDetail.value, [a.id]: '' }
    }
  }
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const res = await api.get('/api/v1/dashboard/stats')
    const data = res.data
    overview.value = data.overview
    trend.value = data.api_calls_trend_7d
    byMethod.value = data.by_method_7d
    byStatus.value = data.by_status_7d

    lineOption.value = {
      tooltip: { trigger: 'axis' },
      grid: { left: 30, right: 16, top: 24, bottom: 30 },
      xAxis: { type: 'category', data: trend.value.map((p) => p.date.slice(5)) },
      yAxis: { type: 'value', minInterval: 1 },
      series: [{
        name: t('dashboard.apiCalls'),
        type: 'line',
        smooth: true,
        areaStyle: { opacity: 0.15 },
        data: trend.value.map((p) => p.count),
      }],
    }

    const methods = Object.entries(byMethod.value)
    methodOption.value = {
      tooltip: { trigger: 'item' },
      legend: { bottom: 0 },
      series: [{
        type: 'pie',
        radius: ['40%', '70%'],
        avoidLabelOverlap: false,
        label: { show: false },
        data: methods.map(([name, value]) => ({ name, value })),
      }],
    }

    const statusEntries = Object.entries(byStatus.value)
    statusOption.value = {
      tooltip: { trigger: 'axis' },
      grid: { left: 30, right: 16, top: 16, bottom: 30 },
      xAxis: { type: 'category', data: statusEntries.map(([k]) => k) },
      yAxis: { type: 'value', minInterval: 1 },
      series: [{
        type: 'bar',
        data: statusEntries.map(([, v]) => v),
        itemStyle: { borderRadius: [4, 4, 0, 0] },
      }],
    }
  } catch (e: any) {
    error.value = e?.message || t('common.loadFailed', '加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  me.value = auth.user
  load()
  loadAnnouncements()
})
</script>

<template>
  <div>
    <h1 class="text-3xl font-semibold tracking-tight">{{ t('nav.dashboard', 'Dashboard') }}</h1>
    <p class="mt-2 text-ink-500">{{ t('dashboard.welcome', '欢迎回来。这是 Cenkor Admin Platform 的起点。') }}</p>

    <!-- 系统更新日志 -->
    <section class="mt-6 card">
      <div class="flex items-center justify-between mb-3">
        <h2 class="font-semibold flex items-center gap-2">
          <span>📌</span><span>系统更新日志</span>
        </h2>
        <router-link :to="{ name: 'announcements' }" class="text-sm text-accent hover:underline">查看全部</router-link>
      </div>
      <div v-if="annLoading" class="text-ink-400 text-sm py-2">加载中…</div>
      <div v-else-if="annError" class="text-red-600 text-sm py-2">{{ annError }}</div>
      <ul v-else-if="announcements.length" class="space-y-3">
        <li v-for="a in announcements" :key="a.id" class="border border-ink-200 rounded-lg p-3">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2 flex-wrap">
                <span v-if="a.is_pinned" class="text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">置顶</span>
                <span v-if="a.category" class="text-xs bg-ink-100 text-ink-600 px-1.5 py-0.5 rounded">{{ a.category }}</span>
                <span v-if="a.priority === 'high'" class="text-xs bg-red-100 text-red-700 px-1.5 py-0.5 rounded">重要</span>
                <span class="font-medium break-words">{{ a.title }}</span>
              </div>
              <p v-if="a.summary" class="mt-1 text-sm text-ink-500 break-words">{{ a.summary }}</p>
              <p v-if="a.created_at" class="mt-1 text-xs text-ink-400">{{ formatDate(a.created_at) }}</p>
            </div>
            <button type="button" class="text-sm text-accent hover:underline shrink-0" @click="toggleAnn(a)">
              {{ expandedAnnId === a.id ? '收起' : '查看全文' }}
            </button>
          </div>
          <div v-if="expandedAnnId === a.id && annDetail[a.id]" class="mt-3 border-t border-ink-200 pt-3">
            <RichTextContent :content="annDetail[a.id]" />
          </div>
        </li>
      </ul>
      <div v-else class="text-ink-400 text-sm py-2">暂无更新日志</div>
    </section>

    <div v-if="loading" class="mt-8 text-ink-400">{{ t('app.loading') }}</div>
    <div v-else-if="error" class="mt-8 text-red-600">{{ error }}</div>

    <template v-else>
      <div class="mt-8 grid md:grid-cols-5 gap-4">
        <div class="card">
          <div class="text-3xl font-semibold">{{ overview?.users ?? 0 }}</div>
          <div class="mt-1 text-sm text-ink-500">{{ t('dashboard.users') }}</div>
        </div>
        <div class="card">
          <div class="text-3xl font-semibold">{{ overview?.products ?? 0 }}</div>
          <div class="mt-1 text-sm text-ink-500">{{ t('dashboard.products') }}</div>
        </div>
        <div class="card">
          <div class="text-3xl font-semibold">{{ overview?.cases ?? 0 }}</div>
          <div class="mt-1 text-sm text-ink-500">{{ t('dashboard.cases') }}</div>
        </div>
        <div class="card">
          <div class="text-3xl font-semibold">{{ overview?.news ?? 0 }}</div>
          <div class="mt-1 text-sm text-ink-500">{{ t('dashboard.news') }}</div>
        </div>
        <div class="card">
          <div class="text-3xl font-semibold">{{ overview?.media ?? 0 }}</div>
          <div class="mt-1 text-sm text-ink-500">{{ t('dashboard.media') }}</div>
        </div>
      </div>

      <div class="mt-8 grid lg:grid-cols-2 gap-4">
        <div class="card">
          <h2 class="font-semibold mb-3">{{ t('dashboard.apiCalls7d') }}</h2>
          <v-chart class="h-64" :option="lineOption" autoresize />
        </div>
        <div class="card">
          <h2 class="font-semibold mb-3">{{ t('dashboard.methodDistribution') }}</h2>
          <v-chart class="h-64" :option="methodOption" autoresize />
        </div>
      </div>

      <div class="mt-4 card">
        <h2 class="font-semibold mb-3">{{ t('dashboard.statusDistribution') }}</h2>
        <v-chart class="h-64" :option="statusOption" autoresize />
      </div>
    </template>

    <div v-if="me" class="mt-8 card">
      <h2 class="font-semibold mb-3">{{ t('dashboard.currentUser') }}</h2>
      <dl class="grid sm:grid-cols-2 gap-3 text-sm">
        <div><dt class="text-ink-500">{{ t('dashboard.username') }}</dt><dd class="font-medium">{{ me.username }}</dd></div>
        <div><dt class="text-ink-500">{{ t('dashboard.permissionCount') }}</dt><dd class="font-medium">{{ me.permissions?.length ?? 0 }}</dd></div>
      </dl>
    </div>
  </div>
</template>