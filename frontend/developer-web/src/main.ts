import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import { i18n, setupLocaleWatcher } from './locales'
import './style.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(i18n)

setupLocaleWatcher().then(() => {
  app.mount('#app')
})
