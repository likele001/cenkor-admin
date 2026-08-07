import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  define: {
    'process.env.NODE_ENV': JSON.stringify('production'),
    'process.env': {},
  },
  build: {
    lib: {
      entry: './src/main.js',
      name: 'CloudStoragePlugin',
      fileName: () => 'plugin.js',
      formats: ['iife'],
    },
    rollupOptions: {
      // 把 vue 标为 external,让 plugin.js 不再 inline 一份 Vue runtime,
      // 而是从 window.Vue 取(由 admin-web 在 main.ts 里挂上),
      // 保证 plugin 跟主程序共享同一个 Vue 实例,响应式/组件实例正常联通
      external: ['vue'],
      output: {
        inlineDynamicImports: true,
        globals: { vue: 'Vue' },
      },
    },
    emptyOutDir: false,
  },
})
