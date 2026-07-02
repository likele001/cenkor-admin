/**
 * vue-i18n 引导
 *
 * 自动加载 src/locales/{zh-CN,en-US}/*.json 并合并为 vue-i18n messages
 * 使用 import.meta.glob 让 vite 在 build 时 inline 所有 JSON 文件
 */
import { createI18n } from 'vue-i18n'
import type { LocaleCode } from '@/stores/locale'

// 收集所有 locale 文件，按 locale code 分组
const zhModules = import.meta.glob('./zh-CN/*.json', { eager: true })
const enModules = import.meta.glob('./en-US/*.json', { eager: true })
const zhExtractedModules = import.meta.glob('./_extracted/*.json', { eager: true })
const enExtractedModules = import.meta.glob('./en-US/_extracted/*.json', { eager: true })

function mergeModules(modules: Record<string, unknown>): Record<string, any> {
  const merged: Record<string, any> = {}
  for (const [, mod] of Object.entries(modules)) {
    const data = (mod as any).default ?? mod
    Object.assign(merged, data)
  }
  return merged
}

const messages = {
  'zh-CN': mergeModules({ ...zhModules, ...zhExtractedModules }),
  'en-US': mergeModules({ ...enModules, ...enExtractedModules }),
}

export const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  // 注意: 此时 Pinia 尚未安装, 不能调用 useLocaleStore().
  // 真实 locale 在 setupLocaleWatcher() 里同步过来.
  locale: 'zh-CN',
  fallbackLocale: 'zh-CN',
  messages,
  // 缺失 key 时显示 key 而非空白, 方便排查
  missingWarn: true,
  fallbackWarn: false,
})

// 双向同步: locale store 变化 → i18n 切换
// 必须在 app.use(createPinia()) 之后调用
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
  // 初始化时同步一次
  i18n.global.locale.value = store.locale as any
}