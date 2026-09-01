// ERP 前端插件入口 —— 打包为 iife 单文件 plugin.js
import 'vue'
import ElementPlusCss from 'element-plus/dist/index.css?inline'

import CustomerListView from './pages/CustomerListView.vue'
import CustomerEditView from './pages/CustomerEditView.vue'
import SupplierListView from './pages/SupplierListView.vue'
import ProductListView from './pages/ProductListView.vue'
import SalesOrderListView from './pages/SalesOrderListView.vue'
import SalesOrderEditView from './pages/SalesOrderEditView.vue'
import PurchaseOrderListView from './pages/PurchaseOrderListView.vue'
import PurchaseOrderEditView from './pages/PurchaseOrderEditView.vue'
import WarehouseListView from './pages/WarehouseListView.vue'
import FinanceView from './pages/FinanceView.vue'
import GlView from './pages/GlView.vue'
import WarehouseExtView from './pages/WarehouseExtView.vue'
import ManufacturingView from './pages/ManufacturingView.vue'

// 内联 Element Plus 样式（避免额外的 plugin.css 加载依赖）
if (typeof document !== 'undefined') {
  const style = document.createElement('style')
  style.setAttribute('data-erp-plugin', 'element-plus')
  style.textContent = ElementPlusCss
  document.head.appendChild(style)
}

// 注册插件 —— 路由挂在 admin-web 的 'layout' 父路由下（相对路径，无前导斜杠）
window.__registerPlugin({
  id: 'erp',
  version: '1.0.0',
  name: 'ERP 管理',
  routes: [
    { path: 'erp/customers', name: 'erp-customers', component: CustomerListView, meta: { permission: 'erp:customer:read' } },
    { path: 'erp/customers/:id', name: 'erp-customer-edit', component: CustomerEditView, meta: { permission: 'erp:customer:read' } },
    { path: 'erp/suppliers', name: 'erp-suppliers', component: SupplierListView, meta: { permission: 'erp:supplier:read' } },
    { path: 'erp/products', name: 'erp-products', component: ProductListView, meta: { permission: 'erp:product:read' } },
    { path: 'erp/sales-orders', name: 'erp-sales-orders', component: SalesOrderListView, meta: { permission: 'erp:sales_order:read' } },
    { path: 'erp/sales-orders/:id', name: 'erp-sales-order-edit', component: SalesOrderEditView, meta: { permission: 'erp:sales_order:read' } },
    { path: 'erp/purchase-orders', name: 'erp-purchase-orders', component: PurchaseOrderListView, meta: { permission: 'erp:purchase:read' } },
    { path: 'erp/purchase-orders/:id', name: 'erp-purchase-order-edit', component: PurchaseOrderEditView, meta: { permission: 'erp:purchase:read' } },
    { path: 'erp/warehouses', name: 'erp-warehouses', component: WarehouseListView, meta: { permission: 'erp:warehouse:read' } },
    { path: 'erp/finance', name: 'erp-finance', component: FinanceView, meta: { permission: 'erp:finance:read' } },
    { path: 'erp/gl', name: 'erp-gl', component: GlView, meta: { permission: 'erp:gl:read' } },
    { path: 'erp/warehouse-ext', name: 'erp-warehouse-ext', component: WarehouseExtView, meta: { permission: 'erp:warehouse:read' } },
    { path: 'erp/manufacturing', name: 'erp-manufacturing', component: ManufacturingView, meta: { permission: 'erp:mfg:read' } }
  ],
  // 菜单（与后端 manifest 相同的 key+path，合并时按 key::path 去重，后端优先）
  menus: [
    { key: 'erp:customer', title: '客户管理', path: '/erp/customers', icon: 'user', sort: 51 },
    { key: 'erp:supplier', title: '供应商', path: '/erp/suppliers', icon: 'office-building', sort: 52 },
    { key: 'erp:product', title: '商品', path: '/erp/products', icon: 'goods', sort: 53 },
    { key: 'erp:sales', title: '销售订单', path: '/erp/sales-orders', icon: 'document', sort: 54 },
    { key: 'erp:purchase', title: '采购订单', path: '/erp/purchase-orders', icon: 'shopping-cart', sort: 55 },
    { key: 'erp:warehouse', title: '仓库', path: '/erp/warehouses', icon: 'box', sort: 56 },
    { key: 'erp:warehouse-ext', title: '仓储深度', path: '/erp/warehouse-ext', icon: 'box', sort: 57 },
    { key: 'erp:finance', title: '财务', path: '/erp/finance', icon: 'money', sort: 58 },
    { key: 'erp:gl', title: '总账', path: '/erp/gl', icon: 'notebook', sort: 59 },
    { key: 'erp:mfg', title: '制造', path: '/erp/manufacturing', icon: 'setting', sort: 60 }
  ],
  locales: {
    'zh-CN': {
      erp: {
        title: 'ERP 管理',
        customer: '客户管理',
        supplier: '供应商',
        product: '商品',
        sales: '销售订单',
        purchase: '采购订单',
        warehouse: '仓库',
        finance: '财务',
        'warehouse-ext': '仓储深度',
        gl: '总账',
        mfg: '制造'
      }
    }
  }
})