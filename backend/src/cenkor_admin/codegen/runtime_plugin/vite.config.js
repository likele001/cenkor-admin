import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import cssInjectedByJs from 'vite-plugin-css-injected-by-js'

// 通用 CRUD 运行时插件的构建配置。
// 产物 backend/src/cenkor_admin/codegen/assets/plugin_head.js：
//   iife 单文件；external vue → 共享 admin-web 的 window.Vue（避免双 Vue 实例）；
//   Element Plus 打包进 bundle，CSS 内联注入 <style>。
//
// 注意：lib 模式下 Vite 会把 SFC 的 <style scoped> 抽成独立的 style.css 文件，
// 而平台只加载 plugin.js 一个脚本（CSS 必须内联），所以必须用
// vite-plugin-css-injected-by-js 把 CSS 注入回 JS。
export default defineConfig({
  plugins: [vue(), cssInjectedByJs()],
  define: {
    'process.env.NODE_ENV': JSON.stringify('production')
  },
  build: {
    lib: {
      entry: 'src/main.js',
      formats: ['iife'],
      name: 'CenkorCodegenRuntime',
      fileName: () => 'plugin_head.js'
    },
    rollupOptions: {
      external: ['vue'],
      output: {
        globals: { vue: 'Vue' },
        inlineDynamicImports: true
      }
    },
    outDir: 'dist',
    emptyOutDir: true
  }
})
