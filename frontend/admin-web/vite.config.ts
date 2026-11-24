import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // 实时通知走 /api/v1/ws/*，需要 ws 才能升级连接
        ws: true,
      },
      // App 插件脚本由后端提供；不代理会落到 vite 的静态目录 → 404
      '/.app-assets': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
