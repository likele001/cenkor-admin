// 插件 API 封装 —— 复用 admin-web 的 __PLUGIN_API__（自带 401 自动刷新 token）
const win = window

function buildInvoke() {
  if (typeof win.__PLUGIN_API__ === 'function') return win.__PLUGIN_API__
  return async (method, path, body) => {
    let token = ''
    try { token = localStorage.getItem('cenkor_token') || '' } catch (e) {}
    if (!token) token = (win.__PLUGIN_TOKEN__ || '').toString()
    const headers = { 'Content-Type': 'application/json' }
    if (token) headers.Authorization = 'Bearer ' + token
    const resp = await fetch(path, {
      method,
      headers,
      body: body != null ? JSON.stringify(body) : undefined
    })
    if (!resp.ok) {
      const e = await resp.json().catch(() => ({}))
      throw new Error(e.detail || resp.statusText || `HTTP ${resp.status}`)
    }
    return resp.status === 204 ? null : resp.json()
  }
}

const invoke = buildInvoke()

function buildQuery(params = {}) {
  const parts = []
  for (const [k, v] of Object.entries(params || {})) {
    if (v === '' || v === null || v === undefined) continue
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
  }
  return parts.length ? '?' + parts.join('&') : ''
}

/** 为某个 App 生成其 CRUD API 客户端（path 以实体 key 开头，如 '/warehouse'） */
export function makeApi(appKey) {
  const BASE = '/api/v1/' + appKey
  return {
    get(path, params) { return invoke('GET', BASE + path + buildQuery(params)) },
    post(path, body) { return invoke('POST', BASE + path, body) },
    put(path, body) { return invoke('PUT', BASE + path, body) },
    patch(path, body) { return invoke('PATCH', BASE + path, body) },
    del(path) { return invoke('DELETE', BASE + path) }
  }
}

export function fmtMoney(v, digits = 2) {
  const n = Number(v || 0)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export function fmtDate(v) {
  if (!v) return '—'
  if (typeof v === 'string' && v.length >= 10) return v.slice(0, 10)
  return String(v).slice(0, 10)
}
