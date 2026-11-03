<script setup lang="ts">
import { computed } from 'vue'
import DOMPurify from 'dompurify'
import { mdToHtml } from '../lib/markdown'

const props = withDefaults(
  defineProps<{
    content?: string | null
    /**
     * auto（默认）：看起来像 HTML 才按 HTML 处理，否则纯文本原样显示
     * html：强制按 HTML 处理
     * markdown：按 Markdown 渲染（AI 产出的正文走这个）
     */
    format?: 'auto' | 'html' | 'markdown'
  }>(),
  { format: 'auto' },
)

const looksHtml = computed(() => !!props.content && /<[a-z][\s\S]*>/i.test(props.content as string))

const mode = computed<'html' | 'markdown' | 'text'>(() => {
  if (!props.content) return 'text'
  if (props.format === 'markdown') return 'markdown'
  if (props.format === 'html') return 'html'
  return looksHtml.value ? 'html' : 'text'
})

const rendered = computed(() => {
  const c = (props.content as string) || ''
  if (mode.value === 'markdown') return mdToHtml(c)
  if (mode.value === 'html') return DOMPurify.sanitize(c, { USE_PROFILES: { html: true } })
  return ''
})
</script>

<template>
  <div v-if="mode !== 'text'" class="rich-content" v-html="rendered"></div>
  <div v-else class="rich-content whitespace-pre-wrap">{{ content }}</div>
</template>

<style scoped>
.rich-content { line-height: 1.7; color: #1f2937; font-size: 14px; word-break: break-word; }
.rich-content :deep(h1) { font-size: 1.5em; font-weight: 700; margin: 0.5em 0; }
.rich-content :deep(h2) { font-size: 1.3em; font-weight: 700; margin: 0.5em 0; }
.rich-content :deep(h3) { font-size: 1.15em; font-weight: 600; margin: 0.5em 0; }
.rich-content :deep(h4) { font-size: 1.05em; font-weight: 600; margin: 0.5em 0; }
.rich-content :deep(p) { margin: 0.45em 0; }
.rich-content :deep(ul), .rich-content :deep(ol) { padding-left: 1.5em; margin: 0.4em 0; }
.rich-content :deep(ul) { list-style: disc; }
.rich-content :deep(ol) { list-style: decimal; }
.rich-content :deep(li) { margin: 0.2em 0; }
.rich-content :deep(strong) { font-weight: 600; color: #111827; }
.rich-content :deep(hr) { border: 0; border-top: 1px solid #e5e7eb; margin: 0.8em 0; }
.rich-content :deep(blockquote) { border-left: 3px solid #d1d5db; padding-left: 12px; color: #6b7280; margin: 0.6em 0; }
.rich-content :deep(a) { color: #4338ca; text-decoration: underline; }
.rich-content :deep(img) { max-width: 100%; border-radius: 8px; margin: 8px 0; }
.rich-content :deep(pre) { background: #1f2937; color: #f9fafb; padding: 12px; border-radius: 8px; overflow: auto; }
.rich-content :deep(code) { background: #f3f4f6; padding: 1px 5px; border-radius: 4px; font-size: 0.9em; }
.rich-content :deep(table) { border-collapse: collapse; width: 100%; margin: 0.6em 0; font-size: 0.95em; }
.rich-content :deep(th), .rich-content :deep(td) { border: 1px solid #e5e7eb; padding: 4px 8px; text-align: left; }
.rich-content :deep(th) { background: #f9fafb; font-weight: 600; }
</style>
