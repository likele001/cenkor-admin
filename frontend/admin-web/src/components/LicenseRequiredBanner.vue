<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
/**
 * 全局「应用未授权」提示条。
 *
 * 触发来源：lib/api.ts 拦截器收到 402（license_required 应用的接口守卫返回），
 * 通过 window 事件广播到这里。不弹 alert：后台很多页面会并发打多个接口，
 * 每个都弹会糊满屏幕；这里按应用去重，固定一条提示，并给出去应用市场的入口。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

interface Notice {
  appKey: string
  message: string
}

const notices = ref<Notice[]>([])
let timer: number | undefined

const current = computed(() => notices.value[0] || null)

function push(e: Event) {
  const detail = (e as CustomEvent).detail || {}
  const appKey = String(detail.appKey || '')
  if (!appKey) return
  const message = String(detail.message || '该应用尚未授权')
  if (notices.value.some((n) => n.appKey === appKey)) return
  notices.value.push({ appKey, message })
  window.clearTimeout(timer)
  timer = window.setTimeout(dismiss, 15000)
}

function dismiss() {
  window.clearTimeout(timer)
  notices.value.shift()
  if (notices.value.length) {
    timer = window.setTimeout(dismiss, 15000)
  }
}

onMounted(() => window.addEventListener('license-required', push))
onUnmounted(() => {
  window.removeEventListener('license-required', push)
  window.clearTimeout(timer)
})
</script>

<template>
  <div
    v-if="current"
    class="fixed top-4 left-1/2 -translate-x-1/2 z-[9999] max-w-[92vw] md:max-w-xl w-max"
    role="alert"
  >
    <div class="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 shadow-lg">
      <span class="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-400/90 text-[11px] font-semibold text-white">!</span>
      <div class="min-w-0">
        <p class="text-sm font-medium text-amber-900">
          应用「{{ current.appKey }}」未授权
        </p>
        <p class="mt-0.5 text-xs text-amber-800/90 leading-relaxed">{{ current.message }}</p>
        <RouterLink
          to="/system/apps"
          class="mt-1.5 inline-block text-xs font-medium text-amber-900 underline underline-offset-2 hover:text-amber-950"
          @click="dismiss"
        >{{ t("licenseRequiredBanner.去应用管_1i2oxv") }}</RouterLink>
      </div>
      <button
        class="ml-1 shrink-0 rounded p-0.5 text-amber-700/70 hover:text-amber-900"
        :aria-label="t('licenseRequiredBanner.close')"
        @click="dismiss"
      >✕</button>
    </div>
  </div>
</template>
