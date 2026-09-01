// 轻量导航助手 —— 不依赖 vue-router 实例注入。
// 插件组件由 admin-web 宿主路由挂载，其 vue-router 未暴露到 window，
// 直接使用 useRouter/useRoute 会产生 symbol 不匹配。改用 location 全导航，
// 宿主 PluginManager 在每次页面加载后重挂路由，天然支持插件 URL。
export function go(url) {
  window.location.href = url
}

export function back() {
  window.history.length > 1 ? window.history.back() : go('/')
}

// 解析当前 URL 段（列表页不传，详情页传所需段名）
export function pathSeg(i) {
  const seg = window.location.pathname.split('/').filter(Boolean)
  return seg[i] || null
}

// 当前资源 ID（匹配路径末尾的数字）；new 时返回 'new'
export function currentId() {
  const seg = window.location.pathname.split('/').filter(Boolean)
  const last = seg[seg.length - 1]
  return /^\d+$/.test(last || '') ? last : null
}

export function isNew() {
  return window.location.pathname.endsWith('/new')
}