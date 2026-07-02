<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import LocaleSwitcher from '@/components/LocaleSwitcher.vue'
import { useI18n } from 'vue-i18n'

const auth = useAuthStore()
const route = useRoute()
const { t } = useI18n()
const mobileOpen = ref(false)
</script>

<template>
  <header class="fixed top-0 inset-x-0 z-50 bg-white/75 backdrop-blur-xl border-b border-[#e5e7eb] font-['Plus_Jakarta_Sans',system-ui,sans-serif]">
    <div class="container-wide flex items-center justify-between h-14">
      <RouterLink to="/" class="flex items-center gap-2 group">
        <span class="text-base font-semibold tracking-tight">辰科 <span class="text-[#8b8e96] font-normal">Cenkor</span></span>
      </RouterLink>
      <nav class="hidden md:flex items-center gap-8">
        <RouterLink to="/" class="nav-link">首页</RouterLink>
        <RouterLink to="/products" class="nav-link">产品中心</RouterLink>
        <RouterLink to="/cases" class="nav-link">客户案例</RouterLink>
        <LocaleSwitcher />
        <template v-if="!auth.isAuthed">
          <RouterLink to="/login" class="nav-link">{{ t('nav.login') }}</RouterLink>
        </template>
        <template v-else>
          <span class="text-sm text-[#6b6e76]">{{ auth.user?.nickname || auth.user?.username }}</span>
          <RouterLink to="/profile" class="nav-link">{{ t('nav.profile') }}</RouterLink>
        </template>
      </nav>
      <button id="mobile-menu-btn" class="md:hidden p-2" aria-label="菜单" @click="mobileOpen = !mobileOpen">
        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-width="1.5" d="M4 7h16M4 12h16M4 17h16"/>
        </svg>
      </button>
    </div>
    <div v-if="mobileOpen" class="md:hidden border-t border-[#e5e7eb] bg-white">
      <div class="container-wide py-4 flex flex-col gap-3">
        <RouterLink to="/" class="py-2">首页</RouterLink>
        <RouterLink to="/products" class="py-2">产品中心</RouterLink>
        <RouterLink to="/cases" class="py-2">客户案例</RouterLink>
        <template v-if="!auth.isAuthed">
          <RouterLink to="/login" class="py-2">登录</RouterLink>
        </template>
        <template v-else>
          <RouterLink to="/profile" class="py-2">个人中心</RouterLink>
        </template>
        <LocaleSwitcher />
      </div>
    </div>
  </header>
  <div class="h-14"></div>
</template>

<style scoped>
.nav-link { font-size: 0.875rem; color: oklch(0.50 0.008 260); transition: color 150ms; }
.nav-link:hover { color: oklch(0.18 0 0); }
</style>
