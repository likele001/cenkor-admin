<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/lib/api'
import { hasPriceInfo, isFreePrice, yuanText, type AppPrice } from '@/lib/pricing'
import SiteHeader from '@/components/SiteHeader.vue'

interface StoreApp {
  id: number
  key: string
  app_key?: string
  name: string
  version: string
  description: string
  summary?: string
  icon: string
  category: string
  category_label?: string
  author: string
  tags?: string[]
  download_count: number
  installed?: boolean
  installed_version?: string | null
  has_update?: boolean
  updated_at?: string | null
  /** null = 免费 / 未定价 */
  price?: AppPrice | null
}

interface Facet { key: string; label: string; count: number }
interface Stats { apps: number; installed: number; upgradable: number; downloads: number }

const { t } = useI18n()

const apps = ref<StoreApp[]>([])
const facets = ref<Facet[]>([])
const stats = ref<Stats>({ apps: 0, installed: 0, upgradable: 0, downloads: 0 })
const total = ref(0)
const hasMore = ref(false)
const loading = ref(true)
const loadingMore = ref(false)
const error = ref('')

const keyword = ref('')
const q = ref('')
const activeCategory = ref('')
const sort = ref<'updated' | 'downloads' | 'name'>('updated')
const page = ref(1)
const PAGE_SIZE = 12

/** 开发者门户（应用发布入口） */
const DEV_PORTAL = 'https://dev.cenkor.cn'

let debounce: ReturnType<typeof setTimeout> | undefined

watch(keyword, (v) => {
  clearTimeout(debounce)
  debounce = setTimeout(() => { q.value = v.trim() }, 300)
})

watch([q, activeCategory, sort], () => {
  page.value = 1
  void load(false)
})

onBeforeUnmount(() => clearTimeout(debounce))

async function load(append: boolean) {
  if (append) loadingMore.value = true
  else loading.value = true
  error.value = ''
  try {
    const params: Record<string, string | number> = {
      page: page.value,
      page_size: PAGE_SIZE,
      sort: sort.value,
    }
    if (q.value) params.q = q.value
    if (activeCategory.value) params.category = activeCategory.value

    const { data } = await api.get('/api/v1/store/apps', { params })
    const items: StoreApp[] = Array.isArray(data?.items) ? data.items : []
    apps.value = append ? [...apps.value, ...items] : items
    if (Array.isArray(data?.facets)) facets.value = data.facets
    if (data?.stats) stats.value = data.stats
    total.value = Number(data?.total ?? items.length)
    hasMore.value = Boolean(data?.has_more)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('appCenter.loadError')
    if (!append) apps.value = []
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

onMounted(() => void load(false))

function loadMore() {
  page.value += 1
  void load(true)
}

function resetFilters() {
  keyword.value = ''
  q.value = ''
  activeCategory.value = ''
}

function categoryLabel(app: StoreApp): string {
  return app.category_label || app.category
}

function relTime(iso?: string | null): string {
  if (!iso) return ''
  const ts = new Date(iso).getTime()
  if (Number.isNaN(ts)) return ''
  const diff = Date.now() - ts
  const hour = 3600000
  const day = 86400000
  if (diff < hour) return t('appCenter.timeJustNow')
  if (diff < day) return t('appCenter.timeHours', { n: Math.floor(diff / hour) })
  if (diff < 30 * day) return t('appCenter.timeDays', { n: Math.floor(diff / day) })
  return new Date(iso).toLocaleDateString()
}
</script>

<template>
  <div class="min-h-screen bg-[#f8f9fb] font-['Plus_Jakarta_Sans',system-ui,sans-serif]">
    <SiteHeader />

    <!-- Hero -->
    <section class="bg-white border-b border-[#eef0f4]">
      <div class="container-wide py-12">
        <div class="max-w-3xl">
          <h1 class="text-3xl md:text-4xl font-semibold tracking-tight text-[#111827]">
            {{ t('appCenter.title') }}
          </h1>
          <p class="mt-3 text-[#6b6e76] leading-relaxed">{{ t('appCenter.subtitle') }}</p>
        </div>

        <div class="mt-8 grid grid-cols-2 md:grid-cols-4 gap-3 max-w-3xl">
          <div class="rounded-xl border border-[#eef0f4] bg-[#fbfcfd] px-4 py-3">
            <div class="text-xl font-semibold text-[#111827]">{{ stats.apps }}</div>
            <div class="mt-0.5 text-[11px] text-[#8b8e96]">{{ t('appCenter.statApps') }}</div>
          </div>
          <div class="rounded-xl border border-[#eef0f4] bg-[#fbfcfd] px-4 py-3">
            <div class="text-xl font-semibold text-[#111827]">{{ stats.installed }}</div>
            <div class="mt-0.5 text-[11px] text-[#8b8e96]">{{ t('appCenter.statInstalled') }}</div>
          </div>
          <div class="rounded-xl border border-[#eef0f4] bg-[#fbfcfd] px-4 py-3">
            <div class="text-xl font-semibold" :class="stats.upgradable ? 'text-[#d97706]' : 'text-[#111827]'">
              {{ stats.upgradable }}
            </div>
            <div class="mt-0.5 text-[11px] text-[#8b8e96]">{{ t('appCenter.statUpgradable') }}</div>
          </div>
          <div class="rounded-xl border border-[#eef0f4] bg-[#fbfcfd] px-4 py-3">
            <div class="text-xl font-semibold text-[#111827]">{{ stats.downloads }}</div>
            <div class="mt-0.5 text-[11px] text-[#8b8e96]">{{ t('appCenter.statDownloads') }}</div>
          </div>
        </div>
      </div>
    </section>

    <section class="container-wide py-8">
      <!-- 工具栏 -->
      <div class="flex flex-col gap-4">
        <div class="flex flex-col sm:flex-row gap-3 sm:items-center">
          <div class="relative flex-1 max-w-md">
            <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9ca3af]" viewBox="0 0 20 20" fill="none">
              <circle cx="9" cy="9" r="6" stroke="currentColor" stroke-width="1.6" />
              <path d="M13.5 13.5 17 17" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
            </svg>
            <input
              v-model="keyword"
              type="text"
              :placeholder="t('appCenter.searchPlaceholder')"
              class="w-full pl-9 pr-9 py-2.5 text-sm rounded-lg border border-[#e5e7eb] bg-white text-[#111827] placeholder:text-[#9ca3af] focus:outline-none focus:border-[#4f46e5] focus:ring-2 focus:ring-[#4f46e5]/10 transition-colors"
            />
            <button
              v-if="keyword"
              class="absolute right-2.5 top-1/2 -translate-y-1/2 w-5 h-5 rounded-full text-[#9ca3af] hover:text-[#4b5563] hover:bg-[#f3f4f6] transition-colors"
              @click="keyword = ''"
              :aria-label="t('appCenter.clearSearch')"
            >×</button>
          </div>

          <div class="flex items-center gap-2 sm:ml-auto">
            <span class="text-xs text-[#8b8e96] shrink-0">{{ t('appCenter.sortLabel') }}</span>
            <select
              v-model="sort"
              class="text-sm rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-[#374151] focus:outline-none focus:border-[#4f46e5] transition-colors"
            >
              <option value="updated">{{ t('appCenter.sortUpdated') }}</option>
              <option value="downloads">{{ t('appCenter.sortDownloads') }}</option>
              <option value="name">{{ t('appCenter.sortName') }}</option>
            </select>
          </div>
        </div>

        <div class="flex flex-wrap gap-2">
          <button
            class="px-3 py-1.5 text-xs rounded-full border transition-colors"
            :class="!activeCategory
              ? 'bg-[#111827] text-white border-[#111827]'
              : 'bg-white text-[#6b6e76] border-[#e5e7eb] hover:border-[#9ca3af]'"
            @click="activeCategory = ''"
          >{{ t('appCenter.all') }} ({{ stats.apps }})</button>
          <button
            v-for="f in facets"
            :key="f.key"
            class="px-3 py-1.5 text-xs rounded-full border transition-colors"
            :class="activeCategory === f.key
              ? 'bg-[#111827] text-white border-[#111827]'
              : 'bg-white text-[#6b6e76] border-[#e5e7eb] hover:border-[#9ca3af]'"
            @click="activeCategory = f.key"
          >{{ f.label }} ({{ f.count }})</button>
        </div>
      </div>

      <!-- 骨架屏 -->
      <div v-if="loading" class="mt-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <div v-for="i in 6" :key="i" class="bg-white rounded-xl border border-[#e5e7eb] p-5 animate-pulse">
          <div class="flex items-start gap-3">
            <div class="w-10 h-10 rounded-lg bg-[#f3f4f6]"></div>
            <div class="flex-1 space-y-2 pt-1">
              <div class="h-3 w-1/2 rounded bg-[#f3f4f6]"></div>
              <div class="h-2.5 w-1/4 rounded bg-[#f3f4f6]"></div>
            </div>
          </div>
          <div class="mt-4 space-y-2">
            <div class="h-2.5 w-full rounded bg-[#f3f4f6]"></div>
            <div class="h-2.5 w-4/5 rounded bg-[#f3f4f6]"></div>
          </div>
        </div>
      </div>

      <div v-else-if="error" class="mt-10 rounded-xl border border-red-200 bg-red-50 px-5 py-4">
        <p class="text-sm text-red-700">{{ error }}</p>
        <button
          class="mt-3 px-3 py-1.5 text-xs rounded-lg border border-red-300 text-red-700 hover:bg-red-100 transition-colors"
          @click="load(false)"
        >{{ t('appCenter.retry') }}</button>
      </div>

      <div v-else-if="apps.length === 0" class="mt-14 text-center">
        <div class="text-3xl">🔍</div>
        <p class="mt-3 text-sm text-[#6b6e76]">{{ t('appCenter.empty') }}</p>
        <button
          v-if="q || activeCategory"
          class="mt-4 px-4 py-2 text-xs rounded-lg border border-[#e5e7eb] text-[#374151] bg-white hover:border-[#9ca3af] transition-colors"
          @click="resetFilters"
        >{{ t('appCenter.clearFilters') }}</button>
      </div>

      <template v-else>
        <p class="mt-6 text-xs text-[#8b8e96]">{{ t('appCenter.resultCount', { n: total }) }}</p>

        <div class="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <RouterLink
            v-for="a in apps"
            :key="a.key"
            :to="`/apps/${a.key}`"
            class="group bg-white rounded-xl border border-[#e5e7eb] p-5 flex flex-col hover:border-[#4f46e5]/40 hover:shadow-[0_4px_16px_rgba(17,24,39,0.06)] transition-all"
          >
            <div class="flex items-start gap-3">
              <span class="w-10 h-10 shrink-0 rounded-lg bg-[#f8f9fb] border border-[#eef0f4] flex items-center justify-center text-xl">
                {{ a.icon }}
              </span>
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                  <h3 class="font-semibold text-[#111827] truncate group-hover:text-[#4f46e5] transition-colors">
                    {{ a.name }}
                  </h3>
                  <code class="text-[10px] text-[#9ca3af]">v{{ a.version }}</code>
                  <span
                    v-if="a.installed && a.has_update"
                    class="px-1.5 py-0.5 text-[10px] rounded-full bg-[#fef3c7] text-[#b45309]"
                  >{{ t('appCenter.upgradable') }}</span>
                  <span
                    v-else-if="a.installed"
                    class="px-1.5 py-0.5 text-[10px] rounded-full bg-[#ecfdf5] text-[#047857]"
                  >{{ t('appCenter.installed') }}</span>
                </div>
                <span class="inline-block mt-1.5 px-2 py-0.5 text-[10px] rounded-full bg-[#eef2ff] text-[#4f46e5]">
                  {{ categoryLabel(a) }}
                </span>
              </div>
            </div>

            <p class="mt-3 text-sm text-[#6b6e76] leading-relaxed line-clamp-3 flex-1">
              {{ a.summary || a.description }}
            </p>

            <div v-if="a.tags && a.tags.length" class="mt-3 flex flex-wrap gap-1.5">
              <span
                v-for="tg in a.tags.slice(0, 3)"
                :key="tg"
                class="px-1.5 py-0.5 text-[10px] rounded bg-[#f8f9fb] border border-[#eef0f4] text-[#6b6e76]"
              >{{ tg }}</span>
            </div>

            <!-- 价格：免费 / 售价（含划线原价、折扣标、促销标）
                 price 为 undefined = 后端未提供价格信息（纯开源部署 / 旧后端）→ 整行不渲染 -->
            <div v-if="hasPriceInfo(a.price)" class="mt-4 flex items-baseline gap-2 flex-wrap">
              <template v-if="isFreePrice(a.price)">
                <span class="text-base font-semibold text-[#047857]">{{ t('price.free') }}</span>
              </template>
              <template v-else-if="a.price">
                <span class="text-base font-semibold text-[#111827]">¥{{ yuanText(a.price.unit_price) }}</span>
                <span
                  v-if="a.price.is_discounted"
                  class="text-xs text-[#9ca3af] line-through"
                >¥{{ yuanText(a.price.list_price) }}</span>
                <span
                  v-if="a.price.is_discounted"
                  class="px-1.5 py-0.5 text-[10px] rounded bg-[#fee2e2] text-[#b91c1c]"
                >{{ a.price.discount_label }}</span>
                <span
                  v-if="a.price.promo_active"
                  class="px-1.5 py-0.5 text-[10px] rounded bg-[#fef3c7] text-[#b45309]"
                >{{ t('price.promo') }}</span>
              </template>
            </div>

            <div class="mt-4 pt-3 border-t border-[#f3f4f6] flex items-center justify-between text-[11px] text-[#9ca3af]">
              <span class="truncate">{{ a.author }}</span>
              <span class="flex items-center gap-3 shrink-0">
                <span>{{ t('appCenter.downloadsShort', { n: a.download_count }) }}</span>
                <span v-if="a.updated_at">{{ relTime(a.updated_at) }}</span>
              </span>
            </div>
          </RouterLink>
        </div>

        <div v-if="hasMore" class="mt-8 flex justify-center">
          <button
            class="px-5 py-2.5 text-sm rounded-lg border border-[#e5e7eb] bg-white text-[#374151] hover:border-[#9ca3af] disabled:opacity-60 transition-colors"
            :disabled="loadingMore"
            @click="loadMore"
          >{{ loadingMore ? t('appCenter.loading') : t('appCenter.loadMore') }}</button>
        </div>
      </template>

      <!-- 开发者入口 -->
      <div class="mt-14 bg-white rounded-xl border border-[#e5e7eb] p-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h2 class="font-semibold text-[#111827]">{{ t('appCenter.devTitle') }}</h2>
          <p class="mt-1 text-sm text-[#6b6e76]">{{ t('appCenter.devSubtitle') }}</p>
        </div>
        <div class="flex gap-3 shrink-0">
          <a
            :href="`${DEV_PORTAL}/docs`"
            target="_blank"
            rel="noopener"
            class="px-4 py-2 text-sm rounded-lg bg-[#111827] text-white hover:bg-[#374151] transition-colors"
          >{{ t('appCenter.devDocs') }}</a>
          <a
            :href="`${DEV_PORTAL}/dashboard/submit`"
            target="_blank"
            rel="noopener"
            class="px-4 py-2 text-sm rounded-lg border border-[#e5e7eb] text-[#374151] hover:border-[#9ca3af] transition-colors"
          >{{ t('appCenter.devSubmit') }}</a>
        </div>
      </div>
    </section>
  </div>
</template>
