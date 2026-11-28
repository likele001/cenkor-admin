<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '@/lib/api'
import { getSiteId, setSiteId } from '@/lib/site'

interface Site {
  id: number
  name: string
  key: string
  domain: string | null
  status: string
}

const sites = ref<Site[]>([])
const current = ref<number | null>(getSiteId())

async function load() {
  try {
    const { data } = await api.get<Site[]>('/api/v1/cms/sites')
    sites.value = data
    // 没选过站点时跟随后端默认站：只有一个站点就锁定它，
    // 避免下拉显示空白让人误以为「没有站点」。
    if (current.value === null && data.length) current.value = data[0].id
  } catch {
    // 无权限或站点未初始化：不打扰，顶栏直接不显示
    sites.value = []
  }
}

function change() {
  setSiteId(current.value)
  // 各页面的数据在 setup 阶段拉取，换站点必须重新挂载才不会再看到旧站的数据
  location.reload()
}

onMounted(load)
</script>

<template>
  <label v-if="sites.length" class="inline-flex items-center gap-1.5 shrink-0" title="切换当前站点">
    <svg class="w-4 h-4 text-ink-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12h18M3 12l4-4M3 12l4 4M21 12l-4-4M21 12l-4 4" />
    </svg>
    <select v-model.number="current" class="input text-sm py-1.5 max-w-[11rem]" @change="change">
      <option v-for="s in sites" :key="s.id" :value="s.id">
        {{ s.name }}{{ s.domain ? ' · ' + s.domain : '' }}
      </option>
    </select>
  </label>
  <router-link
    v-if="sites.length"
    to="/cms/sites"
    class="inline-flex items-center gap-1 px-2 py-1.5 rounded-md text-sm text-ink-500 hover:text-ink-900 hover:bg-ink-50 border border-ink-200 shrink-0"
    title="管理站点"
  >
    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
    </svg>
    <span class="hidden md:inline">站点</span>
  </router-link>
</template>
