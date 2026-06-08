<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const me = computed(() => auth.user)
</script>

<template>
  <div>
    <h1 class="text-3xl font-semibold tracking-tight">Dashboard</h1>
    <p class="mt-2 text-ink-500">欢迎回来。这是 Cenkor Admin Platform 的起点。</p>

    <div class="mt-8 grid md:grid-cols-3 gap-4">
      <div class="card">
        <div class="text-3xl font-semibold">7+</div>
        <div class="mt-1 text-sm text-ink-500">自研产品</div>
      </div>
      <div class="card">
        <div class="text-3xl font-semibold">1</div>
        <div class="mt-1 text-sm text-ink-500">已安装应用（CMS）</div>
      </div>
      <div class="card">
        <div class="text-3xl font-semibold">{{ me?.permissions?.length ?? 0 }}</div>
        <div class="mt-1 text-sm text-ink-500">当前权限数</div>
      </div>
    </div>

    <div v-if="me" class="mt-8 card">
      <h2 class="font-semibold mb-3">当前用户</h2>
      <dl class="grid sm:grid-cols-2 gap-3 text-sm">
        <div><dt class="text-ink-500">用户名</dt><dd class="font-medium">{{ me.username }}</dd></div>
        <div><dt class="text-ink-500">邮箱</dt><dd class="font-medium">{{ me.email }}</dd></div>
        <div><dt class="text-ink-500">昵称</dt><dd class="font-medium">{{ me.nickname }}</dd></div>
        <div><dt class="text-ink-500">超级管理员</dt><dd class="font-medium">{{ me.is_superuser ? '是' : '否' }}</dd></div>
      </dl>
    </div>
  </div>
</template>
