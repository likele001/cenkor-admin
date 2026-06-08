<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'
import { fromProductListItem } from '@/lib/transform'

interface Product {
  id: number
  key: string
  name: string
  chineseName: string | null
  tagline: string
  line: string
  desc: string
  isFlagship: boolean
  status: string
  sort: number
}

const products = ref<Product[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/api/v1/cms/products', { params: { page_size: 100 } })
    products.value = (data.items as Record<string, unknown>[]).map(fromProductListItem)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败（后端未启动？）'
  } finally {
    loading.value = false
  }
}

async function del(p: Product) {
  if (!confirm(`确定删除「${p.name}」吗？`)) return
  try {
    await api.delete(`/api/v1/cms/products/${p.id}`)
    await load()
  } catch (e: any) {
    alert('删除失败：' + (e?.response?.data?.detail || e.message))
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div v-if="loading" class="card text-ink-500">加载中…</div>

      <div v-else-if="error" class="card">
        <div class="text-red-600 font-medium">⚠️ {{ error }}</div>
        <p class="mt-2 text-sm text-ink-500">
          请确认：<br>
          1. <code class="px-1.5 py-0.5 rounded bg-ink-100">docker compose up -d</code> 已运行<br>
          2. <code class="px-1.5 py-0.5 rounded bg-ink-100">alembic upgrade head</code> 已执行<br>
          3. <code class="px-1.5 py-0.5 rounded bg-ink-100">python -m cenkor_admin.scripts.seed</code> 已执行
        </p>
      </div>

      <div v-else>
        <div class="flex items-center justify-between mb-6">
          <h1 class="text-2xl font-semibold tracking-tight">产品列表（{{ products.length }}）</h1>
          <router-link to="/cms/products/new" class="btn-primary">+ 新建产品</router-link>
        </div>
        <div class="card overflow-hidden p-0">
          <table class="w-full text-sm">
            <thead class="bg-ink-50 border-b border-ink-200">
              <tr class="text-left text-ink-500">
                <th class="px-4 py-3 font-medium">名称</th>
                <th class="px-4 py-3 font-medium">业务线</th>
                <th class="px-4 py-3 font-medium">标签</th>
                <th class="px-4 py-3 font-medium">状态</th>
                <th class="px-4 py-3 font-medium">旗舰</th>
                <th class="px-4 py-3 font-medium text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="products.length === 0">
                <td colspan="6" class="px-4 py-12 text-center text-ink-400">暂无产品</td>
              </tr>
              <tr v-for="p in products" :key="p.id" class="border-b border-ink-100 last:border-0 hover:bg-ink-50">
                <td class="px-4 py-3 font-medium">
                  {{ p.name }}
                  <span v-if="p.chineseName" class="text-ink-400 ml-1">{{ p.chineseName }}</span>
                </td>
                <td class="px-4 py-3 text-ink-600">{{ p.line }}</td>
                <td class="px-4 py-3 text-ink-600">{{ p.tagline }}</td>
                <td class="px-4 py-3">
                  <span class="text-xs px-2 py-0.5 rounded-full"
                    :class="p.status === 'published' ? 'bg-emerald-100 text-emerald-700' : 'bg-ink-100 text-ink-600'">
                    {{ p.status === 'published' ? '已发布' : p.status }}
                  </span>
                </td>
                <td class="px-4 py-3">
                  <span v-if="p.isFlagship" class="text-xs px-2 py-0.5 rounded bg-ink-900 text-white">旗舰</span>
                </td>
                <td class="px-4 py-3 text-right space-x-2">
                  <router-link :to="`/cms/products/${p.id}`" class="text-sm text-ink-600 hover:text-ink-900">编辑</router-link>
                  <button @click="del(p)" class="text-sm text-red-600 hover:underline">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
  </div>
</template>
