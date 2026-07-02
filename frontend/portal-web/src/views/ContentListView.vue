<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api } from '@/lib/api'
import SiteHeader from '@/components/SiteHeader.vue'

interface Item {
  id: number; slug: string; title: string
  content: Record<string, any>
  is_flagship?: boolean; website?: string; published_at?: string; view_count?: number
}

const route = useRoute()
const { t } = useI18n()

const ctKey = computed(() => (route.params.ct as string) || 'product')
const items = ref<Item[]>([])
const loading = ref(true)
const total = ref(0)
const page = ref(1)
const pageSize = 20
const errorMsg = ref('')

const pageMeta: Record<string, { title: string; desc: string }> = {
  product: { title: '产品矩阵', desc: '7 款产品覆盖企业后台、AI 智能化与智能制造三大方向，可独立使用，也可组合交付。' },
  case: { title: '客户案例', desc: '看看我们的客户如何借助辰科产品实现数字化转型。' },
  news: { title: '新闻动态', desc: '辰科最新动态、产品更新与行业洞察。' },
}

const meta = computed(() => pageMeta[ctKey.value] || { title: ctKey.value, desc: '' })

const lineHue: Record<string, number> = { enterprise: 250, ai: 295, manufacturing: 165 }

function cardStyle(item: Item) {
  const line = item.content?.line || 'enterprise'
  const hue = lineHue[line] || 250
  return { background: `oklch(0.62 0.165 ${hue})` }
}

async function loadItems() {
  loading.value = true; errorMsg.value = ''
  try {
    const { data } = await api.get(`/api/v1/public/site/${ctKey.value}?page=${page.value}&page_size=${pageSize}`)
    items.value = data.items || []
    total.value = data.total || 0
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e.message || t('error.loadFailed')
  } finally { loading.value = false }
}

watch(() => route.params.ct, () => { page.value = 1; loadItems() })
onMounted(loadItems)
</script>

<template>
  <div class="min-h-screen bg-[#f8f9fb] font-['Plus_Jakarta_Sans',system-ui,sans-serif]">
    <SiteHeader />

    <main id="main">
      <section class="container-narrow pt-20 md:pt-28 pb-12 text-center">
        <h1 class="display-lg reveal">{{ meta.title }}</h1>
        <p class="reveal mt-5 text-lg text-[#5b5e66] max-w-2xl mx-auto" style="max-width:65ch">{{ meta.desc }}</p>
      </section>

      <section class="container-wide pb-24 md:pb-32">
        <div v-if="loading" class="text-center py-12 text-[#8b8e96]">{{ t('common.loading') }}</div>
        <div v-else-if="errorMsg" class="text-center py-12 text-red-600">{{ errorMsg }}</div>
        <div v-else-if="items.length === 0" class="text-center py-12 text-[#8b8e96]">{{ t('contentList.empty') }}</div>
        <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          <router-link
            v-for="item in items"
            :key="item.id"
            :to="`/list/${ctKey}/${item.id}`"
            class="group bento bento-hover flex flex-col min-h-[240px]"
          >
            <div class="flex items-center justify-between">
              <div class="w-9 h-9 rounded-lg" :style="cardStyle(item)"></div>
              <div v-if="item.is_flagship" class="flex gap-1.5">
                <span class="text-[10px] font-medium px-2 py-0.5 rounded-full bg-[#1a1b1e] text-white">旗舰 · 开源</span>
              </div>
            </div>
            <h3 class="mt-5 text-lg font-semibold tracking-tight">
              {{ item.title }}
              <span v-if="item.content?.chineseName" class="text-[#8b8e96]">{{ item.content.chineseName }}</span>
            </h3>
            <p class="mt-2 text-sm text-[#5b5e66] leading-relaxed line-clamp-3">{{ item.content?.desc || item.content?.tagline || '' }}</p>
            <div class="mt-auto pt-5 flex items-center justify-between">
              <span class="text-xs text-[#8b8e96]">{{ item.content?.tagline || '' }}</span>
              <span class="arrow-link">{{ item.website ? '访问官网' : '了解' }}</span>
            </div>
          </router-link>
        </div>

        <!-- Pagination -->
        <div v-if="total > pageSize" class="mt-10 flex items-center justify-center gap-2 text-sm">
          <button class="px-3 py-1.5 rounded-full border border-[#d0d3d9] hover:border-[#1a1b1e] disabled:opacity-40"
                  :disabled="page <= 1" @click="page--; loadItems()">上一页</button>
          <span class="text-[#8b8e96]">{{ page }} / {{ Math.ceil(total / pageSize) }}</span>
          <button class="px-3 py-1.5 rounded-full border border-[#d0d3d9] hover:border-[#1a1b1e] disabled:opacity-40"
                  :disabled="page >= Math.ceil(total / pageSize)" @click="page++; loadItems()">下一页</button>
        </div>
      </section>
    </main>
  </div>
</template>

<style>


.container-narrow { margin: 0 auto; max-width: 72rem; padding-left: 1.5rem; padding-right: 1.5rem; }
@media (min-width: 768px) { .container-narrow { padding-left: 2.5rem; padding-right: 2.5rem; } }
.container-wide { margin: 0 auto; max-width: 80rem; padding-left: 1.5rem; padding-right: 1.5rem; }
@media (min-width: 768px) { .container-wide { padding-left: 2.5rem; padding-right: 2.5rem; } }
.display-lg { font-size: clamp(2.25rem, 4vw + 0.5rem, 4.5rem); line-height: 1.05; letter-spacing: -0.045em; font-weight: 600; }
.bento { border-radius: 1.5rem; border: 1px solid oklch(0.92 0.005 260); background: #fff; padding: 1.5rem; transition: transform 250ms cubic-bezier(0.16, 1, 0.3, 1), box-shadow 250ms cubic-bezier(0.16, 1, 0.3, 1); }
@media (min-width: 768px) { .bento { padding: 2rem; } }
.bento-hover:hover { transform: translateY(-0.125rem); box-shadow: 0 10px 40px -10px rgba(10,10,10,0.12); }
.arrow-link { display: inline-flex; align-items: center; gap: 0.25rem; font-size: 0.875rem; font-weight: 500; color: oklch(0.18 0 0); }
.arrow-link::after { content: '→'; transition: transform 200ms cubic-bezier(0.16, 1, 0.3, 1); }
.group:hover .arrow-link::after { transform: translateX(4px); }
.reveal { opacity: 0; transform: translateY(16px); transition: opacity 700ms cubic-bezier(0.16, 1, 0.3, 1), transform 700ms cubic-bezier(0.16, 1, 0.3, 1); }
.reveal.visible { opacity: 1; transform: translateY(0); }
</style>
