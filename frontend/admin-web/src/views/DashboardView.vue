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
})
</script>

<template>
  <div>
    <h1 class="text-3xl font-semibold tracking-tight">{{ t('nav.dashboard', 'Dashboard') }}</h1>
    <p class="mt-2 text-ink-500">{{ t('dashboard.welcome', '欢迎回来。这是 Cenkor Admin Platform 的起点。') }}</p>

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