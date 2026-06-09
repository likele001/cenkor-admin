<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
// @ts-ignore vditor 3.x 未导出 IOptions
import Vditor from 'vditor'
import 'vditor/dist/index.css'

const props = withDefaults(defineProps<{
  modelValue: string
  height?: number
  placeholder?: string
}>(), {
  height: 480,
  placeholder: '请输入 Markdown 内容…',
})

const emit = defineEmits<{ 'update:modelValue': [string] }>()

const editorRef = ref<HTMLDivElement | null>(null)
let vditor: any = null

function buildOptions(): any {
  return {
    height: props.height,
    placeholder: props.placeholder,
    mode: 'sv', // 分屏预览：左侧编辑，右侧实时渲染
    theme: 'classic',
    icon: 'ant',
    cache: { enable: false },
    preview: {
      hljs: { style: 'github' },
      math: { enable: false },
      actions: [],
    },
    toolbar: [
      'headings', 'bold', 'italic', 'strike', '|',
      'list', 'ordered-list', 'check', '|',
      'quote', 'code', 'inline-code', '|',
      'link', 'upload-image', 'table', '|',
      'undo', 'redo', '|',
      'fullscreen', 'edit-mode',
    ],
    upload: {
      // 媒体上传走 CMS /media/presign 流，简化：仅支持粘贴/拖拽图片走 multipart
      url: '/api/v1/cms/media/upload',
      fieldName: 'file',
      max: 5 * 1024 * 1024,
      headers: () => {
        const token = localStorage.getItem('cenkor.token') || ''
        return { Authorization: token ? `Bearer ${token}` : '' }
      },
      format: (files: File[], responseText: string) => {
        try {
          const r = JSON.parse(responseText)
          if (r && r.url) {
            return JSON.stringify({ msg: '', code: 0, data: { url: r.url } })
          }
        } catch {}
        return responseText
      },
      error: (msg: string) => { console.error('Vditor upload error:', msg) },
    },
    after: () => {
      if (!vditor) return
      vditor.setValue(props.modelValue || '')
    },
    input: (value: string) => {
      if (value !== props.modelValue) emit('update:modelValue', value)
    },
  }
}

onMounted(() => {
  if (!editorRef.value) return
  vditor = new Vditor(editorRef.value, buildOptions())
})

watch(() => props.modelValue, (v) => {
  if (vditor && v !== vditor.getValue()) {
    vditor.setValue(v || '')
  }
})

onBeforeUnmount(() => {
  vditor?.destroy()
  vditor = null
})
</script>

<template>
  <div ref="editorRef" />
</template>

<style>
.vditor-toolbar { background-color: #fafafa; }
</style>
