<script setup lang="ts">
import { watch, onBeforeUnmount, ref } from 'vue'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import Link from '@tiptap/extension-link'
import Image from '@tiptap/extension-image'
import Placeholder from '@tiptap/extension-placeholder'
import { api } from '@/lib/api'

const props = withDefaults(defineProps<{
  modelValue?: string
  placeholder?: string
  disabled?: boolean
  maxlength?: number
}>(), {
  modelValue: '',
  placeholder: '请输入内容…',
  disabled: false,
  maxlength: 0,
})

const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const editor = useEditor({
  content: props.modelValue || '',
  editable: !props.disabled,
  extensions: [
    StarterKit,
    Underline,
    Link.configure({ openOnClick: false, HTMLAttributes: { rel: 'noopener noreferrer', target: '_blank' } }),
    Image.configure({ inline: false, HTMLAttributes: { class: 'rte-image' } }),
    Placeholder.configure({ placeholder: props.placeholder }),
  ],
  onUpdate: ({ editor }) => {
    const html = editor.getHTML()
    emit('update:modelValue', editor.isEmpty ? '' : html)
  },
})

watch(() => props.modelValue, (val) => {
  const e = editor.value
  if (e && val !== e.getHTML()) {
    e.commands.setContent(val || '', false)
  }
})
watch(() => props.disabled, (d) => editor.value?.setEditable(!d))

onBeforeUnmount(() => editor.value?.destroy())

const fileInput = ref<HTMLInputElement | null>(null)
function pickImage() { fileInput.value?.click() }
async function onImage(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    const fd = new FormData()
    fd.append('file', file)
    const { data } = await api.post('/api/v1/cms/media/upload', fd)
    const url = data?.url
    if (url && editor.value) editor.value.chain().focus().setImage({ src: url }).run()
  } catch {
    window.alert('图片上传失败，请重试')
  }
}

function setLink() {
  const e = editor.value
  if (!e) return
  const prev = (e.getAttributes('link').href as string) || ''
  const url = window.prompt('输入链接地址（留空取消链接）', prev)
  if (url === null) return
  if (url === '') { e.chain().focus().extendMarkRange('link').unsetLink().run(); return }
  e.chain().focus().extendMarkRange('link').setLink({ href: url }).run()
}
</script>

<template>
  <div class="rte" :class="{ 'rte--disabled': disabled }">
    <div v-if="editor && !disabled" class="rte-toolbar">
      <button type="button" :class="{ active: editor.isActive('bold') }" @click="editor.chain().focus().toggleBold().run()" title="加粗"><b>B</b></button>
      <button type="button" :class="{ active: editor.isActive('italic') }" @click="editor.chain().focus().toggleItalic().run()" title="斜体"><i>I</i></button>
      <button type="button" :class="{ active: editor.isActive('underline') }" @click="editor.chain().focus().toggleUnderline().run()" title="下划线"><u>U</u></button>
      <button type="button" :class="{ active: editor.isActive('strike') }" @click="editor.chain().focus().toggleStrike().run()" title="删除线"><s>S</s></button>
      <span class="rte-sep"></span>
      <button type="button" :class="{ active: editor.isActive('heading', { level: 1 }) }" @click="editor.chain().focus().toggleHeading({ level: 1 }).run()" title="标题1">H1</button>
      <button type="button" :class="{ active: editor.isActive('heading', { level: 2 }) }" @click="editor.chain().focus().toggleHeading({ level: 2 }).run()" title="标题2">H2</button>
      <button type="button" :class="{ active: editor.isActive('heading', { level: 3 }) }" @click="editor.chain().focus().toggleHeading({ level: 3 }).run()" title="标题3">H3</button>
      <span class="rte-sep"></span>
      <button type="button" :class="{ active: editor.isActive('bulletList') }" @click="editor.chain().focus().toggleBulletList().run()" title="无序列表">• 列表</button>
      <button type="button" :class="{ active: editor.isActive('orderedList') }" @click="editor.chain().focus().toggleOrderedList().run()" title="有序列表">1. 列表</button>
      <button type="button" :class="{ active: editor.isActive('blockquote') }" @click="editor.chain().focus().toggleBlockquote().run()" title="引用">❝</button>
      <button type="button" :class="{ active: editor.isActive('codeBlock') }" @click="editor.chain().focus().toggleCodeBlock().run()" title="代码块">&lt;/&gt;</button>
      <span class="rte-sep"></span>
      <button type="button" @click="setLink" title="链接">🔗</button>
      <button type="button" @click="pickImage" title="插入图片">🖼</button>
      <button type="button" @click="editor.chain().focus().setHorizontalRule().run()" title="分割线">―</button>
      <span class="rte-sep"></span>
      <button type="button" :disabled="!editor.can().undo()" @click="editor.chain().focus().undo().run()" title="撤销">↶</button>
      <button type="button" :disabled="!editor.can().redo()" @click="editor.chain().focus().redo().run()" title="重做">↷</button>
      <button type="button" @click="editor.chain().focus().unsetAllMarks().clearNodes().run()" title="清除格式">清除</button>
    </div>
    <EditorContent :editor="editor" class="rte-content" />
    <input ref="fileInput" type="file" accept="image/*" class="hidden" @change="onImage" />
  </div>
</template>

<style scoped>
.rte { border: 1px solid #e5e7eb; border-radius: 0.75rem; background: #fff; overflow: hidden; }
.rte--disabled { opacity: 0.7; }
.rte-toolbar { display: flex; flex-wrap: wrap; gap: 4px; padding: 8px; border-bottom: 1px solid #f0f0f0; background: #fafafa; }
.rte-toolbar button { min-width: 32px; height: 30px; padding: 0 8px; border: 1px solid transparent; border-radius: 6px; background: #fff; font-size: 13px; cursor: pointer; color: #374151; }
.rte-toolbar button:hover { background: #f3f4f6; }
.rte-toolbar button.active { background: #eef2ff; border-color: #c7d2fe; color: #4338ca; }
.rte-toolbar button:disabled { opacity: 0.4; cursor: not-allowed; }
.rte-sep { width: 1px; height: 20px; background: #e5e7eb; margin: 0 2px; }
.rte-content :deep(.ProseMirror) { min-height: 180px; padding: 12px 14px; outline: none; line-height: 1.6; font-size: 14px; color: #1f2937; }
.rte-content :deep(.ProseMirror p.is-editor-empty:first-child::before) { content: attr(data-placeholder); color: #9ca3af; float: left; height: 0; pointer-events: none; }
.rte-content :deep(.ProseMirror img.rte-image) { max-width: 100%; border-radius: 8px; margin: 8px 0; }
.rte-content :deep(.ProseMirror h1) { font-size: 1.5em; font-weight: 700; margin: 0.4em 0; }
.rte-content :deep(.ProseMirror h2) { font-size: 1.3em; font-weight: 700; margin: 0.4em 0; }
.rte-content :deep(.ProseMirror h3) { font-size: 1.15em; font-weight: 600; margin: 0.4em 0; }
.rte-content :deep(.ProseMirror ul), .rte-content :deep(.ProseMirror ol) { padding-left: 1.4em; }
.rte-content :deep(.ProseMirror blockquote) { border-left: 3px solid #d1d5db; padding-left: 12px; color: #6b7280; margin: 8px 0; }
.rte-content :deep(.ProseMirror pre) { background: #1f2937; color: #f9fafb; padding: 12px; border-radius: 8px; overflow: auto; }
.rte-content :deep(.ProseMirror code) { background: #f3f4f6; padding: 1px 5px; border-radius: 4px; font-size: 0.9em; }
.hidden { display: none; }
</style>
