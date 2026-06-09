<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

const emit = defineEmits<{ 'update:verified': [boolean] }>()
const props = withDefaults(defineProps<{
  width?: number
  height?: number
}>(), { width: 320, height: 40 })

const canvasRef = ref<HTMLCanvasElement | null>(null)
const sliderX = ref(0)
const dragging = ref(false)
const verified = ref(false)
const verifiedToken = ref<string>('')
const errorMsg = ref('')

let puzzleX = 0
let puzzleY = 0
let puzzleSize = 40
let bgImageData: ImageData | null = null
let startMouseX = 0

function rand(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min
}

function generateToken(): string {
  const arr = new Uint8Array(16)
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
    crypto.getRandomValues(arr)
  } else {
    for (let i = 0; i < arr.length; i++) arr[i] = Math.floor(Math.random() * 256)
  }
  return Array.from(arr).map((b) => b.toString(16).padStart(2, '0')).join('')
}

function drawBackground() {
  const c = canvasRef.value
  if (!c) return
  const ctx = c.getContext('2d')
  if (!ctx) return
  const w = props.width
  const h = props.height

  ctx.clearRect(0, 0, w, h)

  // 渐变背景
  const grad = ctx.createLinearGradient(0, 0, w, 0)
  grad.addColorStop(0, '#e2e8f0')
  grad.addColorStop(1, '#cbd5e1')
  ctx.fillStyle = grad
  ctx.fillRect(0, 0, w, h)

  // 噪点
  for (let i = 0; i < 40; i++) {
    ctx.fillStyle = `rgba(${rand(50, 200)}, ${rand(50, 200)}, ${rand(50, 200)}, 0.4)`
    ctx.fillRect(rand(0, w), rand(0, h), 2, 2)
  }

  // 拼图形状
  puzzleX = rand(puzzleSize + 10, w - puzzleSize - 10)
  puzzleY = rand(2, h - puzzleSize - 2)
  drawPuzzle(ctx, puzzleX, puzzleY, '#94a3b8', 'destination-over')

  // 缺口（用目标颜色填充一块凸起区域）
  // 简化：仅画"放置区"提示
  ctx.fillStyle = 'rgba(148, 163, 184, 0.15)'
  ctx.fillRect(puzzleX - 1, puzzleY - 1, puzzleSize + 2, puzzleSize + 2)

  // 记录初始位置，验证 = 拖回的 puzzleX
  bgImageData = ctx.getImageData(0, 0, w, h)
}

function drawPuzzle(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  color: string,
  composite: GlobalCompositeOperation = 'source-over',
) {
  ctx.save()
  ctx.globalCompositeOperation = composite
  ctx.fillStyle = color
  ctx.beginPath()
  ctx.moveTo(x, y)
  ctx.lineTo(x + puzzleSize * 0.4, y)
  ctx.arc(x + puzzleSize * 0.4 + 4, y + 4, 4, Math.PI, 0, false)
  ctx.lineTo(x + puzzleSize, y)
  ctx.lineTo(x + puzzleSize, y + puzzleSize * 0.4)
  ctx.arc(x + puzzleSize - 4, y + puzzleSize * 0.4 + 4, 4, -Math.PI / 2, Math.PI / 2, false)
  ctx.lineTo(x + puzzleSize, y + puzzleSize)
  ctx.lineTo(x + puzzleSize * 0.6, y + puzzleSize)
  ctx.arc(x + puzzleSize * 0.6 - 4, y + puzzleSize - 4, 4, 0, Math.PI, false)
  ctx.lineTo(x, y + puzzleSize)
  ctx.lineTo(x, y + puzzleSize * 0.6)
  ctx.arc(x + 4, y + puzzleSize * 0.6 - 4, 4, Math.PI / 2, -Math.PI / 2, false)
  ctx.closePath()
  ctx.fill()
  ctx.restore()
}

function onPointerDown(e: PointerEvent) {
  if (verified.value) return
  dragging.value = true
  startMouseX = e.clientX
  errorMsg.value = ''
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
}

function onPointerMove(e: PointerEvent) {
  if (!dragging.value) return
  const c = canvasRef.value
  if (!c) return
  const ctx = c.getContext('2d')
  if (!ctx || !bgImageData) return
  const newX = Math.max(0, Math.min(props.width - puzzleSize, e.clientX - startMouseX))
  sliderX.value = newX
  // 重绘：底图 + 拼图块
  ctx.putImageData(bgImageData, 0, 0)
  drawPuzzle(ctx, newX, puzzleY, '#3b82f6', 'source-over')
}

function onPointerUp() {
  if (!dragging.value) return
  dragging.value = false
  const diff = Math.abs(sliderX.value - puzzleX)
  if (diff <= 4) {
    verified.value = true
    sliderX.value = puzzleX
    verifiedToken.value = generateToken()
    emit('update:verified', true)
  } else {
    errorMsg.value = '位置不匹配，请重试'
    setTimeout(() => {
      sliderX.value = 0
      errorMsg.value = ''
    }, 800)
    emit('update:verified', false)
  }
}

function refresh() {
  sliderX.value = 0
  verified.value = false
  verifiedToken.value = ''
  errorMsg.value = ''
  emit('update:verified', false)
  drawBackground()
}

onMounted(() => {
  drawBackground()
})

onBeforeUnmount(() => {
  dragging.value = false
})

defineExpose({ token: () => verifiedToken.value, verified: () => verified.value, refresh })
</script>

<template>
  <div class="space-y-2">
    <div class="relative select-none" :style="{ width: width + 'px', height: height + 'px' }">
      <canvas
        ref="canvasRef"
        :width="width"
        :height="height"
        class="absolute inset-0 rounded-lg border border-ink-200"
      />
      <div
        class="absolute top-0 left-0 h-full flex items-center justify-center text-sm font-medium rounded-lg cursor-pointer transition-colors"
        :class="[
          verified ? 'bg-emerald-500 text-white' : 'bg-brand-500 text-white shadow-md',
          dragging ? 'cursor-grabbing' : 'cursor-grab',
        ]"
        :style="{ width: '40px', transform: `translateX(${sliderX}px)` }"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointercancel="onPointerUp"
      >
        <span v-if="verified">✓</span>
        <span v-else>→</span>
      </div>
      <div class="absolute inset-0 flex items-center justify-center text-sm text-ink-500 pointer-events-none">
        <span v-if="verified" class="text-emerald-600 font-medium">验证通过</span>
        <span v-else-if="errorMsg" class="text-red-600 font-medium">{{ errorMsg }}</span>
        <span v-else>拖动滑块完成拼图</span>
      </div>
    </div>
    <button
      v-if="!verified"
      type="button"
      class="text-xs text-ink-500 hover:text-ink-900"
      @click="refresh"
    >
      换一张
    </button>
  </div>
</template>
