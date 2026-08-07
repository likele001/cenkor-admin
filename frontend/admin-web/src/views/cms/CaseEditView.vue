<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/lib/api'

const route = useRoute()
const router = useRouter()
const isNew = !route.params.id
const loading = ref(!isNew)
const saving = ref(false)
const error = ref('')

const form = ref({
  industry: '',
  name: '',
  desc: '',
  tag: '',
  href: '',
  sort: 0,
  status: 'published',
  seoTitle: '',
  seoDescription: '',
  seoKeywords: '',
})

onMounted(async () => {
  if (isNew) return
  try {
    const { data } = await api.get(`/api/v1/cms/cases/${route.params.id}`)
    Object.assign(form.value, data, {
      seoTitle: (data as any).seo_title || '',
      seoDescription: (data as any).seo_description || '',
      seoKeywords: (data as any).seo_keywords || '',
    })
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 't("caseEdit.loadFailed")'
  } finally {
    loading.value = false
  }
})

async function save() {
  saving.value = true
  error.value = ''
  try {
    if (isNew) {
      const { data } = await api.post('/api/v1/cms/cases', form.value)
      router.push(`/cms/cases/${data.id}`)
    } else {
      await api.patch(`/api/v1/cms/cases/${route.params.id}`, form.value)
    }
    // 简单跳转
    setTimeout(() => router.push('/cms/cases'), 500)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 't("caseEdit.saveFailed")'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-4xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/cms/cases" class="text-sm text-ink-500 hover:text-ink-900">{{ t('caseEdit.text_xav8zo') }}</router-link>
        <span class="font-semibold">{{ isNew ? '新建案例' : '编辑案例' }}</span>
      </div>
    </header>

    <main class="max-w-4xl mx-auto px-6 py-10">
      <div v-if="loading" class="card text-ink-500">{{ t('usersList.加载中_b0k5km') }}</div>
      <form v-else @submit.prevent="save" class="card space-y-4">
        <div class="grid sm:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium mb-1.5">{{ t('caseEdit.行业_hib8wo') }}</label>
            <input v-model="form.industry" required class="input" :placeholder="t('productEdit.智能制造_dglz8t')" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1.5">{{ t('caseEdit.客户名_fuv4de') }}</label>
            <input v-model="form.name" required class="input" :placeholder="t('caseEdit.某精密机_fk7dgg')" />
          </div>
        </div>
        <div>
          <label class="block text-sm font-medium mb-1.5">{{ t('caseEdit.描述_d69xvv') }}</label>
          <textarea v-model="form.desc" required rows="3" class="input"></textarea>
        </div>
        <div class="grid sm:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium mb-1.5">{{ t('caseEdit.标签_dmfqn5') }}</label>
            <input v-model="form.tag" required class="input" placeholder="辰科MES" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1.5">{{ t('caseEdit.外链_fo6wuv') }}</label>
            <input v-model="form.href" class="input" placeholder="https://..." />
          </div>
        </div>
        <div class="grid sm:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium mb-1.5">{{ t('productEdit.排序_hge5') }}</label>
            <input v-model.number="form.sort" type="number" class="input" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1.5">{{ t('usersList.状态_k1e3') }}</label>
            <select v-model="form.status" class="input">
              <option value="published">{{ t('productEdit.已发布_e656s') }}</option>
              <option value="draft">{{ t('productEdit.草稿_n02e') }}</option>
            </select>
          </div>
        </div>

        <!-- SEO -->
        <div class="space-y-4 pt-4 border-t border-ink-200">
          <h2 class="font-semibold text-lg">SEO</h2>
          <p class="text-sm text-ink-500">覆盖站点默认 meta，留空则使用站点全局配置。</p>
          <div>
            <label class="block text-sm font-medium mb-1.5">Meta 标题（title）</label>
            <input v-model="form.seoTitle" class="input" :placeholder="form.name + ' - 客户案例'" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1.5">Meta 描述（description）</label>
            <textarea v-model="form.seoDescription" rows="2" class="input" placeholder="案例摘要 + 客户成果关键词"></textarea>
          </div>
          <div>
            <label class="block text-sm font-medium mb-1.5">Meta 关键词（keywords，逗号分隔）</label>
            <input v-model="form.seoKeywords" class="input" placeholder="客户案例,行业,解决方案" />
          </div>
        </div>

        <div v-if="error" class="text-sm text-red-600">{{ error }}</div>
        <div class="flex gap-3">
          <button type="submit" :disabled="saving" class="btn-primary">
            {{ saving ? '保存中…' : isNew ? '创建案例' : '保存修改' }}
          </button>
          <router-link to="/cms/cases" class="btn-ghost">{{ t('usersList.取消_ev02') }}</router-link>
        </div>
      </form>
    </main>
  </div>
</template>
