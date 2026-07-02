<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <!-- Hero -->
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <img src="/logo.svg" class="w-7 h-7 rounded-lg" width="28" height="28">
          <span class="font-semibold">{{ t('dev.brand') }}</span>
          <span class="text-xs px-2 py-0.5 rounded bg-blue-50 text-blue-600">Developer</span>
        </div>
        <div class="flex items-center gap-4">
          <router-link to="/store" class="text-sm text-ink-600 hover:text-ink-900">{{ t('dev.navStore') }}</router-link>
          <router-link to="/docs" class="text-sm text-ink-600 hover:text-ink-900">{{ t('dev.navDocs') }}</router-link>
          <router-link to="/login" class="btn-ghost text-sm">{{ t('dev.login') }}</router-link>
          <router-link to="/register" class="btn-primary text-sm">{{ t('dev.register') }}</router-link>
        </div>
      </div>
    </header>

    <!-- Hero Content -->
    <main class="max-w-6xl mx-auto px-6 py-20">
      <div class="text-center mb-16">
        <h1 class="text-4xl font-bold tracking-tight mb-4">{{ t('dev.heroTitle') }}</h1>
        <p class="text-lg text-ink-500 max-w-2xl mx-auto">{{ t('dev.heroDesc') }}</p>
        <div class="flex justify-center gap-4 mt-8">
          <router-link to="/register" class="btn-primary text-base px-8 py-3">{{ t('dev.startNow') }}</router-link>
          <router-link to="/docs" class="btn-ghost text-base px-8 py-3">{{ t('dev.readDocs') }}</router-link>
        </div>
      </div>

      <!-- Features -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-8 mb-16">
        <div class="card p-6 text-center">
          <div class="text-3xl mb-4">📦</div>
          <h3 class="font-semibold mb-2">{{ t('dev.feature1Title') }}</h3>
          <p class="text-sm text-ink-500">{{ t('dev.feature1Desc') }}</p>
        </div>
        <div class="card p-6 text-center">
          <div class="text-3xl mb-4">🚀</div>
          <h3 class="font-semibold mb-2">{{ t('dev.feature2Title') }}</h3>
          <p class="text-sm text-ink-500">{{ t('dev.feature2Desc') }}</p>
        </div>
        <div class="card p-6 text-center">
          <div class="text-3xl mb-4">🔒</div>
          <h3 class="font-semibold mb-2">{{ t('dev.feature3Title') }}</h3>
          <p class="text-sm text-ink-500">{{ t('dev.feature3Desc') }}</p>
        </div>
      </div>

      <!-- Steps -->
      <div class="card p-8">
        <h2 class="text-xl font-semibold mb-6 text-center">{{ t('dev.stepsTitle') }}</h2>
        <div class="grid grid-cols-1 md:grid-cols-4 gap-6">
          <div class="text-center">
            <div class="w-10 h-10 rounded-full bg-ink-100 text-ink-700 flex items-center justify-center mx-auto mb-3 font-semibold">1</div>
            <h4 class="font-medium mb-1">{{ t('dev.step1') }}</h4>
            <p class="text-xs text-ink-500">{{ t('dev.step1Desc') }}</p>
          </div>
          <div class="text-center">
            <div class="w-10 h-10 rounded-full bg-ink-100 text-ink-700 flex items-center justify-center mx-auto mb-3 font-semibold">2</div>
            <h4 class="font-medium mb-1">{{ t('dev.step2') }}</h4>
            <p class="text-xs text-ink-500">{{ t('dev.step2Desc') }}</p>
          </div>
          <div class="text-center">
            <div class="w-10 h-10 rounded-full bg-ink-100 text-ink-700 flex items-center justify-center mx-auto mb-3 font-semibold">3</div>
            <h4 class="font-medium mb-1">{{ t('dev.step3') }}</h4>
            <p class="text-xs text-ink-500">{{ t('dev.step3Desc') }}</p>
          </div>
          <div class="text-center">
            <div class="w-10 h-10 rounded-full bg-ink-100 text-ink-700 flex items-center justify-center mx-auto mb-3 font-semibold">4</div>
            <h4 class="font-medium mb-1">{{ t('dev.step4') }}</h4>
            <p class="text-xs text-ink-500">{{ t('dev.step4Desc') }}</p>
          </div>
        </div>
      </div>
    </main>

    <!-- Footer -->
    <footer class="border-t border-ink-200 py-8 text-center text-sm text-ink-400">
      © 2026 Cenkor. {{ t('dev.footer') }}
    </footer>
  </div>
</template>
