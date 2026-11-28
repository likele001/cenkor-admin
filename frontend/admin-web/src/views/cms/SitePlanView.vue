<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '@/lib/api'

interface Cat { key: string; name: string; slug: string; parent_key: string | null; description?: string; seo_title?: string }
interface Art { title: string; category_key: string; keyword?: string; brief?: string }
interface PlanJson { summary?: string; categories: Cat[]; articles: Art[] }

const form = reactive({ brief: '', keywords: '', category_count: 6, article_count: 12 })
const keywordFile = ref<File | null>(null)
const importStats = ref<any>(null)
const plan = ref<PlanJson | null>(null)
const warnings = ref<string[]>([])
const loading = ref(false)
const error = ref('')
const notice = ref('')
const savedId = ref<number | null>(null)
const status = ref('')
const diff = ref<any>(null)
const result = ref<any>(null)
const plans = ref<any[]>([])

// 按 parent_key 算缩进，预览里能直接看出层级
const catOptions = computed(() => plan.value?.categories || [])
function depthOf(c: Cat): number {
  let d = 0
  let cur: Cat | undefined = c
  while (cur?.parent_key && d < 3) {
    cur = catOptions.value.find((x) => x.key === cur!.parent_key)
    d += 1
  }
  return d
}

async function loadList() {
  try {
    const { data } = await api.get('/api/v1/cms/site-plans')
    plans.value = data
  } catch { plans.value = [] }
}

async function draft() {
  error.value = ''
  notice.value = ''
  if (form.brief.trim().length < 2) { error.value = t("sitePlan.先把站点_1g0yzd"); return }
  loading.value = true
  plan.value = null
  diff.value = null
  result.value = null
  savedId.value = null
  try {
    const { data } = await api.post('/api/v1/cms/site-plans/draft', {
      brief: form.brief,
      keywords: form.keywords.split(/[,，\s]+/).filter(Boolean),
      category_count: form.category_count,
      article_count: form.article_count,
    })
    plan.value = data.plan
    warnings.value = data.warnings || []
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t("aiWorkbench.生成失败_f6lwo5")
  } finally {
    loading.value = false
  }
}

async function importKeywords() {
  if (!keywordFile.value) { error.value = t("sitePlan.先选一个_1ew1jh"); return }
  error.value = ''
  loading.value = true
  const fd = new FormData()
  fd.append('file', keywordFile.value)
  try {
    const { data } = await api.post('/api/v1/cms/site-plans/import-keywords', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    plan.value = data.plan
    warnings.value = data.warnings || []
    importStats.value = data.stats
    savedId.value = null
    status.value = ''
    diff.value = null
    result.value = null
    notice.value = `识别 ${data.stats.valid} 行关键词，拆出 ${data.stats.categories} 个栏目，丢弃 ${data.stats.dropped} 行`
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t("sitePlan.关键词包_1ktiow")
  } finally {
    loading.value = false
  }
}

async function savePlan() {
  if (!plan.value) return
  error.value = ''
  loading.value = true
  try {
    const { data } = await api.post('/api/v1/cms/site-plans', {
      brief: form.brief,
      keywords: form.keywords.split(/[,，\s]+/).filter(Boolean),
      category_count: form.category_count,
      article_count: form.article_count,
      plan: plan.value,
    })
    savedId.value = data.plan.id
    status.value = data.plan.status
    notice.value = `方案已保存（#${data.plan.id}），确认后才能执行`
    await loadList()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t("aiMemory.saveFailed")
  } finally {
    loading.value = false
  }
}

async function confirmPlan() {
  if (!savedId.value) return
  try {
    const { data } = await api.post(`/api/v1/cms/site-plans/${savedId.value}/confirm`)
    status.value = data.plan.status
    notice.value = '已确认，可以先预览差异'
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t("sitePlan.确认失败_frpz7u")
  }
}

async function dryRun() {
  if (!savedId.value) return
  error.value = ''
  try {
    const { data } = await api.post(`/api/v1/cms/site-plans/${savedId.value}/dry-run`)
    diff.value = data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t("aiMemory.预览失败_jt50ig")
  }
}

async function applyPlan() {
  if (!savedId.value) return
  if (!confirm(`将创建栏目并把这 ${plan.value?.articles.length || 0} 篇选题送进批量队列，继续？`)) return
  error.value = ''
  loading.value = true
  try {
    const { data } = await api.post(`/api/v1/cms/site-plans/${savedId.value}/apply`)
    result.value = data
    status.value = 'done'
    notice.value = '已执行：栏目已建，选题已进批量队列'
    await loadList()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t("sitePlan.执行失败_cz7pg9")
  } finally {
    loading.value = false
  }
}

onMounted(loadList)
</script>

<template>
  <div class="space-y-4">
    <div>
      <h1 class="text-lg font-semibold text-ink-900">{{ t("sitePlan.建站编排_chv0rf") }}</h1>
      <p class="text-sm text-ink-500 mt-1">{{ t("sitePlan.一句话说_kconoh") }}</p>
    </div>

    <div v-if="error" class="rounded-md bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2">{{ error }}</div>
    <div v-if="notice" class="rounded-md bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm px-3 py-2">{{ notice }}</div>

    <div class="rounded-lg border border-ink-200 bg-white p-4 space-y-3">
      <label class="block text-sm text-ink-600">{{ t("sitePlan.站点需求_fz1mbm") }}
        <textarea v-model="form.brief" rows="3" class="input mt-1 text-sm w-full" :placeholder="t('sitePlan.例如_1enkkm')"></textarea>
      </label>
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-2">
        <label class="block text-sm text-ink-600">{{ t("sitePlan.关键词_18rkkz") }}
          <input v-model="form.keywords" class="input mt-1 text-sm" :placeholder="t('sitePlan.液压油缸_c5a1jd')" />
        </label>
        <label class="block text-sm text-ink-600">{{ t("sitePlan.栏目数_fthg1") }}
          <input v-model.number="form.category_count" type="number" min="1" max="12" class="input mt-1 text-sm" />
        </label>
        <label class="block text-sm text-ink-600">{{ t("sitePlan.选题数_lu081") }}
          <input v-model.number="form.article_count" type="number" min="1" max="60" class="input mt-1 text-sm" />
        </label>
      </div>
      <div class="flex flex-wrap items-center justify-end gap-2">
        <input
          type="file"
          accept=".csv,text/csv"
          class="text-xs text-ink-500 file:mr-2 file:rounded file:border file:border-ink-200 file:bg-ink-50 file:px-2 file:py-1"
          @change="(e: any) => (keywordFile = e.target.files?.[0] || null)"
        />
        <button class="btn text-sm" :disabled="loading || !keywordFile" @click="importKeywords">{{ t("sitePlan.导入关键_16j98y") }}</button>
        <button class="btn btn-primary text-sm" :disabled="loading" @click="draft">{{ loading ? '生成中…' : '生成方案' }}</button>
      </div>
    </div>

    <div v-if="warnings.length" class="rounded-md bg-amber-50 border border-amber-200 text-amber-800 text-sm px-3 py-2 space-y-1">
      <div v-for="(w, i) in warnings" :key="i">· {{ w }}</div>
    </div>

    <div v-if="importStats" class="rounded-md bg-ink-50 border border-ink-200 text-xs text-ink-600 px-3 py-2">
      关键词包：共 {{ importStats.rows }} 行，有效 {{ importStats.valid }}，丢弃 {{ importStats.dropped }}
      <span v-if="importStats.drop_samples && importStats.drop_samples.length">
        · 示例：{{ importStats.drop_samples.map((d: any) => `第${d.row}行 ${d.reason}`).join('；') }}
      </span>
    </div>

    <div v-if="plan" class="rounded-lg border border-ink-200 bg-white p-4 space-y-4">
      <div>
        <h2 class="font-semibold text-ink-900">{{ t("sitePlan.方案预览_d9wdyr") }}</h2>
        <p class="text-sm text-ink-500 mt-1">{{ plan.summary || '（无摘要）' }}</p>
      </div>

      <div>
        <h3 class="text-sm font-medium text-ink-700 mb-2">栏目树（{{ plan.categories.length }}）</h3>
        <ul class="text-sm space-y-1">
          <li v-for="c in plan.categories" :key="c.key" :style="{ paddingLeft: depthOf(c) * 18 + 'px' }">
            <span class="text-ink-900">{{ c.name }}</span>
            <span class="font-mono text-[11px] text-ink-400 ml-2">{{ c.slug }}</span>
            <span v-if="c.seo_title" class="text-ink-500 ml-2">· {{ c.seo_title }}</span>
          </li>
        </ul>
      </div>

      <div>
        <h3 class="text-sm font-medium text-ink-700 mb-2">首批选题（{{ plan.articles.length }}）</h3>
        <ul class="text-sm space-y-1">
          <li v-for="(a, i) in plan.articles" :key="i">
            <span class="text-ink-400 mr-1">{{ i + 1 }}.</span>
            <span class="text-ink-900">{{ a.title }}</span>
            <span class="text-ink-400 ml-2">@ {{ a.category_key }}</span>
          </li>
        </ul>
      </div>

      <div v-if="diff" class="rounded-md bg-sky-50 border border-sky-200 text-sm px-3 py-2 text-sky-900">
        将新建 {{ diff.categories_new }} 个栏目，复用 {{ diff.categories_existing.length }} 个已有栏目；
        {{ diff.articles }} 篇选题进入批量队列。
      </div>

      <div v-if="result" class="rounded-md bg-emerald-50 border border-emerald-200 text-sm px-3 py-2 text-emerald-800">
        已建 {{ result.categories_created }} 个栏目、复用 {{ result.categories_reused }} 个；
        <router-link v-if="result.batch_job_id" :to="`/cms/ai-batch?id=${result.batch_job_id}`" class="underline">查看批次 #{{ result.batch_job_id }}</router-link>
      </div>

      <div class="flex flex-wrap justify-end gap-2">
        <button class="btn text-sm" :disabled="loading" @click="savePlan">{{ t("sitePlan.保存方案_agi5u2") }}</button>
        <button class="btn text-sm" :disabled="!savedId || status !== 'draft'" @click="confirmPlan">{{ t("sitePlan.confirm") }}</button>
        <button class="btn text-sm" :disabled="!savedId || status !== 'confirmed'" @click="dryRun">{{ t("sitePlan.预览差异_jt5kew") }}</button>
        <button class="btn btn-primary text-sm" :disabled="!savedId || status !== 'confirmed' || loading" @click="applyPlan">{{ t("sitePlan.执行_hhhh") }}</button>
      </div>
      <p v-if="savedId" class="text-xs text-ink-400 text-right">方案 #{{ savedId }} · 状态 {{ status }}</p>
    </div>

    <div class="rounded-lg border border-ink-200 bg-white">
      <div class="px-4 py-3 border-b border-ink-100 text-sm font-medium text-ink-700">{{ t("sitePlan.历史方案_aw1g4b") }}</div>
      <div v-if="!plans.length" class="px-4 py-6 text-center text-sm text-ink-400">{{ t("sitePlan.还没有方_8b9atr") }}</div>
      <ul v-else class="divide-y divide-ink-100">
        <li v-for="p in plans" :key="p.id" class="px-4 py-3 text-sm flex items-center justify-between gap-3">
          <div class="min-w-0">
            <div class="text-ink-900 truncate">{{ p.summary || `方案 #${p.id}` }}</div>
            <div class="text-xs text-ink-400">#{{ p.id }} · {{ p.categories }} 栏目 · {{ p.articles }} 选题 · {{ p.status }}</div>
          </div>
          <router-link v-if="p.batch_job_id" :to="`/cms/ai-batch?id=${p.batch_job_id}`" class="text-sky-600 shrink-0">批次 #{{ p.batch_job_id }}</router-link>
        </li>
      </ul>
    </div>
  </div>
</template>
