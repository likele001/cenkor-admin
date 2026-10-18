// 库存管理 前端插件入口 —— 打包为 iife 单文件 plugin.js（由 scripts/gen-app.py 生成）
import 'vue'
import ElementPlusCss from 'element-plus/dist/index.css?inline'

import WarehouseView from './pages/WarehouseView.vue'
import LocationView from './pages/LocationView.vue'

if (typeof document !== 'undefined') {
  const style = document.createElement('style')
  style.setAttribute('data-inventory-plugin', 'element-plus')
  style.textContent = ElementPlusCss
  document.head.appendChild(style)
}

// 路由 path 必须与后端 manifest menus 的 path 一致（此处相对路径无前导斜杠）
window.__registerPlugin({
  id: 'inventory',
  version: '1.0.0',
  name: '库存管理',
  routes: [
    { path: 'inventory/warehouse', name: 'inventory-warehouse', component: WarehouseView, meta: { permission: 'inventory:warehouse:read' } },
    { path: 'inventory/location', name: 'inventory-location', component: LocationView, meta: { permission: 'inventory:location:read' } },
  ],
  menus: [
    { key: 'inventory:warehouse', title: '仓库', path: '/inventory/warehouse', icon: 'menu', sort: 81 },
    { key: 'inventory:location', title: '库位', path: '/inventory/location', icon: 'menu', sort: 82 },
  ],
  locales: {
    'zh-CN': { inventory: { title: '库存管理' } }
  }
})
