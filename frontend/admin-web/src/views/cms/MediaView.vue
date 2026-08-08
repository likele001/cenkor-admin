<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, onMounted, computed, watch } from 'vue'
import { api } from '@/lib/api'
import SearchInput from '@/components/SearchInput.vue'

interface MediaItem {
  id: number
  url: string
  mime: string
  size: number
  width: number | null
  height: number | null
  bucket: string
  key: string
  created_at: string
}

const media = ref<MediaItem[]>([])
const loading = ref(true)
const error = ref('')
const uploading = ref(false)
const dragOver = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const filter = ref<'all' | 'image' | 'doc'>('all')
const selected = ref<MediaItem | null>(null)
const copied = ref(false)
const search = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/api/v1/cms/media', {
      params: { page_size: 200, search: search.value || undefined },
    })
    media.value = data.items
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 't("caseEdit.loadFailed")'
  } finally {
    loading.value = false
  }
}

async function uploadFile(file: File) {
  uploading.value = true
  error.value = ''
  try {
    const fd = new FormData()
    fd.append('file', file)
    const { data } = await api.post('/api/v1/cms/media/upload', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    await load()
    console.log('t("media.上传成功")', data)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 't("media.上传失败")'
  } finally {
    uploading.value = false
  }
}

function handleDrop(e: DragEvent) {
  e.preventDefault()
  dragOver.value = false
  if (e.dataTransfer?.files) {
    Array.from(e.dataTransfer.files).forEach(uploadFile)
  }
}

function handleFileInput(e: Event) {
  const target = e.target as HTMLInputElement
  if (target.files) Array.from(target.files).forEach(uploadFile)
}

function formatSize(b: number): string {
  if (b < 1024) return b + ' B'
  if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' KB'
  return (b / 1024 / 1024).toFixed(1) + ' MB'
}

const filtered = computed(() => {
  if (filter.value === 'image') return media.value.filter(m => m.mime.startsWith('image/'))
  if (filter.value === 'doc') return media.value.filter(m => !m.mime.startsWith('image/'))
  return media.value
})

const stats = computed(() => ({
  total: media.value.length,
  images: media.value.filter(m => m.mime.startsWith('image/')).length,
  totalSize: media.value.reduce((s, m) => s + m.size, 0),
}))

async function del(m: MediaItem) {
  if (!confirm(`确定删除媒体 ${m.key} 吗？`)) return
  try {
    await api.delete(`/api/v1/cms/media/${m.id}`)
    selected.value = null
    await load()
  } catch (e: any) {
    alert('t("usersList.删除失败_1kc17l")' + (e?.response?.data?.detail || e.message))
  }
}

async function copyUrl(m: MediaItem) {
  try {
    await navigator.clipboard.writeText(m.url)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    // Fallback
    const ta = document.createElement('textarea')
    ta.value = m.url
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  }
}

function getPresignedUrl(m: MediaItem) {
  // 简化：直接用 public_url（生产应调 /media/{id}/signed-url）
  return m.url
}

onMounted(load)
watch(search, () => { load() })
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/" class="text-sm text-ink-500 hover:text-ink-900">← Dashboard</router-link>
        <span class="font-semibold">{{ t('media.媒体库_dnl4i') }}</span>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-10">
      <!-- 统计 -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        <div class="card text-center">
          <div class="text-3xl font-semibold">{{ stats.total }}</div>
          <div class="text-sm text-ink-500 mt-1">{{ t('media.总文件数_ck7e1y') }}</div>
        </div>
        <div class="card text-center">
          <div class="text-3xl font-semibold">{{ stats.images }}</div>
          <div class="text-sm text-ink-500 mt-1">{{ t('media.图片_ff9l') }}</div>
        </div>
        <div class="card text-center">
          <div class="text-3xl font-semibold">{{ formatSize(stats.totalSize) }}</div>
          <div class="text-sm text-ink-500 mt-1">{{ t('media.总大小_ej39f') }}</div>
        </div>
      </div>

      <!-- 筛选 + 搜索 -->
      <div class="flex flex-wrap items-center gap-3 mb-4">
        <div class="flex gap-2">
          <button @click="filter = 'all'" :class="filter === 'all' ? 'bg-ink-900 text-white' : 'bg-white border border-ink-200 text-ink-700'" class="px-3 py-1.5 rounded-full text-sm">{{ t('media.全部_en40') }}</button>
          <button @click="filter = 'image'" :class="filter === 'image' ? 'bg-ink-900 text-white' : 'bg-white border border-ink-200 text-ink-700'" class="px-3 py-1.5 rounded-full text-sm">{{ t('media.图片_ff9l') }}</button>
          <button @click="filter = 'doc'" :class="filter === 'doc' ? 'bg-ink-900 text-white' : 'bg-white border border-ink-200 text-ink-700'" class="px-3 py-1.5 rounded-full text-sm">{{ t('media.文档_hubg') }}</button>
        </div>
        <SearchInput v-model="search" :placeholder="t('media.按_xd7i7v')" />
      </div>

      <!-- 上传区 -->
      <div
        class="card mb-6 text-center cursor-pointer transition-colors"
        :class="dragOver ? 'border-accent bg-accent-light' : ''"
        @click="fileInput?.click()"
        @dragover.prevent="dragOver = true"
        @dragleave="dragOver = false"
        @drop="handleDrop"
      >
        <input ref="fileInput" type="file" multiple class="hidden" @change="handleFileInput" />
        <div v-if="uploading" class="text-ink-500">{{ t('media.上传中_a6b52n') }}</div>
        <div v-else>
          <div class="text-3xl mb-2">📁</div>
          <p class="text-sm text-ink-600">{{ t('media.点击或拖_1ypob7') }}</p>
          <p class="text-xs text-ink-400 mt-1">{{ t('media.图片自动_hn4nmi') }}</p>
        </div>
      </div>

      <div v-if="error" class="card mb-4 text-red-600">⚠️ {{ error }}</div>

      <!-- 媒体列表 -->
      <div v-if="loading" class="card text-ink-500">{{ t('usersList.加载中_b0k5km') }}</div>
      <div v-else-if="filtered.length === 0" class="card text-center text-ink-400 py-12">
        {{ t('media.暂无媒体') }}
      </div>
      <div v-else class="grid grid-cols-1 sm:grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
        <div
          v-for="m in filtered" :key="m.id"
          class="card !p-3 group cursor-pointer hover:shadow-lg transition-shadow"
          :class="selected?.id === m.id ? 'ring-2 ring-accent' : ''"
          @click="selected = m"
        >
          <div class="aspect-square rounded-xl overflow-hidden bg-ink-100 mb-2 flex items-center justify-center relative">
            <img v-if="m.mime.startsWith('image/')" :src="m.url" class="w-full h-full object-cover" loading="lazy" />
            <span v-else class="text-3xl">📄</span>
            <span v-if="m.width && m.height" class="absolute bottom-1 right-1 text-[10px] px-1.5 py-0.5 rounded bg-ink-900/70 text-white">
              {{ m.width }}×{{ m.height }}
            </span>
          </div>
          <div class="text-xs text-ink-700 truncate" :title="m.key">{{ m.key.split('/').pop() }}</div>
          <div class="flex items-center justify-between mt-1">
            <span class="text-xs text-ink-400">{{ formatSize(m.size) }}</span>
            <span class="text-xs text-ink-400 opacity-0 group-hover:opacity-100 transition">
              {{ m.mime.split('/')[1]?.toUpperCase() }}
            </span>
          </div>
        </div>
      </div>

      <!-- 详情侧栏（选中时显示）-->
      <div v-if="selected" class="fixed bottom-6 right-6 w-full sm:w-96 card !p-5 shadow-2xl z-40">
        <div class="flex items-start justify-between mb-3">
          <h3 class="font-semibold">{{ t('media.媒体详情_brjfj4') }}</h3>
          <button @click="selected = null" class="text-ink-400 hover:text-ink-900">✕</button>
        </div>
        <div v-if="selected.mime.startsWith('image/')" class="aspect-video rounded-lg overflow-hidden bg-ink-100 mb-3">
          <img :src="selected.url" class="w-full h-full object-contain" />
        </div>
        <dl class="text-sm space-y-1.5">
          <div class="flex justify-between"><dt class="text-ink-500">{{ t('media.文件名_f98ri') }}</dt><dd class="font-mono text-xs truncate ml-2">{{ selected.key.split('/').pop() }}</dd></div>
          <div class="flex justify-between"><dt class="text-ink-500">{{ t('media.类型_lnjk') }}</dt><dd>{{ selected.mime }}</dd></div>
          <div class="flex justify-between"><dt class="text-ink-500">{{ t('media.大小_fo3s') }}</dt><dd>{{ formatSize(selected.size) }}</dd></div>
          <div v-if="selected.width && selected.height" class="flex justify-between"><dt class="text-ink-500">{{ t('media.尺寸_g6wu') }}</dt><dd>{{ selected.width }} × {{ selected.height }} px</dd></div>
          <div class="flex justify-between"><dt class="text-ink-500">{{ t('media.上传_dphy') }}</dt><dd class="text-xs">{{ selected.created_at?.slice(0, 19) }}</dd></div>
        </dl>
        <div class="mt-4 space-y-2">
          <input :value="selected.url" readonly class="input text-xs font-mono" />
          <div class="flex gap-2">
            <button @click="copyUrl(selected)" class="btn-outline flex-1 text-sm">
              {{ copied ? '✓ 已复制' : '复制 URL' }}
            </button>
            <a :href="getPresignedUrl(selected)" target="_blank" class="btn-ghost text-sm">{{ t('media.打开_h8ul') }}</a>
            <button @click="del(selected)" class="text-sm text-red-600 hover:underline px-2">{{ t('usersList.删除_eslg') }}</button>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>
