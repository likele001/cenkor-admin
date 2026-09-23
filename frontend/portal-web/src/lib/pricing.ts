/**
 * 门户（portal-web）侧的定价展示工具。
 *
 * 与 developer-web / admin-web 的 `market.ts` 定位不同：门户只需要「展示」能力
 * （金额格式化、折扣标签、促销状态与倒计时），不需要编辑表单与写入逻辑。
 *
 * 字段口径与后端 `apps/commerce/pricing.py` 的 `PUBLIC_PRICE_FIELDS` 白名单一一对应 ——
 * 那里是买家可见字段的唯一真相源，**不含** developer_id / 平台扣点等经营数据。
 */

/** 销售模式（2026-09-23 收敛：试用与订阅已下线） */
export type PricingModel = 'free' | 'one_time' | 'seat'

/** 促销状态机 */
export type PromoState = 'none' | 'scheduled' | 'active' | 'expired'

/** 后端公开接口返回的价格视图。接口返回 `null` 表示「免费 / 未定价」。 */
export interface AppPrice {
  app_key: string
  model: PricingModel
  currency: string
  /** 定价行是否上架；false 时能看不能买 */
  enabled: boolean
  intro?: string | null
  list_price_cents: number
  price_cents: number
  promo_price_cents: number
  seat_price_cents: number
  list_price: string
  price: string
  promo_price: string
  seat_price: string
  seat_list_price_cents: number
  seat_list_price: string
  /** 生效价（下单口径）：促销期内为促销价，否则为售价 */
  unit_price_cents: number
  unit_price: string
  promo_state: PromoState
  promo_active: boolean
  promo_label?: string | null
  promo_start_at?: string | null
  promo_end_at?: string | null
  is_discounted: boolean
  discount_percent?: number | null
  discount_label?: string | null
  /** 授权周期（仅「按席位」有意义；买断为永久） */
  period_days: number
  min_seats: number
  max_seats: number
}

/**
 * 是否免费 / 未定价。
 *
 * 后端把「没有定价行」与「model=free」都视作免费（见 create_order 的 model 兜底），
 * 门户据此统一显示「免费」—— 这是产品决策，不是技术推断。
 */
export function isFreePrice(p: AppPrice | null | undefined): boolean {
  return !p || p.model === 'free' || !p.price_cents
}

/**
 * 后端是否提供了价格信息。
 *
 * 两种情况下后端**不会**返回 `price` 字段（取值 `undefined`，与「免费」的 `null` 语义不同）：
 * 1. 纯开源部署未安装 commerce 应用（商店接口静默降级）；
 * 2. 后端尚未升级到含价格桥的版本。
 *
 * 此时门户**什么都不显示** —— 绝不能当成「免费」，否则会把付费应用误导成免费。
 */
export function hasPriceInfo(p: AppPrice | null | undefined): boolean {
  return p !== undefined
}

/** 是否可购买：免费即可买；付费需定价行处于上架状态 */
export function isPurchasable(p: AppPrice | null | undefined): boolean {
  if (isFreePrice(p)) return true
  return p!.enabled !== false
}

/**
 * 金额展示：整数不带小数，非整数保留两位（`29.00` → `29`，`29.5` → `29.50`）。
 *
 * 中文电商习惯用整数价，而后端返回的是 `toFixed(2)` 字符串，故在此收口。
 */
export function yuanText(v: string | number | null | undefined): string {
  const n = Number(v ?? 0)
  if (Number.isNaN(n)) return '0'
  return n % 1 === 0 ? String(n) : n.toFixed(2)
}

const PROMO_STATE_LABEL: Record<PromoState, string> = {
  none: '',
  scheduled: '即将开始',
  active: '促销中',
  expired: '已结束',
}

export function promoStateLabel(state?: string | null): string {
  return PROMO_STATE_LABEL[(state || 'none') as PromoState] || ''
}

/**
 * 促销剩余时间文案（供倒计时展示）。
 *
 * Args:
 *   endIso: 促销结束时间（ISO 8601，UTC）
 *   now: 当前时间戳，由调用方传入以便随定时器刷新
 *
 * Returns:
 *   形如「3 天 12 小时」；已结束或时间非法时返回 `null`。
 */
export function promoRemaining(endIso?: string | null, now: number = Date.now()): string | null {
  if (!endIso) return null
  const end = new Date(endIso).getTime()
  if (Number.isNaN(end) || end <= now) return null
  const diff = end - now
  const minute = 60_000
  const hour = 60 * minute
  const day = 24 * hour
  if (diff >= day) return `${Math.floor(diff / day)} 天 ${Math.floor((diff % day) / hour)} 小时`
  if (diff >= hour) return `${Math.floor(diff / hour)} 小时 ${Math.floor((diff % hour) / minute)} 分钟`
  return `${Math.max(1, Math.floor(diff / minute))} 分钟`
}
