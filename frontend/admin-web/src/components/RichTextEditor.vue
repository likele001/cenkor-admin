<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
// 富文本编辑器（M4 打磨升级）：TipTap + 表格 / 对齐 / 文字颜色 / 图片增强 / 粘贴上传 / 字数统计
import { watch, onBeforeUnmount, ref, computed } from 'vue'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Link from '@tiptap/extension-link'
import Image from '@tiptap/extension-image'
import Placeholder from '@tiptap/extension-placeholder'
import { Table } from '@tiptap/extension-table'
import TableRow from '@tiptap/extension-table-row'
import TableHeader from '@tiptap/extension-table-header'
import TableCell from '@tiptap/extension-table-cell'
import TextAlign from '@tiptap/extension-text-align'
import { TextStyle } from '@tiptap/extension-text-style'
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
    // Tiptap 3 的 StarterKit 已内置 link / underline；这里禁用内置 link，
    // 否则与下面自定义 rel/target 的 Link 扩展重名，编辑器会拒绝初始化。
    StarterKit.configure({ link: false }),
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
    // v3 起 setContent 第二个参数是 options 对象，不再是 emitUpdate 布尔值
    e.commands.setContent(val || '', { emitUpdate: false })
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
  const url = window.prompt(t("richTextEditor.输入链接_1v3yuc"), prev)
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
      <button type="button" :class="{ active: editor.isActive('bold') }" @click="editor.chain().focus().toggleBold().run()" :title="t('richTextEditor.加粗_eqk7')"><b>B</b></button>
      <button type="button" :class="{ active: editor.isActive('italic') }" @click="editor.chain().focus().toggleItalic().run()" :title="t('richTextEditor.斜体_hpvb')"><i>I</i></button>
      <button type="button" :class="{ active: editor.isActive('underline') }" @click="editor.chain().focus().toggleUnderline().run()" :title="t('richTextEditor.下划线_bu69k')"><u>U</u></button>
      <button type="button" :class="{ active: editor.isActive('strike') }" @click="editor.chain().focus().toggleStrike().run()" :title="t('richTextEditor.删除线_crbi3')"><s>S</s></button>
      <span class="rte-sep"></span>
      <!-- 标题 / 列表 / 引用 / 代码 -->
      <button type="button" :class="{ active: editor.isActive('heading', { level: 1 }) }" @click="editor.chain().focus().toggleHeading({ level: 1 }).run()" :title="t('richTextEditor.标题_fyhnk')">H1</button>
      <button type="button" :class="{ active: editor.isActive('heading', { level: 2 }) }" @click="editor.chain().focus().toggleHeading({ level: 2 }).run()" :title="t('richTextEditor.标题_fyhnl')">H2</button>
      <button type="button" :class="{ active: editor.isActive('heading', { level: 3 }) }" @click="editor.chain().focus().toggleHeading({ level: 3 }).run()" :title="t('richTextEditor.标题_fyhnm')">H3</button>
      <span class="rte-sep"></span>
      <button type="button" :class="{ active: editor.isActive('bulletList') }" @click="editor.chain().focus().toggleBulletList().run()" :title="t('richTextEditor.无序列表_d8u1b4')">{{ t("richTextEditor.text_42bvfz") }}</button>
      <button type="button" :class="{ active: editor.isActive('orderedList') }" @click="editor.chain().focus().toggleOrderedList().run()" :title="t('richTextEditor.有序列表_de3oev')">{{ t("richTextEditor.text_s6ntg") }}</button>
      <button type="button" :class="{ active: editor.isActive('blockquote') }" @click="editor.chain().focus().toggleBlockquote().run()" :title="t('richTextEditor.引用_gtdf')">❝</button>
      <button type="button" :class="{ active: editor.isActive('codeBlock') }" @click="editor.chain().focus().toggleCodeBlock().run()" :title="t('richTextEditor.代码块_c4uxl')">&lt;/&gt;</button>
      <span class="rte-sep"></span>
      <!-- 对齐 -->
      <button type="button" :class="{ active: editor.isActive({ textAlign: 'left' }) }" @click="editor.chain().focus().setTextAlign('left').run()" :title="t('richTextEditor.左对齐_e7n4t')">⇤</button>
      <button type="button" :class="{ active: editor.isActive({ textAlign: 'center' }) }" @click="editor.chain().focus().setTextAlign('center').run()" :title="t('richTextEditor.居中_g4g8')">⇹</button>
      <button type="button" :class="{ active: editor.isActive({ textAlign: 'right' }) }" @click="editor.chain().focus().setTextAlign('right').run()" :title="t('richTextEditor.右对齐_cr6i2')">⇥</button>
      <span class="rte-sep"></span>
      <!-- 颜色 -->
      <select class="rte-select" :title="t('richTextEditor.文字颜色_d74746')" :value="editor.getAttributes('textStyle').color || ''" @change="setColor(($event.target as HTMLSelectElement).value)">
        <option value="">{{ t("richTextEditor.颜色_qo9i") }}</option>
        <option v-for="c in COLORS.filter(x => x.color)" :key="c.color" :value="c.color">{{ c.name }}</option>
      </select>
      <span class="rte-sep"></span>
      <!-- 链接 / 图片 / 表格 / 分割线 -->
      <button type="button" @click="setLink" :title="t('richTextEditor.link')">🔗</button>
      <button type="button" :class="{ active: imgActive }" @click="pickImage" :title="t('richTextEditor.插入图片_cxlgyk')">🖼</button>
      <button type="button" :class="{ active: editor.isActive('table') }" @click="insertTable" :title="t('richTextEditor.插入表格_cxttk7')">▦</button>
      <button type="button" @click="editor.chain().focus().setHorizontalRule().run()" :title="t('richTextEditor.分割线_cf85v')">―</button>
      <span class="rte-sep"></span>
      <button type="button" :disabled="!editor.can().undo()" @click="editor.chain().focus().undo().run()" :title="t('richTextEditor.撤销_hxp8')">↶</button>
      <button type="button" :disabled="!editor.can().redo()" @click="editor.chain().focus().redo().run()" :title="t('richTextEditor.重做_p8od')">↷</button>
      <button type="button" @click="editor.chain().focus().unsetAllMarks().clearNodes().run()" :title="t('richTextEditor.清除格式_ei3atu')">{{ t("richTextEditor.清除_jjen") }}</button>
    </div>

    <!-- 表格工具条（光标在表格内时显示） -->
    <div v-if="editor && !disabled && editor.isActive('table')" class="rte-toolbar rte-toolbar--sub">
      <button type="button" @click="editor.chain().focus().addRowAfter().run()" :title="t('richTextEditor.下方插入_y9q2a3')">{{ t("richTextEditor.行_n6n3") }}</button>
      <button type="button" @click="editor.chain().focus().deleteRow().run()" :title="t('richTextEditor.删除行_crde0')">{{ t("richTextEditor.行_ndc6") }}</button>
      <button type="button" @click="editor.chain().focus().addColumnAfter().run()" :title="t('richTextEditor.右侧插入_1ikv0u')">{{ t("richTextEditor.列_dypg") }}</button>
      <button type="button" @click="editor.chain().focus().deleteColumn().run()" :title="t('richTextEditor.删除列_cr2oj')">{{ t("richTextEditor.列_e5ej") }}</button>
      <span class="rte-sep"></span>
      <button type="button" @click="editor.chain().focus().mergeCells().run()" :title="t('richTextEditor.合并单元_1kp8i8')">{{ t("richTextEditor.合并_et7y") }}</button>
      <button type="button" @click="editor.chain().focus().splitCell().run()" :title="t('richTextEditor.拆分单元_15qqxd')">{{ t("richTextEditor.拆分_h91c") }}</button>
      <button type="button" class="text-red-600" @click="editor.chain().focus().deleteTable().run()" :title="t('richTextEditor.删除表格_azl4bc')">{{ t("richTextEditor.删除表格_azl4bc") }}</button>
    </div>

    <!-- 图片工具条（选中图片时显示） -->
    <div v-if="editor && !disabled && imgActive" class="rte-toolbar rte-toolbar--sub">
      <button type="button" :class="{ active: editor.getAttributes('image').align === 'left' }" @click="imgAlign('left')">{{ t("richTextEditor.居左_g7k1") }}</button>
      <button type="button" :class="{ active: editor.getAttributes('image').align === 'center' }" @click="imgAlign('center')">{{ t("richTextEditor.居中_g4g8") }}</button>
      <button type="button" :class="{ active: editor.getAttributes('image').align === 'right' }" @click="imgAlign('right')">{{ t("richTextEditor.居右_g5la") }}</button>
      <span class="rte-sep"></span>
      <button type="button" :class="{ active: editor.getAttributes('image').width === '50%' }" @click="imgWidth('50%')">50%</button>
      <button type="button" :class="{ active: editor.getAttributes('image').width === '75%' }" @click="imgWidth('75%')">75%</button>
      <button type="button" :class="{ active: !editor.getAttributes('image').width }" @click="imgWidth('100%')">100%</button>
      <span class="rte-sep"></span>
      <button type="button" @click="pickReplace" :title="t('richTextEditor.替换图片_denfyk')">{{ t("richTextEditor.替换_i2bn") }}</button>
      <button type="button" class="text-red-600" @click="imgDelete" :title="t('richTextEditor.删除图片_azcrpp')">{{ t("richTextEditor.delete") }}</button>
    </div>

    <EditorContent :editor="editor" class="rte-content" />
    <div class="rte-footer">
      <span class="text-xs text-ink-400">{{ $t('richTextEditor.支持粘贴_7c4tn4') }}</span>
      <span class="text-xs text-ink-400">{{ charCount }} {{ $t('richTextEditor.字_i1j') }}</span>
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
