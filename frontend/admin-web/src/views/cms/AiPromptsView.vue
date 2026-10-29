<script setup lang="ts">
/**
 * 提示词管理 · 改措辞不用发版
 *
 * 左栏选提示词，右栏编辑 / 保存新版本 / 回滚 / 恢复出厂 / 看 diff。
 * 保存即生效（后端清缓存），所以「保存」按钮要给出明确后果提示。
 */
import { computed, onMounted, ref } from 'vue'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

interface Overview {
  key: string
  label: string
  active_version: number | null
  note: string | null
  updated_at: string | null
  differs_from_default: boolean
  has_versions: boolean
}

interface Version {
  id: number
  version: number
  content: string
  note: string | null
  is_active: boolean
  created_by: number | null
  created_at: string | null
}

interface Detail {
  key: string
  label: string
  factory_default: string
  active_content: string
  versions: Version[]
}

const auth = useAuthStore()
/** 改提示词等于改全站 AI 产出，和「换模型」同档，需要 cms:ai:manage */
const canManage = computed(() => auth.hasPermission('cms:ai:manage'))

const list = ref<Overview[]>([])
const detail = ref<Detail | null>(null)
const selected = ref<string>('')

const draft = ref('')
const note = ref('')
const busy = ref(false)
const error = ref('')
const toast = ref('')

const diffText = ref('')
const diffFrom = ref<number | null>(null)

const dirty = computed(
  () => detail.value !== null && draft.value.trim() !== (detail.value.active_content || '').trim(),
)
const activeVer = computed(() => detail.value?.versions.find((v) => v.is_active) ?? null)
const currentItem = computed(() => list.value.find((i) => i.key === selected.value) ?? null)

async function loadList() {
  const { data } = await api.get<Overview[]>('/api/v1/cms/ai/prompts')
  list.value = data
}

async function selectKey(key: string) {
  if (dirty.value && !window.confirm('当前修改尚未保存，切换后将丢失。继续？')) return
  selected.value = key
  diffText.value = ''
  error.value = ''
  const { data } = await api.get<Detail>(`/api/v1/cms/ai/prompts/${key}`)
  detail.value = data
  draft.value = data.active_content
  note.value = ''
}

async function save() {
  if (!canManage.value) {
    error.value = '没有修改提示词的权限（需 cms:ai:manage）'
    return
  }
  if (!detail.value || !draft.value.trim()) {
    error.value = '提示词不能为空'
    return
  }
  if (!window.confirm('保存后立即生效，之后所有 AI 调用都会用新提示词。确认？')) return
  busy.value = true
  error.value = ''
  try {
    await api.post(`/api/v1/cms/ai/prompts/${detail.value.key}`, {
      content: draft.value,
      note: note.value || null,
      activate: true,
    })
    toast.value = '已保存并启用'
    await loadList()
    await selectKey(detail.value.key)
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? '保存失败'
  } finally {
    busy.value = false
    setTimeout(() => (toast.value = ''), 2500)
  }
}

async function activate(version: number) {
  if (!canManage.value) {
    error.value = '没有修改提示词的权限（需 cms:ai:manage）'
    return
  }
  if (!detail.value) return
  if (!window.confirm(`切换到 v${version}？切换后立即生效。`)) return
  busy.value = true
  error.value = ''
  try {
    await api.post(`/api/v1/cms/ai/prompts/${detail.value.key}/${version}/activate`)
    toast.value = `已切到 v${version}`
    await loadList()
    await selectKey(detail.value.key)
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? '切换失败'
  } finally {
    busy.value = false
    setTimeout(() => (toast.value = ''), 2500)
  }
}

async function resetDefault() {
  if (!canManage.value) {
    error.value = '没有修改提示词的权限（需 cms:ai:manage）'
    return
  }
  if (!detail.value) return
  if (!window.confirm('恢复出厂默认？会存为一个新版本并启用，历史版本不丢，随时可以再切回来。')) return
  busy.value = true
  error.value = ''
  try {
    await api.post(`/api/v1/cms/ai/prompts/${detail.value.key}/reset`)
    toast.value = '已恢复出厂默认'
    await loadList()
    await selectKey(detail.value.key)
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? '恢复失败'
  } finally {
    busy.value = false
    setTimeout(() => (toast.value = ''), 2500)
  }
}

async function showDiff(from: number) {
  if (!detail.value || !activeVer.value) return
  diffFrom.value = from
  const { data } = await api.get(`/api/v1/cms/ai/prompts/${detail.value.key}/diff`, {
    params: { from, to: activeVer.value.version },
  })
  diffText.value = data.diff || '(两版内容相同)'
}

function resetDraft() {
  draft.value = detail.value?.active_content ?? ''
  note.value = ''
}

function fmtTime(s: string | null) {
  if (!s) return ''
  return new Date(s).toLocaleString('zh-CN', { hour12: false })
}

onMounted(async () => {
  try {
    await loadList()
    if (list.value.length) await selectKey(list.value[0].key)
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? '加载失败'
  }
})
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/cms/ai-settings" class="text-sm text-ink-500 hover:text-ink-900">
          ← AI 设置
        </router-link>
        <span class="font-semibold">提示词管理</span>
        <span class="text-xs text-ink-400">改措辞不用发版，可回滚</span>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-8">
      <p v-if="error" class="mb-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
        {{ error }}
      </p>
      <p v-if="toast" class="mb-4 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
        {{ toast }}
      </p>

      <div class="grid grid-cols-1 lg:grid-cols-[240px_1fr] gap-6">
        <!-- 左：提示词清单 -->
        <aside class="space-y-2">
          <button
            v-for="item in list"
            :key="item.key"
            class="w-full text-left px-3 py-2.5 rounded-lg border transition-colors"
            :class="
              selected === item.key
                ? 'bg-white border-ink-900 shadow-sm'
                : 'bg-white/60 border-ink-200 hover:border-ink-400'
            "
            @click="selectKey(item.key)"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="text-sm font-medium text-ink-900">{{ item.label }}</span>
              <span v-if="item.active_version" class="text-xs text-ink-400 font-mono">
                v{{ item.active_version }}
              </span>
            </div>
            <div class="mt-0.5 flex items-center gap-2">
              <span class="text-[11px] text-ink-400 font-mono">{{ item.key }}</span>
              <span
                v-if="item.differs_from_default"
                class="text-[11px] px-1.5 py-0.5 rounded bg-amber-50 text-amber-700"
              >
                已改动
              </span>
            </div>
          </button>
        </aside>

        <!-- 右：编辑与历史 -->
        <section v-if="detail" class="space-y-6">
          <div
            v-if="!canManage"
            class="text-xs rounded-lg border border-amber-200 bg-amber-50 text-amber-800 px-3 py-2"
          >
            你当前是只读权限（缺 <span class="font-mono">cms:ai:manage</span>），可以查看历史版本但不能修改或切换。需要调整请联系超级管理员。
          </div>
          <div class="card">
            <div class="flex flex-wrap items-center justify-between gap-3 mb-3">
              <div>
                <h2 class="text-base font-semibold text-ink-900">{{ detail.label }}</h2>
                <p class="mt-0.5 text-xs text-ink-400 font-mono">
                  {{ detail.key }} · 当前生效
                  {{ activeVer ? `v${activeVer.version}` : '（出厂默认）' }}
                </p>
              </div>
              <span
                v-if="dirty"
                class="text-xs px-2 py-1 rounded bg-amber-50 text-amber-700 border border-amber-200"
              >
                有未保存的修改
              </span>
            </div>

            <textarea
              v-model="draft"
              rows="14"
              spellcheck="false"
              :readonly="!canManage"
              class="w-full font-mono text-[13px] leading-relaxed rounded-lg border border-ink-200 px-3 py-2.5 focus:outline-none focus:border-ink-900 resize-y"
              :class="!canManage ? 'bg-ink-50 text-ink-500 cursor-not-allowed' : ''"
            ></textarea>

            <div class="mt-3 flex flex-wrap items-center gap-2">
              <input
                v-model="note"
                placeholder="本次改动说明（选填，便于以后回滚时辨认）"
                class="flex-1 min-w-[220px] text-sm rounded-lg border border-ink-200 px-3 py-2 focus:outline-none focus:border-ink-900"
              />
              <button
                class="px-3 py-2 text-sm rounded-lg border border-ink-200 text-ink-600 hover:border-ink-400 disabled:opacity-40"
                :disabled="!dirty"
                @click="resetDraft"
              >
                放弃修改
              </button>
              <button
                class="px-3 py-2 text-sm rounded-lg border border-ink-200 text-ink-600 hover:border-ink-400 disabled:opacity-40"
                :disabled="busy || !canManage"
                @click="resetDefault"
              >
                恢复出厂
              </button>
              <button
                class="px-4 py-2 text-sm rounded-lg bg-ink-900 text-white font-medium disabled:opacity-40"
                :disabled="!dirty || busy || !canManage"
                @click="save"
              >
                保存并启用
              </button>
            </div>
            <p class="mt-2 text-xs text-ink-400">
              提示词直接决定 AI 产出质量。保存后立即生效，若效果变差可在下方切回上一版。
            </p>
          </div>

          <!-- 版本历史 -->
          <div class="card">
            <h3 class="text-sm font-semibold text-ink-900 mb-3">版本历史</h3>
            <div v-if="!detail.versions.length" class="text-sm text-ink-400">
              还没有版本记录，当前用的是代码里的出厂默认。
            </div>
            <ul v-else class="divide-y divide-ink-100">
              <li
                v-for="v in detail.versions"
                :key="v.id"
                class="py-2.5 flex flex-wrap items-center gap-3"
              >
                <span class="font-mono text-sm text-ink-900 w-10">v{{ v.version }}</span>
                <span
                  v-if="v.is_active"
                  class="text-[11px] px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700"
                >
                  生效中
                </span>
                <span class="text-xs text-ink-500 flex-1 min-w-[160px] truncate">
                  {{ v.note || '（无说明）' }}
                </span>
                <span class="text-xs text-ink-400">{{ fmtTime(v.created_at) }}</span>
                <button
                  v-if="!v.is_active"
                  class="text-xs px-2 py-1 rounded border border-ink-200 text-ink-600 hover:border-ink-900 disabled:opacity-40 disabled:cursor-not-allowed"
                  :disabled="busy || !canManage"
                  @click="activate(v.version)"
                >
                  切到此版
                </button>
                <button
                  v-if="!v.is_active && activeVer"
                  class="text-xs px-2 py-1 rounded border border-ink-200 text-ink-600 hover:border-ink-900"
                  @click="showDiff(v.version)"
                >
                  对比
                </button>
              </li>
            </ul>
          </div>

          <!-- diff -->
          <div v-if="diffText" class="card">
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-sm font-semibold text-ink-900">
                v{{ diffFrom }} → v{{ activeVer?.version }} 的差异
              </h3>
              <button class="text-xs text-ink-500 hover:text-ink-900" @click="diffText = ''">
                关闭
              </button>
            </div>
            <pre class="text-[12px] leading-relaxed font-mono bg-ink-50 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap"><template v-for="(line, i) in diffText.split('\n')" :key="i"><span
                :class="
                  line.startsWith('+') && !line.startsWith('+++')
                    ? 'text-emerald-700 bg-emerald-50 block'
                    : line.startsWith('-') && !line.startsWith('---')
                      ? 'text-red-700 bg-red-50 block'
                      : 'text-ink-600 block'
                "
              >{{ line }}</span></template></pre>
          </div>
        </section>

        <div v-else class="text-sm text-ink-400">请选择左侧的提示词</div>
      </div>
    </main>
  </div>
</template>
