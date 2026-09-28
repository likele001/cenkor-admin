import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

/**
 * 预渲染专用的 SSR 构建配置（只在 scripts/prerender.mjs 之前跑一次）。
 *
 * 产物 dist-ssr/entry-server.js 由 Node 加载执行，不发布到线上。
 * base 必须与主配置一致（/landing/），否则 SSR 输出的 <router-link> href 会是
 * /features 而不是 /landing/features。
 */
export default defineConfig({
  base: '/landing/',
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  css: {
    preprocessorOptions: {
      scss: {
        additionalData: '@import "@/styles/variables.scss";\n@import "@/styles/mixins.scss";\n'
      }
    }
  },
  build: {
    ssr: 'src/entry-server.ts',
    outDir: 'dist-ssr',
    emptyOutDir: true,
    minify: false,
    cssCodeSplit: false
  }
})
