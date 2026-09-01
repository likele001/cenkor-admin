import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// ERP 前端插件构建：IIFE 单文件 plugin.js
// - external vue → 共享 admin-web 的 window.Vue（避免双 Vue 实例不兼容）
// - Element Plus 打包进 plugin.js，CSS 内联注入 <style>
export default defineConfig({
  plugins: [vue()],
  define: {
    // 浏览器无 process 全局；Element Plus 等依赖会引用 process.env.NODE_ENV，
    // 必须在构建期替换成字面量，否则 plugin.js 运行时报 ReferenceError 导致路由未注册
    'process.env.NODE_ENV': JSON.stringify('production'),
    'process.env': {},
  },
  build: {
    lib: {
      entry: 'src/main.js',
      formats: ['iife'],
      name: 'ErpPlugin',
      fileName: () => 'plugin.js'
    },
    rollupOptions: {
      external: ['vue'],
      output: {
        globals: { vue: 'Vue' },
        inlineDynamicImports: true
      }
    }
  }
})