import { defineComponent } from 'vue'
import CloudStorageView from './CloudStorageView.vue'

const Component = defineComponent(CloudStorageView)

window.__registerPlugin({
  id: 'cloud_storage',
  version: '1.0.0',
  name: '云存储',
  routes: [
    {
      path: 'cloud_storage',
      name: 'cloud-storage',
      component: Component,
      meta: { permission: 'cloud_storage:read' },
    },
  ],
  menus: [
    {
      key: 'cloud_storage',
      title: '云存储',
      path: '/cloud_storage',
      icon: 'cloud',
      sort: 95,
    },
  ],
  locales: {
    'zh-CN': { cloud_storage: { title: '云存储' } },
  },
})
