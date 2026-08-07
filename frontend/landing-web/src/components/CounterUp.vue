<template>
  <span class="counter-up">{{ displayValue }}{{ suffix }}</span>
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

const currentValue = ref(0)
const isVisible = ref(false)
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

  const el = document.querySelector('.counter-up')
  if (el) {
    observer.observe(el)
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
