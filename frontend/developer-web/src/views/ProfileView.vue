<script setup lang="ts">
import { ref } from 'vue'

const user = ref(JSON.parse(localStorage.getItem('dev_user') || '{}'))
</script>

<template>
  <div class="card p-6 max-w-xl">
    <h2 class="text-lg font-semibold mb-4">个人设置</h2>
    <div class="space-y-3">
      <div>
        <label class="block text-sm font-medium mb-1">用户名</label>
        <input :value="user.username" disabled class="input bg-ink-50" />
      </div>
      <div>
        <label class="block text-sm font-medium mb-1">邮箱</label>
        <input :value="user.email" disabled class="input bg-ink-50" />
      </div>
      <div>
        <label class="block text-sm font-medium mb-1">昵称</label>
        <input :value="user.nickname" disabled class="input bg-ink-50" />
      </div>
    </div>
    <p class="text-xs text-ink-400 mt-4">如需修改个人信息，请联系管理员。</p>
  </div>
</template>
