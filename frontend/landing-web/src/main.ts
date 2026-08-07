import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createHead } from '@unhead/vue'
import App from './App.vue'
import router from './router'
import './styles/global.scss'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(createHead())

app.mount('#app')
