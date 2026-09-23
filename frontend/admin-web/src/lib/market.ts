/**
 * 应用市场（开发者侧）共享工具：金额换算、状态文案、错误提取。
 * 金额一律以「分」与后端交互，展示时转「元」。
 */

export interface Wallet {
  developer_id: number | null
  available_cents: number
  pending_cents: number
  frozen_cents: number
  total_cents: number
  available: string
  pending: string
  frozen: string
  total: string
  total_income_cents: number
  total_withdrawn_cents: number
  total_refunded_cents: number
  total_income: string
  total_withdrawn: string
  total_refunded: string
}

export interface Pricing {
  app_key: string
  model: string
  price_cents: number
  seat_price_cents: number
  currency: string
  period_days: number
  trial_days: number
  min_seats: number
  max_seats: number
  require_approval: boolean
  enabled: boolean
  intro: string | null
  price: string
  seat_price: string
  developer_id: number | null
  platform_fee_bp: number | null
  listed: boolean
  effective_fee_bp?: number
  updated_at?: string
}

export interface MyApp {
  app_key: string
  name: string
  version: string
  category: string
  submission_status: string
  submission_id: number
  installed: boolean
  pricing: Pricing
  order_count: number
  gross_cents: number
  income_cents: number
  gross: string
  income: string
}

/** 计费模式文案 */
export const MODEL_LABEL: Record<string, string> = {
  free: '免费',
  one_time: '一次性买断',
  subscription: '按期订阅',
  seat: '按席位',
}

export const MODEL_CLASS: Record<string, string> = {
  free: 'bg-ink-100 text-ink-600',
  one_time: 'bg-blue-50 text-blue-600',
  subscription: 'bg-violet-50 text-violet-600',
  seat: 'bg-emerald-50 text-emerald-600',
}

/** 提交审核状态 */
export const SUB_LABEL: Record<string, string> = {
  pending: '待审核',
  approved: '已通过',
  rejected: '已拒绝',
  installed: '已安装',
}

export const SUB_CLASS: Record<string, string> = {
  pending: 'bg-amber-50 text-amber-600',
  approved: 'bg-blue-50 text-blue-600',
  rejected: 'bg-red-50 text-red-600',
  installed: 'bg-emerald-50 text-emerald-600',
}

/** 提现单状态 */
export const WD_LABEL: Record<string, string> = {
  pending: '待审核',
  approved: '待打款',
  rejected: '已驳回',
  paid: '已打款',
}

export const WD_CLASS: Record<string, string> = {
  pending: 'bg-amber-50 text-amber-600',
  approved: 'bg-blue-50 text-blue-600',
  rejected: 'bg-red-50 text-red-600',
  paid: 'bg-emerald-50 text-emerald-600',
}

/** 结算状态 */
export const SETTLE_LABEL: Record<string, string> = {
  none: '—',
  pending: '结算中',
  settled: '已可提',
  refunded: '已冲正',
}

/** 订单状态 */
export const ORDER_LABEL: Record<string, string> = {
  pending: '待支付',
  paid: '已支付',
  cancelled: '已取消',
  refunded: '已退款',
  expired: '已过期',
}

export const ORDER_CLASS: Record<string, string> = {
  pending: 'bg-amber-50 text-amber-600',
  paid: 'bg-emerald-50 text-emerald-600',
  cancelled: 'bg-ink-100 text-ink-500',
  refunded: 'bg-red-50 text-red-600',
  expired: 'bg-ink-100 text-ink-500',
}

export const ACCOUNT_LABEL: Record<string, string> = {
  alipay: '支付宝',
  wechat: '微信',
  bank: '银行账户',
}

export const POOL_LABEL: Record<string, string> = {
  available: '可提现',
  pending: '待结算',
  frozen: '提现中',
}

/** 分 → 元字符串（两位小数，不带符号） */
export function centsToYuan(cents: number | null | undefined): string {
  return ((Number(cents) || 0) / 100).toFixed(2)
}

/** 分 → 元字符串（带 ¥ 前缀） */
export function yuan(cents: number | null | undefined): string {
  return '¥' + centsToYuan(cents)
}

/** 元输入 → 分（四舍五入，负数归零） */
export function toCents(v: string | number | null | undefined): number {
  const n = typeof v === 'number' ? v : parseFloat(String(v ?? '').replace(/[^\d.-]/g, ''))
  if (!isFinite(n)) return 0
  return Math.max(0, Math.round(n * 100))
}

/** 万元比 → 百分比展示，如 2000 → "20.00" */
export function bpToPercent(bp: number | null | undefined): string {
  return ((Number(bp) || 0) / 100).toFixed(2)
}

/** 时间戳 → YYYY-MM-DD HH:mm */
export function fmtTime(v: string | null | undefined): string {
  if (!v) return '—'
  const d = new Date(v)
  if (isNaN(d.getTime())) return String(v)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

/** 时间戳 → YYYY-MM-DD */
export function fmtDate(v: string | null | undefined): string {
  if (!v) return '—'
  const d = new Date(v)
  if (isNaN(d.getTime())) return String(v)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/** 统一提取后端错误文案（FastAPI detail 可能是字符串或校验数组） */
export function errText(e: any): string {
  const d = e?.response?.data?.detail
  if (Array.isArray(d)) return d.map((x: any) => x?.msg || JSON.stringify(x)).join('; ')
  if (typeof d === 'string') return d
  return e?.message || '操作失败，请稍后重试'
}
