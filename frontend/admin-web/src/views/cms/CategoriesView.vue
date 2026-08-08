<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, onMounted, computed } from 'vue'
import { api } from '@/lib/api'

interface Category {
  id: number; content_type_id: number; parent_id: number | null
  slug: string; name: string; icon: string | null; color: string | null
  sort: number; status: string; children?: Category[]
}

interface ContentType { id: number; key: string; name: string; icon: string | null }

const contentTypes = ref<ContentType[]>([])
const selectedCtKey = ref('')
const categories = ref<Category[]>([])
const flatCategories = ref<Category[]>([])
const loading = ref(true)
const saving = ref(false)
const showModal = ref(false)
const editing = ref<Category | null>(null)
const form = ref({ name: '', slug: '', parent_id: null as number | null, icon: '', color: '', sort: 0 })

const selectedCtName = computed(() => contentTypes.value.find(c => c.key === selectedCtKey.value)?.name || selectedCtKey.value)

async function loadContentTypes() {
  try {
    const { data } = await api.get('/api/v1/cms/content-types')
    contentTypes.value = data.items
    if (data.items.length && !selectedCtKey.value) {
      selectedCtKey.value = data.items[0].key
    }
  } catch { /* ignore */ }
}

async function loadCategories() {
  if (!selectedCtKey.value) return
  loading.value = true
  try {
    const { data } = await api.get(`/api/v1/cms/categories/tree?content_type_key=${selectedCtKey.value}`)
    categories.value = data
    const { data: flatData } = await api.get(`/api/v1/cms/categories?content_type_key=${selectedCtKey.value}`)
    flatCategories.value = flatData.items || []
  } catch { /* ignore */ }
  finally { loading.value = false }
}

function openCreate(parentId: number | null = null) {
  editing.value = null
  form.value = { name: '', slug: '', parent_id: parentId, icon: '', color: '', sort: 0 }
  showModal.value = true
}

function openEdit(cat: Category) {
  editing.value = cat
  form.value = {
    name: cat.name, slug: cat.slug, parent_id: cat.parent_id,
    icon: cat.icon || '', color: cat.color || '', sort: cat.sort,
  }
  showModal.value = true
}

async function save() {
  saving.value = true
  try {
    if (editing.value) {
      await api.patch(`/api/v1/cms/categories/${editing.value.id}`, {
        name: form.value.name, slug: form.value.slug,
        parent_id: form.value.parent_id, icon: form.value.icon || null,
        color: form.value.color || null, sort: form.value.sort,
      })
    } else {
      await api.post('/api/v1/cms/categories', {
        content_type_key: selectedCtKey.value,
        name: form.value.name, slug: form.value.slug,
        parent_id: form.value.parent_id, icon: form.value.icon || null,
        color: form.value.color || null, sort: form.value.sort,
      })
    }
    showModal.value = false
    await loadCategories()
  } catch (e: any) {
    alert(e?.response?.data?.detail || 't("caseEdit.saveFailed")')
  } finally { saving.value = false }
}

async function remove(cat: Category) {
  if (cat.children?.length) {
    alert(`该分类下有 ${cat.children.length} 个子分类，请先删除子分类`)
    return
  }
  if (!confirm(`确定删除分类「${cat.name}」？`)) return
  try {
    await api.delete(`/api/v1/cms/categories/${cat.id}`)
    await loadCategories()
  } catch (e: any) {
    alert(e?.response?.data?.detail || 't("categories.删除失败")')
  }
}

function onCtChange() {
  loadCategories()
}

onMounted(async () => {
  await loadContentTypes()
  await loadCategories()
})
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">{{ t('categories.分类管理_av9sai') }}</h1>
        <p class="text-ink-500">{{ t('categories.管理各内_b6gtl6') }}</p>
      </div>
      <div class="flex gap-2">
        <select v-model="selectedCtKey" class="input w-full sm:w-40" @change="onCtChange">
          <option v-for="ct in contentTypes" :key="ct.key" :value="ct.key">{{ ct.name }}</option>
        </select>
        <button class="btn-primary" @click="openCreate(null)">{{ t('categories.text_y2kogk') }}</button>
      </div>
    </div>

    <div v-if="loading" class="card text-ink-500">{{ t('usersList.加载中_b0k5km') }}</div>
    <div v-else-if="categories.length === 0" class="card text-center text-ink-400 py-12">
      {{ t('categories.暂无分类点击新建分类创建第一个') }}
    </div>
    <div v-else class="space-y-1">
      <template v-for="cat in categories" :key="cat.id">
        <!-- Level 1 -->
        <div class="card flex items-center gap-3 py-3">
          <span class="text-lg">{{ cat.icon || '📁' }}</span>
          <div class="flex-1 min-w-0">
            <span class="font-medium">{{ cat.name }}</span>
            <code class="text-xs text-ink-400 ml-2">{{ cat.slug }}</code>
            <span v-if="cat.color" class="inline-block w-3 h-3 rounded-full ml-2" :style="{ backgroundColor: cat.color }"></span>
          </div>
          <span class="text-xs text-ink-400">{{ cat.children?.length || 0 }} 子分类</span>
          <div class="flex gap-1">
            <button class="btn-ghost text-xs" @click="openCreate(cat.id)">{{ t('categories.text_11zpjk') }}</button>
            <button class="btn-ghost text-xs" @click="openEdit(cat)">{{ t('usersList.编辑_mekb') }}</button>
            <button class="btn-ghost text-xs text-red-600" @click="remove(cat)">{{ t('usersList.删除_eslg') }}</button>
          </div>
        </div>
        <!-- Level 2 -->
        <template v-for="child in (cat.children || [])" :key="child.id">
          <div class="card flex items-center gap-3 py-2 ml-8">
            <span>{{ child.icon || '📂' }}</span>
            <div class="flex-1 min-w-0">
              <span class="font-medium text-sm">{{ child.name }}</span>
              <code class="text-xs text-ink-400 ml-2">{{ child.slug }}</code>
              <span v-if="child.color" class="inline-block w-2 h-2 rounded-full ml-2" :style="{ backgroundColor: child.color }"></span>
            </div>
            <div class="flex gap-1">
              <button class="btn-ghost text-xs" @click="openCreate(child.id)">{{ t('categories.text_11zpjk') }}</button>
              <button class="btn-ghost text-xs" @click="openEdit(child)">{{ t('usersList.编辑_mekb') }}</button>
              <button class="btn-ghost text-xs text-red-600" @click="remove(child)">{{ t('usersList.删除_eslg') }}</button>
            </div>
          </div>
          <!-- Level 3 -->
          <template v-for="grandchild in (child.children || [])" :key="grandchild.id">
            <div class="card flex items-center gap-3 py-2 ml-16">
              <span class="text-sm">{{ grandchild.icon || '📄' }}</span>
              <div class="flex-1 min-w-0">
                <span class="text-sm">{{ grandchild.name }}</span>
                <code class="text-xs text-ink-400 ml-2">{{ grandchild.slug }}</code>
              </div>
              <div class="flex gap-1">
                <button class="btn-ghost text-xs" @click="openEdit(grandchild)">{{ t('usersList.编辑_mekb') }}</button>
                <button class="btn-ghost text-xs text-red-600" @click="remove(grandchild)">{{ t('usersList.删除_eslg') }}</button>
              </div>
            </div>
          </template>
        </template>
      </template>
    </div>

    <!-- Modal -->
    <div v-if="showModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showModal = false">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h2 class="text-lg font-semibold mb-4">{{ editing ? '编辑分类' : '新建分类' }}</h2>
        <div class="space-y-3">
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('tags.名称_eyrn') }}</label>
            <input v-model="form.name" class="input" :placeholder="t('categories.分类名称')" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">Slug</label>
            <input v-model="form.slug" class="input" placeholder="url-friendly-key" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('categories.父级分类') }}</label>
            <select v-model="form.parent_id" class="input">
              <option :value="null">{{ t('categories.顶级分类') }}</option>
              <option v-for="c in flatCategories" :key="c.id" :value="c.id" :disabled="editing?.id === c.id">
                {{ c.parent_id ? '  └ ' : '' }}{{ c.name }}
              </option>
            </select>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('fieldDefinitions.图标_fd8p') }}</label>
              <input v-model="form.icon" class="input" placeholder="📁" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('tags.颜色_qo9i') }}</label>
              <input v-model="form.color" type="color" class="input h-10 p-1" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('productEdit.排序_hge5') }}</label>
              <input v-model.number="form.sort" type="number" class="input" />
            </div>
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button class="btn-ghost" @click="showModal = false">{{ t('usersList.取消_ev02') }}</button>
          <button class="btn-primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
