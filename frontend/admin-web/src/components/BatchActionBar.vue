<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  selectedCount: number
  totalCount: number
  actions: Array<{
    label: string
    danger?: boolean
    confirm?: { title: string; message: string; confirmText?: string }
    onAction: () => void | Promise<void>
  }>
}>()

const visible = computed(() => props.selectedCount > 0)
const allSelected = computed(() => props.selectedCount === props.totalCount && props.totalCount > 0)
const emit = defineEmits<{ 'select-all': [boolean]; 'clear': [] }>()
</script>

<template>
  <Transition
    enter-active-class="transition duration-200 ease-out"
    enter-from-class="opacity-0 -translate-y-2"
    enter-to-class="opacity-100 translate-y-0"
    leave-active-class="transition duration-150 ease-in"
    leave-from-class="opacity-100"
    leave-to-class="opacity-0"
  >
    <div
      v-if="visible"
      class="sticky top-0 z-20 mb-3 px-4 py-2.5 rounded-lg bg-brand-50 border border-brand-200 flex items-center justify-between text-sm shadow-sm"
    >
      <div class="flex items-center gap-3">
        <span class="font-medium text-brand-700">已选 {{ selectedCount }} / {{ totalCount }} 项</span>
        <label class="inline-flex items-center gap-1.5 text-brand-600 cursor-pointer">
          <input
            type="checkbox"
            :checked="allSelected"
            class="rounded text-brand-500 focus:ring-brand-500"
            @change="emit('select-all', ($event.target as HTMLInputElement).checked)"
          />
          <span>全选当前页</span>
        </label>
        <button
          type="button"
          class="text-brand-600 hover:text-brand-900 underline-offset-2 hover:underline"
          @click="emit('clear')"
        >
          取消选择
        </button>
      </div>
      <div class="flex items-center gap-2">
        <template v-for="(a, i) in actions" :key="i">
          <button
            type="button"
            class="px-3 py-1.5 rounded-md text-sm font-medium transition-colors"
            :class="a.danger
              ? 'bg-red-600 text-white hover:bg-red-700'
              : 'bg-white border border-brand-200 text-brand-700 hover:bg-brand-100'"
            @click="a.onAction"
          >
            {{ a.label }}
          </button>
        </template>
      </div>
    </div>
  </Transition>
</template>
