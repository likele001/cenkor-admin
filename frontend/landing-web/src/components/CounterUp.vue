<template>
  <span ref="elRef" class="counter-up">{{ displayValue }}{{ suffix }}</span>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'

const props = withDefaults(defineProps<{
  value: number
  duration?: number
  suffix?: string
}>(), {
  duration: 2000,
  suffix: ''
})

// 初值 = 终值：服务端预渲染时直接输出最终数字（爬虫/无 JS 环境看到的是真实数据，
// 而不是 "0"），客户端首帧也渲染同一个值 → hydration 不会 mismatch。
// 真正的"从 0 开始涨"在 onMounted 里（浏览器首次绘制之前）把值归零后播放。
const currentValue = ref(props.value)
const isVisible = ref(false)
// 用模板 ref 拿到「本实例」的 DOM 节点。
// 原先用 document.querySelector('.counter-up') 取的是全局第一个匹配元素，
// 4 个统计实例会全部 observe 同一个节点 → 只要有一个进入视口，其余数字也一起跳（拆行/换布局必错乱）。
const elRef = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null
let animationFrame: number | null = null

const displayValue = computed(() => {
  if (props.value >= 1000000) {
    return (currentValue.value / 1000000).toFixed(1) + 'M'
  }
  if (props.value >= 1000) {
    return (currentValue.value / 1000).toFixed(1) + 'K'
  }
  return Math.floor(currentValue.value).toString()
})

function animate() {
  const startTime = performance.now()
  const startValue = 0
  const endValue = props.value

  function step(currentTime: number) {
    const elapsed = currentTime - startTime
    const progress = Math.min(elapsed / props.duration, 1)
    
    // Easing function (ease-out)
    const easeProgress = 1 - Math.pow(1 - progress, 3)
    currentValue.value = startValue + (endValue - startValue) * easeProgress

    if (progress < 1) {
      animationFrame = requestAnimationFrame(step)
    }
  }

  animationFrame = requestAnimationFrame(step)
}

onMounted(() => {
  // 无 IntersectionObserver（老的/受限环境、预渲染）：保持终值，不播动画。
  if (typeof IntersectionObserver === 'undefined') {
    currentValue.value = props.value
    return
  }

  // 挂载后归零：此刻首帧尚未绘制，用户看不到跳动；进入视口时再从头动画。
  currentValue.value = 0

  observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting && !isVisible.value) {
          isVisible.value = true
          animate()
          observer?.unobserve(entry.target)
        }
      })
    },
    { threshold: 0.5 }
  )

  if (elRef.value) {
    observer.observe(elRef.value)
  }
})

onUnmounted(() => {
  observer?.disconnect()
  if (animationFrame) {
    cancelAnimationFrame(animationFrame)
  }
})
</script>

<style lang="scss" scoped>
.counter-up {
  font-family: $font-display;
  font-weight: 700;
}
</style>
