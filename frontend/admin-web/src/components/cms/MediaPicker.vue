<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { api } from '@/lib/api'

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

const props = defineProps<{
  visible: boolean
  multiple?: boolean
}>()

const emit = defineEmits<{
  close: []
  select: [urls: string[]]
}>()

const media = ref<MediaItem[]>([])
const loading = ref(false)
const error = ref('')
const search = ref('')
const selected = ref<Set<number>>(new Set())
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

async function load() {
  if (!props.visible) return
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/api/v1/cms/media', {
      params: { page_size: 200, search: search.value || undefined }
    })
    media.value = (data.items || []).filter((m: MediaItem) => m.mime.startsWith('image/'))
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载媒体库失败'
  } finally {
    loading.value = false
  }
}

function toggleSelect(m: MediaItem) {
  if (props.multiple) {
    const next = new Set(selected.value)
    if (next.has(m.id)) next.delete(m.id)
    else next.add(m.id)
    selected.value = next
  } else {
    selected.value = new Set([m.id])
  }
}

function confirm() {
  const urls = media.value.filter(m => selected.value.has(m.id)).map(m => m.url)
  emit('select', urls)
  emit('close')
}

function openFilePicker() {
  fileInput.value?.click()
}

async function handleFileUpload(e: Event) {
  const files = (e.target as HTMLInputElement).files
  if (!files?.length) return
  uploading.value = true
  error.value = ''
  try {
    for (const f of files) {
      const fd = new FormData()
      fd.append('file', f)
      const { data } = await api.post('/api/v1/cms/media/upload', fd, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      // 构造媒体项并直接加入列表、自动选中
      const item: MediaItem = {
        id: data.id,
        url: data.url,
        mime: data.mime || 'image/*',
        size: data.size || 0,
        width: null,
        height: null,
        bucket: data.bucket || '',
        key: data.key || (data.url ? data.url.split('/').pop() : ''),
        created_at: new Date().toISOString()
      }
      media.value.unshift(item)
      if (props.multiple) selected.value = new Set([...Array.from(selected.value), item.id])
      else selected.value = new Set([item.id])
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '上传失败'
  } finally {
    uploading.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

function formatSize(b: number): string {
  if (b < 1024) return b + ' B'
  if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' KB'
  return (b / 1024 / 1024).toFixed(1) + ' MB'
}

function onImageLoadError(e: Event) {
  const target = e.currentTarget as HTMLElement | null
  if (target) target.style.display = 'none'
}

onMounted(load)
watch(() => props.visible, (v) => {
  if (v) {
    selected.value = new Set()
    load()
  }
})
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="mp-overlay" @click.self="emit('close')">
      <div class="mp-modal" @click.stop>
        <div class="mp-header">
          <h3 class="mp-title">{{ multiple ? '从媒体库选择图片（可多选）' : '从媒体库选择图片' }}</h3>
          <button type="button" class="mp-close" @click="emit('close')">✕</button>
        </div>

        <div class="mp-toolbar">
          <input
            v-model="search"
            type="text"
            class="mp-search"
            placeholder="搜索文件名..."
            @keyup.enter="load"
          />
          <button
            type="button"
            class="mp-upload-btn"
            :disabled="uploading"
            @click="openFilePicker"
          >
            {{ uploading ? '上传中...' : '⬆️ 上传新图' }}
          </button>
          <input
            ref="fileInput"
            type="file"
            accept="image/*"
            multiple
            class="hidden"
            @change="handleFileUpload"
          />
        </div>

        <div v-if="error" class="mp-error">⚠️ {{ error }}</div>
        <div v-if="loading" class="mp-loading">加载中...</div>
        <div v-else-if="media.length === 0" class="mp-empty">暂无图片，请上传或搜索其他关键词</div>
        <div v-else class="mp-grid">
          <div
            v-for="m in media"
            :key="m.id"
            class="mp-item"
            :class="{ selected: selected.has(m.id) }"
            @click="toggleSelect(m)"
          >
            <div class="mp-thumb-wrap">
              <img :src="m.url" class="mp-thumb" loading="lazy" @error="onImageLoadError" />
            </div>
            <div class="mp-meta">
              <div class="mp-name" :title="m.key">{{ (m.key || m.url).split('/').pop() }}</div>
              <div class="mp-size">{{ formatSize(m.size) }}</div>
            </div>
            <div v-if="selected.has(m.id)" class="mp-check">✓</div>
          </div>
        </div>

        <div class="mp-footer">
          <span class="mp-count">已选 {{ selected.size }} 张</span>
          <div class="mp-actions">
            <button type="button" class="mp-btn cancel" @click="emit('close')">取消</button>
            <button type="button" class="mp-btn confirm" :disabled="selected.size === 0" @click="confirm">
              确定
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.mp-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.mp-modal {
  background: #ffffff;
  border-radius: 12px;
  width: 100%;
  max-width: 900px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.2);
  overflow: hidden;
}

.mp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #e5e7eb;
}

.mp-title {
  font-size: 16px;
  font-weight: 600;
  color: #111827;
  margin: 0;
}

.mp-close {
  background: transparent;
  border: none;
  font-size: 18px;
  color: #6b7280;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
}

.mp-close:hover {
  background: #f3f4f6;
  color: #111827;
}

.mp-toolbar {
  display: flex;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid #e5e7eb;
}

.mp-search {
  flex: 1;
  padding: 8px 12px;
  border: 1.5px solid #e5e7eb;
  border-radius: 8px;
  font-size: 14px;
  outline: none;
}

.mp-search:focus {
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.mp-upload-btn {
  padding: 8px 14px;
  background: #eff6ff;
  color: #3b82f6;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s ease;
}

.mp-upload-btn:hover:not(:disabled) {
  background: #dbeafe;
}

.mp-upload-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.mp-error,
.mp-loading,
.mp-empty {
  padding: 40px 20px;
  text-align: center;
  color: #6b7280;
  font-size: 14px;
}

.mp-error {
  color: #ef4444;
}

.mp-grid {
  flex: 1;
  overflow-y: auto;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
  padding: 16px 20px;
}

.mp-item {
  position: relative;
  border: 2px solid #e5e7eb;
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  background: #f9fafb;
  transition: all 0.2s ease;
}

.mp-item:hover {
  border-color: #3b82f6;
}

.mp-item.selected {
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
}

.mp-thumb-wrap {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: #f3f4f6;
}

.mp-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.mp-meta {
  padding: 8px;
  background: #ffffff;
  border-top: 1px solid #e5e7eb;
}

.mp-name {
  font-size: 11px;
  color: #374151;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mp-size {
  font-size: 10px;
  color: #9ca3af;
  margin-top: 2px;
}

.mp-check {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 22px;
  height: 22px;
  background: #3b82f6;
  color: #ffffff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: bold;
}

.mp-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-top: 1px solid #e5e7eb;
  background: #f9fafb;
}

.mp-count {
  font-size: 13px;
  color: #6b7280;
}

.mp-actions {
  display: flex;
  gap: 8px;
}

.mp-btn {
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  border: none;
  transition: background 0.2s ease;
}

.mp-btn.cancel {
  background: #ffffff;
  color: #374151;
  border: 1px solid #d1d5db;
}

.mp-btn.cancel:hover {
  background: #f3f4f6;
}

.mp-btn.confirm {
  background: #3b82f6;
  color: #ffffff;
}

.mp-btn.confirm:hover:not(:disabled) {
  background: #2563eb;
}

.mp-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.hidden {
  display: none;
}
</style>
