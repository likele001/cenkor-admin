// 导航辅助 —— 走 admin-web 的 __PLUGIN_NAV__
export function go(path) {
  if (typeof window !== 'undefined' && window.__PLUGIN_NAV__) {
    return window.__PLUGIN_NAV__(path)
  }
  if (typeof window !== 'undefined' && window.history && window.history.pushState) {
    window.history.pushState({}, '', path)
  }
  return path
}
