/**
 * vue-i18n 引导（portal-web）
 *
 * 与 admin-web 一致的目录结构：
 *   - locales/{zh-CN,en-US}/*.json  按页面分文件
 *   - locales/index.ts  实例 + 双向同步
 *   - stores/locale.ts  Pinia store + 持久化
 */
import { createI18n } from 'vue-i18n'
import type { LocaleCode } from '@/stores/locale'

const zhModules = import.meta.glob('./zh-CN/*.json', { eager: true })
const enModules = import.meta.glob('./en-US/*.json', { eager: true })

function mergeModules(modules: Record<string, unknown>): Record<string, any> {
  const merged: Record<string, any> = {}
  for (const [, mod] of Object.entries(modules)) {
    const data = (mod as any).default ?? mod
    Object.assign(merged, data)
  }
  return merged
}

const messages = {
  'zh-CN': mergeModules(zhModules),
  'en-US': mergeModules(enModules),
}

export const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  // 注意: 此时 Pinia 尚未安装, 不能调用 useLocaleStore().
  // 真实 locale 在 setupLocaleWatcher() 里同步过来.
  locale: 'zh-CN',
  fallbackLocale: 'zh-CN',
  messages,
  missingWarn: true,
  fallbackWarn: false,
})

export async function setupLocaleWatcher() {
  const { useLocaleStore } = await import('@/stores/locale')
  const store = useLocaleStore()
  store.$subscribe(
    (_, state) => {
      if (i18n.global.locale.value !== state.locale) {
        i18n.global.locale.value = state.locale as any
      }
    },
    { detached: true },
  )
  i18n.global.locale.value = store.locale as any
}