<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/lib/api'
import { fromProductApi, toProductPayload } from '@/lib/transform'
import DynamicFieldRenderer from '@/components/cms/DynamicFieldRenderer.vue'

const route = useRoute()
const router = useRouter()
const isNew = !route.params.id
const loading = ref(!isNew)
const saving = ref(false)
const error = ref('')
const success = ref('')

const fieldDefs = ref<any[]>([])
const fieldGroups = ref<any[]>([])

const form = ref({
  name: '',
  chineseName: '',
  slug: '',
  tagline: '',
  line: 'enterprise' as string,
  stack: '',
  desc: '',
  features: [] as string[],
  isFlagship: false,
  isOpenSource: false,
  github: '',
  demo: '',
  website: '',
  license: '',
  sort: 0,
  status: 'published',
  custom_fields: {} as Record<string, any>,
  seoTitle: '',
  seoDescription: '',
  seoKeywords: '',
})

const featureInput = ref('')

function addFeature() {
  const v = featureInput.value.trim()
  if (!v) return
  form.value.features.push(v)
  featureInput.value = ''
}

function removeFeature(i: number) {
  form.value.features.splice(i, 1)
}

async function loadFieldDefs(contentTypeKey: string) {
  try {
    const { data } = await api.get('/api/v1/cms/content-types')
    const ct = data.items?.find((t: any) => t.key === contentTypeKey)
    if (ct) {
      fieldGroups.value = ct.field_groups || []
      fieldDefs.value = ct.field_definitions?.filter((d: any) => d.status === 'active') || []
    }
  } catch { /* V2 内容引擎不可用 */ }
}

async function load() {
  if (isNew) return
  try {
    const [prodRes] = await Promise.all([
      api.get(`/api/v1/cms/products/${route.params.id}`),
      loadFieldDefs('product'),
    ])
    Object.assign(form.value, fromProductApi(prodRes.data))
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 't("caseEdit.loadFailed")'
  } finally {
    loading.value = false
  }
}

// 即使新建也加载字段定义
if (isNew) loadFieldDefs('product')

async function save() {
  saving.value = true
  error.value = ''
  success.value = ''
  try {
    const payload = toProductPayload(form.value)
    if (isNew) {
      const { data } = await api.post('/api/v1/cms/products', payload)
      success.value = 't("productEdit.已创建")'
      setTimeout(() => router.push(`/cms/products/${data.id}`), 600)
    } else {
      await api.patch(`/api/v1/cms/products/${route.params.id}`, payload)
      success.value = 't("productEdit.已保存")'
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 't("caseEdit.saveFailed")'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-4xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/cms/products" class="text-sm text-ink-500 hover:text-ink-900">{{ t('productEdit.text_u39d8b') }}</router-link>
        <span class="font-semibold">{{ isNew ? '新建产品' : '编辑产品' }}</span>
      </div>
    </header>

    <main class="max-w-4xl mx-auto px-6 py-10">
      <div v-if="loading" class="card text-ink-500">{{ t('usersList.加载中_b0k5km') }}</div>

      <form v-else @submit.prevent="save" class="space-y-6">
        <!-- 基础信息 -->
        <div class="card space-y-4">
          <h2 class="font-semibold text-lg">{{ t('productEdit.基础信息_blh1h0') }}</h2>
          <div class="grid sm:grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium mb-1.5">{{ t('roles.名称_b3i4lp') }}</label>
              <input v-model="form.name" required class="input" placeholder="PlantFlow" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1.5">{{ t('productEdit.中文名_bxy6r') }}</label>
              <input v-model="form.chineseName" class="input" :placeholder="t('productEdit.厂流_esxr')" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1.5">Slug *</label>
              <input v-model="form.slug" required :disabled="!isNew" class="input" placeholder="plantflow" />
              <p v-if="!isNew" class="mt-1 text-xs text-ink-400">{{ t('productEdit.text_vf2d7m') }}</p>
            </div>
            <div>
              <label class="block text-sm font-medium mb-1.5">{{ t('productEdit.业务线_w6ta02') }}</label>
              <select v-model="form.line" required class="input">
                <option value="enterprise">{{ t('productEdit.企业级后_z5nxyo') }}</option>
                <option value="ai">{{ t('productEdit.text_wc9lmj') }}</option>
                <option value="manufacturing">{{ t('productEdit.智能制造_dglz8t') }}</option>
              </select>
            </div>
            <div class="sm:col-span-2">
              <label class="block text-sm font-medium mb-1.5">{{ t('productEdit.一句话标_e69yk9') }}</label>
              <input v-model="form.tagline" required class="input" :placeholder="t('productEdit.开源工厂_amhp2g')" />
            </div>
            <div class="sm:col-span-2">
              <label class="block text-sm font-medium mb-1.5">{{ t('productEdit.技术栈_exid5') }}</label>
              <input v-model="form.stack" class="input" placeholder="React 18 / Vite / PostgreSQL / Docker" />
            </div>
            <div class="sm:col-span-2">
              <label class="block text-sm font-medium mb-1.5">{{ t('productEdit.详细描述_1r9w02') }}</label>
              <textarea v-model="form.desc" required rows="4" class="input"></textarea>
            </div>
          </div>
        </div>

        <!-- 特性列表 -->
        <div class="card">
          <h2 class="font-semibold text-lg mb-3">{{ t('productEdit.特性列表_eu9ojj') }}</h2>
          <ul class="space-y-2 mb-3">
            <li v-for="(f, i) in form.features" :key="i" class="flex items-center gap-2 text-sm">
              <span class="text-ink-400">•</span>
              <span class="flex-1">{{ f }}</span>
              <button type="button" @click="removeFeature(i)" class="text-xs text-red-600 hover:underline">{{ t('productEdit.移除_lknd') }}</button>
            </li>
            <li v-if="form.features.length === 0" class="text-sm text-ink-400">{{ t('productEdit.暂无特性_dcxcdo') }}</li>
          </ul>
          <div class="flex gap-2">
            <input v-model="featureInput" @keydown.enter.prevent="addFeature" class="input flex-1" :placeholder="t('productEdit.如_1maf91')" />
            <button type="button" @click="addFeature" class="btn-ghost shrink-0">{{ t('productEdit.text_1b9y2') }}</button>
          </div>
        </div>

        <!-- 链接 / 标记 -->
        <div class="card space-y-4">
          <h2 class="font-semibold text-lg">{{ t('productEdit.链接_18x7iz') }}</h2>
          <div class="grid sm:grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium mb-1.5">GitHub URL</label>
              <input v-model="form.github" class="input" placeholder="https://github.com/..." />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1.5">Demo URL</label>
              <input v-model="form.demo" class="input" placeholder="https://demo.example.com" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1.5">{{ t('productEdit.官网_lsprhk') }}</label>
              <input v-model="form.website" class="input" placeholder="https://example.com" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1.5">License</label>
              <input v-model="form.license" class="input" placeholder="MIT" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1.5">{{ t('productEdit.排序_hge5') }}</label>
              <input v-model.number="form.sort" type="number" class="input" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1.5">{{ t('usersList.状态_k1e3') }}</label>
              <select v-model="form.status" class="input">
                <option value="published">{{ t('productEdit.已发布_e656s') }}</option>
                <option value="draft">{{ t('productEdit.草稿_n02e') }}</option>
                <option value="archived">{{ t('productEdit.已归档_e85oj') }}</option>
              </select>
            </div>
            <div class="flex items-end gap-4">
              <label class="flex items-center gap-2 text-sm">
                <input v-model="form.isFlagship" type="checkbox" class="rounded" /> {{ t('productsList.旗舰_i1bt') }}
              </label>
              <label class="flex items-center gap-2 text-sm">
                <input v-model="form.isOpenSource" type="checkbox" class="rounded" /> {{ t('productEdit.开源') }}
              </label>
            </div>
          </div>
        </div>

        <!-- SEO -->
        <div class="card space-y-4">
          <h2 class="font-semibold text-lg">SEO</h2>
          <p class="text-sm text-ink-500">覆盖站点默认 meta，留空则使用站点全局配置。</p>
          <div class="grid sm:grid-cols-2 gap-4">
            <div class="sm:col-span-2">
              <label class="block text-sm font-medium mb-1.5">Meta 标题（title）</label>
              <input v-model="form.seoTitle" class="input" placeholder="辰科MES · 中小加工厂生产管理系统" />
            </div>
            <div class="sm:col-span-2">
              <label class="block text-sm font-medium mb-1.5">Meta 描述（description）</label>
              <textarea v-model="form.seoDescription" rows="2" class="input" placeholder="源码交付·私有部署·数据不出厂。扫码报工/计件工资/CRM/AI。"></textarea>
            </div>
            <div class="sm:col-span-2">
              <label class="block text-sm font-medium mb-1.5">Meta 关键词（keywords，逗号分隔）</label>
              <input v-model="form.seoKeywords" class="input" placeholder="MES系统,生产管理系统,扫码报工,计件工资,加工厂管理软件" />
            </div>
          </div>
        </div>

        <!-- 自定义字段 -->
        <div v-if="fieldDefs.length" class="card space-y-4">
          <h2 class="font-semibold text-lg">{{ t('productEdit.自定义字_mmnfx3') }}</h2>
          <template v-for="group in fieldGroups" :key="group.id">
            <div v-if="fieldDefs.filter(d => d.group_id === group.id || d.group_id === null).length">
              <h3 v-if="group.key !== 'basic'" class="text-sm font-medium text-ink-500 mb-2">{{ group.label }}</h3>
              <div class="grid sm:grid-cols-2 gap-4">
                <DynamicFieldRenderer
                  v-for="fd in fieldDefs.filter(d => d.group_id === group.id || d.group_id === null)"
                  :key="fd.id"
                  :definition="fd"
                  :modelValue="form.custom_fields[fd.field_key] ?? ''"
                  @update:modelValue="form.custom_fields[fd.field_key] = $event"
                />
              </div>
            </div>
          </template>
          <template v-if="!fieldGroups.length">
            <div class="grid sm:grid-cols-2 gap-4">
              <DynamicFieldRenderer
                v-for="fd in fieldDefs"
                :key="fd.id"
                :definition="fd"
                :modelValue="form.custom_fields[fd.field_key] ?? ''"
                @update:modelValue="form.custom_fields[fd.field_key] = $event"
              />
            </div>
          </template>
        </div>

        <div v-if="error" class="text-sm text-red-600">{{ error }}</div>
        <div v-if="success" class="text-sm text-emerald-600">{{ success }}</div>

        <div class="flex gap-3">
          <button type="submit" :disabled="saving" class="btn-primary">
            {{ saving ? '保存中…' : isNew ? '创建产品' : '保存修改' }}
          </button>
          <router-link to="/cms/products" class="btn-ghost">{{ t('usersList.取消_ev02') }}</router-link>
        </div>
      </form>
    </main>
  </div>
</template>
