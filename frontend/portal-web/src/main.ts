import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import { installGlobalRender } from './lib/cms-render'
import { i18n, setupLocaleWatcher } from './locales'
import './style.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(i18n)

setupLocaleWatcher().then(() => {
  app.mount('#app')
})

// 挂载全局 cmsRender 供外部脚本/动态内容使用
installGlobalRender()
