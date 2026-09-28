<template>
  <div
    ref="element"
    class="scroll-reveal"
    :class="[animation, { visible: isVisible, pending: isPending }]"
    :style="delayStyle"
  >
    <slot></slot>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = withDefaults(defineProps<{
  animation?: 'fade-up' | 'fade-left' | 'fade-right' | 'scale'
  delay?: number
}>(), {
  animation: 'fade-up',
  delay: 0
})

const element = ref<HTMLElement | null>(null)
// isVisible：已进入视口 → 显示
const isVisible = ref(false)
// isPending：已挂载、等待进入视口 → 隐藏待动画。
// 关键：初始值必须是 false，让服务端预渲染输出的 HTML 里**内容可见**（爬虫才能读到正文，
// Google 对 opacity:0 的文本会降权/判隐藏）。真正的"隐藏"动作放到 onMounted（paint 之前）再施加，
// 视觉上与原先"一开始就 opacity:0"没有区别，但预渲染 HTML 是干净的。
const isPending = ref(false)
let observer: IntersectionObserver | null = null

const delayStyle = computed(() => {
  return props.delay > 0 ? { transitionDelay: `${props.delay}ms` } : {}
})

onMounted(() => {
  // 预渲染 / 无 IntersectionObserver 的环境：保持可见，不做动画
  if (typeof IntersectionObserver === 'undefined') return

  isPending.value = true

  observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          isVisible.value = true
          isPending.value = false
          observer?.unobserve(entry.target)
        }
      })
    },
    { threshold: 0.1 }
  )

  if (element.value) {
    observer.observe(element.value)
  }
})

onUnmounted(() => {
  observer?.disconnect()
})
</script>

<style lang="scss" scoped>
.scroll-reveal {
  transition: opacity 0.6s ease, transform 0.6s ease;

  &.fade-up.pending {
    opacity: 0;
    transform: translateY(30px);
  }

  &.fade-left.pending {
    opacity: 0;
    transform: translateX(-30px);
  }

  &.fade-right.pending {
    opacity: 0;
    transform: translateX(30px);
  }

  &.scale.pending {
    opacity: 0;
    transform: scale(0.9);
  }

  &.visible {
    opacity: 1;
    transform: none;
  }
}
</style>
