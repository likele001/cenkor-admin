<script setup lang="ts">
import { computed, ref } from 'vue'
import MediaPicker from './MediaPicker.vue'

export interface FieldDef {
  id: number
  field_key: string
  label: string
  field_type: string
  required: boolean
  default_value: string | null
  options: Record<string, any> | null
  validation: Record<string, any> | null
  group_id: number | null
  sort: number
  status: string
  field_options: { id: number; value: string; label: string; color: string | null; sort: number }[]
}

const props = defineProps<{
  definition: FieldDef
  modelValue: any
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: any]
}>()

const fieldValue = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const uploading = ref(false)
const uploadError = ref('')

// 媒体库选择弹窗状态
const pickerVisible = ref(false)
const pickerMultiple = ref(false)

function openMediaPicker(multiple: boolean) {
  pickerMultiple.value = multiple
  pickerVisible.value = true
}

function onMediaSelected(urls: string[]) {
  if (!urls.length) return
  if (pickerMultiple.value) {
    const current = [...(fieldValue.value || [])]
    for (const u of urls) {
      if (!current.includes(u)) current.push(u)
    }
    fieldValue.value = current
  } else {
    fieldValue.value = urls[0]
  }
}

const validation = computed(() => props.definition.validation || {})

// 字段图标映射
const fieldIcon = computed(() => {
  const map: Record<string, string> = {
    text: '✏️',
    longtext: '📝',
    richtext: '📄',
    markdown: '📋',
    number: '🔢',
    boolean: '☑️',
    date: '📅',
    datetime: '🕐',
    url: '🔗',
    email: '📧',
    phone: '📱',
    image: '🖼️',
    images: '📸',
    file: '📎',
    files: '📁',
    select: '📊',
    multiselect: '☑️',
    color: '🎨',
    json: '💻',
    repeater: '📑',
    relation: '🔗',
  }
  return map[props.definition.field_type] || '📌'
})

// 字段类型描述
const fieldTypeDesc = computed(() => {
  const map: Record<string, string> = {
    text: '文本',
    longtext: '长文本',
    richtext: '富文本',
    markdown: 'Markdown',
    number: '数字',
    boolean: '布尔值',
    date: '日期',
    datetime: '日期时间',
    url: '链接',
    email: '邮箱',
    phone: '电话',
    image: '单图',
    images: '多图',
    file: '文件',
    files: '多文件',
    select: '单选',
    multiselect: '多选',
    color: '颜色',
    json: 'JSON',
    repeater: '重复组',
    relation: '关联',
  }
  return map[props.definition.field_type] || '文本'
})

const placeholder = computed(() => {
  const map: Record<string, string> = {
    text: '请输入文本...',
    longtext: '请输入内容...',
    richtext: '支持 HTML 格式...',
    markdown: '支持 Markdown 语法...',
    number: '请输入数字',
    url: 'https://example.com',
    email: 'name@example.com',
    phone: '请输入手机号',
    json: '{\n  "key": "value"\n}',
  }
  return map[props.definition.field_type] || ''
})

function onNumberInput(e: Event) {
  const val = (e.target as HTMLInputElement).value
  fieldValue.value = val === '' ? null : Number(val)
}

function onFileUpload(type: 'image' | 'file') {
  const input = document.createElement('input')
  input.type = 'file'
  if (type === 'image') input.accept = 'image/*'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    uploading.value = true
    uploadError.value = ''
    try {
      const { api } = await import('@/lib/api')
      const { data } = await api.post('/api/v1/cms/media/upload', formData)
      fieldValue.value = data.url
    } catch (e: any) {
      uploadError.value = e?.response?.data?.detail || '上传失败'
    } finally {
      uploading.value = false
    }
  }
  input.click()
}

function onMultiFileUpload(type: 'images' | 'files') {
  const input = document.createElement('input')
  input.type = 'file'
  input.multiple = true
  if (type === 'images') input.accept = 'image/*'
  input.onchange = async () => {
    const files = input.files
    if (!files?.length) return
    uploading.value = true
    uploadError.value = ''
    try {
      const urls = [...(fieldValue.value || [])]
      for (const f of files) {
        const fd = new FormData()
        fd.append('file', f)
        const { api } = await import('@/lib/api')
        const { data } = await api.post('/api/v1/cms/media/upload', fd)
        urls.push(data.url)
      }
      fieldValue.value = urls
    } catch (e: any) {
      uploadError.value = e?.response?.data?.detail || '上传失败'
    } finally {
      uploading.value = false
    }
  }
  input.click()
}

function addRepeaterRow() {
  const arr = fieldValue.value || []
  arr.push({})
  fieldValue.value = [...arr]
}

function removeRepeaterRow(index: number) {
  const arr = fieldValue.value || []
  arr.splice(index, 1)
  fieldValue.value = [...arr]
}

function toggleMultiSelect(optValue: string) {
  const arr: string[] = [...(fieldValue.value || [])]
  const idx = arr.indexOf(optValue)
  if (idx >= 0) arr.splice(idx, 1)
  else arr.push(optValue)
  fieldValue.value = arr
}

function removeImage(index: number) {
  const arr = [...(fieldValue.value || [])]
  arr.splice(index, 1)
  fieldValue.value = arr
}

function updateImageUrl(index: number, url: string) {
  const arr = [...(fieldValue.value || [])]
  arr[index] = url
  fieldValue.value = arr
}

function onImageError(e: Event) {
  const img = e.target as HTMLImageElement
  if (img) {
    img.src = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMDAiIGhlaWdodD0iMTAwIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjZjBmMGYwIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtc2l6ZT0iMTQiIGZpbGw9IiM5OTkiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGR5PSIuM2VtIj7ljJZES+mihjwvdGV4dD48L3N2Zz4='
  }
}
</script>

<template>
  <div class="field-renderer">
    <!-- 字段标签 -->
    <label class="field-label">
      <span class="field-icon">{{ fieldIcon }}</span>
      <span class="field-name">{{ definition.label }}</span>
      <span class="field-type">{{ fieldTypeDesc }}</span>
      <span v-if="definition.required" class="required-mark">*</span>
    </label>

    <!-- text -->
    <div v-if="definition.field_type === 'text'" class="field-input-wrapper">
      <input v-model="fieldValue" type="text" class="field-input" :placeholder="placeholder" :disabled="disabled"
        :maxlength="validation.max_length" />
    </div>

    <!-- longtext -->
    <div v-else-if="definition.field_type === 'longtext'" class="field-input-wrapper">
      <textarea v-model="fieldValue" class="field-textarea" :placeholder="placeholder" :disabled="disabled"
        :maxlength="validation.max_length" rows="4"></textarea>
    </div>

    <!-- richtext -->
    <div v-else-if="definition.field_type === 'richtext'" class="field-input-wrapper">
      <div class="rich-text-toolbar">HTML 编辑器</div>
      <textarea v-model="fieldValue" class="field-textarea field-code" :placeholder="placeholder" :disabled="disabled"
        rows="6"></textarea>
    </div>

    <!-- markdown -->
    <div v-else-if="definition.field_type === 'markdown'" class="field-input-wrapper">
      <div class="rich-text-toolbar">Markdown 编辑器</div>
      <textarea v-model="fieldValue" class="field-textarea field-code" :placeholder="placeholder" :disabled="disabled"
        rows="6"></textarea>
    </div>

    <!-- number -->
    <div v-else-if="definition.field_type === 'number'" class="field-input-wrapper">
      <div class="number-input-wrapper">
        <input type="number" class="field-input number-input" :value="fieldValue" :placeholder="placeholder"
          :disabled="disabled" :min="validation.min" :max="validation.max" :step="validation.step || 1"
          @input="onNumberInput" />
        <span v-if="validation.unit" class="unit-badge">{{ validation.unit }}</span>
      </div>
      <div v-if="validation.min !== undefined || validation.max !== undefined" class="validation-hint">
        <span v-if="validation.min !== undefined">最小: {{ validation.min }}</span>
        <span v-if="validation.max !== undefined">最大: {{ validation.max }}</span>
      </div>
    </div>

    <!-- boolean -->
    <div v-else-if="definition.field_type === 'boolean'" class="field-input-wrapper">
      <label class="boolean-toggle">
        <div class="toggle-switch" :class="{ active: !!fieldValue }">
          <input type="checkbox" :checked="!!fieldValue" :disabled="disabled"
            @change="fieldValue = ($event.target as HTMLInputElement).checked" class="toggle-input" />
          <span class="toggle-slider"></span>
        </div>
        <span class="toggle-label">{{ fieldValue ? '是' : '否' }}</span>
      </label>
    </div>

    <!-- date -->
    <div v-else-if="definition.field_type === 'date'" class="field-input-wrapper">
      <div class="date-input-wrapper">
        <span class="date-icon">📅</span>
        <input v-model="fieldValue" type="date" class="field-input date-input" :disabled="disabled" />
      </div>
    </div>

    <!-- datetime -->
    <div v-else-if="definition.field_type === 'datetime'" class="field-input-wrapper">
      <div class="date-input-wrapper">
        <span class="date-icon">🕐</span>
        <input v-model="fieldValue" type="datetime-local" class="field-input date-input" :disabled="disabled" />
      </div>
    </div>

    <!-- url -->
    <div v-else-if="definition.field_type === 'url'" class="field-input-wrapper">
      <div class="url-input-wrapper">
        <span class="url-icon">🔗</span>
        <input v-model="fieldValue" type="url" class="field-input url-input" :placeholder="placeholder"
          :disabled="disabled" />
      </div>
      <a v-if="fieldValue" :href="fieldValue" target="_blank" class="preview-link">
        🔗 在新窗口打开链接
      </a>
    </div>

    <!-- email -->
    <div v-else-if="definition.field_type === 'email'" class="field-input-wrapper">
      <div class="url-input-wrapper">
        <span class="url-icon">📧</span>
        <input v-model="fieldValue" type="email" class="field-input url-input" :placeholder="placeholder"
          :disabled="disabled" />
      </div>
    </div>

    <!-- phone -->
    <div v-else-if="definition.field_type === 'phone'" class="field-input-wrapper">
      <div class="url-input-wrapper">
        <span class="url-icon">📱</span>
        <input v-model="fieldValue" type="tel" class="field-input url-input" :placeholder="placeholder"
          :disabled="disabled" />
      </div>
    </div>

    <!-- image -->
    <div v-else-if="definition.field_type === 'image'" class="field-input-wrapper">
        <div v-if="fieldValue" class="image-preview-single">
        <div class="image-card">
          <img :src="fieldValue" class="preview-img" @error="onImageError" />
          <div class="image-actions">
            <button type="button" class="action-btn replace" :disabled="disabled || uploading" @click="onFileUpload('image')">
              {{ uploading ? '⏳' : '🔄' }} 替换
            </button>
            <button type="button" class="action-btn pick" :disabled="disabled || uploading" @click="openMediaPicker(false)">
              📚 从媒体库选择
            </button>
            <button type="button" class="action-btn delete" @click="fieldValue = ''">
              🗑️ 删除
            </button>
          </div>
        </div>
        <input v-model="fieldValue" type="url" class="field-input image-url-input" placeholder="图片 URL" :disabled="disabled" />
      </div>
      <div v-else>
        <div class="upload-zone" @click="!disabled && onFileUpload('image')" :class="{ disabled, uploading }">
          <div class="upload-icon">🖼️</div>
          <div class="upload-text">{{ uploading ? '上传中...' : '点击上传图片' }}</div>
          <div class="upload-hint">支持 JPG、PNG、GIF、WebP 格式</div>
        </div>
        <div class="media-picker-trigger">
          <button type="button" class="picker-link" :disabled="disabled || uploading" @click="openMediaPicker(false)">
            📚 或从媒体库选择
          </button>
        </div>
      </div>
      <p v-if="uploadError" class="error-text">{{ uploadError }}</p>
    </div>

    <!-- images -->
    <div v-else-if="definition.field_type === 'images'" class="field-input-wrapper">
      <div class="images-grid">
        <div v-for="(url, i) in (fieldValue || [])" :key="i" class="image-card">
          <img :src="url" class="preview-img" @error="onImageError" />
          <div class="image-overlay">
            <button type="button" class="overlay-btn" @click="removeImage(i)">🗑️</button>
          </div>
          <input :value="url" type="url" class="image-url-input" placeholder="图片 URL"
            @input="updateImageUrl(i, ($event.target as HTMLInputElement).value)" />
        </div>
        <div class="upload-zone add-more" @click="!disabled && onMultiFileUpload('images')"
          :class="{ disabled, uploading }">
          <div class="upload-icon">➕</div>
          <div class="upload-text">{{ uploading ? '上传中...' : '添加图片' }}</div>
        </div>
      </div>
      <div class="media-picker-trigger">
        <button type="button" class="picker-link" :disabled="disabled || uploading" @click="openMediaPicker(true)">
          📚 从媒体库选择
        </button>
      </div>
      <p v-if="uploadError" class="error-text">{{ uploadError }}</p>
    </div>

    <!-- file -->
    <div v-else-if="definition.field_type === 'file'" class="field-input-wrapper">
      <div v-if="fieldValue" class="file-preview">
        <div class="file-card">
          <span class="file-icon">📄</span>
          <span class="file-name">{{ (fieldValue as string).split('/').pop() || '文件' }}</span>
          <button type="button" class="action-btn replace" :disabled="disabled || uploading"
            @click="onFileUpload('file')">{{ uploading ? '⏳' : '🔄' }}</button>
          <button type="button" class="action-btn delete" @click="fieldValue = ''">🗑️</button>
        </div>
        <input v-model="fieldValue" type="url" class="field-input" placeholder="文件 URL" :disabled="disabled" />
      </div>
      <div v-else class="upload-zone file-zone" @click="!disabled && onFileUpload('file')" :class="{ disabled, uploading }">
        <div class="upload-icon">📎</div>
        <div class="upload-text">{{ uploading ? '上传中...' : '点击上传文件' }}</div>
      </div>
      <p v-if="uploadError" class="error-text">{{ uploadError }}</p>
    </div>

    <!-- files -->
    <div v-else-if="definition.field_type === 'files'" class="field-input-wrapper">
      <div class="file-list">
        <div v-for="(url, i) in (fieldValue || [])" :key="i" class="file-card">
          <span class="file-icon">📄</span>
          <input :value="url" type="url" class="field-input flex-1" placeholder="文件 URL"
            @input="($event: Event) => { const arr = [...(fieldValue || [])]; arr[i] = ($event.target as HTMLInputElement).value; fieldValue = arr }" />
          <button type="button" class="action-btn delete" @click="($event: Event) => { const arr = [...(fieldValue || [])]; arr.splice(i, 1); fieldValue = arr }">🗑️</button>
        </div>
        <button type="button" class="add-file-btn" :disabled="disabled || uploading"
          @click="onMultiFileUpload('files')">
          <span class="btn-icon">📎</span>
          <span>{{ uploading ? '上传中...' : '添加文件' }}</span>
        </button>
      </div>
      <p v-if="uploadError" class="error-text">{{ uploadError }}</p>
    </div>

    <!-- select -->
    <div v-else-if="definition.field_type === 'select'" class="field-input-wrapper">
      <div class="select-wrapper">
        <select v-model="fieldValue" class="field-select" :disabled="disabled">
          <option value="" disabled>请选择 {{ definition.label }}</option>
          <option v-for="opt in definition.field_options" :key="opt.id" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
        <span class="select-arrow">▼</span>
      </div>
      <p v-if="!definition.field_options?.length" class="warning-text">
        ⚠️ 请先在字段定义中添加选项
      </p>
    </div>

    <!-- multiselect -->
    <div v-else-if="definition.field_type === 'multiselect'" class="field-input-wrapper">
      <div class="multiselect-options">
        <label v-for="opt in definition.field_options" :key="opt.id" class="option-chip"
          :class="{ selected: (fieldValue || []).includes(opt.value) }">
          <input type="checkbox" :checked="(fieldValue || []).includes(opt.value)" :disabled="disabled"
            @change="toggleMultiSelect(opt.value)" class="hidden-checkbox" />
          <span v-if="opt.color" class="option-dot" :style="{ backgroundColor: opt.color }"></span>
          <span class="option-label">{{ opt.label }}</span>
          <span v-if="(fieldValue || []).includes(opt.value)" class="check-icon">✓</span>
        </label>
      </div>
      <p v-if="!definition.field_options?.length" class="warning-text">
        ⚠️ 请先在字段定义中添加选项
      </p>
    </div>

    <!-- color -->
    <div v-else-if="definition.field_type === 'color'" class="field-input-wrapper">
      <div class="color-picker-wrapper">
        <div class="color-preview" :style="{ backgroundColor: fieldValue || '#f0f0f0' }">
          <input v-model="fieldValue" type="color" class="color-input" :disabled="disabled" />
        </div>
        <div class="color-values">
          <input v-model="fieldValue" type="text" class="field-input color-hex" placeholder="#000000"
            :disabled="disabled" />
          <div class="color-suggestions">
            <button v-for="c in ['#000000', '#ffffff', '#ef4444', '#f97316', '#f59e0b', '#84cc16', '#10b981', '#06b6d4', '#3b82f6', '#8b5cf6', '#d946ef', '#f43f5e']"
              :key="c" type="button" class="color-swatch" :style="{ backgroundColor: c }"
              @click="fieldValue = c" :disabled="disabled"></button>
          </div>
        </div>
      </div>
    </div>

    <!-- json -->
    <div v-else-if="definition.field_type === 'json'" class="field-input-wrapper">
      <div class="json-editor">
        <textarea :value="typeof fieldValue === 'string' ? fieldValue : JSON.stringify(fieldValue, null, 2)"
          class="field-textarea field-code" :disabled="disabled" rows="8"
          @input="($event: Event) => { try { fieldValue = JSON.parse(($event.target as HTMLTextAreaElement).value) } catch { fieldValue = ($event.target as HTMLTextAreaElement).value } }"
          :placeholder="placeholder"></textarea>
      </div>
    </div>

    <!-- repeater -->
    <div v-else-if="definition.field_type === 'repeater'" class="field-input-wrapper">
      <div class="repeater-list">
        <div v-for="(_, i) in (fieldValue || [])" :key="i" class="repeater-item">
          <div class="repeater-header">
            <span class="repeater-number">#{{ i + 1 }}</span>
            <button type="button" class="action-btn delete" @click="removeRepeaterRow(i)">🗑️ 删除</button>
          </div>
          <textarea :value="JSON.stringify(fieldValue[i], null, 2)" class="field-textarea field-code"
            :disabled="disabled" rows="4"
            @input="($event: Event) => { try { (fieldValue as any[])[i] = JSON.parse(($event.target as HTMLTextAreaElement).value); fieldValue = [...fieldValue] } catch {} }"></textarea>
        </div>
        <button type="button" class="add-repeater-btn" :disabled="disabled" @click="addRepeaterRow">
          <span class="btn-icon">➕</span>
          <span>添加行</span>
        </button>
      </div>
    </div>

    <!-- relation -->
    <div v-else-if="definition.field_type === 'relation'" class="field-input-wrapper">
      <div class="relation-input">
        <span class="relation-icon">🔗</span>
        <input v-model="fieldValue" type="number" class="field-input relation-field" placeholder="关联内容 ID"
          :disabled="disabled" />
        <span class="relation-hint">输入关联内容的 ID</span>
      </div>
    </div>

    <!-- fallback -->
    <div v-else class="field-input-wrapper">
      <input v-model="fieldValue" type="text" class="field-input" :disabled="disabled" />
    </div>
  </div>

  <MediaPicker
    :visible="pickerVisible"
    :multiple="pickerMultiple"
    @close="pickerVisible = false"
    @select="onMediaSelected"
  />
</template>

<style scoped>
.field-renderer {
  background: #ffffff;
  border-radius: 12px;
  padding: 16px;
  border: 1px solid #e5e7eb;
  transition: all 0.2s ease;
}

.field-renderer:hover {
  border-color: #d1d5db;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.field-label {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
}

.field-icon {
  font-size: 18px;
  line-height: 1;
}

.field-name {
  color: #111827;
}

.field-type {
  font-size: 11px;
  color: #9ca3af;
  font-weight: 500;
  padding: 2px 8px;
  background: #f3f4f6;
  border-radius: 4px;
  margin-left: auto;
}

.required-mark {
  color: #ef4444;
  font-size: 14px;
}

.field-input-wrapper {
  position: relative;
}

.field-input,
.field-textarea,
.field-select {
  width: 100%;
  padding: 10px 14px;
  border: 1.5px solid #e5e7eb;
  border-radius: 8px;
  font-size: 14px;
  color: #374151;
  background: #ffffff;
  transition: all 0.2s ease;
  outline: none;
}

.field-input:focus,
.field-textarea:focus,
.field-select:focus {
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.field-input:disabled,
.field-textarea:disabled,
.field-select:disabled {
  background: #f9fafb;
  color: #9ca3af;
  cursor: not-allowed;
}

.field-textarea {
  resize: vertical;
  font-family: inherit;
  line-height: 1.6;
}

.field-code {
  font-family: 'Monaco', 'Consolas', 'Courier New', monospace;
  font-size: 13px;
  background: #f8fafc;
}

/* 富文本编辑器 */
.rich-text-toolbar {
  background: #f3f4f6;
  padding: 6px 12px;
  font-size: 12px;
  color: #6b7280;
  border-radius: 8px 8px 0 0;
  border: 1.5px solid #e5e7eb;
  border-bottom: none;
}

.rich-text-toolbar+.field-textarea {
  border-radius: 0 0 8px 8px;
}

/* 数字输入 */
.number-input-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

.number-input {
  text-align: right;
}

.unit-badge {
  padding: 4px 10px;
  background: #eff6ff;
  color: #3b82f6;
  font-size: 12px;
  font-weight: 600;
  border-radius: 6px;
  white-space: nowrap;
}

.validation-hint {
  display: flex;
  gap: 12px;
  margin-top: 6px;
  font-size: 12px;
  color: #9ca3af;
}

/* 布尔开关 */
.boolean-toggle {
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
}

.toggle-switch {
  position: relative;
  width: 48px;
  height: 26px;
  background: #e5e7eb;
  border-radius: 13px;
  transition: background 0.3s ease;
}

.toggle-switch.active {
  background: #3b82f6;
}

.toggle-input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 20px;
  height: 20px;
  background: white;
  border-radius: 50%;
  transition: transform 0.3s ease;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.toggle-switch.active .toggle-slider {
  transform: translateX(22px);
}

.toggle-label {
  font-size: 14px;
  color: #374151;
  font-weight: 500;
}

/* 日期输入 */
.date-input-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

.date-icon {
  font-size: 18px;
}

.date-input {
  flex: 1;
}

/* URL 输入 */
.url-input-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

.url-icon {
  font-size: 18px;
  flex-shrink: 0;
}

.url-input {
  flex: 1;
}

.preview-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
  font-size: 13px;
  color: #3b82f6;
  text-decoration: none;
  font-weight: 500;
}

.preview-link:hover {
  text-decoration: underline;
}

/* 上传区域 */
.upload-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 24px;
  border: 2px dashed #d1d5db;
  border-radius: 12px;
  background: #f9fafb;
  cursor: pointer;
  transition: all 0.2s ease;
}

.upload-zone:hover {
  border-color: #3b82f6;
  background: #eff6ff;
}

.upload-zone.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.upload-zone.uploading {
  opacity: 0.7;
}

.upload-icon {
  font-size: 32px;
  line-height: 1;
}

.upload-text {
  font-size: 14px;
  font-weight: 600;
  color: #374151;
}

.upload-hint {
  font-size: 12px;
  color: #9ca3af;
}

/* 图片预览 */
.image-preview-single {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.image-card {
  position: relative;
  border-radius: 12px;
  overflow: hidden;
  border: 1.5px solid #e5e7eb;
  background: #f9fafb;
}

.preview-img {
  width: 100%;
  max-height: 200px;
  object-fit: cover;
  display: block;
}

.image-actions {
  display: flex;
  gap: 8px;
  padding: 12px;
  background: #ffffff;
  border-top: 1px solid #e5e7eb;
}

.image-url-input {
  font-size: 12px;
  padding: 8px 12px;
}

.image-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.image-card:hover .image-overlay {
  opacity: 1;
}

.overlay-btn {
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.9);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s ease;
}

.overlay-btn:hover {
  background: #ffffff;
}

/* 多图网格 */
.images-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
}

.images-grid .image-card {
  aspect-ratio: 1;
}

.images-grid .preview-img {
  width: 100%;
  height: 100%;
  max-height: none;
}

.images-grid .image-url-input {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 6px 8px;
  font-size: 11px;
  background: rgba(255, 255, 255, 0.95);
  border: none;
  border-top: 1px solid #e5e7eb;
  border-radius: 0 0 12px 12px;
  outline: none;
}

.add-more {
  aspect-ratio: 1;
  min-height: 150px;
}

/* 文件 */
.file-preview {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.file-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #f9fafb;
  border: 1.5px solid #e5e7eb;
  border-radius: 10px;
}

.file-icon {
  font-size: 24px;
}

.file-name {
  flex: 1;
  font-size: 14px;
  color: #374151;
  word-break: break-all;
}

.file-zone .upload-icon {
  font-size: 28px;
}

.file-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.add-file-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  background: #f9fafb;
  border: 2px dashed #d1d5db;
  border-radius: 10px;
  font-size: 14px;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.2s ease;
}

.add-file-btn:hover {
  border-color: #3b82f6;
  background: #eff6ff;
  color: #3b82f6;
}

/* 下拉选择 */
.select-wrapper {
  position: relative;
}

.field-select {
  appearance: none;
  padding-right: 36px;
}

.select-arrow {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 10px;
  color: #9ca3af;
  pointer-events: none;
}

/* 多选 */
.multiselect-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.option-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: #ffffff;
  border: 1.5px solid #e5e7eb;
  border-radius: 8px;
  font-size: 13px;
  color: #374151;
  cursor: pointer;
  transition: all 0.2s ease;
  user-select: none;
}

.option-chip:hover {
  border-color: #3b82f6;
  background: #eff6ff;
}

.option-chip.selected {
  background: #eff6ff;
  border-color: #3b82f6;
  color: #3b82f6;
  font-weight: 500;
}

.hidden-checkbox {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.option-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.check-icon {
  font-size: 12px;
  font-weight: bold;
}

/* 颜色选择器 */
.color-picker-wrapper {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.color-preview {
  width: 60px;
  height: 60px;
  border-radius: 12px;
  border: 2px solid #e5e7eb;
  overflow: hidden;
  position: relative;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.color-input {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  cursor: pointer;
}

.color-values {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.color-hex {
  font-family: 'Monaco', 'Consolas', monospace;
  font-size: 13px;
}

.color-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.color-swatch {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  border: 2px solid #e5e7eb;
  cursor: pointer;
  transition: transform 0.2s ease;
}

.color-swatch:hover {
  transform: scale(1.15);
  border-color: #3b82f6;
}

/* 重复组 */
.repeater-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.repeater-item {
  border: 1.5px solid #e5e7eb;
  border-radius: 10px;
  overflow: hidden;
}

.repeater-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
}

.repeater-number {
  font-size: 13px;
  font-weight: 600;
  color: #6b7280;
}

.repeater-item .field-textarea {
  border: none;
  border-radius: 0;
}

.add-repeater-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  background: #f9fafb;
  border: 2px dashed #d1d5db;
  border-radius: 10px;
  font-size: 14px;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.2s ease;
}

.add-repeater-btn:hover {
  border-color: #3b82f6;
  background: #eff6ff;
  color: #3b82f6;
}

/* 关联字段 */
.relation-input {
  display: flex;
  align-items: center;
  gap: 12px;
}

.relation-icon {
  font-size: 18px;
}

.relation-field {
  max-width: 200px;
}

.relation-hint {
  font-size: 12px;
  color: #9ca3af;
}

/* 操作按钮 */
.action-btn {
  padding: 6px 12px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 4px;
}

.action-btn.replace {
  background: #eff6ff;
  color: #3b82f6;
}

.action-btn.replace:hover {
  background: #dbeafe;
}

.action-btn.delete {
  background: #fef2f2;
  color: #ef4444;
}

.action-btn.delete:hover {
  background: #fee2e2;
}

.action-btn.pick {
  background: #f3f4f6;
  color: #374151;
}

.action-btn.pick:hover {
  background: #e5e7eb;
}

.media-picker-trigger {
  margin-top: 10px;
  text-align: center;
}

.picker-link {
  background: transparent;
  border: none;
  color: #3b82f6;
  font-size: 13px;
  cursor: pointer;
  padding: 6px 12px;
  border-radius: 6px;
  transition: background 0.2s ease;
}

.picker-link:hover:not(:disabled) {
  background: #eff6ff;
}

.picker-link:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 错误和警告 */
.error-text {
  margin-top: 8px;
  font-size: 13px;
  color: #ef4444;
  display: flex;
  align-items: center;
  gap: 4px;
}

.warning-text {
  margin-top: 8px;
  font-size: 13px;
  color: #f59e0b;
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 按钮图标 */
.btn-icon {
  font-size: 16px;
  line-height: 1;
}
</style>