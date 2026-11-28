<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
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
    label: t("aiBuilder.新字段_fcbn2"),
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
    if (!f.options?.choices?.length) f.options = { choices: ['选项一', t("aiBuilder.选项二_ltuyk")] }
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
        <span class="font-semibold">{{ $t('aiBuilder.text_73b0ru') }}</span>
        <span class="text-xs text-ink-400">{{ $t('aiBuilder.说清你要_9bre9v') }}</span>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-8">
      <!-- AI 未配置 -->
      <div
        v-if="aiUnavailable"
        class="mb-6 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3"
      >
        {{ $t('aiBuilder.text_wyv7qy') }}
        <router-link to="/cms/ai-settings" class="font-medium underline">{{ $t('aiBuilder.去_1kv3c3') }}</router-link>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <!-- 左：需求输入 -->
        <section class="lg:col-span-2 space-y-4">
          <div class="card">
            <h2 class="text-base font-semibold text-ink-900">{{ $t('aiBuilder.告诉_15tk9d') }}</h2>
            <p class="mt-1 text-xs text-ink-500 leading-relaxed">
              {{ $t('aiBuilder.写清内容_1ns19l') }}
            </p>

            <label class="block mt-4 text-xs font-medium text-ink-700">{{ $t('aiBuilder.需求描述_jhzetf') }}</label>
            <textarea
              v-model="description"
              rows="6"
              class="input mt-1.5 resize-y"
              :placeholder="$t('aiBuilder.例_1o286s')"
            ></textarea>
            <p class="mt-1 text-xs text-ink-400">{{ description.trim().length }} {{ $t('aiBuilder.字_1x8phu') }}</p>

            <label class="block mt-3 text-xs font-medium text-ink-700">{{ $t('aiBuilder.补充要求_1iqy3h') }}</label>
            <input
              v-model="extraHint"
              class="input mt-1.5"
              :placeholder="$t('aiBuilder.例_a895nu')"
            />

            <button class="btn-primary w-full mt-4" :disabled="!canPropose" @click="propose">
              {{ loading ? $t('aiBuilder.正在生成_56cv8w') : spec ? $t('aiBuilder.重新生成_17cemr') : $t('aiBuilder.生成结构_yopwld') }}
            </button>

            <p v-if="errorMsg" class="mt-3 text-xs text-red-600 leading-relaxed">{{ errorMsg }}</p>
          </div>

          <!-- 迭代记录 -->
          <div v-if="rounds.length" class="card">
            <h3 class="text-sm font-semibold text-ink-900">{{ $t('aiBuilder.生成记录_f6u8ty') }}</h3>
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
                <p class="mt-1 text-ink-400">{{ r.fieldCount }} {{ $t('aiBuilder.个字段_bwa94') }}<span v-if="r.hint"> {{ $t('aiBuilder.text_1simd7') }}</span></p>
              </li>
            </ul>
          </div>
        </section>

        <!-- 右：草案编辑 -->
        <section class="lg:col-span-3">
          <div v-if="!spec" class="card flex flex-col items-center justify-center py-20 text-center">
            <div class="text-4xl">🧩</div>
            <p class="mt-3 text-sm font-medium text-ink-700">{{ $t('aiBuilder.还没有草_8bebun') }}</p>
            <p class="mt-1 text-xs text-ink-400 max-w-xs leading-relaxed">
              {{ $t('aiBuilder.左侧描述_hrjztj') }}
            </p>
          </div>

          <div v-else class="space-y-4">
            <!-- 创建成功 -->
            <div v-if="createdId" class="card border-emerald-200 bg-emerald-50">
              <p class="text-sm font-medium text-emerald-800">
                {{ $t('aiBuilder.内容类型_1apaxc') }}{{ spec.name }}{{ $t('aiBuilder.text_1tzcnw') }}{{ createdId }}，{{ spec.fields.length }} {{ $t('aiBuilder.个字段_a8u881') }}
              </p>
              <div class="mt-3 flex gap-2">
                <button class="btn-primary" @click="goFields">{{ $t('aiBuilder.配置字段_1q3qc3') }}</button>
                <router-link :to="`/cms/entries?ct=${spec.key}`" class="btn-outline">{{ $t('aiBuilder.去录入内_1jmkhx') }}</router-link>
              </div>
            </div>

            <!-- 基本信息 -->
            <div class="card">
              <div class="flex items-center justify-between">
                <h2 class="text-base font-semibold text-ink-900">{{ $t('aiBuilder.草案_mwin') }}</h2>
                <span v-if="spec._meta?.model" class="text-xs text-ink-400 font-mono">
                  {{ spec._meta.model }}
                </span>
              </div>

              <p
                v-if="spec.key_conflict"
                class="mt-3 text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2"
              >
                {{ $t('aiBuilder.标识_igm7') }} <code class="font-mono">{{ spec.key }}</code> {{ $t('aiBuilder.已存在_deo03i') }}
              </p>

              <div class="mt-4 grid grid-cols-1 sm:grid-cols-6 gap-3">
                <div class="sm:col-span-1">
                  <label class="block text-xs font-medium text-ink-700">{{ $t('aiBuilder.图标_fd8p') }}</label>
                  <input v-model="spec.icon" class="input mt-1.5 text-center" maxlength="4" />
                </div>
                <div class="sm:col-span-3">
                  <label class="block text-xs font-medium text-ink-700">{{ $t('aiBuilder.名称_eyrn') }}</label>
                  <input v-model="spec.name" class="input mt-1.5" />
                </div>
                <div class="sm:col-span-2">
                  <label class="block text-xs font-medium text-ink-700">{{ $t('aiBuilder.标识_ew3y3i') }}</label>
                  <input v-model="spec.key" class="input mt-1.5 font-mono" />
                </div>
              </div>

              <div class="mt-3">
                <label class="block text-xs font-medium text-ink-700">{{ $t('aiBuilder.说明_od5m') }}</label>
                <input v-model="spec.description" class="input mt-1.5" :placeholder="$t('aiBuilder.一句话说_rcfd7z')" />
              </div>

              <div class="mt-4 flex flex-wrap gap-5 text-xs text-ink-700">
                <label class="inline-flex items-center gap-2">
                  <input v-model="spec.supports_category" type="checkbox" class="rounded border-ink-300" />
                  {{ $t('aiBuilder.支持分类_d6cdpj') }}
                </label>
                <label class="inline-flex items-center gap-2">
                  <input v-model="spec.supports_tags" type="checkbox" class="rounded border-ink-300" />
                  {{ $t('aiBuilder.支持标签_d6g495') }}
                </label>
                <label class="inline-flex items-center gap-2">
                  <input v-model="spec.translatable" type="checkbox" class="rounded border-ink-300" />
                  {{ $t('aiBuilder.需要多语_13vtkj') }}
                </label>
              </div>
            </div>

            <!-- 字段 -->
            <div class="card">
              <div class="flex items-center justify-between">
                <h3 class="text-sm font-semibold text-ink-900">
                  {{ $t('aiBuilder.字段_g4la') }} <span class="text-ink-400 font-normal">（{{ spec.fields.length }} {{ $t('aiBuilder.个_ep0f') }}</span>
                </h3>
                <button class="btn-ghost text-xs" @click="addField">{{ $t('aiBuilder.text_z2gmoo') }}</button>
              </div>

              <div class="mt-3 -mx-2 overflow-x-auto">
                <table class="w-full text-xs">
                  <thead>
                    <tr class="text-left text-ink-500 border-b border-ink-200">
                      <th class="px-2 py-2 font-medium">{{ $t('aiBuilder.字段名_dwexb') }}</th>
                      <th class="px-2 py-2 font-medium">field_key</th>
                      <th class="px-2 py-2 font-medium">{{ $t('aiBuilder.类型_lnjk') }}</th>
                      <th class="px-2 py-2 font-medium text-center">{{ $t('aiBuilder.必填_grwm') }}</th>
                      <th class="px-2 py-2 font-medium">{{ $t('aiBuilder.选项_pc40') }}</th>
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
                          :placeholder="$t('aiBuilder.逗号分隔_iiyrym')"
                          @input="setChoices(f, $event)"
                        />
                        <span v-else class="text-ink-300">—</span>
                      </td>
                      <td class="px-2 py-2 text-right">
                        <button class="text-ink-400 hover:text-red-600" :title="$t('aiBuilder.删除字段_azdh1e')" @click="removeField(i)">
                          ✕
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div class="mt-5 flex items-center gap-3">
                <button class="btn-primary" :disabled="!canApply" @click="apply">
                  {{ applying ? $t('aiBuilder.正在创建_517pfm') : $t('aiBuilder.确认创建_froiph') }}
                </button>
                <span class="text-xs text-ink-400">
                  {{ $t('aiBuilder.创建后内_115c7t') }}
                </span>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  </div>
</template>
