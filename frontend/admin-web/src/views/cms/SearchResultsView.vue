<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/lib/api'

const route = useRoute()
const q = ref(String(route.query.q || ''))
const items = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const ctFilter = ref('')

async function search() {
  loading.value = true
  try {
    const params: any = { q: q.value, page_size: 50 }
    if (ctFilter.value) params.content_type_key = ctFilter.value
    const { data } = await api.get('/api/v1/cms/search', { params })
    items.value = data.items || []
    total.value = data.total || 0
  } catch { items.value = [] } finally { loading.value = false }
}
function statusLabel(s: string) {
  return ({ draft: t("searchResults.draft"), published: t("searchResults.published"), archived: t("searchResults.归档_gsb5"), pending_review: t("searchResults.待审核_eftvg"), approved: t("searchResults.已通过_ego67") } as Record<string, string>)[s] || s
}
watch(ctFilter, search)
watch(() => route.query.q, v => { q.value = String(v || ''); search() })
onMounted(search)
</script>

<template>
  <div>
    <div class="flex items-center gap-3 mb-6">
      <h1 class="text-2xl font-semibold tracking-tight">{{ t("searchResults.text_g5wlxm") }}</h1>
      <input v-model="q" class="input flex-1 max-w-md" :placeholder="t('searchResults.关键词_zi5ft0')" @keyup.enter="search" />
      <select v-model="ctFilter" class="input w-36">
        <option value="">{{ t("entryList.全部类型_avglbk") }}</option>
        <option value="article">{{ t("searchResults.文章_hxyx") }}</option>
        <option value="news">{{ t("searchResults.news") }}</option>
        <option value="product">{{ t("searchResults.产品_dud6") }}</option>
        <option value="case">{{ t("searchResults.cases") }}</option>
      </select>
      <button class="btn-primary" @click="search">{{ t("searchResults.search") }}</button>
    </div>

    <div class="card overflow-hidden">
      <div v-if="loading" class="text-ink-500 p-6">{{ t("searchResults.搜索中_d59ehr") }}</div>
      <template v-else>
        <div class="text-sm text-ink-400 px-3 pt-3">{{ $t('searchResults.共_g35') }} {{ total }} {{ $t('searchResults.条结果_fr96y') }}</div>
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-ink-400 border-b">
              <th class="p-3">{{ t("searchResults.title") }}</th><th class="p-3">Slug</th><th class="p-3">{{ t("searchResults.status") }}</th><th class="p-3">{{ t("entryList.更新时间_devbay") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="it in items" :key="it.id" class="border-b last:border-0">
              <td class="p-3">
                <router-link :to="`/cms/entries/${it.id}?ct=${it.content_type_id}`" class="text-blue-600 hover:underline">{{ it.title }}</router-link>
              </td>
              <td class="p-3 text-xs text-ink-400">{{ it.slug || '-' }}</td>
              <td class="p-3"><span class="text-xs px-1.5 py-0.5 bg-ink-50 rounded">{{ statusLabel(it.status) }}</span></td>
              <td class="p-3 text-xs text-ink-400">{{ it.updated_at ? new Date(it.updated_at).toLocaleString() : '' }}</td>
            </tr>
            <tr v-if="!items.length"><td colspan="4" class="p-6 text-center text-ink-400">{{ q ? $t('searchResults.无匹配结_1ia23p') : $t('searchResults.输入关键_19eznl') }}</td></tr>
          </tbody>
        </table>
      </template>
    </div>
  </div>
</template>
