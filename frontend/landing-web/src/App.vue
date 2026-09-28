<template>
  <!-- 注意：根元素不能再用 id="app"（宿主 index.html 里已有 <div id="app">，
       重复 id 不合规范，且预渲染水合时容器会错位）→ 用 class -->
  <div class="app-shell">
    <Navbar />
    <main>
      <router-view />
    </main>
    <Footer />
  </div>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import { useHead } from '@unhead/vue'
import Navbar from '@/components/Navbar.vue'
import Footer from '@/components/Footer.vue'
import { seoFor, canonicalFor, SHARED_META } from '@/config/seo'

const route = useRoute()

// 全站 head 在这里统一维护（数据来自 @/config/seo）。
// 传函数形式 = 响应式，路由切换时 head 自动更新。
// 这里声明的标签集合必须与预渲染脚本写进静态 HTML 的**完全一致** —— 见 SHARED_META 的注释。
useHead(() => {
  const seo = seoFor(route.path)
  const canonical = canonicalFor(route.path)
  return {
    title: seo.title,
    link: [{ rel: 'canonical', href: canonical }],
    meta: [
      { name: 'description', content: seo.description },
      { property: 'og:title', content: seo.title },
      { property: 'og:description', content: seo.description },
      { property: 'og:url', content: canonical },
      { name: 'twitter:title', content: seo.title },
      { name: 'twitter:description', content: seo.description },
      ...SHARED_META
    ]
  }
})
</script>

<style lang="scss">
#app {
  min-height: 100vh;
}

.app-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

main {
  flex: 1;
}
</style>
