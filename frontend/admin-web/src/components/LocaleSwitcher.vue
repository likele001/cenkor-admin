<script setup lang="ts">
import { ref, watchEffect } from 'vue'
import { useI18n } from 'vue-i18n'
import { setLocale } from '@/locales'

const { locale } = useI18n()
const open = ref(false)

const options = [
  { value: 'zh-CN', label: '简体中文' },
  { value: 'en-US', label: 'English' },
]

function pick(v: string) {
  setLocale(v)
  open.value = false
}

function currentLabel() {
  return options.find((o) => o.value === locale.value)?.label || 'zh-CN'
}
</script>

<template>
  <div class="relative">
    <button
      type="button"
      class="px-2.5 py-1.5 rounded-md text-sm text-ink-600 hover:bg-ink-100 inline-flex items-center gap-1.5"
      :aria-label="'Language switcher'"
      @click="open = !open"
    >
      <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10" />
        <path d="M2 12h20" />
        <path d="M12 2a15 15 0 0 1 0 20a15 15 0 0 1 0-20" />
      </svg>
      <span class="hidden md:inline">{{ currentLabel() }}</span>
    </button>
    <div
      v-if="open"
      class="absolute right-0 mt-1.5 w-32 rounded-lg border border-ink-200 bg-white shadow-md py-1 z-50"
    >
      <button
        v-for="o in options"
        :key="o.value"
        type="button"
        class="w-full text-left px-3 py-1.5 text-sm hover:bg-ink-50"
        :class="{ 'text-brand-600': locale === o.value }"
        @click="pick(o.value)"
      >
        {{ o.label }}
      </button>
    </div>
  </div>
</template>
