// 产品类型（product slug）单一真相源：值必须与后端 store_router.ALLOWED_PRODUCTS 完全一致。
// product 只表示「归属哪个产品 / 分发隔离」；「交付安装目标」由 dev_method 表达。
export const PRODUCT_KEYS = ['cenkor-admin', 'cenkormes', 'lightmes', 'cenkor-process'] as const
export type ProductKey = (typeof PRODUCT_KEYS)[number]

export const PRODUCT_LABELS: Record<string, string> = {
  'cenkor-admin': 'Cenkor 平台',
  cenkormes: 'CenkorMES',
  lightmes: 'LightMES',
  'cenkor-process': 'CenkorProcess',
}

export function productLabel(p?: string | null): string {
  if (!p) return ''
  return PRODUCT_LABELS[p] || p
}

// 应用开发方式（交付安装目标）：与后端 store_router.DEV_METHODS 对齐。
export const DEV_METHOD_LABELS: Record<string, string> = {
  platform: '平台内置',
  extension: '产品扩展',
  standalone: '独立应用',
}

export function devMethodLabel(m?: string | null): string {
  if (!m) return ''
  return DEV_METHOD_LABELS[m] || m
}
