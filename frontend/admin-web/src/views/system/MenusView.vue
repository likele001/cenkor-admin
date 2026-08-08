<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'

interface MenuNode {
  id: number
  key: string
  parent_id: number | null
  title: string
  icon: string | null
  path: string | null
  component: string | null
  sort: number
  status: string
  children?: MenuNode[]
}

const menus = ref<MenuNode[]>([])
const flatMenus = ref<MenuNode[]>([])  // 全部平铺（用于父菜单选择）
const loading = ref(true)
const error = ref('')
const showDialog = ref(false)
const isNew = ref(true)
const isChild = ref(false)  // 当前是新增子菜单
const saving = ref(false)
const form = ref({
  id: 0,
  key: '',
  parent_id: null as number | null,
  title: '',
  icon: '',
  path: '',
  component: '',
  sort: 0,
  status: 'active',
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/api/v1/rbac/menus')
    menus.value = data
    flatMenus.value = flatten(data)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 't("caseEdit.loadFailed")'
  } finally {
    loading.value = false
  }
}

function flatten(tree: MenuNode[]): MenuNode[] {
  const out: MenuNode[] = []
  function walk(ns: MenuNode[]) {
    for (const n of ns) {
      out.push(n)
      if (n.children) walk(n.children)
    }
  }
  walk(tree)
  return out
}

function openNew(parentId: number | null = null) {
  isNew.value = true
  isChild.value = parentId !== null
  form.value = {
    id: 0,
    key: '',
    parent_id: parentId,
    title: '',
    icon: '',
    path: '',
    component: '',
    sort: 0,
    status: 'active',
  }
  showDialog.value = true
}

function openEdit(m: MenuNode) {
  isNew.value = false
  isChild.value = !!m.parent_id
  form.value = { ...m, parent_id: m.parent_id, icon: m.icon || '', path: m.path || '', component: m.component || '' }
  showDialog.value = true
}

async function save() {
  saving.value = true
  error.value = ''
  try {
    const body = { ...form.value, parent_id: form.value.parent_id || null }
    if (isNew.value) {
      await api.post('/api/v1/rbac/menus', body)
    } else {
      await api.patch(`/api/v1/rbac/menus/${form.value.id}`, body)
    }
    showDialog.value = false
    await load()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 't("caseEdit.saveFailed")'
  } finally {
    saving.value = false
  }
}

async function del(m: MenuNode) {
  if (!confirm(`确定删除菜单「${m.title}」吗？子菜单也会被删除。`)) return
  try {
    await api.delete(`/api/v1/rbac/menus/${m.id}`)
    await load()
  } catch (e: any) {
    alert('t("usersList.删除失败_1kc17l")' + (e?.response?.data?.detail || e.message))
  }
}

function editChild(c: MenuNode, _parentId: number) {
  openEdit(c)
}

async function moveUp(m: MenuNode) {
  // 简单实现：减 1
  try {
    await api.post('/api/v1/rbac/menus/reorder', {
      items: [{ id: m.id, sort: m.sort - 1 }],
    })
    await load()
  } catch (e: any) {
    alert('t("usersList.失败_drpmu")' + (e?.response?.data?.detail || e.message))
  }
}

async function moveDown(m: MenuNode) {
  try {
    await api.post('/api/v1/rbac/menus/reorder', {
      items: [{ id: m.id, sort: m.sort + 1 }],
    })
    await load()
  } catch (e: any) {
    alert('t("usersList.失败_drpmu")' + (e?.response?.data?.detail || e.message))
  }
}

onMounted(load)
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/" class="text-sm text-ink-500 hover:text-ink-900">← Dashboard</router-link>
        <span class="font-semibold">{{ t('menus.菜单管理_gzj3um') }}</span>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-10">
      <div v-if="loading" class="card text-ink-500">{{ t('usersList.加载中_b0k5km') }}</div>
      <div v-else-if="error" class="card text-red-600">⚠️ {{ error }}</div>
      <div v-else>
        <div class="flex items-center justify-between mb-6">
          <h1 class="text-2xl font-semibold tracking-tight">菜单树（{{ flatMenus.length }} 个）</h1>
          <button @click="openNew(null)" class="btn-primary">{{ t('menus.text_6dvuyx') }}</button>
        </div>

        <div class="card overflow-hidden p-0">
          <div class="overflow-x-auto"><table class="w-full text-sm">
            <thead class="bg-ink-50 border-b border-ink-200">
              <tr class="text-left text-ink-500">
                <th class="px-4 py-3 font-medium">{{ t('menus.菜单_mvw9') }}</th>
                <th class="px-4 py-3 font-medium">Key</th>
                <th class="px-4 py-3 font-medium">{{ t('menus.路径_onzp') }}</th>
                <th class="px-4 py-3 font-medium">{{ t('usersList.状态_k1e3') }}</th>
                <th class="px-4 py-3 font-medium">{{ t('productEdit.排序_hge5') }}</th>
                <th class="px-4 py-3 font-medium text-right">{{ t('usersList.操作_hkxb') }}</th>
              </tr>
            </thead>
            <tbody>
              <!-- 顶级菜单 -->
              <template v-for="m in menus" :key="m.id">
                <tr class="border-b border-ink-100 hover:bg-ink-50">
                  <td class="px-4 py-3 font-medium">
                    <span class="inline-flex items-center gap-2">
                      <span class="w-6 h-6 rounded bg-ink-100 flex items-center justify-center text-xs">{{ m.icon?.[0] || '·' }}</span>
                      {{ m.title }}
                    </span>
                  </td>
                  <td class="px-4 py-3 font-mono text-xs text-ink-500">{{ m.key }}</td>
                  <td class="px-4 py-3 font-mono text-xs">{{ m.path || '—' }}</td>
                  <td class="px-4 py-3">
                    <span class="text-xs px-2 py-0.5 rounded-full"
                      :class="m.status === 'active' ? 'bg-emerald-100 text-emerald-700' : 'bg-ink-100 text-ink-500'">
                      {{ m.status === 'active' ? '激活' : m.status }}
                    </span>
                  </td>
                  <td class="px-4 py-3 text-ink-500">{{ m.sort }}</td>
                  <td class="px-4 py-3 text-right space-x-1 whitespace-nowrap">
                    <button @click="moveUp(m)" class="text-xs text-ink-500 hover:text-ink-900">↑</button>
                    <button @click="moveDown(m)" class="text-xs text-ink-500 hover:text-ink-900">↓</button>
                    <button @click="openNew(m.id)" class="text-xs text-ink-600 hover:text-ink-900">{{ t('menus.text_j2d') }}</button>
                    <button @click="openEdit(m)" class="text-xs text-ink-600 hover:text-ink-900">{{ t('usersList.编辑_mekb') }}</button>
                    <button @click="del(m)" class="text-xs text-red-600 hover:underline">{{ t('usersList.删除_eslg') }}</button>
                  </td>
                </tr>
                <!-- 子菜单 -->
                <tr v-for="c in m.children" :key="c.id" class="border-b border-ink-100 hover:bg-ink-50 bg-ink-50/30">
                  <td class="px-4 py-3 text-ink-700 pl-12">
                    <span class="inline-flex items-center gap-2">
                      <span class="text-ink-300">└</span>
                      {{ c.title }}
                    </span>
                  </td>
                  <td class="px-4 py-3 font-mono text-xs text-ink-500">{{ c.key }}</td>
                  <td class="px-4 py-3 font-mono text-xs">{{ c.path || '—' }}</td>
                  <td class="px-4 py-3">
                    <span class="text-xs px-2 py-0.5 rounded-full bg-ink-100 text-ink-500">{{ t('menus.子') }}</span>
                  </td>
                  <td class="px-4 py-3 text-ink-500">{{ c.sort }}</td>
                  <td class="px-4 py-3 text-right space-x-1 whitespace-nowrap">
                    <button @click="editChild(c, m.id)" class="text-xs text-ink-600 hover:text-ink-900">{{ t('usersList.编辑_mekb') }}</button>
                    <button @click="del(c)" class="text-xs text-red-600 hover:underline">{{ t('usersList.删除_eslg') }}</button>
                  </td>
                </tr>
              </template>
            </tbody>
          </table></div>
        </div>
      </div>
    </main>

    <!-- 编辑/新建对话框 -->
    <div v-if="showDialog" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/40" @click.self="showDialog = false">
      <div class="bg-white rounded-2xl w-full max-w-md p-6">
        <h2 class="text-lg font-semibold mb-4">
          {{ isNew ? (isChild ? '新建子菜单' : '新建顶级菜单') : '编辑菜单' }}
        </h2>
        <form @submit.prevent="save" class="space-y-4">
          <div>
            <label class="block text-sm font-medium mb-1.5">Key *</label>
            <input v-model="form.key" required :disabled="!isNew" class="input" placeholder="cms" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1.5">{{ t('newsEdit.标题_dqp6wr') }}</label>
            <input v-model="form.title" required class="input" :placeholder="t('menus.内容管理')" />
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block text-sm font-medium mb-1.5">{{ t('fieldDefinitions.图标_fd8p') }}</label>
              <input v-model="form.icon" class="input" placeholder="newspaper" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1.5">{{ t('productEdit.排序_hge5') }}</label>
              <input v-model.number="form.sort" type="number" class="input" />
            </div>
          </div>
          <div>
            <label class="block text-sm font-medium mb-1.5">{{ t('menus.路径_onzp') }}</label>
            <input v-model="form.path" class="input" placeholder="/cms/products" />
          </div>
          <div v-if="!isNew">
            <label class="block text-sm font-medium mb-1.5">{{ t('menus.父菜单') }}</label>
            <select v-model="form.parent_id" class="input">
              <option :value="null">{{ t('menus.顶级') }}</option>
              <option v-for="m in flatMenus.filter(x => x.id !== form.id && !x.parent_id)" :key="m.id" :value="m.id">
                {{ m.title }}
              </option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium mb-1.5">{{ t('usersList.状态_k1e3') }}</label>
            <select v-model="form.status" class="input">
              <option value="active">{{ t('menus.激活') }}</option>
              <option value="inactive">{{ t('usersList.禁用_lb5z') }}</option>
            </select>
          </div>
          <div v-if="error" class="text-sm text-red-600">{{ error }}</div>
          <div class="flex gap-3 pt-2">
            <button type="submit" :disabled="saving" class="btn-primary flex-1">
              {{ saving ? '保存中…' : isNew ? '创建' : '保存' }}
            </button>
            <button type="button" @click="showDialog = false" class="btn-ghost">{{ t('usersList.取消_ev02') }}</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
