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
  /** 原价（划线价），仅展示，不参与结算 */
  list_price_cents: number
  /** 售价（常规成交价） */
  price_cents: number
  /** 限时促销价，0 = 无促销 */
  promo_price_cents: number
  promo_label: string | null
  promo_start_at: string | null
  promo_end_at: string | null
  seat_price_cents: number
  currency: string
  /** 授权周期，仅「按席位」模式生效；买断永久有效 */
  period_days: number
  min_seats: number
  max_seats: number
  require_approval: boolean
  enabled: boolean
  intro: string | null
  list_price: string
  price: string
  promo_price: string
  seat_price: string
  seat_list_price_cents: number
  seat_list_price: string
  /** 当前生效成交单价（促销期内即促销价） */
  unit_price_cents: number
  unit_price: string
  /** none / scheduled / active / expired */
  promo_state: string
  promo_active: boolean
  is_discounted: boolean
  discount_percent: number | null
  discount_label: string | null
  developer_id: number | null
  platform_fee_bp: number | null
  listed: boolean
  /** 平台自营（developer_id 为 0/1 或为空）：收入全额归平台，不产生开发者收入 */
  owner_self_operated?: boolean
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
  seat: '按席位',
}

export const MODEL_CLASS: Record<string, string> = {
  free: 'bg-ink-100 text-ink-600',
  one_time: 'bg-blue-50 text-blue-600',
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

// ============================================================
// 定价表单（原价 / 售价 / 限时促销）—— 提交应用页与定价弹层共用
// ============================================================

/** 促销状态 */
export const PROMO_STATE_LABEL: Record<string, string> = {
  none: '无促销',
  scheduled: '未开始',
  active: '促销中',
  expired: '已结束',
}

export const PROMO_STATE_CLASS: Record<string, string> = {
  none: 'bg-ink-100 text-ink-500',
  scheduled: 'bg-blue-50 text-blue-600',
  active: 'bg-red-50 text-red-600',
  expired: 'bg-ink-100 text-ink-500',
}

export interface PriceForm {
  model: string
  /** 以下价格字段都是「元」字符串，提交前用 toCents 转分 */
  list_price: string
  /**
   * 售价。座位模式下即「每席位售价」—— 后端 seat_price_cents 与 price_cents 取同值，
   * 座位价的原价/促销比例换算因此退化为 1:1，展示与计费天然一致。
   */
  price: string
  promo_price: string
  promo_label: string
  /** datetime-local 值，如 2026-10-01T00:00；空字符串 = 不限制 */
  promo_start: string
  promo_end: string
  /** 授权周期，仅「按席位」模式生效；买断永久有效 */
  period_days: number
  min_seats: number
  max_seats: number
  require_approval: boolean
  enabled: boolean
  intro: string
}

export function emptyPriceForm(): PriceForm {
  return {
    model: 'free',
    list_price: '',
    price: '',
    promo_price: '',
    promo_label: '',
    promo_start: '',
    promo_end: '',
    period_days: 365,
    min_seats: 1,
    max_seats: 0,
    require_approval: false,
    enabled: true,
    intro: '',
  }
}

/** 从接口返回的定价回填表单（提交页与定价弹层共用，保证两处口径一致） */
export function priceFormFrom(p: Partial<Pricing> | null | undefined): PriceForm {
  const f = emptyPriceForm()
  if (!p) return f
  const cents = (v: any) => (Number(v) > 0 ? centsToYuan(Number(v)) : '')
  const model = p.model || 'free'
  f.model = model
  f.list_price = cents(p.list_price_cents)
  // 座位价优先按每席位价回填，避免「历史数据里 price 与 seat_price 不一致」被静默改写
  f.price = model === 'seat' && Number(p.seat_price_cents) > 0
    ? cents(p.seat_price_cents)
    : cents(p.price_cents)
  f.promo_price = cents(p.promo_price_cents)
  f.promo_label = p.promo_label || ''
  f.promo_start = isoToLocal(p.promo_start_at)
  f.promo_end = isoToLocal(p.promo_end_at)
  f.period_days = p.period_days ?? 365
  f.min_seats = p.min_seats ?? 1
  f.max_seats = p.max_seats ?? 0
  f.require_approval = !!p.require_approval
  f.enabled = p.enabled !== false
  f.intro = p.intro || ''
  return f
}

/** 表单 → 后端 payload（金额转分；免费模式不发价格字段，由后端归零） */
export function priceFormToPayload(f: PriceForm): Record<string, any> {
  if (f.model === 'free') {
    return { model: 'free' }
  }
  const price = toCents(f.price)
  return {
    model: f.model,
    list_price_cents: toCents(f.list_price),
    price_cents: price,
    promo_price_cents: toCents(f.promo_price),
    promo_label: f.promo_label.trim() || null,
    promo_start_at: localToIso(f.promo_start),
    promo_end_at: localToIso(f.promo_end),
    // 座位制：每席位价与主售价同值
    seat_price_cents: price,
    period_days: Number(f.period_days) || 365,
    min_seats: Number(f.min_seats) || 1,
    max_seats: Number(f.max_seats) || 0,
    require_approval: !!f.require_approval,
    enabled: !!f.enabled,
    intro: f.intro.trim() || null,
  }
}

/** 与后端 pricing_rules 同规则的本地校验，命中即返回错误文案，通过返回 '' */
export function validatePriceForm(f: PriceForm): string {
  if (f.model === 'free') return ''
  const price = toCents(f.price)
  const list = toCents(f.list_price)
  const promo = toCents(f.promo_price)

  if (price <= 0) return '售价必须大于 0（免费应用请把计费模式选为「免费」）'
  if (list && list < price) return '原价不能低于售价（原价是划线价）'
  if (promo) {
    if (promo >= price) return '促销价必须低于售价（否则不是促销）'
    const s = localToIso(f.promo_start)
    const e = localToIso(f.promo_end)
    if (s && e && new Date(e) <= new Date(s)) return '促销结束时间必须晚于开始时间'
  }
  if ((f.promo_label || '').trim().length > 60) return '促销活动名最长 60 个字'
  return ''
}

/** 折扣预览：返回生效价、折扣率与标签（口径与后端一致，向下取一位不虚报） */
export function previewDiscount(f: PriceForm): {
  /** 原价（座位制即每席位原价） */
  unitList: number
  /** 当前生效成交价（座位制即每席位价） */
  unit: number
  price: number
  promo: number
  percent: number | null
  label: string | null
  /** none / scheduled / active / expired */
  state: string
} {
  const price = toCents(f.price)
  const unitList = toCents(f.list_price)
  const promo = toCents(f.promo_price)

  let state = 'none'
  if (f.model !== 'free' && promo > 0 && promo < price) {
    const s = localToIso(f.promo_start)
    const e = localToIso(f.promo_end)
    const now = Date.now()
    if (s && now < new Date(s).getTime()) state = 'scheduled'
    else if (e && now >= new Date(e).getTime()) state = 'expired'
    else state = 'active'
  }
  const unit = state === 'active' ? promo : price

  let percent: number | null = null
  let label: string | null = null
  if (unitList > 0 && unit > 0 && unit < unitList) {
    percent = Math.round((unit / unitList) * 1000) / 10
    const zhe = Math.floor((percent / 10) * 10 + 1e-9) / 10
    if (zhe < 10) label = `${String(zhe.toFixed(1)).replace(/\.0$/, '')}折`
  }
  return { unitList, unit, price, promo, percent, label, state }
}

/** datetime-local 值（本地时间）→ ISO 8601 UTC 字符串；空值返回 null */
export function localToIso(v: string | null | undefined): string | null {
  const s = (v || '').trim()
  if (!s) return null
  const d = new Date(s)
  if (isNaN(d.getTime())) return null
  return d.toISOString()
}

/** ISO 字符串 → datetime-local 值（本地时间，YYYY-MM-DDTHH:mm） */
export function isoToLocal(v: string | null | undefined): string {
  if (!v) return ''
  const d = new Date(v)
  if (isNaN(d.getTime())) return ''
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
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
