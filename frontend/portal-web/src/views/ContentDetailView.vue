<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api } from '@/lib/api'
import SiteHeader from '@/components/SiteHeader.vue'

interface ProductItem {
  id: number; slug: string; title: string
  content: { tagline: string; line: string; stack: string; desc: string; features: string[]; chineseName: string }
  custom_fields: Record<string, any>
  status: string; sort: number; view_count: number
  is_flagship?: boolean; is_open_source?: boolean
  github?: string; demo?: string; website?: string; license?: string
}

const route = useRoute()
const { t } = useI18n()

const ctKey = computed(() => (route.params.ct as string) || 'product')
const entry = ref<ProductItem | null>(null)
const loading = ref(true)
const errorMsg = ref('')
const relatedProducts = ref<ProductItem[]>([])

const lineMeta: Record<string, { label: string; hue: number }> = {
  enterprise: { label: '企业级后台', hue: 250 },
  ai: { label: 'AI 智能化', hue: 295 },
  manufacturing: { label: '智能制造', hue: 165 },
}

const meta = computed(() => lineMeta[entry.value?.content?.line || ''] || lineMeta.enterprise)

async function loadEntry() {
  loading.value = true; errorMsg.value = ''
  const idOrSlug = route.params.id
  try {
    const { data } = await api.get(`/api/v1/public/site/${ctKey.value}/${idOrSlug}`)
    entry.value = data
    if (data?.content?.line && ctKey.value === 'product') {
      const { data: list } = await api.get(`/api/v1/public/site/product?page=1&page_size=20`)
      relatedProducts.value = (list.items || []).filter((p: ProductItem) =>
        p.content?.line === data.content.line && p.id !== data.id
      )
    }
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e.message || '加载失败'
  } finally { loading.value = false }
}

watch(() => route.params.id, () => loadEntry())
watch(ctKey, () => loadEntry())

onMounted(loadEntry)

const flags = computed(() => {
  const arr: string[] = []
  if (entry.value?.is_flagship) arr.push('旗舰产品')
  if (entry.value?.is_open_source) arr.push('开源')
  if (entry.value?.license) arr.push(entry.value.license)
  return arr
})

const hue = computed(() => meta.value.hue)
</script>

<template>
  <div class="min-h-screen bg-[#f8f9fb] font-['Plus_Jakarta_Sans',system-ui,sans-serif]">
    <SiteHeader />

    <div v-if="loading" class="h-64 flex items-center justify-center text-[#8b8e96]">{{ t('common.loading') }}</div>
    <div v-else-if="errorMsg" class="h-64 flex items-center justify-center text-red-600">{{ errorMsg }}</div>

    <template v-else-if="entry">
      <!-- Breadcrumb -->
      <nav class="container-wide pt-20 md:pt-24 pb-4 text-sm text-[#8b8e96]">
        <router-link to="/" class="hover:text-[#1a1b1e]">首页</router-link>
        <span class="mx-2">/</span>
        <router-link to="/products" class="hover:text-[#1a1b1e]">产品中心</router-link>
        <span class="mx-2">/</span>
        <router-link :to="`/list/${ctKey}`" class="hover:text-[#1a1b1e]">{{ meta.label }}</router-link>
        <span class="mx-2">/</span>
        <span class="text-[#1a1b1e]">{{ entry.title }}</span>
      </nav>

      <!-- Detail -->
      <section class="container-wide pb-24 md:pb-32">
        <article class="bento !p-8 md:!p-12 grid md:grid-cols-5 gap-8 md:gap-12 items-start">
          <!-- Left: gradient hero -->
          <div class="md:col-span-2 aspect-[4/3] rounded-2xl relative overflow-hidden"
               :style="{ background: `linear-gradient(135deg, oklch(0.62 0.165 ${hue}) 0%, oklch(0.45 0.18 ${hue}) 100%)` }">
            <div class="absolute inset-0 opacity-10"
                 style="background-image:radial-gradient(#fff 1px, transparent 1px); background-size:18px 18px;"></div>
            <div class="absolute bottom-5 left-5 right-5 text-white">
              <div class="text-xs uppercase tracking-widest opacity-80">{{ entry.content?.stack || '' }}</div>
              <div class="text-2xl font-semibold mt-1">{{ entry.title }}</div>
            </div>
          </div>
          <!-- Right: details -->
          <div class="md:col-span-3">
            <div class="flex flex-wrap gap-2">
              <span v-for="f in flags" :key="f" class="tag">{{ f }}</span>
            </div>
            <h1 class="display-lg mt-4">
              {{ entry.title }}
              <span v-if="entry.content?.chineseName" class="text-[#8b8e96] text-2xl"> {{ entry.content.chineseName }}</span>
            </h1>
            <p class="mt-2 text-lg text-[#6b6e76]">{{ entry.content?.tagline || '' }}</p>
            <p class="mt-6 text-[#5b5e66] leading-relaxed text-lg" style="max-width:65ch">{{ entry.content?.desc || '' }}</p>

            <!-- Features -->
            <ul v-if="entry.content?.features?.length" class="mt-8 grid sm:grid-cols-2 gap-x-6 gap-y-3">
              <li v-for="(f, i) in entry.content.features" :key="i" class="flex gap-2.5 text-sm text-[#3b3d44]">
                <span class="text-[#10b981] mt-0.5">✓</span>
                <span>{{ f }}</span>
              </li>
            </ul>

            <!-- Action buttons -->
            <div class="mt-8 flex flex-wrap gap-3">
              <a v-if="entry.website" :href="entry.website" target="_blank" rel="noopener" class="btn-primary">访问官网</a>
              <a v-if="entry.demo" :href="entry.demo" target="_blank" rel="noopener" class="inline-flex items-center justify-center gap-2 rounded-full px-5 py-2.5 text-sm font-medium text-white"
                 :style="{ background: `linear-gradient(135deg, oklch(0.62 0.195 295), oklch(0.65 0.22 330))` }">立即体验</a>
              <a v-if="entry.github" :href="entry.github" target="_blank" rel="noopener" class="btn-outline">GitHub</a>
              <a href="https://www.cenkor.cn/contact.html" class="btn-ghost">联系咨询</a>
            </div>
          </div>
        </article>

        <!-- Related products (same business line) -->
        <section v-if="relatedProducts.length" class="mt-16">
          <h2 class="display-sm mb-6">同业务线产品</h2>
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            <router-link
              v-for="p in relatedProducts" :key="p.id"
              :to="`/list/product/${p.id}`"
              class="group bento bento-hover flex flex-col min-h-[180px]"
            >
              <div class="w-9 h-9 rounded-lg mb-4"
                   :style="{ background: `oklch(0.62 0.165 ${hue})` }"></div>
              <h3 class="text-lg font-semibold">{{ p.title }}</h3>
              <p class="mt-2 text-sm text-[#5b5e66] line-clamp-2">{{ p.content?.tagline || p.content?.desc || '' }}</p>
              <span class="mt-auto pt-4 arrow-link">了解</span>
            </router-link>
          </div>
        </section>
      </section>
    </template>

    <!-- Footer for empty state -->
    <footer v-if="!entry && !loading" class="border-t border-[#e5e7eb] bg-[#f2f3f6]">
      <div class="container-wide py-16 text-center text-[#8b8e96] text-sm">内容未找到</div>
    </footer>
  </div>
</template>

<style>


.container-wide { margin: 0 auto; max-width: 80rem; padding-left: 1.5rem; padding-right: 1.5rem; }
@media (min-width: 768px) { .container-wide { padding-left: 2.5rem; padding-right: 2.5rem; } }
.display-lg { font-size: clamp(2.25rem, 4vw + 0.5rem, 4.5rem); line-height: 1.05; letter-spacing: -0.045em; font-weight: 600; }
.display-sm { font-size: clamp(1.375rem, 1.5vw + 0.5rem, 2rem); line-height: 1.2; letter-spacing: -0.03em; font-weight: 600; }
.bento { border-radius: 1.5rem; border: 1px solid oklch(0.92 0.005 260); background: #fff; padding: 1.5rem; transition: transform 250ms cubic-bezier(0.16, 1, 0.3, 1), box-shadow 250ms cubic-bezier(0.16, 1, 0.3, 1); }
@media (min-width: 768px) { .bento { padding: 2rem; } }
.bento-hover:hover { transform: translateY(-0.125rem); box-shadow: 0 10px 40px -10px rgba(10,10,10,0.12); }
.btn-primary { display: inline-flex; align-items: center; justify-content: center; gap: 0.5rem; border-radius: 9999px; background: oklch(0.18 0 0); padding: 0.75rem 1.5rem; font-size: 0.875rem; font-weight: 500; color: #fff; transition: transform 200ms cubic-bezier(0.16, 1, 0.3, 1), background 200ms ease-out; }
.btn-primary:hover { background: oklch(0.28 0.005 260); }
.btn-ghost { display: inline-flex; align-items: center; justify-content: center; gap: 0.5rem; border-radius: 9999px; padding: 0.75rem 1.5rem; font-size: 0.875rem; font-weight: 500; color: oklch(0.18 0 0); transition: color 200ms ease-out; }
.btn-ghost:hover { color: oklch(0.40 0.008 260); }
.btn-outline { display: inline-flex; align-items: center; justify-content: center; gap: 0.5rem; border-radius: 9999px; border: 1px solid oklch(0.83 0.005 260); background: #fff; padding: 0.625rem 1.25rem; font-size: 0.875rem; font-weight: 500; color: oklch(0.18 0 0); transition: all 200ms ease-out; }
.btn-outline:hover { border-color: oklch(0.18 0 0); background: oklch(0.985 0.003 250); }
.tag { display: inline-flex; align-items: center; gap: 0.375rem; border-radius: 9999px; background: oklch(0.97 0.003 260); padding: 0.25rem 0.625rem; font-size: 0.75rem; font-weight: 500; color: oklch(0.40 0.008 260); }
.arrow-link { display: inline-flex; align-items: center; gap: 0.25rem; font-size: 0.875rem; font-weight: 500; color: oklch(0.18 0 0); }
.arrow-link::after { content: '→'; transition: transform 200ms cubic-bezier(0.16, 1, 0.3, 1); }
.group:hover .arrow-link::after { transform: translateX(4px); }
</style>
