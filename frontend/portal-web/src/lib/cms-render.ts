/**
 * Liquid 模板引擎前端封装（liquidjs）
 *
 * 使用：
 *   import { cmsRender, validateTemplate, injectGlobals } from '@/lib/cms-render'
 *   const html = cmsRender('Hello {{ name }}!', { name: 'World' })
 *   const ok = validateTemplate('{{ unclosed')
 *
 * 全局：
 *   window.cmsRender(template, data, globals?)  —— 供外部脚本使用
 */
import { Liquid } from 'liquidjs'
import { useLocaleStore } from '@/stores/locale'

// ============================================================
// 单例引擎
// ============================================================

let _engine: Liquid | null = null

export function getEngine(): Liquid {
  if (!_engine) {
    _engine = new Liquid({
      strictFilters: false, // 允许未注册的 filter（不抛错）
      strictVariables: false,
    })
    registerFilters(_engine)
  }
  return _engine
}

// ============================================================
// 自定义 Filters
// ============================================================

const I18N_MAP: Record<string, Record<string, string>> = {
  'zh-CN': {
    enterprise: '企业应用',
    ai: 'AI 应用',
    manufacturing: '智能制造',
  },
  'en-US': {
    enterprise: 'Enterprise',
    ai: 'AI',
    manufacturing: 'Manufacturing',
  },
}

function getI18nMap(): Record<string, string> {
  try {
    const code = useLocaleStore().locale
    return I18N_MAP[code] || I18N_MAP['zh-CN']
  } catch {
    return I18N_MAP['zh-CN']
  }
}

function registerFilters(engine: Liquid): void {
  // 字符串
  engine.registerFilter('upcase', (s: unknown) => String(s ?? '').toUpperCase())
  engine.registerFilter('downcase', (s: unknown) => String(s ?? '').toLowerCase())
  engine.registerFilter('capitalize', (s: unknown) => {
    const str = String(s ?? '')
    return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase()
  })
  engine.registerFilter('truncate', (s: unknown, length = 100, suffix = '...') => {
    const str = String(s ?? '')
    if (str.length <= length) return str
    return str.slice(0, length).trimEnd() + suffix
  })
  engine.registerFilter('append', (s: unknown, suffix = '') => String(s ?? '') + String(suffix))
  engine.registerFilter('prepend', (s: unknown, prefix = '') => String(prefix) + String(s ?? ''))
  engine.registerFilter('strip', (s: unknown) => String(s ?? '').trim())
  engine.registerFilter('escape', (s: unknown) => {
    const str = String(s ?? '')
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
  })
  engine.registerFilter('strip_html', (s: unknown) => {
    const str = String(s ?? '')
    return str.replace(/<[^>]+>/g, '')
  })
  engine.registerFilter('replace', (s: unknown, oldStr = '', newStr = '') => {
    return String(s ?? '').split(oldStr).join(newStr)
  })
  engine.registerFilter('remove', (s: unknown, sub = '') => {
    return String(s ?? '').split(sub).join('')
  })
  engine.registerFilter('slice', (s: unknown, start = 0, length?: number) => {
    const str = String(s ?? '')
    if (length == null) return str.slice(start)
    return str.slice(start, start + length)
  })

  // 日期
  engine.registerFilter('date', (value: unknown, fmt = '%Y-%m-%d') => {
    if (!value) return ''
    let d: Date
    if (value instanceof Date) {
      d = value
    } else {
      d = new Date(String(value))
    }
    if (isNaN(d.getTime())) return String(value)
    // 支持 %Y, %m, %d, %H, %M, %S 等
    return fmt
      .replace(/%Y/g, String(d.getFullYear()))
      .replace(/%m/g, String(d.getMonth() + 1).padStart(2, '0'))
      .replace(/%d/g, String(d.getDate()).padStart(2, '0'))
      .replace(/%H/g, String(d.getHours()).padStart(2, '0'))
      .replace(/%M/g, String(d.getMinutes()).padStart(2, '0'))
      .replace(/%S/g, String(d.getSeconds()).padStart(2, '0'))
  })

  // 数字 / 货币
  engine.registerFilter('currency', (v: unknown, symbol = '¥', decimal = 2) => {
    const num = Number(v) || 0
    return `${symbol}${num.toFixed(decimal).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}`
  })
  engine.registerFilter('abs', (v: unknown) => Math.abs(Number(v) || 0))
  engine.registerFilter('round', (v: unknown, precision = 0) => {
    const num = Number(v) || 0
    const factor = 10 ** precision
    return Math.round(num * factor) / factor
  })
  engine.registerFilter('number_format', (v: unknown, decimal = 0) => {
    const num = Number(v) || 0
    return num.toFixed(decimal).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  })

  // 数组
  engine.registerFilter('size', (x: unknown) => Array.isArray(x) ? x.length : (x ? Object.keys(x).length : 0))
  engine.registerFilter('first', (x: unknown) => Array.isArray(x) && x.length > 0 ? x[0] : null)
  engine.registerFilter('last', (x: unknown) => Array.isArray(x) && x.length > 0 ? x[x.length - 1] : null)
  engine.registerFilter('join', (x: unknown, sep = ', ') => Array.isArray(x) ? x.map(String).join(sep) : '')
  engine.registerFilter('uniq', (x: unknown) => {
    if (!Array.isArray(x)) return []
    return [...new Set(x)]
  })
  engine.registerFilter('compact', (x: unknown) => {
    if (!Array.isArray(x)) return []
    return x.filter((v: any) => v != null && v !== '' && v !== 0 && v !== false)
  })
  engine.registerFilter('sort', (x: unknown, key?: string, reverse = false) => {
    if (!Array.isArray(x)) return []
    const sorted = [...x].sort((a: any, b: any) => {
      const va = key ? a?.[key] : a
      const vb = key ? b?.[key] : b
      if (va == null) return 1
      if (vb == null) return -1
      return va > vb ? 1 : va < vb ? -1 : 0
    })
    return reverse ? sorted.reverse() : sorted
  })
  engine.registerFilter('map', (x: unknown, key: string) => {
    if (!Array.isArray(x)) return []
    return x.map((item: any) => item?.[key])
  })
  engine.registerFilter('where', (x: unknown, key: string, value?: any) => {
    if (!Array.isArray(x)) return []
    if (arguments.length === 2) {
      return x.filter((item: any) => item?.[key])
    }
    return x.filter((item: any) => item?.[key] === value)
  })
  engine.registerFilter('reverse', (x: unknown) => Array.isArray(x) ? [...x].reverse() : [])

  // 序列化
  engine.registerFilter('json', (v: unknown) => JSON.stringify(v, null, 2))

  // Markdown（简单实现：仅支持 # ## ### - 列表，复杂场景建议使用服务端渲染）
  engine.registerFilter('markdown', (text: unknown) => {
    const str = String(text ?? '')
    if (!str) return ''
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/^### (.*$)/gim, '<h3>$1</h3>')
      .replace(/^## (.*$)/gim, '<h2>$1</h2>')
      .replace(/^# (.*$)/gim, '<h1>$1</h1>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/^\s*[-*]\s+(.+)$/gim, '<li>$1</li>')
      .replace(/(<li>[\s\S]*?<\/li>)/gim, '<ul>$1</ul>')
      .replace(/\n\n/g, '</p><p>')
      .replace(/^([^<].*)$/gim, '<p>$1</p>')
      .replace(/<p><\/p>/g, '')
  })

  // 默认值
  engine.registerFilter('default', (v: unknown, fallback = '') => {
    if (v == null || v === '' || (Array.isArray(v) && v.length === 0)) return fallback
    return v
  })

  // ============================================================
  // 业务自定义 Filters
  // ============================================================

  // t：i18n 翻译（基于当前 locale 反应式查表）
  engine.registerFilter('t', (value: unknown) => {
    if (!value) return ''
    const map = getI18nMap()
    return map[String(value)] || String(value)
  })

  // format_price
  engine.registerFilter('format_price', (v: unknown, currency = '¥') => {
    const num = Number(v) || 0
    return `${currency}${num.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}`
  })

  // asset_url
  let CDN_BASE = ''
  engine.registerFilter('asset_url', (path: unknown) => {
    const p = String(path ?? '')
    if (!p) return ''
    if (/^(https?:)?\/\//.test(p)) return p
    if (p.startsWith('/')) return CDN_BASE + p
    return CDN_BASE + '/' + p
  })
  ;(engine as any)._setCdnBase = (base: string) => { CDN_BASE = base }

  // thumb
  engine.registerFilter('thumb', (url: unknown, size = '300x200') => {
    const u = String(url ?? '')
    if (!u) return ''
    return u.includes('?') ? `${u}&resize=${size}` : `${u}?resize=${size}`
  })

  // reading_time
  engine.registerFilter('reading_time', (content: unknown) => {
    const text = String(content ?? '').replace(/<[^>]+>/g, '')
    return Math.max(1, Math.round(text.length / 500))
  })
}

// ============================================================
// 全局变量注入
// ============================================================

export interface GlobalVars {
  now?: string
  site?: Record<string, any>
  theme?: Record<string, any>
  current_user?: Record<string, any> | null
  request?: Record<string, any>
}

export function injectGlobals(data: Record<string, any>, globals: GlobalVars = {}): Record<string, any> {
  return {
    now: new Date().toISOString(),
    site: globals.site || {},
    theme: globals.theme || {},
    current_user: globals.current_user || null,
    request: globals.request || {},
    ...data,
  }
}

// ============================================================
// 公共 API
// ============================================================

export function cmsRender(
  template: string,
  data: Record<string, any> = {},
  globals: GlobalVars = {},
): string {
  if (!template) return ''
  const engine = getEngine()
  const fullData = injectGlobals(data, globals)
  try {
    return engine.parseAndRenderSync(template, fullData) as string
  } catch (e) {
    console.error('[cmsRender] error:', e)
    return ''
  }
}

export async function cmsRenderAsync(
  template: string,
  data: Record<string, any> = {},
  globals: GlobalVars = {},
): Promise<string> {
  if (!template) return ''
  const engine = getEngine()
  const fullData = injectGlobals(data, globals)
  try {
    return (await engine.parseAndRender(template, fullData)) as string
  } catch (e) {
    console.error('[cmsRenderAsync] error:', e)
    return ''
  }
}

export function validateTemplate(template: string): { valid: boolean; error: string | null } {
  if (!template) return { valid: true, error: null }
  try {
    const engine = getEngine()
    engine.parse(template)
    return { valid: true, error: null }
  } catch (e: any) {
    return { valid: false, error: e?.message || String(e) }
  }
}

// ============================================================
// 全局挂载（供外部脚本使用）
// ============================================================

export function installGlobalRender(): void {
  if (typeof window !== 'undefined') {
    ;(window as any).cmsRender = cmsRender
    ;(window as any).cmsValidate = validateTemplate
  }
}
