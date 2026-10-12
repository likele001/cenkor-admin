<script setup lang="ts">
import { computed } from 'vue'
import DOMPurify from 'dompurify'

const props = defineProps<{ content?: string | null }>()

const isHtml = computed(() => !!props.content && /<[a-z][\s\S]*>/i.test(props.content as string))
const safeHtml = computed(() => {
  const c = (props.content as string) || ''
  if (!isHtml.value) return ''
  return DOMPurify.sanitize(c, { USE_PROFILES: { html: true } })
})
</script>

<template>
  <div v-if="isHtml" class="rich-content" v-html="safeHtml"></div>
  <div v-else class="rich-content whitespace-pre-wrap">{{ content }}</div>
</template>

<style scoped>
.rich-content { line-height: 1.7; color: #1f2937; font-size: 14px; word-break: break-word; }
.rich-content :deep(h1) { font-size: 1.5em; font-weight: 700; margin: 0.5em 0; }
.rich-content :deep(h2) { font-size: 1.3em; font-weight: 700; margin: 0.5em 0; }
.rich-content :deep(h3) { font-size: 1.15em; font-weight: 600; margin: 0.5em 0; }
.rich-content :deep(ul), .rich-content :deep(ol) { padding-left: 1.5em; margin: 0.4em 0; }
.rich-content :deep(li) { margin: 0.2em 0; }
.rich-content :deep(blockquote) { border-left: 3px solid #d1d5db; padding-left: 12px; color: #6b7280; margin: 0.6em 0; }
.rich-content :deep(a) { color: #4338ca; text-decoration: underline; }
.rich-content :deep(img) { max-width: 100%; border-radius: 8px; margin: 8px 0; }
.rich-content :deep(pre) { background: #1f2937; color: #f9fafb; padding: 12px; border-radius: 8px; overflow: auto; }
.rich-content :deep(code) { background: #f3f4f6; padding: 1px 5px; border-radius: 4px; font-size: 0.9em; }
</style>
