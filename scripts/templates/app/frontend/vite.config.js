import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 前端构建配置（与平台其它 App 对齐）
// - 打包为 iife 单文件 plugin.js
// - external vue → 共享 admin-web 的 window.Vue（避免双 Vue 实例不兼容）
// - Element Plus 打包进 plugin.js，CSS 内联注入 <style>
export default defineConfig({
  plugins: [vue()],
  define: {
    'process.env.NODE_ENV': JSON.stringify('production')
  },
  build: {
    lib: {
      entry: 'src/main.js',
      formats: ['iife'],
      name: '@@PLUGIN_NAME@@',
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
