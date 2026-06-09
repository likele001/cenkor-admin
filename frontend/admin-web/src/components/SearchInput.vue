<script setup lang="ts">
import { ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: string
  placeholder?: string
  debounce?: number
}>(), {
  placeholder: '搜索…',
  debounce: 300,
})

const emit = defineEmits<{ 'update:modelValue': [string] }>()

const local = ref(props.modelValue)
let timer: number | undefined

watch(() => props.modelValue, (v) => { local.value = v })

function onInput() {
  if (timer) window.clearTimeout(timer)
  timer = window.setTimeout(() => {
    emit('update:modelValue', local.value.trim())
  }, props.debounce)
}
</script>

<template>
  <div class="relative">
    <input
      v-model="local"
      type="search"
      :placeholder="placeholder"
      class="w-full sm:w-72 pl-9 pr-3 py-2 rounded-lg border border-ink-200 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
      @input="onInput"
    />
    <svg class="absolute left-2.5 top-2.5 w-4 h-4 text-ink-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  </div>
</template>
