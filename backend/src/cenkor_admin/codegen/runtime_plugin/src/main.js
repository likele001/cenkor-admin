// 通用 CRUD 运行时插件入口
//
// 由「代码生成器」生成的每个 App，其 frontend/dist/plugin.js =
//   window.__CODEGEN_APP__ = { ...本 App 的 spec 元数据... }
//   + 本文件构建出的 bundle
// 因此本 bundle 只构建一次，所有生成的 App 复用。
//
// 注册时机：admin-web 在 app.use(router) / mount 之前调用 loadInstalledPlugins()，
// 所以这里必须**同步**完成 __registerPlugin（菜单才能被侧边栏读到）。
import { defineComponent, h } from 'vue'
import ElementPlusCss from 'element-plus/dist/index.css?inline'
import GenericCrud from './crud/GenericCrud.vue'

const app = window.__CODEGEN_APP__

if (app && Array.isArray(app.entities)) {
  // Element Plus 样式内联注入（平台只加载 plugin.js 这一个脚本）
  if (typeof document !== 'undefined') {
    const style = document.createElement('style')
    style.setAttribute('data-plugin', app.key)
    style.textContent = ElementPlusCss
    document.head.appendChild(style)
  }

  const routes = app.entities.map((entity) => ({
    path: entity.route,
    name: `${app.key}-${entity.key}`,
    // 每个实体一个闭包组件：把 entity 元数据传给通用 CRUD 页面
    component: defineComponent({
      name: `${app.key}-${entity.key}`,
      setup() {
        return () => h(GenericCrud, { appKey: app.key, entity })
      }
    }),
    meta: { permission: `${app.key}:${entity.key}:read` }
  }))

  const menus = app.entities.map((entity) => ({
    key: `${app.key}:${entity.key}`,
    title: entity.title,
    path: entity.menu_path,
    icon: 'menu',
    sort: entity.sort
  }))

  window.__registerPlugin({
    id: app.key,
    version: app.version,
    name: app.name,
    routes,
    menus,
    locales: { 'zh-CN': { [app.key]: { title: app.name } } }
  })
}
