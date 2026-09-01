// ERP API 封装 —— 复用 admin-web 的 __PLUGIN_API__（自带 401 自动刷新 token）
const win = window
const BASE = '/api/v1/erp'

function buildInvoke() {
  if (typeof win.__PLUGIN_API__ === 'function') return win.__PLUGIN_API__
  // 兜底：宿主未注入时直接用 fetch + localStorage token
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

export const api = {
  get(path, params) {
    return invoke('GET', BASE + path + buildQuery(params))
  },
  post(path, body) {
    return invoke('POST', BASE + path, body)
  },
  put(path, body) {
    return invoke('PUT', BASE + path, body)
  },
  del(path) {
    return invoke('DELETE', BASE + path)
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

export const STATUS_TAGS = {
  active: 'success',
  inactive: 'info',
  disabled: 'warning',
  draft: 'info',
  confirmed: 'warning',
  converted: 'primary',
  shipped: 'success',
  pending: 'info',
  fulfilled: 'success',
  issued: 'warning',
  paid: 'success',
  received: 'success',
  open: 'warning',
  settled: 'success',
  partial: 'primary'
}

export const STATUS_LABELS = {
  active: '启用',
  inactive: '停用',
  disabled: '禁用',
  draft: '草稿',
  confirmed: '已确认',
  converted: '已转订单',
  shipped: '已出货',
  pending: '待处理',
  fulfilled: '已履行',
  issued: '已开票',
  paid: '已结清',
  received: '已收货',
  open: '未结清',
  settled: '已结清',
  partial: '部分'
}

export function statusLabel(v) {
  return STATUS_LABELS[v] || v || '—'
}

export function statusTagType(v) {
  return STATUS_TAGS[v] || 'info'
}

export function moneySum(items, key = 'amount') {
  return (items || []).reduce((s, it) => s + Number(it[key] || 0), 0)
}