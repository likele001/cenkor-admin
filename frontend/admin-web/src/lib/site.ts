/** 当前站点上下文：sessionStorage 持久化 + 变更广播。
 *
 * 为什么放 sessionStorage 而不是 localStorage：
 * 同一个浏览器开两个标签页分别看两个站点是常见用法，共享会互相打架。
 */
const STORAGE_KEY = 'cms.siteId'
const EVENT = 'cms-site-changed'

export function getSiteId(): number | null {
  const raw = sessionStorage.getItem(STORAGE_KEY)
  if (!raw) return null
  const n = Number(raw)
  return Number.isFinite(n) && n > 0 ? n : null
}

export function setSiteId(id: number | null): void {
  if (id && id > 0) sessionStorage.setItem(STORAGE_KEY, String(id))
  else sessionStorage.removeItem(STORAGE_KEY)
  window.dispatchEvent(new CustomEvent(EVENT, { detail: { siteId: id } }))
}

export function onSiteChange(fn: (id: number | null) => void): () => void {
  const handler = (e: Event) => {
    const detail = (e as CustomEvent).detail as { siteId?: number | null } | undefined
    fn(detail?.siteId ?? getSiteId())
  }
  window.addEventListener(EVENT, handler)
  return () => window.removeEventListener(EVENT, handler)
}
