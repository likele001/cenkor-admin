<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/lib/api'
import { fromProductApi, toProductPayload } from '@/lib/transform'

const route = useRoute()
const router = useRouter()
const isNew = !route.params.id
const loading = ref(!isNew)
const saving = ref(false)
const error = ref('')
const success = ref('')

const form = ref({
  name: '',
  chineseName: '',
  slug: '',
  tagline: '',
  line: 'enterprise',
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

async function load() {
  if (isNew) return
  try {
    const { data } = await api.get(`/api/v1/cms/products/${route.params.id}`)
    Object.assign(form.value, fromProductApi(data))
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  error.value = ''
  success.value = ''
  try {
    const payload = toProductPayload(form.value)
    if (isNew) {
      const { data } = await api.post('/api/v1/cms/products', payload)
      success.value = '已创建！'
      setTimeout(() => router.push(`/cms/products/${data.id}`), 600)
    } else {
      await api.patch(`/api/v1/cms/products/${route.params.id}`, payload)
      success.value = '已保存！'
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '保存失败'
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
        <router-link to="/cms/products" class="text-sm text-ink-500 hover:text-ink-900">← 产品列表</router-link>
        <span class="font-semibold">{{ isNew ? '新建产品' : '编辑产品' }}</span>
      </div>
    </header>

    <main class="max-w-4xl mx-auto px-6 py-10">
      <div v-if="loading" class="card text-ink-500">加载中…</div>

      <form v-else @submit.prevent="save" class="space-y-6">
        <!-- 基础信息 -->
        <div class="card space-y-4">
          <h2 class="font-semibold text-lg">基础信息</h2>
          <div class="grid sm:grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium mb-1.5">名称 *</label>
              <input v-model="form.name" required class="input" placeholder="PlantFlow" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1.5">中文名</label>
              <input v-model="form.chineseName" class="input" placeholder="厂流" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1.5">Slug *</label>
              <input v-model="form.slug" required :disabled="!isNew" class="input" placeholder="plantflow" />
              <p v-if="!isNew" class="mt-1 text-xs text-ink-400">slug 不可修改</p>
            </div>
            <div>
              <label class="block text-sm font-medium mb-1.5">业务线 *</label>
              <select v-model="form.line" required class="input">
                <option value="enterprise">企业级后台</option>
                <option value="ai">AI 智能化</option>
                <option value="manufacturing">智能制造</option>
              </select>
            </div>
            <div class="sm:col-span-2">
              <label class="block text-sm font-medium mb-1.5">一句话标签 *</label>
              <input v-model="form.tagline" required class="input" placeholder="开源工厂工作流平台（n8n + Dify 双能力）" />
            </div>
            <div class="sm:col-span-2">
              <label class="block text-sm font-medium mb-1.5">技术栈</label>
              <input v-model="form.stack" class="input" placeholder="React 18 / Vite / PostgreSQL / Docker" />
            </div>
            <div class="sm:col-span-2">
              <label class="block text-sm font-medium mb-1.5">详细描述 *</label>
              <textarea v-model="form.desc" required rows="4" class="input"></textarea>
            </div>
          </div>
        </div>

        <!-- 特性列表 -->
        <div class="card">
          <h2 class="font-semibold text-lg mb-3">特性列表</h2>
          <ul class="space-y-2 mb-3">
            <li v-for="(f, i) in form.features" :key="i" class="flex items-center gap-2 text-sm">
              <span class="text-ink-400">•</span>
              <span class="flex-1">{{ f }}</span>
              <button type="button" @click="removeFeature(i)" class="text-xs text-red-600 hover:underline">移除</button>
            </li>
            <li v-if="form.features.length === 0" class="text-sm text-ink-400">暂无特性</li>
          </ul>
          <div class="flex gap-2">
            <input v-model="featureInput" @keydown.enter.prevent="addFeature" class="input flex-1" placeholder="如：工作流编辑器：拖拽节点、条件分支" />
            <button type="button" @click="addFeature" class="btn-ghost shrink-0">+ 添加</button>
          </div>
        </div>

        <!-- 链接 / 标记 -->
        <div class="card space-y-4">
          <h2 class="font-semibold text-lg">链接 & 标记</h2>
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
              <label class="block text-sm font-medium mb-1.5">官网 URL</label>
              <input v-model="form.website" class="input" placeholder="https://example.com" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1.5">License</label>
              <input v-model="form.license" class="input" placeholder="MIT" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1.5">排序</label>
              <input v-model.number="form.sort" type="number" class="input" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1.5">状态</label>
              <select v-model="form.status" class="input">
                <option value="published">已发布</option>
                <option value="draft">草稿</option>
                <option value="archived">已归档</option>
              </select>
            </div>
            <div class="flex items-end gap-4">
              <label class="flex items-center gap-2 text-sm">
                <input v-model="form.isFlagship" type="checkbox" class="rounded" /> 旗舰
              </label>
              <label class="flex items-center gap-2 text-sm">
                <input v-model="form.isOpenSource" type="checkbox" class="rounded" /> 开源
              </label>
            </div>
          </div>
        </div>

        <div v-if="error" class="text-sm text-red-600">{{ error }}</div>
        <div v-if="success" class="text-sm text-emerald-600">{{ success }}</div>

        <div class="flex gap-3">
          <button type="submit" :disabled="saving" class="btn-primary">
            {{ saving ? '保存中…' : isNew ? '创建产品' : '保存修改' }}
          </button>
          <router-link to="/cms/products" class="btn-ghost">取消</router-link>
        </div>
      </form>
    </main>
  </div>
</template>
