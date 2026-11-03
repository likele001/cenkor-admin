/**
 * Markdown → 安全 HTML
 *
 * AI 产出的正文（改写稿、工作台草稿、再分发文案）都是 Markdown 源码。
 * 直接文本输出会把 `##`、`**` 裸露出来；直接 v-html 又有 XSS 风险。
 * 统一走这里：marked 渲染 → DOMPurify 消毒 → 结果缓存。
 */
import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({ gfm: true, breaks: true })

const cache = new Map<string, string>()
const CACHE_MAX = 200

export function mdToHtml(md?: string | null): string {
  if (!md) return ''
  const hit = cache.get(md)
  if (hit !== undefined) return hit

  const html = DOMPurify.sanitize(marked.parse(md, { async: false }) as string, {
    USE_PROFILES: { html: true },
    ADD_ATTR: ['target', 'rel'],
  })

  // 这类文本块数量有限，满了整体清空即可，不必做 LRU
  if (cache.size >= CACHE_MAX) cache.clear()
  cache.set(md, html)
  return html
}
