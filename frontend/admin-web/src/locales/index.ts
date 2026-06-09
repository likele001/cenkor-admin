import { createI18n } from 'vue-i18n'
import zhCN from './zh-CN'
import enUS from './en-US'

const STORAGE_KEY = 'cenkor.locale'

function detectInitialLocale(): string {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'zh-CN' || stored === 'en-US') return stored
  const browser = navigator.language || (navigator as any).userLanguage
  if (browser.toLowerCase().startsWith('en')) return 'en-US'
  return 'zh-CN'
}

export const i18n = createI18n({
  legacy: false,
  locale: detectInitialLocale(),
  fallbackLocale: 'zh-CN',
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS,
  },
})

export function setLocale(loc: string) {
  i18n.global.locale.value = loc as any
  localStorage.setItem(STORAGE_KEY, loc)
  document.documentElement.lang = loc
}
