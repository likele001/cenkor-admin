<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/lib/api'

/** 后端 copilot.py 的 FIELD_TYPES 白名单，保持一致 */
const FIELD_TYPES = [
  'text', 'longtext', 'richtext', 'markdown', 'number', 'boolean',
  'date', 'datetime', 'url', 'email', 'phone', 'image', 'images',
  'file', 'files', 'select', 'multiselect', 'color', 'json',
  'repeater', 'relation',
]

const TYPE_LABEL: Record<string, string> = {
  text: '单行文本', longtext: '多行文本', richtext: '富文本', markdown: 'Markdown',
  number: '数字', boolean: '布尔', date: '日期', datetime: '日期时间',
  url: '链接', email: '邮箱', phone: '电话', image: '单图', images: '多图',
  file: '单文件', files: '多文件', select: '单选', multiselect: '多选',
  color: '颜色', json: 'JSON', repeater: '重复组', relation: '关联',
}

interface FieldSpec {
  field_key: string
  label: string
  field_type: string
  required: boolean
  default_value: any
  options: { choices?: string[] } | null
  validation: any
  group: string | null
  sort: number
}

interface Spec {
  key: string
  name: string
  description: string | null
  icon: string | null
  supports_category: boolean
  supports_tags: boolean
  translatable: boolean
  fields: FieldSpec[]
  key_conflict?: boolean
  _meta?: { provider?: string; model?: string; tokens_in?: number; tokens_out?: number }
}

interface Round {
  desc: string
  hint: string
  fieldCount: number
  key: string
  at: string
}

const router = useRouter()

const description = ref('')
const extraHint = ref('')
const spec = ref<Spec | null>(null)
const rounds = ref<Round[]>([])
const loading = ref(false)
const applying = ref(false)
const errorMsg = ref('')
const aiUnavailable = ref(false)
const createdId = ref<number | null>(null)

const canPropose = computed(() => description.value.trim().length >= 4 && !loading.value)
const canApply = computed(
  () => !!spec.value && !applying.value && spec.value.fields.length > 0 && !spec.value.key_conflict,
)

function errText(e: any): string {
  const d = e?.response?.data?.detail
  if (Array.isArray(d)) return d.map((x: any) => x.msg || JSON.stringify(x)).join('; ')
  return d || e?.message || '未知错误'
}

async function propose() {
  if (!canPropose.value) return
  loading.value = true
  errorMsg.value = ''
  createdId.value = null
  try {
    const { data } = await api.post('/api/v1/cms/ai/content-types/propose', {
      description: description.value.trim(),
      extra_hint: extraHint.value.trim(),
      locale: 'zh-CN',
    })
    spec.value = data as Spec
    rounds.value.unshift({
      desc: description.value.trim().slice(0, 60),
      hint: extraHint.value.trim(),
      fieldCount: (data as Spec).fields?.length ?? 0,
      key: (data as Spec).key,
      at: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
    })
  } catch (e: any) {
    if (e?.response?.status === 503) {
      aiUnavailable.value = true
      errorMsg.value = errText(e)
    } else {
      errorMsg.value = errText(e)
    }
  } finally {
    loading.value = false
  }
}

async function apply() {
  if (!canApply.value || !spec.value) return
  applying.value = true
  errorMsg.value = ''
  try {
    const { data } = await api.post('/api/v1/cms/ai/content-types/apply', spec.value)
    createdId.value = data.id
    spec.value.key_conflict = false
  } catch (e: any) {
    errorMsg.value = errText(e)
  } finally {
    applying.value = false
  }
}

function addField() {
  if (!spec.value) return
  spec.value.fields.push({
    field_key: `field_${spec.value.fields.length + 1}`,
    label: '新字段',
    field_type: 'text',
    required: false,
    default_value: null,
    options: null,
    validation: null,
    group: null,
    sort: spec.value.fields.length,
  })
}

function removeField(i: number) {
  spec.value?.fields.splice(i, 1)
}

function onTypeChange(f: FieldSpec) {
  if (f.field_type === 'select' || f.field_type === 'multiselect') {
    if (!f.options?.choices?.length) f.options = { choices: ['选项一', '选项二'] }
  } else if (f.options) {
    f.options = null
  }
}

function choicesText(f: FieldSpec): string {
  return (f.options?.choices || []).join(', ')
}

function setChoices(f: FieldSpec, ev: Event) {
  const raw = (ev.target as HTMLInputElement).value
  const parts = raw.split(/[,，]/).map((s) => s.trim()).filter(Boolean)
  f.options = { choices: parts }
}

function reuse(r: Round) {
  description.value = r.desc
  extraHint.value = r.hint
}

function goFields() {
  if (createdId.value) {
    router.push({ name: 'cms-content-type-fields', params: { id: createdId.value } })
  }
}
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/" class="text-sm text-ink-500 hover:text-ink-900">← Dashboard</router-link>
        <span class="font-semibold">AI 建模向导</span>
        <span class="text-xs text-ink-400">说清你要管什么内容，生成字段结构，确认后落库</span>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-8">
      <!-- AI 未配置 -->
      <div
        v-if="aiUnavailable"
        class="mb-6 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3"
      >
        AI 尚未配置，无法生成草案。
        <router-link to="/cms/ai-settings" class="font-medium underline">去 AI 设置绑定服务商与密钥 →</router-link>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <!-- 左：需求输入 -->
        <section class="lg:col-span-2 space-y-4">
          <div class="card">
            <h2 class="text-base font-semibold text-ink-900">告诉 AI 你要管什么</h2>
            <p class="mt-1 text-xs text-ink-500 leading-relaxed">
              写清内容对象、要记哪些信息、给谁看。越具体，字段越贴合。
            </p>

            <label class="block mt-4 text-xs font-medium text-ink-700">需求描述</label>
            <textarea
              v-model="description"
              rows="6"
              class="input mt-1.5 resize-y"
              placeholder="例：我要管理工业阀门产品，需要记录型号、口径、压力等级、材质、连接方式、适用介质、产品图片和样本 PDF，还要能按行业分类。"
            ></textarea>
            <p class="mt-1 text-xs text-ink-400">{{ description.trim().length }} 字，至少 4 字</p>

            <label class="block mt-3 text-xs font-medium text-ink-700">补充要求（可选）</label>
            <input
              v-model="extraHint"
              class="input mt-1.5"
              placeholder="例：必填项只要型号和名称；不要价格字段"
            />

            <button class="btn-primary w-full mt-4" :disabled="!canPropose" @click="propose">
              {{ loading ? '正在生成…' : spec ? '重新生成草案' : '生成结构草案' }}
            </button>

            <p v-if="errorMsg" class="mt-3 text-xs text-red-600 leading-relaxed">{{ errorMsg }}</p>
          </div>

          <!-- 迭代记录 -->
          <div v-if="rounds.length" class="card">
            <h3 class="text-sm font-semibold text-ink-900">生成记录</h3>
            <ul class="mt-3 space-y-2">
              <li
                v-for="(r, i) in rounds"
                :key="i"
                class="text-xs border border-ink-200 rounded-lg px-3 py-2 cursor-pointer hover:bg-ink-50"
                @click="reuse(r)"
              >
                <div class="flex items-center justify-between gap-2">
                  <span class="font-mono text-ink-700">{{ r.key }}</span>
                  <span class="text-ink-400">{{ r.at }}</span>
                </div>
                <p class="mt-1 text-ink-500 line-clamp-2">{{ r.desc }}</p>
                <p class="mt-1 text-ink-400">{{ r.fieldCount }} 个字段<span v-if="r.hint"> · 含补充要求</span></p>
              </li>
            </ul>
          </div>
        </section>

        <!-- 右：草案编辑 -->
        <section class="lg:col-span-3">
          <div v-if="!spec" class="card flex flex-col items-center justify-center py-20 text-center">
            <div class="text-4xl">🧩</div>
            <p class="mt-3 text-sm font-medium text-ink-700">还没有草案</p>
            <p class="mt-1 text-xs text-ink-400 max-w-xs leading-relaxed">
              左侧描述你的内容需求，AI 会生成内容类型和字段结构。生成后可以在这里逐项调整，确认无误再创建。
            </p>
          </div>

          <div v-else class="space-y-4">
            <!-- 创建成功 -->
            <div v-if="createdId" class="card border-emerald-200 bg-emerald-50">
              <p class="text-sm font-medium text-emerald-800">
                内容类型「{{ spec.name }}」已创建（id={{ createdId }}，{{ spec.fields.length }} 个字段）
              </p>
              <div class="mt-3 flex gap-2">
                <button class="btn-primary" @click="goFields">配置字段与选项 →</button>
                <router-link :to="`/cms/entries?ct=${spec.key}`" class="btn-outline">去录入内容</router-link>
              </div>
            </div>

            <!-- 基本信息 -->
            <div class="card">
              <div class="flex items-center justify-between">
                <h2 class="text-base font-semibold text-ink-900">草案</h2>
                <span v-if="spec._meta?.model" class="text-xs text-ink-400 font-mono">
                  {{ spec._meta.model }}
                </span>
              </div>

              <p
                v-if="spec.key_conflict"
                class="mt-3 text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2"
              >
                标识 <code class="font-mono">{{ spec.key }}</code> 已存在，改一个 key 再创建。
              </p>

              <div class="mt-4 grid grid-cols-1 sm:grid-cols-6 gap-3">
                <div class="sm:col-span-1">
                  <label class="block text-xs font-medium text-ink-700">图标</label>
                  <input v-model="spec.icon" class="input mt-1.5 text-center" maxlength="4" />
                </div>
                <div class="sm:col-span-3">
                  <label class="block text-xs font-medium text-ink-700">名称</label>
                  <input v-model="spec.name" class="input mt-1.5" />
                </div>
                <div class="sm:col-span-2">
                  <label class="block text-xs font-medium text-ink-700">标识 key</label>
                  <input v-model="spec.key" class="input mt-1.5 font-mono" />
                </div>
              </div>

              <div class="mt-3">
                <label class="block text-xs font-medium text-ink-700">说明</label>
                <input v-model="spec.description" class="input mt-1.5" placeholder="一句话说明装什么内容" />
              </div>

              <div class="mt-4 flex flex-wrap gap-5 text-xs text-ink-700">
                <label class="inline-flex items-center gap-2">
                  <input v-model="spec.supports_category" type="checkbox" class="rounded border-ink-300" />
                  支持分类
                </label>
                <label class="inline-flex items-center gap-2">
                  <input v-model="spec.supports_tags" type="checkbox" class="rounded border-ink-300" />
                  支持标签
                </label>
                <label class="inline-flex items-center gap-2">
                  <input v-model="spec.translatable" type="checkbox" class="rounded border-ink-300" />
                  需要多语言
                </label>
              </div>
            </div>

            <!-- 字段 -->
            <div class="card">
              <div class="flex items-center justify-between">
                <h3 class="text-sm font-semibold text-ink-900">
                  字段 <span class="text-ink-400 font-normal">（{{ spec.fields.length }} 个）</span>
                </h3>
                <button class="btn-ghost text-xs" @click="addField">+ 添加字段</button>
              </div>

              <div class="mt-3 -mx-2 overflow-x-auto">
                <table class="w-full text-xs">
                  <thead>
                    <tr class="text-left text-ink-500 border-b border-ink-200">
                      <th class="px-2 py-2 font-medium">字段名</th>
                      <th class="px-2 py-2 font-medium">field_key</th>
                      <th class="px-2 py-2 font-medium">类型</th>
                      <th class="px-2 py-2 font-medium text-center">必填</th>
                      <th class="px-2 py-2 font-medium">选项</th>
                      <th class="px-2 py-2"></th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(f, i) in spec.fields" :key="i" class="border-b border-ink-100 last:border-0">
                      <td class="px-2 py-2">
                        <input v-model="f.label" class="input py-1 text-xs" />
                      </td>
                      <td class="px-2 py-2">
                        <input v-model="f.field_key" class="input py-1 text-xs font-mono" />
                      </td>
                      <td class="px-2 py-2">
                        <select v-model="f.field_type" class="input py-1 text-xs" @change="onTypeChange(f)">
                          <option v-for="t in FIELD_TYPES" :key="t" :value="t">
                            {{ TYPE_LABEL[t] || t }}
                          </option>
                        </select>
                      </td>
                      <td class="px-2 py-2 text-center">
                        <input v-model="f.required" type="checkbox" class="rounded border-ink-300" />
                      </td>
                      <td class="px-2 py-2">
                        <input
                          v-if="f.field_type === 'select' || f.field_type === 'multiselect'"
                          :value="choicesText(f)"
                          class="input py-1 text-xs"
                          placeholder="逗号分隔"
                          @input="setChoices(f, $event)"
                        />
                        <span v-else class="text-ink-300">—</span>
                      </td>
                      <td class="px-2 py-2 text-right">
                        <button class="text-ink-400 hover:text-red-600" title="删除字段" @click="removeField(i)">
                          ✕
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div class="mt-5 flex items-center gap-3">
                <button class="btn-primary" :disabled="!canApply" @click="apply">
                  {{ applying ? '正在创建…' : '确认创建' }}
                </button>
                <span class="text-xs text-ink-400">
                  创建后内容类型与字段会落库，可再进「内容类型」页调整
                </span>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  </div>
</template>
