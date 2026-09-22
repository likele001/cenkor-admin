<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api } from '@/lib/api'
import SiteHeader from '@/components/SiteHeader.vue'

interface AppVersion {
  version: string
  status: string
  released_at?: string | null
  download_count: number
  is_current: boolean
}

interface AppDetail {
  id: number
  key: string
  name: string
  version: string
  description: string
  summary: string
  highlights: string[]
  tags: string[]
  screenshots: string[]
  icon: string
  category: string
  category_label: string
  download_count: number
  updated_at?: string | null
  released_at?: string | null
  developer: { name: string; website?: string | null; description?: string | null }
  installed: boolean
  installed_version?: string | null
  has_update: boolean
  has_frontend: boolean
  permissions: string[]
  permission_count: number
  menu_count: number
  min_platform_version?: string | null
  dependencies: string[]
  versions: AppVersion[]
  install_hint: string
}

const { t } = useI18n()
const route = useRoute()

const detail = ref<AppDetail | null>(null)
const loading = ref(true)
const error = ref('')
const showPermissions = ref(false)

const ADMIN_CONSOLE = 'https://admin.cenkor.cn'

const PERM_GROUP_LABELS: Record<string, string> = {
  customer: '客户', lead: '线索', followup: '跟进', opportunity: '商机',
  quotation: '报价', contract: '合同', payment: '回款', ticket: '工单',
  dashboard: '仪表盘', admin: '管理', user: '用户', role: '角色',
  content: '内容', storage: '存储', system: '系统',
}

const PERM_ACTION_LABELS: Record<string, string> = {
  read: '查看', write: '编辑', create: '新建', delete: '删除', export: '导出',
  import: '导入', approve: '审批', assign: '指派', reply: '回复', resolve: '关闭',
  claim: '认领', release: '释放', recycle: '回收', stage: '阶段推进',
  won: '标记赢单', lost: '标记输单', push_erp: '推送 ERP', admin: '管理',
  manage: '管理', audit: '审核', publish: '发布',
}

const permissionGroups = computed(() => {
  const map = new Map<string, string[]>()
  for (const p of detail.value?.permissions || []) {
    const parts = p.split(':')
    const group = parts.length >= 3 ? parts[1] : (parts.length === 2 ? parts[0] : 'other')
    const action = parts.length >= 2 ? parts[parts.length - 1] : p
    const list = map.get(group) || []
    list.push(action)
    map.set(group, list)
  }
  return Array.from(map.entries()).map(([key, actions]) => ({
    key,
    label: PERM_GROUP_LABELS[key] || key,
    actions: actions.map(a => PERM_ACTION_LABELS[a] || a),
  }))
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get(`/api/v1/store/apps/${route.params.key}`)
    detail.value = data
  } catch (e: any) {
    error.value = e?.response?.status === 404
      ? t('appDetail.notFound')
      : (e?.response?.data?.detail || t('appDetail.loadError'))
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => route.params.key, load)

function fmtDate(iso?: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString()
}
</script>

<template>
  <div class="min-h-screen bg-[#f8f9fb] font-['Plus_Jakarta_Sans',system-ui,sans-serif]">
    <SiteHeader />

    <section class="container-wide py-8">
      <!-- 面包屑 -->
      <nav class="flex items-center gap-2 text-xs text-[#8b8e96]">
        <RouterLink to="/" class="hover:text-[#4f46e5] transition-colors">{{ t('appDetail.home') }}</RouterLink>
        <span>/</span>
        <RouterLink to="/apps" class="hover:text-[#4f46e5] transition-colors">{{ t('appCenter.title') }}</RouterLink>
        <span>/</span>
        <span class="text-[#374151] truncate">{{ detail?.name || route.params.key }}</span>
      </nav>

      <!-- 加载中 -->
      <div v-if="loading" class="mt-6 bg-white rounded-xl border border-[#e5e7eb] p-6 animate-pulse">
        <div class="flex items-start gap-4">
          <div class="w-14 h-14 rounded-xl bg-[#f3f4f6]"></div>
          <div class="flex-1 space-y-3 pt-1">
            <div class="h-4 w-1/3 rounded bg-[#f3f4f6]"></div>
            <div class="h-3 w-1/2 rounded bg-[#f3f4f6]"></div>
          </div>
        </div>
      </div>

      <!-- 错误 / 404 -->
      <div v-else-if="error" class="mt-6 rounded-xl border border-red-200 bg-red-50 px-5 py-4">
        <p class="text-sm text-red-700">{{ error }}</p>
        <RouterLink
          to="/apps"
          class="inline-block mt-3 px-3 py-1.5 text-xs rounded-lg border border-red-300 text-red-700 hover:bg-red-100 transition-colors"
        >{{ t('appDetail.backToList') }}</RouterLink>
      </div>

      <template v-else-if="detail">
        <!-- 头部 -->
        <div class="mt-6 bg-white rounded-xl border border-[#e5e7eb] p-6">
          <div class="flex flex-col lg:flex-row lg:items-start gap-5">
            <span class="w-16 h-16 shrink-0 rounded-xl bg-[#f8f9fb] border border-[#eef0f4] flex items-center justify-center text-3xl">
              {{ detail.icon }}
            </span>

            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <h1 class="text-2xl font-semibold tracking-tight text-[#111827]">{{ detail.name }}</h1>
                <code class="text-xs text-[#9ca3af]">v{{ detail.version }}</code>
                <span
                  v-if="detail.installed && detail.has_update"
                  class="px-2 py-0.5 text-[10px] rounded-full bg-[#fef3c7] text-[#b45309]"
                >{{ t('appDetail.upgradableFrom', { v: detail.installed_version }) }}</span>
                <span
                  v-else-if="detail.installed"
                  class="px-2 py-0.5 text-[10px] rounded-full bg-[#ecfdf5] text-[#047857]"
                >{{ t('appCenter.installed') }}</span>
              </div>

              <p class="mt-2 text-sm text-[#6b6e76] leading-relaxed max-w-3xl">
                {{ detail.summary || detail.description }}
              </p>

              <div class="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-[#8b8e96]">
                <span class="px-2 py-0.5 rounded-full bg-[#eef2ff] text-[#4f46e5]">{{ detail.category_label }}</span>
                <span>{{ t('appDetail.author') }}：{{ detail.developer.name }}</span>
                <span>{{ t('appDetail.downloads') }}：{{ detail.download_count }}</span>
                <span>{{ t('appDetail.updated') }}：{{ fmtDate(detail.updated_at) }}</span>
              </div>

              <div v-if="detail.tags.length" class="mt-3 flex flex-wrap gap-1.5">
                <span
                  v-for="tg in detail.tags"
                  :key="tg"
                  class="px-2 py-0.5 text-[10px] rounded bg-[#f8f9fb] border border-[#eef0f4] text-[#6b6e76]"
                >{{ tg }}</span>
              </div>
            </div>

            <div class="shrink-0 flex flex-col items-stretch gap-2 lg:w-44">
              <a
                v-if="detail.installed"
                :href="ADMIN_CONSOLE"
                target="_blank"
                rel="noopener"
                class="px-4 py-2.5 text-sm text-center rounded-lg bg-[#111827] text-white hover:bg-[#374151] transition-colors"
              >{{ t('appDetail.openConsole') }}</a>
              <a
                v-else
                :href="ADMIN_CONSOLE"
                target="_blank"
                rel="noopener"
                class="px-4 py-2.5 text-sm text-center rounded-lg bg-[#4f46e5] text-white hover:bg-[#4338ca] transition-colors"
              >{{ t('appDetail.installApp') }}</a>
              <p class="text-[11px] text-[#9ca3af] leading-relaxed">{{ detail.install_hint }}</p>
            </div>
          </div>
        </div>

        <div class="mt-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
          <!-- 左：主体 -->
          <div class="lg:col-span-2 space-y-6">
            <!-- 功能亮点 -->
            <div v-if="detail.highlights.length" class="bg-white rounded-xl border border-[#e5e7eb] p-6">
              <h2 class="font-semibold text-[#111827]">{{ t('appDetail.highlights') }}</h2>
              <ul class="mt-4 space-y-2.5">
                <li v-for="(h, i) in detail.highlights" :key="i" class="flex gap-3 text-sm text-[#374151] leading-relaxed">
                  <span class="mt-1.5 w-1.5 h-1.5 rounded-full bg-[#4f46e5] shrink-0"></span>
                  <span>{{ h }}</span>
                </li>
              </ul>
            </div>

            <!-- 应用介绍 -->
            <div v-if="detail.description" class="bg-white rounded-xl border border-[#e5e7eb] p-6">
              <h2 class="font-semibold text-[#111827]">{{ t('appDetail.overview') }}</h2>
              <p class="mt-3 text-sm text-[#6b6e76] leading-relaxed whitespace-pre-line">{{ detail.description }}</p>
            </div>

            <!-- 版本历史 -->
            <div class="bg-white rounded-xl border border-[#e5e7eb] p-6">
              <h2 class="font-semibold text-[#111827]">{{ t('appDetail.versions') }}</h2>
              <div class="mt-4 overflow-x-auto">
                <table class="w-full text-sm">
                  <thead>
                    <tr class="text-left text-xs text-[#8b8e96] border-b border-[#f3f4f6]">
                      <th class="pb-2 font-normal">{{ t('appDetail.colVersion') }}</th>
                      <th class="pb-2 font-normal">{{ t('appDetail.colStatus') }}</th>
                      <th class="pb-2 font-normal">{{ t('appDetail.colDate') }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="v in detail.versions" :key="v.version" class="border-b border-[#f9fafb] last:border-0">
                      <td class="py-2.5">
                        <span class="font-medium text-[#111827]">v{{ v.version }}</span>
                        <span
                          v-if="v.is_current"
                          class="ml-2 px-1.5 py-0.5 text-[10px] rounded bg-[#eef2ff] text-[#4f46e5]"
                        >{{ t('appDetail.current') }}</span>
                      </td>
                      <td class="py-2.5 text-[#6b6e76] text-xs">
                        {{ v.status === 'installed' ? t('appDetail.statusInstalled') : t('appDetail.statusApproved') }}
                      </td>
                      <td class="py-2.5 text-[#8b8e96] text-xs">{{ fmtDate(v.released_at) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- 权限清单 -->
            <div v-if="detail.permission_count" class="bg-white rounded-xl border border-[#e5e7eb] p-6">
              <div class="flex items-center justify-between gap-4">
                <div>
                  <h2 class="font-semibold text-[#111827]">{{ t('appDetail.permissions') }}</h2>
                  <p class="mt-1 text-xs text-[#8b8e96]">
                    {{ t('appDetail.permissionsDesc', { n: detail.permission_count }) }}
                  </p>
                </div>
                <button
                  class="px-3 py-1.5 text-xs rounded-lg border border-[#e5e7eb] text-[#374151] hover:border-[#9ca3af] transition-colors shrink-0"
                  @click="showPermissions = !showPermissions"
                >{{ showPermissions ? t('appDetail.collapse') : t('appDetail.expand') }}</button>
              </div>

              <div v-if="showPermissions" class="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div v-for="g in permissionGroups" :key="g.key" class="rounded-lg border border-[#f3f4f6] bg-[#fbfcfd] p-3">
                  <div class="text-xs font-medium text-[#374151]">{{ g.label }}</div>
                  <div class="mt-2 flex flex-wrap gap-1.5">
                    <span
                      v-for="a in g.actions"
                      :key="a"
                      class="px-1.5 py-0.5 text-[10px] rounded bg-white border border-[#eef0f4] text-[#6b6e76]"
                    >{{ a }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 右：侧栏 -->
          <div class="space-y-6">
            <div class="bg-white rounded-xl border border-[#e5e7eb] p-5">
              <h2 class="font-semibold text-[#111827] text-sm">{{ t('appDetail.info') }}</h2>
              <dl class="mt-3 space-y-2.5 text-xs">
                <div class="flex justify-between gap-3">
                  <dt class="text-[#8b8e96]">{{ t('appDetail.labelCategory') }}</dt>
                  <dd class="text-[#374151] text-right">{{ detail.category_label }}</dd>
                </div>
                <div class="flex justify-between gap-3">
                  <dt class="text-[#8b8e96]">{{ t('appDetail.labelVersion') }}</dt>
                  <dd class="text-[#374151] text-right">v{{ detail.version }}</dd>
                </div>
                <div class="flex justify-between gap-3">
                  <dt class="text-[#8b8e96]">{{ t('appDetail.labelReleased') }}</dt>
                  <dd class="text-[#374151] text-right">{{ fmtDate(detail.released_at) }}</dd>
                </div>
                <div v-if="detail.menu_count > 0" class="flex justify-between gap-3">
                  <dt class="text-[#8b8e96]">{{ t('appDetail.labelMenus') }}</dt>
                  <dd class="text-[#374151] text-right">{{ detail.menu_count }}</dd>
                </div>
                <div class="flex justify-between gap-3">
                  <dt class="text-[#8b8e96]">{{ t('appDetail.labelFrontend') }}</dt>
                  <dd class="text-[#374151] text-right">
                    {{ detail.has_frontend ? t('appDetail.yes') : t('appDetail.no') }}
                  </dd>
                </div>
                <div v-if="detail.min_platform_version" class="flex justify-between gap-3">
                  <dt class="text-[#8b8e96]">{{ t('appDetail.labelMinPlatform') }}</dt>
                  <dd class="text-[#374151] text-right">v{{ detail.min_platform_version }}</dd>
                </div>
                <div v-if="detail.dependencies.length" class="flex justify-between gap-3">
                  <dt class="text-[#8b8e96]">{{ t('appDetail.labelDeps') }}</dt>
                  <dd class="text-[#374151] text-right">{{ detail.dependencies.join('、') }}</dd>
                </div>
              </dl>
            </div>

            <div class="bg-white rounded-xl border border-[#e5e7eb] p-5">
              <h2 class="font-semibold text-[#111827] text-sm">{{ t('appDetail.developer') }}</h2>
              <div class="mt-3 flex items-start gap-3">
                <span class="w-9 h-9 shrink-0 rounded-lg bg-[#f8f9fb] border border-[#eef0f4] flex items-center justify-center text-sm">
                  🏢
                </span>
                <div class="min-w-0">
                  <div class="text-sm font-medium text-[#111827]">{{ detail.developer.name }}</div>
                  <p v-if="detail.developer.description" class="mt-1 text-xs text-[#6b6e76] leading-relaxed">
                    {{ detail.developer.description }}
                  </p>
                  <a
                    v-if="detail.developer.website"
                    :href="detail.developer.website"
                    target="_blank"
                    rel="noopener"
                    class="inline-block mt-1.5 text-xs text-[#4f46e5] hover:underline"
                  >{{ detail.developer.website }}</a>
                </div>
              </div>
            </div>

            <div class="rounded-xl border border-[#e5e7eb] bg-white p-5">
              <h2 class="font-semibold text-[#111827] text-sm">{{ t('appDetail.more') }}</h2>
              <RouterLink
                to="/apps"
                class="mt-3 inline-flex items-center gap-1 text-xs text-[#4f46e5] hover:underline"
              >{{ t('appDetail.backToList') }} →</RouterLink>
            </div>
          </div>
        </div>
      </template>
    </section>
  </div>
</template>
