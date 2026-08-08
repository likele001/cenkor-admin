<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useLocaleStore, SUPPORTED_LOCALES } from '@/stores/locale'
import { useI18n } from 'vue-i18n'

const localeStore = useLocaleStore()
const { t } = useI18n()
const open = ref(false)
const rootRef = ref<HTMLElement | null>(null)

function pick(code: typeof SUPPORTED_LOCALES[number]['code']) {
  localeStore.setLocale(code)
  open.value = false
}

function onClickOutside(e: MouseEvent) {
  if (!open.value) return
  if (rootRef.value && !rootRef.value.contains(e.target as Node)) {
    open.value = false
  }
}

function onEscape(e: KeyboardEvent) {
  if (e.key === 'Escape' && open.value) open.value = false
}

onMounted(() => {
  document.addEventListener('click', onClickOutside)
  document.addEventListener('keydown', onEscape)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onClickOutside)
  document.removeEventListener('keydown', onEscape)
})

const current = computed(() => localeStore.currentMeta)
</script>

<template>
  <div ref="rootRef" class="relative">
    <button
      type="button"
      class="px-2.5 py-1.5 rounded-md text-sm text-ink-600 hover:bg-ink-100 inline-flex items-center gap-1.5"
      :aria-label="t('app.switchLanguage', 'Switch language')"
      @click.stop="open = !open"
    >
      <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10" />
        <path d="M2 12h20" />
        <path d="M12 2a15 15 0 0 1 0 20a15 15 0 0 1 0-20" />
      </svg>
      <span class="hidden md:inline">{{ current.flag }} {{ current.label }}</span>
      <span class="md:hidden">{{ current.flag }}</span>
      <svg class="w-3 h-3 opacity-60" viewBox="0 0 20 20" fill="currentColor">
        <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.06l3.71-3.83a.75.75 0 0 1 1.08 1.04l-4.25 4.39a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06z" />
      </svg>
    </button>
    <transition
      enter-active-class="transition duration-100 ease-out"
      enter-from-class="opacity-0 scale-95"
      enter-to-class="opacity-100 scale-100"
      leave-active-class="transition duration-75 ease-in"
      leave-from-class="opacity-100 scale-100"
      leave-to-class="opacity-0 scale-95"
    >
      <div
        v-if="open"
        class="absolute right-0 mt-1.5 w-full sm:w-40 rounded-lg border border-ink-200 bg-white shadow-lg py-1 z-50"
        role="menu"
      >
        <button
          v-for="o in SUPPORTED_LOCALES"
          :key="o.code"
          type="button"
          class="w-full text-left px-3 py-1.5 text-sm hover:bg-ink-50 flex items-center gap-2"
          :class="{ 'text-brand-600 bg-brand-50/50': localeStore.locale === o.code }"
          role="menuitem"
          @click="pick(o.code)"
        >
          <span>{{ o.flag }}</span>
          <span class="flex-1">{{ o.label }}</span>
          <svg
            v-if="localeStore.locale === o.code"
            class="w-4 h-4 text-brand-600"
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path fill-rule="evenodd" d="M16.7 5.3a1 1 0 0 1 0 1.4l-7.5 7.5a1 1 0 0 1-1.4 0L3.3 9.7a1 1 0 0 1 1.4-1.4l4.3 4.3 6.8-6.8a1 1 0 0 1 1.4 0z" clip-rule="evenodd" />
          </svg>
        </button>
      </div>
    </transition>
  </div>
</template>