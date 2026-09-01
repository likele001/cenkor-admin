<script setup lang="ts">
// 富文本编辑器（M4 打磨升级）：TipTap + 表格 / 对齐 / 文字颜色 / 图片增强 / 粘贴上传 / 字数统计
import { watch, onBeforeUnmount, ref, computed } from 'vue'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import Link from '@tiptap/extension-link'
import Image from '@tiptap/extension-image'
import Placeholder from '@tiptap/extension-placeholder'
import Table from '@tiptap/extension-table'
import TableRow from '@tiptap/extension-table-row'
import TableHeader from '@tiptap/extension-table-header'
import TableCell from '@tiptap/extension-table-cell'
import TextAlign from '@tiptap/extension-text-align'
import TextStyle from '@tiptap/extension-text-style'
import Color from '@tiptap/extension-color'
import { api } from '@/lib/api'

const props = withDefaults(defineProps<{
  modelValue?: string | null
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

// 自定义图片扩展：支持 width / align 属性
const ResizableImage = Image.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      width: {
        default: null,
        parseHTML: (el: any) => el.getAttribute('width'),
        renderHTML: (attrs: any) => (attrs.width ? { width: attrs.width } : {}),
      },
      align: {
        default: null,
        parseHTML: (el: any) => el.getAttribute('align'),
        renderHTML: (attrs: any) => (attrs.align ? { align: attrs.align } : {}),
      },
    }
  },
})

const charCount = ref(0)

async function uploadImage(file: File): Promise<string | null> {
  const fd = new FormData()
  fd.append('file', file)
  const { data } = await api.post('/api/v1/cms/media/upload', fd)
  return data?.url || null
}

async function insertImageFile(file: File) {
  try {
    const url = await uploadImage(file)
    if (url && editor.value) editor.value.chain().focus().setImage({ src: url }).run()
  } catch {
    window.alert('图片上传失败，请重试')
  }
}

const editor = useEditor({
  content: props.modelValue || '',
  editable: !props.disabled,
  extensions: [
    StarterKit,
    Underline,
    Link.configure({ openOnClick: false, HTMLAttributes: { rel: 'noopener noreferrer', target: '_blank' } }),
    ResizableImage.configure({ inline: false, HTMLAttributes: { class: 'rte-image' } }),
    Placeholder.configure({ placeholder: props.placeholder }),
    Table.configure({ resizable: true }),
    TableRow,
    TableHeader,
    TableCell,
    TextAlign.configure({ types: ['heading', 'paragraph'] }),
    TextStyle,
    Color,
  ],
  editorProps: {
    // 剪贴板直接粘贴图片 → 自动上传并插入
    handlePaste: (view: any, event: any) => {
      const files: File[] = Array.from(event.clipboardData?.files || [])
      const img = files.find((f) => f.type.startsWith('image/'))
      if (!img) return false
      uploadImage(img).then((url) => {
        if (!url) return
        const { schema, tr } = view.state
        const node = schema.nodes.image.create({ src: url })
        view.dispatch(tr.replaceSelectionWith(node))
      })
      return true
    },
  },
  onUpdate: ({ editor }) => {
    const html = editor.getHTML()
    charCount.value = editor.getText().replace(/\s/g, '').length
    emit('update:modelValue', editor.isEmpty ? '' : html)
  },
})

watch(() => props.modelValue, (val) => {
  const e = editor.value
  if (e && val !== e.getHTML()) {
    e.commands.setContent(val || '', false)
    charCount.value = e.getText().replace(/\s/g, '').length
  }
})
watch(() => props.disabled, (d) => editor.value?.setEditable(!d))

onBeforeUnmount(() => editor.value?.destroy())

// ---- 图片上传（工具栏按钮） ----
const fileInput = ref<HTMLInputElement | null>(null)
const replaceInput = ref<HTMLInputElement | null>(null)
function pickImage() { fileInput.value?.click() }
function pickReplace() { replaceInput.value?.click() }
async function onImage(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (file) await insertImageFile(file)
}
async function onReplaceImage(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || !editor.value) return
  try {
    const url = await uploadImage(file)
    if (url) editor.value.chain().focus().updateAttributes('image', { src: url }).run()
  } catch {
    window.alert('图片上传失败，请重试')
  }
}

// ---- 链接 ----
function setLink() {
  const e = editor.value
  if (!e) return
  const prev = (e.getAttributes('link').href as string) || ''
  const url = window.prompt('输入链接地址（留空取消链接）', prev)
  if (url === null) return
  if (url === '') { e.chain().focus().extendMarkRange('link').unsetLink().run(); return }
  e.chain().focus().extendMarkRange('link').setLink({ href: url }).run()
}

// ---- 表格 ----
function insertTable() {
  editor.value?.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()
}

// ---- 颜色 ----
const COLORS = [
  { name: '默认', color: '' },
  { name: '红', color: '#dc2626' },
  { name: '橙', color: '#ea580c' },
  { name: '黄', color: '#ca8a04' },
  { name: '绿', color: '#16a34a' },
  { name: '蓝', color: '#2563eb' },
  { name: '紫', color: '#7c3aed' },
  { name: '灰', color: '#6b7280' },
]
function setColor(color: string) {
  const e = editor.value
  if (!e) return
  if (!color) e.chain().focus().unsetColor().run()
  else e.chain().focus().setColor(color).run()
}

// ---- 图片工具（选中图片时显示） ----
const imgActive = computed(() => !!editor.value?.isActive('image'))
function imgAlign(align: string) {
  editor.value?.chain().focus().updateAttributes('image', { align }).run()
}
function imgWidth(pct: string) {
  editor.value?.chain().focus().updateAttributes('image', { width: pct }).run()
}
function imgDelete() {
  editor.value?.chain().focus().deleteSelection().run()
}
</script>

<template>
  <div class="rte" :class="{ 'rte--disabled': disabled }">
    <div v-if="editor && !disabled" class="rte-toolbar">
      <!-- 文字样式 -->
      <button type="button" :class="{ active: editor.isActive('bold') }" @click="editor.chain().focus().toggleBold().run()" title="加粗"><b>B</b></button>
      <button type="button" :class="{ active: editor.isActive('italic') }" @click="editor.chain().focus().toggleItalic().run()" title="斜体"><i>I</i></button>
      <button type="button" :class="{ active: editor.isActive('underline') }" @click="editor.chain().focus().toggleUnderline().run()" title="下划线"><u>U</u></button>
      <button type="button" :class="{ active: editor.isActive('strike') }" @click="editor.chain().focus().toggleStrike().run()" title="删除线"><s>S</s></button>
      <span class="rte-sep"></span>
      <!-- 标题 / 列表 / 引用 / 代码 -->
      <button type="button" :class="{ active: editor.isActive('heading', { level: 1 }) }" @click="editor.chain().focus().toggleHeading({ level: 1 }).run()" title="标题1">H1</button>
      <button type="button" :class="{ active: editor.isActive('heading', { level: 2 }) }" @click="editor.chain().focus().toggleHeading({ level: 2 }).run()" title="标题2">H2</button>
      <button type="button" :class="{ active: editor.isActive('heading', { level: 3 }) }" @click="editor.chain().focus().toggleHeading({ level: 3 }).run()" title="标题3">H3</button>
      <span class="rte-sep"></span>
      <button type="button" :class="{ active: editor.isActive('bulletList') }" @click="editor.chain().focus().toggleBulletList().run()" title="无序列表">• 列表</button>
      <button type="button" :class="{ active: editor.isActive('orderedList') }" @click="editor.chain().focus().toggleOrderedList().run()" title="有序列表">1. 列表</button>
      <button type="button" :class="{ active: editor.isActive('blockquote') }" @click="editor.chain().focus().toggleBlockquote().run()" title="引用">❝</button>
      <button type="button" :class="{ active: editor.isActive('codeBlock') }" @click="editor.chain().focus().toggleCodeBlock().run()" title="代码块">&lt;/&gt;</button>
      <span class="rte-sep"></span>
      <!-- 对齐 -->
      <button type="button" :class="{ active: editor.isActive({ textAlign: 'left' }) }" @click="editor.chain().focus().setTextAlign('left').run()" title="左对齐">⇤</button>
      <button type="button" :class="{ active: editor.isActive({ textAlign: 'center' }) }" @click="editor.chain().focus().setTextAlign('center').run()" title="居中">⇹</button>
      <button type="button" :class="{ active: editor.isActive({ textAlign: 'right' }) }" @click="editor.chain().focus().setTextAlign('right').run()" title="右对齐">⇥</button>
      <span class="rte-sep"></span>
      <!-- 颜色 -->
      <select class="rte-select" title="文字颜色" :value="editor.getAttributes('textStyle').color || ''" @change="setColor(($event.target as HTMLSelectElement).value)">
        <option value="">颜色</option>
        <option v-for="c in COLORS.filter(x => x.color)" :key="c.color" :value="c.color">{{ c.name }}</option>
      </select>
      <span class="rte-sep"></span>
      <!-- 链接 / 图片 / 表格 / 分割线 -->
      <button type="button" @click="setLink" title="链接">🔗</button>
      <button type="button" :class="{ active: imgActive }" @click="pickImage" title="插入图片">🖼</button>
      <button type="button" :class="{ active: editor.isActive('table') }" @click="insertTable" title="插入表格">▦</button>
      <button type="button" @click="editor.chain().focus().setHorizontalRule().run()" title="分割线">―</button>
      <span class="rte-sep"></span>
      <button type="button" :disabled="!editor.can().undo()" @click="editor.chain().focus().undo().run()" title="撤销">↶</button>
      <button type="button" :disabled="!editor.can().redo()" @click="editor.chain().focus().redo().run()" title="重做">↷</button>
      <button type="button" @click="editor.chain().focus().unsetAllMarks().clearNodes().run()" title="清除格式">清除</button>
    </div>

    <!-- 表格工具条（光标在表格内时显示） -->
    <div v-if="editor && !disabled && editor.isActive('table')" class="rte-toolbar rte-toolbar--sub">
      <button type="button" @click="editor.chain().focus().addRowAfter().run()" title="下方插入行">行+</button>
      <button type="button" @click="editor.chain().focus().deleteRow().run()" title="删除行">行−</button>
      <button type="button" @click="editor.chain().focus().addColumnAfter().run()" title="右侧插入列">列+</button>
      <button type="button" @click="editor.chain().focus().deleteColumn().run()" title="删除列">列−</button>
      <span class="rte-sep"></span>
      <button type="button" @click="editor.chain().focus().mergeCells().run()" title="合并单元格">合并</button>
      <button type="button" @click="editor.chain().focus().splitCell().run()" title="拆分单元格">拆分</button>
      <button type="button" class="text-red-600" @click="editor.chain().focus().deleteTable().run()" title="删除表格">删除表格</button>
    </div>

    <!-- 图片工具条（选中图片时显示） -->
    <div v-if="editor && !disabled && imgActive" class="rte-toolbar rte-toolbar--sub">
      <button type="button" :class="{ active: editor.getAttributes('image').align === 'left' }" @click="imgAlign('left')">居左</button>
      <button type="button" :class="{ active: editor.getAttributes('image').align === 'center' }" @click="imgAlign('center')">居中</button>
      <button type="button" :class="{ active: editor.getAttributes('image').align === 'right' }" @click="imgAlign('right')">居右</button>
      <span class="rte-sep"></span>
      <button type="button" :class="{ active: editor.getAttributes('image').width === '50%' }" @click="imgWidth('50%')">50%</button>
      <button type="button" :class="{ active: editor.getAttributes('image').width === '75%' }" @click="imgWidth('75%')">75%</button>
      <button type="button" :class="{ active: !editor.getAttributes('image').width }" @click="imgWidth('100%')">100%</button>
      <span class="rte-sep"></span>
      <button type="button" @click="pickReplace" title="替换图片">替换</button>
      <button type="button" class="text-red-600" @click="imgDelete" title="删除图片">删除</button>
    </div>

    <EditorContent :editor="editor" class="rte-content" />
    <div class="rte-footer">
      <span class="text-xs text-ink-400">支持粘贴图片 / Markdown 快捷输入（`# `、`- `、`> `、`---`）</span>
      <span class="text-xs text-ink-400">{{ charCount }} 字</span>
    </div>
    <input ref="fileInput" type="file" accept="image/*" class="hidden" @change="onImage" />
    <input ref="replaceInput" type="file" accept="image/*" class="hidden" @change="onReplaceImage" />
  </div>
</template>

<style scoped>
.rte { border: 1px solid #e5e7eb; border-radius: 0.75rem; background: #fff; overflow: hidden; }
.rte--disabled { opacity: 0.7; }
.rte-toolbar { display: flex; flex-wrap: wrap; gap: 4px; padding: 8px; border-bottom: 1px solid #f0f0f0; background: #fafafa; align-items: center; }
.rte-toolbar--sub { border-top: 0; }
.rte-toolbar button { min-width: 32px; height: 30px; padding: 0 8px; border: 1px solid transparent; border-radius: 6px; background: #fff; font-size: 13px; cursor: pointer; color: #374151; }
.rte-toolbar button:hover { background: #f3f4f6; }
.rte-toolbar button.active { background: #eef2ff; border-color: #c7d2fe; color: #4338ca; }
.rte-toolbar button:disabled { opacity: 0.4; cursor: not-allowed; }
.rte-select { height: 30px; border: 1px solid #e5e7eb; border-radius: 6px; font-size: 12px; background: #fff; color: #374151; }
.rte-sep { width: 1px; height: 20px; background: #e5e7eb; margin: 0 2px; }
.rte-footer { display: flex; justify-content: space-between; padding: 4px 12px; background: #fafafa; border-top: 1px solid #f0f0f0; }
.rte-content :deep(.ProseMirror) { min-height: 180px; padding: 12px 14px; outline: none; line-height: 1.6; font-size: 14px; color: #1f2937; }
.rte-content :deep(.ProseMirror p.is-editor-empty:first-child::before) { content: attr(data-placeholder); color: #9ca3af; float: left; height: 0; pointer-events: none; }
.rte-content :deep(.ProseMirror img.rte-image) { max-width: 100%; border-radius: 8px; margin: 8px 0; }
.rte-content :deep(.ProseMirror img.rte-image[align="left"]) { float: left; margin-right: 12px; }
.rte-content :deep(.ProseMirror img.rte-image[align="right"]) { float: right; margin-left: 12px; }
.rte-content :deep(.ProseMirror img.rte-image[align="center"]) { display: block; margin-left: auto; margin-right: auto; }
.rte-content :deep(.ProseMirror img.rte-image.ProseMirror-selectednode) { outline: 2px solid #6366f1; outline-offset: 2px; }
.rte-content :deep(.ProseMirror h1) { font-size: 1.5em; font-weight: 700; margin: 0.4em 0; }
.rte-content :deep(.ProseMirror h2) { font-size: 1.3em; font-weight: 700; margin: 0.4em 0; }
.rte-content :deep(.ProseMirror h3) { font-size: 1.15em; font-weight: 600; margin: 0.4em 0; }
.rte-content :deep(.ProseMirror ul), .rte-content :deep(.ProseMirror ol) { padding-left: 1.4em; }
.rte-content :deep(.ProseMirror blockquote) { border-left: 3px solid #d1d5db; padding-left: 12px; color: #6b7280; margin: 8px 0; }
.rte-content :deep(.ProseMirror pre) { background: #1f2937; color: #f9fafb; padding: 12px; border-radius: 8px; overflow: auto; }
.rte-content :deep(.ProseMirror code) { background: #f3f4f6; padding: 1px 5px; border-radius: 4px; font-size: 0.9em; }
.rte-content :deep(.ProseMirror table) { border-collapse: collapse; margin: 8px 0; table-layout: fixed; width: 100%; }
.rte-content :deep(.ProseMirror th), .rte-content :deep(.ProseMirror td) { border: 1px solid #d1d5db; padding: 6px 10px; min-width: 48px; vertical-align: top; }
.rte-content :deep(.ProseMirror th) { background: #f3f4f6; font-weight: 600; }
.rte-content :deep(.ProseMirror .selectedCell::after) { content: ""; position: absolute; inset: 0; background: rgba(99, 102, 241, 0.08); pointer-events: none; }
.rte-content :deep(.ProseMirror .selectedCell) { position: relative; }
.hidden { display: none; }
</style>
