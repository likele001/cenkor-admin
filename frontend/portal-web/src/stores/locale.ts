/**
 * LocaleStore - portal-web 全局 locale 状态管理
 */
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

export type LocaleCode = 'zh-CN' | 'en-US'

const STORAGE_KEY = 'cenkor.portal.locale'

export const SUPPORTED_LOCALES: { code: LocaleCode; label: string; flag: string }[] = [
  { code: 'zh-CN', label: '简体中文', flag: '🇨🇳' },
  { code: 'en-US', label: 'English', flag: '🇺🇸' },
]

function detectInitialLocale(): LocaleCode {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'zh-CN' || stored === 'en-US') return stored as LocaleCode
  const browser = navigator.language || ''
  if (browser.toLowerCase().startsWith('en')) return 'en-US'
  return 'zh-CN'
}

export const useLocaleStore = defineStore('locale', () => {
  const locale = ref<LocaleCode>(detectInitialLocale())

  watch(
    locale,
    (val) => {
      localStorage.setItem(STORAGE_KEY, val)
      if (typeof document !== 'undefined') {
        document.documentElement.lang = val
      }
    },
    { immediate: true },
  )

  const isZhCN = computed(() => locale.value === 'zh-CN')
  const isEnUS = computed(() => locale.value === 'en-US')
  const currentMeta = computed(
    () => SUPPORTED_LOCALES.find((l) => l.code === locale.value) || SUPPORTED_LOCALES[0],
  )

  function setLocale(code: LocaleCode) {
    locale.value = code
  }

  function toggle() {
    locale.value = locale.value === 'zh-CN' ? 'en-US' : 'zh-CN'
  }

  return { locale, isZhCN, isEnUS, currentMeta, setLocale, toggle }
})