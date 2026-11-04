<script setup lang="ts">
/**
 * 模板市场 —— 站长浏览/安装第三方主题，开发者上架自己的主题。
 *
 * 四个 Tab：
 *   1. 市场     浏览主题（过滤 dev_method=theme）
 *   2. 已装     已安装的主题（含内置）
 *   3. 我的模板  开发者提交的主题（状态/版本/下载量）
 *   4. 开发指南  模板开发文档（可一键灌入知识库）
 */
import { ref, onMounted, computed } from 'vue'
import { api } from '@/lib/api'

// ---- 类型 ----
interface ThemeItem {
  key: string
  name: string
  version: string | null
  latest_version: string | null
  summary: string
  description: string
  icon: string
  category: string
  category_label: string
  author: string
  price: any
  is_free: boolean
  installed: boolean
  installed_version: string | null
  has_update: boolean
  dev_method: string
  local_files?: number
}

interface InstalledTheme {
  theme: string
  name: string
  version: string | null
  description: string
  settings_count: number
  widgets_count: number
  files: number
  source: string
}

interface MySubmission {
  id: number
  app_key: string
  name: string
  version: string
  status: string
  created_at: string
  download_count: number
  review_note: string | null
}

interface DevDoc {
  id: string
  filename: string
  title: string
  summary: string
  size: number
}

// ---- 状态 ----
const activeTab = ref<'market' | 'installed' | 'mine' | 'docs'>('market')
const loading = ref(false)
const error = ref('')

// 市场
const marketItems = ref<ThemeItem[]>([])
const marketTotal = ref(0)
const marketPage = ref(1)
const marketSearch = ref('')

// 已装
const installedItems = ref<InstalledTheme[]>([])

// 我的模板
const mySubmissions = ref<MySubmission[]>([])

// 开发指南
const devDocs = ref<DevDoc[]>([])
const docContent = ref('')
const docTitle = ref('')
const importingKb = ref(false)
const kbImportResult = ref('')

// 安装弹窗
const showInstallDialog = ref(false)
const installTarget = ref<ThemeItem | null>(null)
const licenseKey = ref('')
const activateAfterInstall = ref(false)
const installing = ref(false)

// ---- 生命周期 ----
onMounted(() => {
  loadMarket()
})

// ---- 方法 ----
async function loadMarket() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/api/v1/cms/theme-market/catalog', {
      params: { page: marketPage.value, page_size: 24, q: marketSearch.value },
    })
    marketItems.value = data.items
    marketTotal.value = data.total
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

async function loadInstalled() {
  loading.value = true
  try {
    const { data } = await api.get('/api/v1/cms/theme-market/installed')
    installedItems.value = data.items
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

async function loadMySubmissions() {
  loading.value = true
  try {
    const { data } = await api.get('/api/v1/store/submissions', {
      params: { page: 1, page_size: 50 },
    })
    // 只留主题包
    mySubmissions.value = (data.items || []).filter(
      (s: any) => s.dev_method === 'theme'
    )
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

async function loadDevDocs() {
  loading.value = true
  try {
    const { data } = await api.get('/api/v1/developer/docs')
    devDocs.value = data.items
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

async function openDoc(docId: string) {
  try {
    const { data } = await api.get(`/api/v1/developer/docs/${docId}`)
    docContent.value = data.content
    docTitle.value = data.title
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载文档失败'
  }
}

async function importDocsToKb() {
  importingKb.value = true
  kbImportResult.value = ''
  try {
    const { data } = await api.post('/api/v1/developer/docs/import-kb')
    kbImportResult.value = `已导入 ${data.imported.length} 份文档${data.skipped.length ? `，跳过 ${data.skipped.length} 份（已存在）` : ''}`
  } catch (e: any) {
    kbImportResult.value = `导入失败：${e?.response?.data?.detail || e.message}`
  } finally {
    importingKb.value = false
  }
}

function openInstall(item: ThemeItem) {
  installTarget.value = item
  licenseKey.value = ''
  activateAfterInstall.value = false
  showInstallDialog.value = true
}

async function doInstall() {
  if (!installTarget.value) return
  installing.value = true
  try {
    const { data } = await api.post('/api/v1/cms/theme-market/install', {
      app_key: installTarget.value.key,
      license_key: licenseKey.value,
      activate: activateAfterInstall.value,
    })
    showInstallDialog.value = false
    await loadMarket()
    await loadInstalled()
    alert(`安装成功：${data.manifest?.name || installTarget.value.key}`)
  } catch (e: any) {
    alert(`安装失败：${e?.response?.data?.detail || e.message}`)
  } finally {
    installing.value = false
  }
}

function switchTab(tab: typeof activeTab.value) {
  activeTab.value = tab
  error.value = ''
  if (tab === 'market') loadMarket()
  else if (tab === 'installed') loadInstalled()
  else if (tab === 'mine') loadMySubmissions()
  else if (tab === 'docs') loadDevDocs()
}

function statusLabel(s: string): string {
  const map: Record<string, string> = {
    pending: '待审核',
    approved: '已通过',
    published: '已上架',
    rejected: '已拒绝',
    installed: '已安装',
  }
  return map[s] || s
}

function statusColor(s: string): string {
  const map: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-800',
    approved: 'bg-green-100 text-green-800',
    published: 'bg-blue-100 text-blue-800',
    rejected: 'bg-red-100 text-red-800',
    installed: 'bg-purple-100 text-purple-800',
  }
  return map[s] || 'bg-gray-100 text-gray-800'
}
</script>

<template>
  <div class="p-6">
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-900">模板市场</h1>
      <p class="mt-1 text-sm text-gray-500">浏览、安装、管理主题模板</p>
    </div>

    <!-- Tab 导航 -->
    <div class="border-b border-gray-200 mb-6">
      <nav class="flex gap-6">
        <button
          v-for="tab in [
            { key: 'market', label: '市场' },
            { key: 'installed', label: '已装' },
            { key: 'mine', label: '我的模板' },
            { key: 'docs', label: '开发指南' },
          ]"
          :key="tab.key"
          @click="switchTab(tab.key as any)"
          :class="[
            'pb-3 px-1 border-b-2 font-medium text-sm transition-colors',
            activeTab === tab.key
              ? 'border-blue-500 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300',
          ]"
        >
          {{ tab.label }}
        </button>
      </nav>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="mb-4 p-3 bg-red-50 text-red-700 rounded-lg text-sm">
      {{ error }}
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="flex justify-center py-12">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
    </div>

    <!-- ===== 市场 ===== -->
    <div v-if="activeTab === 'market' && !loading">
      <div class="mb-4 flex gap-3">
        <input
          v-model="marketSearch"
          @keyup.enter="loadMarket"
          placeholder="搜索主题..."
          class="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        <button
          @click="loadMarket"
          class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          搜索
        </button>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div
          v-for="item in marketItems"
          :key="item.key"
          class="border border-gray-200 rounded-xl p-5 hover:shadow-md transition-shadow"
        >
          <div class="flex items-start gap-3">
            <span class="text-3xl">{{ item.icon || '🎨' }}</span>
            <div class="flex-1 min-w-0">
              <h3 class="font-semibold text-gray-900 truncate">{{ item.name }}</h3>
              <p class="text-xs text-gray-500 mt-0.5">by {{ item.author || '未知' }}</p>
            </div>
            <span
              v-if="item.is_free"
              class="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded-full"
            >
              免费
            </span>
            <span
              v-else
              class="px-2 py-0.5 bg-orange-100 text-orange-700 text-xs rounded-full"
            >
              付费
            </span>
          </div>

          <p class="mt-3 text-sm text-gray-600 line-clamp-2">
            {{ item.summary || item.description || '暂无简介' }}
          </p>

          <div class="mt-3 flex items-center gap-2 text-xs text-gray-500">
            <span>v{{ item.latest_version || item.version }}</span>
            <span v-if="item.installed" class="text-green-600">已安装</span>
            <span v-if="item.has_update" class="text-orange-600">可更新</span>
          </div>

          <button
            @click="openInstall(item)"
            :class="[
              'mt-4 w-full py-2 rounded-lg font-medium text-sm transition-colors',
              item.installed
                ? 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                : 'bg-blue-600 text-white hover:bg-blue-700',
            ]"
          >
            {{ item.has_update ? '更新' : item.installed ? '重新安装' : '安装' }}
          </button>
        </div>
      </div>

      <div v-if="marketItems.length === 0" class="text-center py-12 text-gray-500">
        暂无主题
      </div>
    </div>

    <!-- ===== 已装 ===== -->
    <div v-if="activeTab === 'installed' && !loading">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div
          v-for="item in installedItems"
          :key="item.theme"
          class="border border-gray-200 rounded-xl p-5"
        >
          <div class="flex items-center justify-between">
            <div>
              <h3 class="font-semibold text-gray-900">{{ item.name }}</h3>
              <p class="text-xs text-gray-500 mt-0.5">
                {{ item.source === 'builtin' ? '内置主题' : '已安装' }}
                <span v-if="item.version"> · v{{ item.version }}</span>
              </p>
            </div>
            <div class="flex gap-2">
              <span class="px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded">
                {{ item.files }} 文件
              </span>
              <span v-if="item.settings_count" class="px-2 py-1 bg-blue-100 text-blue-700 text-xs rounded">
                {{ item.settings_count }} 设置
              </span>
            </div>
          </div>
          <p v-if="item.description" class="mt-2 text-sm text-gray-600 line-clamp-2">
            {{ item.description }}
          </p>
        </div>
      </div>
    </div>

    <!-- ===== 我的模板 ===== -->
    <div v-if="activeTab === 'mine' && !loading">
      <div v-if="mySubmissions.length === 0" class="text-center py-12 text-gray-500">
        还没有提交过模板
      </div>
      <div v-else class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">名称</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">版本</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">状态</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">下载</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">提交时间</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-for="sub in mySubmissions" :key="sub.id">
              <td class="px-4 py-3">
                <div class="font-medium text-gray-900">{{ sub.name }}</div>
                <div class="text-xs text-gray-500">{{ sub.app_key }}</div>
              </td>
              <td class="px-4 py-3 text-sm text-gray-600">v{{ sub.version }}</td>
              <td class="px-4 py-3">
                <span :class="['px-2 py-1 text-xs rounded-full', statusColor(sub.status)]">
                  {{ statusLabel(sub.status) }}
                </span>
              </td>
              <td class="px-4 py-3 text-sm text-gray-600">{{ sub.download_count }}</td>
              <td class="px-4 py-3 text-sm text-gray-500">
                {{ new Date(sub.created_at).toLocaleDateString() }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ===== 开发指南 ===== -->
    <div v-if="activeTab === 'docs' && !loading">
      <div class="flex items-center justify-between mb-4">
        <p class="text-sm text-gray-600">
          模板开发文档。灌入知识库后，AI 能回答模板开发相关问题。
        </p>
        <button
          @click="importDocsToKb"
          :disabled="importingKb"
          class="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
        >
          {{ importingKb ? '导入中...' : '一键灌入知识库' }}
        </button>
      </div>

      <div v-if="kbImportResult" class="mb-4 p-3 bg-green-50 text-green-700 rounded-lg text-sm">
        {{ kbImportResult }}
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div
          v-for="doc in devDocs"
          :key="doc.id"
          @click="openDoc(doc.id)"
          class="border border-gray-200 rounded-xl p-4 cursor-pointer hover:shadow-md transition-shadow"
        >
          <h3 class="font-medium text-gray-900">{{ doc.title }}</h3>
          <p class="mt-1 text-xs text-gray-500 line-clamp-2">{{ doc.summary }}</p>
          <div class="mt-2 text-xs text-gray-400">{{ doc.filename }}</div>
        </div>
      </div>

      <!-- 文档内容弹窗 -->
      <div
        v-if="docContent"
        class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
        @click.self="docContent = ''"
      >
        <div class="bg-white rounded-xl max-w-4xl w-full max-h-[80vh] overflow-hidden flex flex-col">
          <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
            <h2 class="text-lg font-semibold text-gray-900">{{ docTitle }}</h2>
            <button @click="docContent = ''" class="text-gray-400 hover:text-gray-600">
              <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div class="flex-1 overflow-y-auto p-6">
            <pre class="whitespace-pre-wrap text-sm text-gray-700 font-mono">{{ docContent }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- 安装弹窗 -->
    <div
      v-if="showInstallDialog"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
      @click.self="showInstallDialog = false"
    >
      <div class="bg-white rounded-xl max-w-md w-full p-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-4">
          安装 {{ installTarget?.name }}
        </h2>

        <div v-if="!installTarget?.is_free" class="mb-4">
          <label class="block text-sm font-medium text-gray-700 mb-1">授权码</label>
          <input
            v-model="licenseKey"
            placeholder="请输入购买后获得的授权码"
            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <label class="flex items-center gap-2 mb-4">
          <input
            v-model="activateAfterInstall"
            type="checkbox"
            class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          />
          <span class="text-sm text-gray-700">安装后立即切换为生效主题</span>
        </label>

        <div class="flex gap-3">
          <button
            @click="showInstallDialog = false"
            class="flex-1 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50"
          >
            取消
          </button>
          <button
            @click="doInstall"
            :disabled="installing"
            class="flex-1 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {{ installing ? '安装中...' : '确认安装' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
