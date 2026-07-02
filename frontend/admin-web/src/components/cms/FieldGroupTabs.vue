<script setup lang="ts">
export interface FieldGroup { id: number; key: string; label: string; sort: number; icon: string | null }

const props = defineProps<{
  groups: FieldGroup[]
  modelValue: number | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: number | null]
}>()

function selectGroup(groupId: number | null) {
  emit('update:modelValue', groupId)
}
</script>

<template>
  <div class="flex gap-1 border-b mb-4">
    <button
      class="px-4 py-2 text-sm font-medium border-b-2 transition-colors"
      :class="modelValue === null ? 'border-blue-500 text-blue-600' : 'border-transparent text-ink-500 hover:text-ink-700'"
      @click="selectGroup(null)"
    >
      全部
    </button>
    <button
      v-for="g in groups"
      :key="g.id"
      class="px-4 py-2 text-sm font-medium border-b-2 transition-colors"
      :class="modelValue === g.id ? 'border-blue-500 text-blue-600' : 'border-transparent text-ink-500 hover:text-ink-700'"
      @click="selectGroup(g.id)"
    >
      {{ g.icon ? g.icon + ' ' : '' }}{{ g.label }}
    </button>
  </div>
</template>
