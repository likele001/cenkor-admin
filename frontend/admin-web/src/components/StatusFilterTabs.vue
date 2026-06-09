<script setup lang="ts">
const props = defineProps<{
  modelValue: 'all' | 'published' | 'draft' | 'archived'
  includeDeleted?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [string]
  'update:include-deleted': [boolean]
}>()

const tabs: Array<{ key: 'all' | 'published' | 'draft' | 'archived'; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'published', label: '已发布' },
  { key: 'draft', label: '草稿' },
  { key: 'archived', label: '已归档' },
]
</script>

<template>
  <div class="flex flex-wrap items-center justify-between gap-3 mb-3">
    <div class="inline-flex rounded-lg border border-ink-200 bg-white p-0.5">
      <button
        v-for="t in tabs"
        :key="t.key"
        type="button"
        class="px-3 py-1.5 text-sm rounded-md transition-colors"
        :class="modelValue === t.key ? 'bg-ink-900 text-white' : 'text-ink-600 hover:text-ink-900'"
        @click="emit('update:modelValue', t.key)"
      >
        {{ t.label }}
      </button>
    </div>
    <label class="inline-flex items-center gap-2 text-sm text-ink-600 cursor-pointer">
      <input
        type="checkbox"
        :checked="includeDeleted"
        class="rounded"
        @change="emit('update:include-deleted', ($event.target as HTMLInputElement).checked)"
      />
      <span>包含已删除（回收站）</span>
    </label>
  </div>
</template>
