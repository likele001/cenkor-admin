import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  // 线上经 nginx 挂在 admin.cenkor.cn/landing/ 子路径下（部署目录 frontend/landing/），
  // base 必须为 /landing/，否则产物资源路径为 /assets/... 会 404
  base: '/landing/',
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  server: {
    port: 9910,
    host: '0.0.0.0'
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets'
  },
  css: {
    preprocessorOptions: {
      scss: {
        additionalData: '@import "@/styles/variables.scss";\n@import "@/styles/mixins.scss";\n'
      }
    }
  }
})
