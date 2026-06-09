<script setup lang="ts">
defineProps<{
  open: boolean
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  danger?: boolean
}>()

const emit = defineEmits<{ confirm: []; cancel: [] }>()
</script>

<script lang="ts">
import { ref } from 'vue'

// 静态 Promise API（与本组件 <ConfirmModal> 视觉一致）
let _resolver: ((v: boolean) => void) | null = null
const _state = ref<{
  open: boolean
  title: string
  message: string
  confirmText: string
  cancelText: string
  danger: boolean
} | null>(null)

export function confirm(opts: {
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  danger?: boolean
}): Promise<boolean> {
  _state.value = {
    open: true,
    title: opts.title,
    message: opts.message,
    confirmText: opts.confirmText ?? '确定',
    cancelText: opts.cancelText ?? '取消',
    danger: opts.danger ?? false,
  }
  return new Promise((resolve) => { _resolver = resolve })
}

function _ok() {
  if (_state.value) _state.value.open = false
  _resolver?.(true)
  _resolver = null
}
function _cancel() {
  if (_state.value) _state.value.open = false
  _resolver?.(false)
  _resolver = null
}
</script>

<template>
  <Teleport to="body">
    <!-- 1. 受控模式（父组件 :open + @confirm/@cancel） -->
    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition duration-100 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="open"
        class="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-ink-900/40 backdrop-blur-sm"
        @click.self="emit('cancel')"
      >
        <div class="w-full max-w-md bg-white rounded-2xl shadow-xl border border-ink-200 p-6">
          <h3 class="text-lg font-semibold">{{ title }}</h3>
          <p class="mt-2 text-sm text-ink-600 whitespace-pre-line">{{ message }}</p>
          <div class="mt-6 flex items-center justify-end gap-3">
            <button
              type="button"
              class="px-4 py-2 rounded-lg text-sm font-medium text-ink-700 hover:bg-ink-100"
              @click="emit('cancel')"
            >
              {{ cancelText ?? '取消' }}
            </button>
            <button
              type="button"
              class="px-4 py-2 rounded-lg text-sm font-medium text-white"
              :class="danger ? 'bg-red-600 hover:bg-red-700' : 'bg-ink-900 hover:bg-ink-800'"
              @click="emit('confirm')"
            >
              {{ confirmText ?? '确定' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- 2. 静态 confirm({...}) 模式（共享一个全局 dialog） -->
    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition duration-100 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="_state?.open"
        class="fixed inset-0 z-[101] flex items-center justify-center p-4 bg-ink-900/40 backdrop-blur-sm"
        @click.self="_cancel"
      >
        <div class="w-full max-w-md bg-white rounded-2xl shadow-xl border border-ink-200 p-6">
          <h3 class="text-lg font-semibold">{{ _state.title }}</h3>
          <p class="mt-2 text-sm text-ink-600 whitespace-pre-line">{{ _state.message }}</p>
          <div class="mt-6 flex items-center justify-end gap-3">
            <button
              type="button"
              class="px-4 py-2 rounded-lg text-sm font-medium text-ink-700 hover:bg-ink-100"
              @click="_cancel"
            >
              {{ _state.cancelText }}
            </button>
            <button
              type="button"
              class="px-4 py-2 rounded-lg text-sm font-medium text-white"
              :class="_state.danger ? 'bg-red-600 hover:bg-red-700' : 'bg-ink-900 hover:bg-ink-800'"
              @click="_ok"
            >
              {{ _state.confirmText }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
