<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
/**
 * AI 落地页 / 官网子站。
 *
 * 定位：**一句话 → 一个能投放、能留资的页面**，不是又一个可视化编辑器。
 *
 * 三个刻意的设计：
 *   1. 生成很慢（单页约 50 秒，子站 1~3 分钟），所以按钮上直接显示计时。
 *      只转圈不给秒数的等待，用户 20 秒就会以为挂了并点第二次。
 *   2. 生成与落库分开：先给「区块清单」让人判断内容对不对，再决定保存。
 *      直接落库的结果是每次重试都在库里留一版垃圾。
 *   3. 预览走 `/lp/{key}?preview=1`，跟线上同一套渲染。用另一套预览
 *      逻辑的话，预览好看、上线变形，是最典型的交付事故。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '@/lib/api'

interface Block {
  type: string
  data: Record<string, any>
}

interface PageDraft {
  key: string
  name: string
  title: string
  seo: { title?: string; description?: string; keywords?: string; accent?: string }
  blocks: Block[]
}

interface Draft {
  brand: string
  accent: string
  form: { key: string; title: string; success_message: string; fields: any[] }
  pages: PageDraft[]
  dropped: string[]
  kb_used: number
  mode: string
  generation_id?: number
}

interface PageRow {
  id: number
  key: string
  title: string
  kind: string
  site_key: string | null
  status: string
  url: string
  block_count: number
  form_keys: string[]
  submissions: number
  published_at: string | null
  updated_at: string | null
}

const BLOCK_LABEL: Record<string, string> = {
  navbar: '导航', hero: '主视觉', features: '卖点', steps: '步骤',
  stats: '数据', testimonial: '客户评价', faq: '常见问题', cta: '行动号召',
  form: '留资表单', footer: '页脚',
}

const brief = ref('')
const mode = ref<'page' | 'site'>('page')
const brand = ref('')
const goal = ref('获取线索')
const useKb = ref(true)

const drafting = ref(false)
const elapsed = ref(0)
const saved = ref(false)
const saving = ref(false)
const errorMsg = ref('')
const okMsg = ref('')

const draft = ref<Draft | null>(null)
const activeIdx = ref(0)
const pageKey = ref('')
const siteKey = ref('')

const rows = ref<PageRow[]>([])
const loading = ref(false)
const previewUrl = ref('')
const previewTitle = ref('')

let timer: number | undefined
const ORIGIN = 'https://www.cenkor.cn'

const currentPage = computed(() => draft.value?.pages?.[activeIdx.value] || null)

function fmtTime(s?: string | null) {
  if (!s) return '—'
  // 后端给的是 UTC ISO，界面统一显示北京时间
  const d = new Date(s)
  return isNaN(d.getTime()) ? '—' : d.toLocaleString('zh-CN', { hour12: false })
}

async function generate() {
  if (!brief.value.trim()) {
    errorMsg.value = t("landingStudio.先写一句_nv929k")
    return
  }
  drafting.value = true
  errorMsg.value = ''
  okMsg.value = ''
  draft.value = null
  saved.value = false
  previewUrl.value = ''
  elapsed.value = 0
  timer = window.setInterval(() => (elapsed.value += 1), 1000)
  try {
    const { data } = await api.post(
      '/api/v1/cms/ai/landing/draft',
      {
        brief: brief.value.trim(),
        mode: mode.value,
        brand: brand.value.trim(),
        goal: goal.value,
        use_kb: useKb.value,
      },
      { timeout: 300000 },
    )
    draft.value = data
    activeIdx.value = 0
    pageKey.value = data.pages?.[0]?.key || ''
    siteKey.value = ''
    okMsg.value = `生成完成：${data.pages?.length || 0} 个页面${
      data.kb_used ? `，参考了 ${data.kb_used} 段企业资料` : ''
    }${data.dropped?.length ? `；丢弃了 ${data.dropped.length} 个不支持的区块（${data.dropped.join('、')}）` : ''}`
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || t("aiWorkbench.生成失败_f6lwo5")
  } finally {
    drafting.value = false
    if (timer) window.clearInterval(timer)
  }
}

async function saveDraft() {
  if (!draft.value) return
  saving.value = true
  errorMsg.value = ''
  try {
    const { data } = await api.post(
      '/api/v1/cms/ai/landing/save',
      {
        payload: draft.value,
        page_key: mode.value === 'page' ? pageKey.value || undefined : undefined,
        site_key: mode.value === 'site' ? siteKey.value || undefined : undefined,
      },
      { timeout: 60000 },
    )
    saved.value = true
    okMsg.value = `已保存 ${data.pages.length} 个页面（草稿）。点「预览」看实际效果，确认后发布。`
    const first = data.pages[0]
    previewUrl.value = `${ORIGIN}${first.url}?preview=1`
    previewTitle.value = first.title
    await loadRows()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || t("aiMemory.saveFailed")
  } finally {
    saving.value = false
  }
}

async function loadRows() {
  loading.value = true
  try {
    const { data } = await api.get('/api/v1/cms/ai/landing/pages')
    rows.value = data.items || []
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || t("landingStudio.列表加载_1gvdsg")
  } finally {
    loading.value = false
  }
}

function preview(row: PageRow) {
  previewUrl.value = `${ORIGIN}${row.url}?preview=1`
  previewTitle.value = row.title
}

async function togglePublish(row: PageRow) {
  try {
    const next = row.status !== 'published'
    const { data } = await api.post(`/api/v1/cms/ai/landing/pages/${row.id}/publish`, {
      published: next,
    })
    okMsg.value = next
      ? `已发布 ${data.affected} 个页面：${ORIGIN}${row.url}`
      : '已下线'
    await loadRows()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || t("aiMemory.操作失败_d1rj43")
  }
}

async function removeRow(row: PageRow) {
  if (!window.confirm(`删除页面 ${row.title}？发布中的链接会立即失效。`)) return
  try {
    await api.delete(`/api/v1/cms/ai/landing/pages/${row.id}`)
    okMsg.value = t("landingStudio.已删除_e65yu")
    if (previewUrl.value.includes(row.url)) previewUrl.value = ''
    await loadRows()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || t("aiMemory.删除失败_azdahk")
  }
}

function copyUrl(url: string) {
  navigator.clipboard?.writeText(ORIGIN + url)
  okMsg.value = `已复制：${ORIGIN}${url}`
}

onMounted(loadRows)
onUnmounted(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/cms/ai" class="text-sm text-ink-500 hover:text-ink-900">{{ t("contentHealth.text_11m1s0") }}</router-link>
        <span class="font-semibold">{{ t("landingStudio.落地页工_vgmx8n") }}</span>
        <span class="text-xs text-ink-400">{{ t("landingStudio.一句话生_kbjkwl") }}</span>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-8">
      <p v-if="errorMsg" class="mb-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl px-4 py-2.5">
        {{ errorMsg }}
      </p>
      <p v-if="okMsg" class="mb-4 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-2.5">
        {{ okMsg }}
      </p>

      <!-- 生成区 -->
      <div class="card mb-6">
        <div class="flex items-center gap-3 mb-3">
          <h2 class="font-semibold">{{ t("landingStudio.text_46xd08") }}</h2>
          <span class="text-xs text-ink-400">{{ t("landingStudio.写得具体_hfoc2n") }}</span>
        </div>
        <textarea
          v-model="brief"
          rows="3"
          class="w-full text-sm rounded-xl border border-ink-200 px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-ink-300"
          :placeholder="t('landingStudio.例_1ivlhn')"
        />

        <div class="mt-4 flex flex-wrap items-center gap-4">
          <div class="flex items-center gap-1.5">
            <button
              class="px-3 py-1.5 text-sm rounded-lg border"
              :class="mode === 'page' ? 'bg-ink-900 text-white border-ink-900' : 'border-ink-200 hover:bg-ink-50'"
              @click="mode = 'page'"
            >{{ t("landingStudio.单页落地_1phcns") }}</button>
            <button
              class="px-3 py-1.5 text-sm rounded-lg border"
              :class="mode === 'site' ? 'bg-ink-900 text-white border-ink-900' : 'border-ink-200 hover:bg-ink-50'"
              @click="mode = 'site'"
            >{{ t("landingStudio.官网子站_1xery0") }}</button>
          </div>
          <input
            v-model="brand"
            class="text-sm rounded-lg border border-ink-200 px-3 py-1.5 w-48"
            :placeholder="t('landingStudio.品牌名_3oknq7')"
          />
          <select v-model="goal" class="text-sm rounded-lg border border-ink-200 px-2 py-1.5">
            <option>{{ t("landingStudio.获取线索_gyypvm") }}</option>
            <option>{{ t("landingStudio.预约演示_jrlxag") }}</option>
            <option>{{ t("landingStudio.活动报名_e4k591") }}</option>
            <option>{{ t("landingStudio.产品发布_a9ydak") }}</option>
          </select>
          <label class="text-sm text-ink-600 flex items-center gap-1.5">
            <input v-model="useKb" type="checkbox" />
            {{ t("landingStudio.参考知识_24aaau") }}
          </label>
          <button class="btn-primary ml-auto" :disabled="drafting" @click="generate">
            {{ drafting ? `生成中 ${elapsed}s…` : '生成' }}
          </button>
        </div>
        <p class="mt-2 text-[11px] text-ink-400">
          {{ t("landingStudio.单页约_140688") }}
        </p>
      </div>

      <!-- 草稿结果 -->
      <div v-if="draft" class="card mb-6">
        <div class="flex items-center gap-3 mb-4">
          <h2 class="font-semibold">{{ t("landingStudio.text_qqvi7o") }}</h2>
          <span class="text-xs text-ink-400">
            表单「{{ draft.form?.title }}」共 {{ draft.form?.fields?.length || 0 }} 个字段，提交即进 CRM 线索
          </span>
        </div>

        <div class="flex gap-1.5 mb-4 flex-wrap">
          <button
            v-for="(p, i) in draft.pages"
            :key="p.key"
            class="px-3 py-1.5 text-xs rounded-lg border"
            :class="i === activeIdx ? 'bg-ink-900 text-white border-ink-900' : 'border-ink-200 hover:bg-ink-50'"
            @click="activeIdx = i"
          >{{ p.name || p.key }}（{{ p.blocks.length }}）</button>
        </div>

        <div v-if="currentPage" class="grid gap-4 md:grid-cols-3">
          <div class="md:col-span-2">
            <div class="rounded-xl border border-ink-200 divide-y divide-ink-100">
              <div v-for="(b, i) in currentPage.blocks" :key="i" class="px-4 py-2.5">
                <div class="flex items-center gap-2">
                  <span class="text-[11px] px-1.5 py-0.5 rounded bg-ink-100 text-ink-600">
                    {{ BLOCK_LABEL[b.type] || b.type }}
                  </span>
                  <span class="text-sm font-medium truncate">
                    {{ b.data.title || b.data.text || b.data.brand || b.type }}
                  </span>
                </div>
                <p v-if="b.data.subtitle || b.data.desc" class="text-xs text-ink-400 mt-0.5 line-clamp-2">
                  {{ b.data.subtitle || b.data.desc }}
                </p>
                <p v-else-if="b.data.items?.length" class="text-xs text-ink-400 mt-0.5 truncate">
                  {{ b.data.items.length }} 项：{{ b.data.items.map((x: any) => x.title || x.q || x.label || x.value).join(' / ') }}
                </p>
              </div>
            </div>
          </div>
          <div class="space-y-3">
            <div>
              <p class="text-xs text-ink-400 mb-1">{{ t("landingStudio.text_14em2i") }}</p>
              <p class="text-sm">{{ currentPage.seo?.title || '（空）' }}</p>
            </div>
            <div>
              <p class="text-xs text-ink-400 mb-1">{{ t("landingStudio.description") }}</p>
              <p class="text-xs text-ink-600">{{ currentPage.seo?.description || '（空）' }}</p>
            </div>
            <div>
              <p class="text-xs text-ink-400 mb-1">{{ t("landingStudio.关键词_cnmdu") }}</p>
              <p class="text-xs text-ink-600">{{ currentPage.seo?.keywords || '（空）' }}</p>
            </div>
            <div v-if="mode === 'page'">
              <p class="text-xs text-ink-400 mb-1">{{ t("landingStudio.访问路径_i96gg4") }}</p>
              <div class="flex items-center gap-1">
                <span class="text-xs text-ink-400">/lp/</span>
                <input v-model="pageKey" class="text-xs rounded border border-ink-200 px-2 py-1 w-40" />
              </div>
            </div>
            <div v-else>
              <p class="text-xs text-ink-400 mb-1">{{ t("landingStudio.子站标识_c14dt4") }}</p>
              <input v-model="siteKey" class="text-xs rounded border border-ink-200 px-2 py-1 w-40" :placeholder="t('landingStudio.如_nfa59c')" />
              <p class="text-[11px] text-ink-400 mt-1">发布后：/lp/{{ siteKey || 'site' }}/home</p>
            </div>
            <button class="btn-primary w-full" :disabled="saving || saved" @click="saveDraft">
              {{ saved ? '已保存' : saving ? '保存中…' : '保存为草稿' }}
            </button>
          </div>
        </div>
      </div>

      <!-- 预览 -->
      <div v-if="previewUrl" class="card mb-6">
        <div class="flex items-center gap-3 mb-3">
          <h2 class="font-semibold">{{ t("landingStudio.text_1kpxn7") }}</h2>
          <a :href="previewUrl" target="_blank" class="text-xs text-accent-dark hover:underline">{{ t("landingStudio.新窗口打_1m9aaq") }}</a>
          <button class="ml-auto text-xs text-ink-400 hover:text-ink-900" @click="previewUrl = ''">{{ t("landingStudio.收起_hzpd") }}</button>
        </div>
        <iframe :src="previewUrl" :title="previewTitle" class="w-full h-[720px] rounded-xl border border-ink-200 bg-white" />
      </div>

      <!-- 页面列表 -->
      <div class="card">
        <div class="flex items-center gap-3 mb-4">
          <h2 class="font-semibold">{{ t("landingStudio.已生成的_1uq619") }}</h2>
          <span class="text-xs text-ink-400">{{ t("landingStudio.发布后对_1jr1ny") }}</span>
          <button class="ml-auto text-sm text-ink-500 hover:text-ink-900" @click="loadRows">{{ t("landingStudio.刷新_ejix") }}</button>
        </div>

        <div v-if="loading && !rows.length" class="py-12 text-center text-sm text-ink-400">{{ t("apiKeys.加载中_b0k5km") }}</div>
        <div v-else-if="!rows.length" class="py-12 text-center text-sm text-ink-400">
          {{ t("landingStudio.还没有页_1lffnu") }}
        </div>
        <table v-else class="w-full text-sm">
          <thead>
            <tr class="text-xs text-ink-400 border-b border-ink-100">
              <th class="text-left font-normal py-2">{{ t("landingStudio.title") }}</th>
              <th class="text-left font-normal py-2 w-24">{{ t("landingStudio.type") }}</th>
              <th class="text-left font-normal py-2 w-24">{{ t("landingStudio.status") }}</th>
              <th class="text-right font-normal py-2 w-20 pr-4">{{ t("landingStudio.区块_emvx") }}</th>
              <th class="text-right font-normal py-2 w-20 pr-4">{{ t("landingStudio.留资_kqh7") }}</th>
              <th class="text-left font-normal py-2 w-40">{{ t("entryList.更新时间_devbay") }}</th>
              <th class="text-right font-normal py-2 w-56">{{ t("landingStudio.actions") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rows" :key="r.id" class="border-b border-ink-50 last:border-0">
              <td class="py-2.5 pr-3">
                <div class="font-medium truncate max-w-xs">{{ r.title }}</div>
                <button class="text-[11px] text-ink-400 hover:text-accent-dark" @click="copyUrl(r.url)">
                  {{ r.url }}
                </button>
              </td>
              <td class="py-2.5 text-xs text-ink-500">
                {{ r.kind === 'page' ? '单页' : r.site_key ? '子站·' + r.site_key : '子站' }}
              </td>
              <td class="py-2.5">
                <span
                  class="text-xs px-2 py-0.5 rounded-full"
                  :class="r.status === 'published' ? 'bg-emerald-50 text-emerald-700' : 'bg-ink-100 text-ink-500'"
                >{{ r.status === 'published' ? '已发布' : '草稿' }}</span>
              </td>
              <td class="py-2.5 text-right text-xs text-ink-500 pr-4 tabular-nums">{{ r.block_count }}</td>
              <td class="py-2.5 text-right text-xs pr-4 tabular-nums"
                  :class="r.submissions ? 'text-emerald-600 font-medium' : 'text-ink-400'">
                {{ r.submissions }}
              </td>
              <td class="py-2.5 text-xs text-ink-400 tabular-nums">{{ fmtTime(r.updated_at) }}</td>
              <td class="py-2.5 text-right whitespace-nowrap">
                <button class="px-2 py-1 text-xs rounded border border-ink-200 hover:bg-ink-50" @click="preview(r)">{{ t("landingStudio.预览_qp50") }}</button>
                <button
                  class="ml-1.5 px-2 py-1 text-xs rounded border"
                  :class="r.status === 'published' ? 'border-ink-200 hover:bg-ink-50' : 'border-accent text-accent-dark hover:bg-ink-50'"
                  @click="togglePublish(r)"
                >{{ r.status === 'published' ? '下线' : '发布' }}</button>
                <button class="ml-1.5 px-2 py-1 text-xs rounded border border-red-200 text-red-600 hover:bg-red-50" @click="removeRow(r)">{{ t("landingStudio.delete") }}</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </main>
  </div>
</template>
