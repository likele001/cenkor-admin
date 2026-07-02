<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import SiteHeader from '@/components/SiteHeader.vue'

interface Product {
  id: number; key: string; name: string; chineseName?: string; tagline: string; line: string
  stack: string; desc: string; features: string[]
  isFlagship: boolean; isOpenSource: boolean
  github?: string; demo?: string; website?: string; license?: string
}

interface CaseItem { industry: string; name: string; desc: string; tag: string; href?: string }

interface BusinessLine { id: string; title: string; titleEn: string; desc: string; products: { id: number; name: string }[] }

const { t } = useI18n()
const siteConfig = ref<Record<string, string>>({})
const products = ref<Product[]>([])
const cases = ref<CaseItem[]>([])
const loading = ref(true)
const auth = useAuthStore()

const brand = ref({ name: '辰科', nameEn: 'Cenkor', tagline: '', description: '' })
const lines = ref<BusinessLine[]>([])

onMounted(async () => {
  try {
    const { data } = await api.get('/api/v1/public/site')
    const sc = data.site_config || {}
    siteConfig.value = sc
    brand.value = {
      name: sc['brand.name'] || '辰科',
      nameEn: sc['brand.name_en'] || 'Cenkor',
      tagline: sc['brand.tagline'] || '让企业软件 更简单 更智能',
      description: sc['brand.description'] || '',
    }
    products.value = (data.products || []).map((p: any) => ({
      ...p,
      isFlagship: !!p.isFlagship,
      isOpenSource: !!p.isOpenSource,
      features: p.features || [],
    }))
    cases.value = data.cases || []
    const ids = ['enterprise', 'ai', 'manufacturing']
    const labels: Record<string, { title: string; titleEn: string; desc: string }> = {
      enterprise: { title: '企业级后台', titleEn: 'Enterprise Backoffice', desc: '多租户底座、RBAC 权限、应用中心。私有化部署，按需启用业务模块。' },
      ai: { title: 'AI 智能化', titleEn: 'AI & Intelligence', desc: 'AI 自动运营、LLM 聚合网关、商用计费一站式。' },
      manufacturing: { title: '智能制造', titleEn: 'Smart Manufacturing', desc: '轻量化 MES：扫码报工、计件工资、扫码溯源。中小加工厂开箱即用。' },
    }
    lines.value = ids.map(id => {
      const prods = (data.products || []).filter((p: Product) => p.line === id)
      return {
        id,
        ...labels[id],
        products: prods.map((p: Product) => ({ id: p.id, name: p.name + (p.chineseName ? ` ${p.chineseName}` : '') })),
      }
    })
  } catch {
    // use defaults
  } finally {
    loading.value = false
  }
})

function lineGradient(line: string): string {
  const colors: Record<string, string> = {
    enterprise: 'linear-gradient(135deg, #6366f1, #4f46e5)',
    ai: 'linear-gradient(135deg, #a855f7, #d946ef)',
    manufacturing: 'linear-gradient(135deg, #10b981, #0d9488)',
  }
  return colors[line] || 'linear-gradient(135deg, #6366f1, #4f46e5)'
}

const flagshipProduct = (() => {
  const pf = products.value.find(p => p.isFlagship)
  return pf
})()

const enterpriseLine = (() => lines.value.find(l => l.id === 'enterprise'))()
const aiLine = (() => lines.value.find(l => l.id === 'ai'))()
const mfgLine = (() => lines.value.find(l => l.id === 'manufacturing'))()
</script>

<template>
  <div class="min-h-screen bg-[#f8f9fb] font-['Plus_Jakarta_Sans',system-ui,sans-serif]">
    <SiteHeader />

    <!-- Hero -->
    <section class="container-narrow pt-20 md:pt-32 pb-20 md:pb-28 text-center">
      <h1 class="display-xl max-w-4xl mx-auto">
        企业软件，<br>
        <span style="color: oklch(0.62 0.165 165);">更简单</span> · <span style="color: oklch(0.62 0.195 295);">更智能</span>。
      </h1>
      <p class="mt-6 md:mt-8 text-lg md:text-xl text-[#5b5e66] max-w-2xl mx-auto">
        {{ brand.description || '辰科为企业提供可私有化、可扩展的产品矩阵——多租户后台、AI 自动运营、LLM 聚合网关、轻量化 MES，一套底座，按需启用。' }}
      </p>
      <div class="mt-8 md:mt-10 flex flex-col sm:flex-row gap-3 justify-center">
        <router-link to="/products" class="btn-primary !inline-flex">浏览产品矩阵</router-link>
        <a href="https://www.cenkor.cn/contact.html" class="btn-ghost !inline-flex">联系咨询</a>
      </div>
    </section>

    <!-- 三大业务线 -->
    <section class="container-wide pb-20 md:pb-28">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-5">
        <div v-for="line in lines" :key="line.id" class="group bento bento-hover flex flex-col min-h-[240px]">
          <div class="w-11 h-11 rounded-xl mb-5" :style="{ background: lineGradient(line.id) }"></div>
          <h3 class="display-sm">{{ line.title }}</h3>
          <p class="mt-3 text-[#5b5e66] leading-relaxed">{{ line.desc }}</p>
          <div class="mt-auto pt-6 flex flex-wrap gap-1.5">
            <router-link v-for="p in line.products" :key="p.id" :to="`/list/product/${p.id}`" class="tag hover:bg-[#e5e7eb] transition-colors">{{ p.name }}</router-link>
          </div>
        </div>
      </div>
    </section>

    <!-- PlantFlow 旗舰 -->
    <section v-if="products.length" class="container-wide pb-20 md:pb-28">
      <div class="group rounded-3xl overflow-hidden"
           style="background: linear-gradient(135deg, oklch(0.28 0.06 285) 0%, oklch(0.18 0.08 265) 100%);">
        <div class="grid md:grid-cols-2 gap-8 p-8 md:p-12 items-center">
          <div class="text-white">
            <div class="flex items-center gap-2 mb-5">
              <span class="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-white/10 text-white/90">
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                Open Source · MIT
              </span>
              <span class="text-xs font-medium px-2.5 py-1 rounded-full bg-white/10 text-white/90">旗舰</span>
            </div>
            <h2 class="display-md">PlantFlow <span class="text-white/50">厂流</span></h2>
            <p class="mt-4 text-white/70 text-base md:text-lg leading-relaxed">
              可视化工作流 + AI 知识库，开箱即用。n8n 的编排能力 + Dify 的 AI 应用能力，MIT 协议开源。
            </p>
            <div class="mt-6 flex flex-wrap items-center gap-3">
              <router-link to="/products" class="inline-flex items-center px-5 py-2.5 rounded-full bg-white text-[#1a1b1e] text-sm font-medium hover:bg-[#f0f1f3] transition">立即体验 Demo</router-link>
              <a href="https://github.com/likele001/PlantFlow" class="arrow-link text-white">GitHub 仓库</a>
            </div>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div class="rounded-xl bg-white/5 border border-white/10 p-4 text-white">
              <div class="text-sm font-medium">🔀 编排</div>
              <div class="mt-1 text-xs text-white/50">类 n8n 拖拽</div>
            </div>
            <div class="rounded-xl bg-white/5 border border-white/10 p-4 text-white">
              <div class="text-sm font-medium">📚 RAG</div>
              <div class="mt-1 text-xs text-white/50">知识库检索</div>
            </div>
            <div class="rounded-xl bg-white/5 border border-white/10 p-4 text-white">
              <div class="text-sm font-medium">💬 对话</div>
              <div class="mt-1 text-xs text-white/50">类 Dify</div>
            </div>
            <div class="rounded-xl bg-white/5 border border-white/10 p-4 text-white">
              <div class="text-sm font-medium">🤖 Agent</div>
              <div class="mt-1 text-xs text-white/50">工具调用</div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 客户案例 -->
    <section v-if="cases.length" class="container-wide pb-20 md:pb-28">
      <h2 class="display-md mb-8">客户案例</h2>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-5">
        <div v-for="(c, i) in cases" :key="i" class="bento">
          <div class="text-xs font-medium text-[#8b8e96] uppercase tracking-widest mb-2">{{ c.industry }}</div>
          <h3 class="text-lg font-semibold mb-2">{{ c.name }}</h3>
          <p class="text-sm text-[#5b5e66] leading-relaxed">{{ c.desc }}</p>
          <div class="mt-4 flex items-center gap-2">
            <span class="tag">{{ c.tag }}</span>
            <a v-if="c.href" :href="c.href" class="arrow-link text-sm ml-auto">查看详情</a>
          </div>
        </div>
      </div>
    </section>

    <!-- 价值主张 -->
    <section class="container-wide pb-20 md:pb-28">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-5">
        <div class="bento">
          <h3 class="display-sm">模块化</h3>
          <p class="mt-3 text-[#5b5e66] leading-relaxed">通用能力抽成可复用模块，让交付更快、运维更轻。</p>
        </div>
        <div class="bento">
          <h3 class="display-sm">可私有化</h3>
          <p class="mt-3 text-[#5b5e66] leading-relaxed">全部支持内网部署，数据自主可控，适配等保合规。</p>
        </div>
        <div class="bento">
          <h3 class="display-sm">AI 落地</h3>
          <p class="mt-3 text-[#5b5e66] leading-relaxed">AI 能力深度集成到产品中，自动化、智能化、产线化。</p>
        </div>
      </div>
    </section>

    <!-- CTA -->
    <section class="container-wide pb-24 md:pb-32">
      <div class="bento !p-12 md:!p-20 text-center"
           style="background: linear-gradient(135deg, oklch(0.32 0.04 280) 0%, oklch(0.22 0.06 260) 100%); border-color: oklch(0.40 0.04 280); color: white;">
        <h2 class="display-md">准备好开始了吗？</h2>
        <p class="mt-4 text-[#b0b3b9] max-w-xl mx-auto">无论是产品咨询、技术对接还是私有化部署，我们都能提供支持。</p>
        <div class="mt-8 flex flex-col sm:flex-row gap-3 justify-center">
          <a href="https://www.cenkor.cn/contact.html" class="inline-flex items-center justify-center px-6 py-3 rounded-full bg-white text-[#1a1b1e] text-sm font-medium hover:bg-[#f0f1f3] transition">联系销售</a>
          <router-link to="/products" class="inline-flex items-center justify-center px-6 py-3 rounded-full text-white text-sm font-medium hover:text-[#d0d3d9] transition">先看看产品</router-link>
        </div>
      </div>
    </section>

    <!-- Footer -->
    <footer class="border-t border-[#e5e7eb] bg-[#f2f3f6]">
      <div class="container-wide py-16">
        <div class="grid grid-cols-2 md:grid-cols-5 gap-8">
          <div class="col-span-2">
            <div class="flex items-center gap-2">
              <span class="text-base font-semibold">{{ brand.name }} {{ brand.nameEn }}</span>
            </div>
            <p class="mt-4 text-sm text-[#6b6e76] max-w-xs">{{ brand.description }}</p>
          </div>
          <div>
            <div class="text-xs font-medium text-[#8b8e96] uppercase tracking-widest mb-4">产品</div>
            <ul class="space-y-2 text-sm text-[#5b5e66]">
              <li><a href="https://www.cenkor.cn/solutions/enterprise.html" class="hover:text-[#1a1b1e]">企业级后台</a></li>
              <li><a href="https://www.cenkor.cn/solutions/ai.html" class="hover:text-[#1a1b1e]">AI 智能化</a></li>
              <li><a href="https://www.cenkor.cn/solutions/manufacturing.html" class="hover:text-[#1a1b1e]">智能制造</a></li>
              <li><router-link to="/products" class="hover:text-[#1a1b1e]">全部产品</router-link></li>
            </ul>
          </div>
          <div>
            <div class="text-xs font-medium text-[#8b8e96] uppercase tracking-widest mb-4">公司</div>
            <ul class="space-y-2 text-sm text-[#5b5e66]">
              <li><a href="https://www.cenkor.cn/about.html" class="hover:text-[#1a1b1e]">关于辰科</a></li>
              <li><a href="https://www.cenkor.cn/cases.html" class="hover:text-[#1a1b1e]">客户案例</a></li>
              <li><a href="https://www.cenkor.cn/contact.html" class="hover:text-[#1a1b1e]">联系咨询</a></li>
            </ul>
          </div>
          <div>
            <div class="text-xs font-medium text-[#8b8e96] uppercase tracking-widest mb-4">联系</div>
            <ul class="space-y-2 text-sm text-[#5b5e66]">
              <li>cenkor.cn</li>
              <li>contact@cenkor.cn</li>
            </ul>
          </div>
        </div>
        <div class="mt-12 pt-6 border-t border-[#d0d3d9] flex flex-col md:flex-row justify-between gap-3 text-xs text-[#8b8e96]">
          <div>© {{ new Date().getFullYear() }} {{ brand.name }}（{{ brand.nameEn }}）. All rights reserved.</div>
        </div>
      </div>
    </footer>
  </div>
</template>

<style>


.container-narrow { margin: 0 auto; max-width: 72rem; padding-left: 1.5rem; padding-right: 1.5rem; }
@media (min-width: 768px) { .container-narrow { padding-left: 2.5rem; padding-right: 2.5rem; } }

.container-wide { margin: 0 auto; max-width: 80rem; padding-left: 1.5rem; padding-right: 1.5rem; }
@media (min-width: 768px) { .container-wide { padding-left: 2.5rem; padding-right: 2.5rem; } }

.display-xl { font-size: clamp(2.75rem, 5.5vw + 0.5rem, 5.5rem); line-height: 1.02; letter-spacing: -0.05em; font-weight: 600; }
.display-md { font-size: clamp(1.75rem, 2.5vw + 0.5rem, 3rem); line-height: 1.1; letter-spacing: -0.035em; font-weight: 600; }
.display-sm { font-size: clamp(1.375rem, 1.5vw + 0.5rem, 2rem); line-height: 1.2; letter-spacing: -0.03em; font-weight: 600; }

.bento { border-radius: 1.5rem; border: 1px solid oklch(0.92 0.005 260); background: #fff; padding: 1.5rem; transition: transform 250ms cubic-bezier(0.16, 1, 0.3, 1), box-shadow 250ms cubic-bezier(0.16, 1, 0.3, 1); }
@media (min-width: 768px) { .bento { padding: 2rem; } }
.bento-hover:hover { transform: translateY(-0.125rem); box-shadow: 0 10px 40px -10px rgba(10,10,10,0.12); }

.btn-primary { display: inline-flex; align-items: center; justify-content: center; gap: 0.5rem; border-radius: 9999px; background: oklch(0.18 0 0); padding: 0.75rem 1.5rem; font-size: 0.875rem; font-weight: 500; color: #fff; transition: transform 200ms cubic-bezier(0.16, 1, 0.3, 1), background 200ms ease-out; }
.btn-primary:hover { background: oklch(0.28 0.005 260); }
.btn-primary:active { transform: scale(0.97); }

.btn-ghost { display: inline-flex; align-items: center; justify-content: center; gap: 0.5rem; border-radius: 9999px; padding: 0.75rem 1.5rem; font-size: 0.875rem; font-weight: 500; color: oklch(0.18 0 0); transition: color 200ms ease-out; }
.btn-ghost:hover { color: oklch(0.40 0.008 260); }

.tag { display: inline-flex; align-items: center; gap: 0.375rem; border-radius: 9999px; background: oklch(0.97 0.003 260); padding: 0.25rem 0.625rem; font-size: 0.75rem; font-weight: 500; color: oklch(0.40 0.008 260); }

.arrow-link { display: inline-flex; align-items: center; gap: 0.25rem; font-size: 0.875rem; font-weight: 500; color: oklch(0.18 0 0); }
.arrow-link::after { content: '→'; transition: transform 200ms cubic-bezier(0.16, 1, 0.3, 1); }
.group:hover .arrow-link::after { transform: translateX(4px); }
</style>
