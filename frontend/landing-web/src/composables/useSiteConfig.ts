import { ref } from 'vue'

interface SiteContact {
  wechat: string
  phone: string
  email: string
  bdEmail: string
  supportEmail: string
}

const contact = ref<SiteContact>({
  wechat: '',
  phone: '',
  email: 'contact@cenkor.cn',
  bdEmail: 'bd@cenkor.cn',
  supportEmail: 'support@cenkor.cn',
})
let loaded = false

// 必须走同域相对路径：landing 与后台同挂在 admin.cenkor.cn 下，/api/ 已由 nginx 反代到后端（127.0.0.1:8002）。
// 原先写死 https://www.cenkor.cn/api/... 属跨域请求，而该接口响应不带 Access-Control-Allow-Origin
// → 微信/电话在页脚永不显示（浏览器静默拦截），只有 email 的硬编码默认值能出来。
const PUBLIC_SITE_API = '/api/v1/public/site'

export function useSiteConfig() {
  async function fetchContact() {
    if (loaded) return contact.value
    loaded = true
    try {
      const res = await fetch(PUBLIC_SITE_API, { method: 'GET' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      const cfg = json?.site_config ?? {}
      contact.value = {
        wechat: cfg['contact.wechat'] ?? '',
        phone: cfg['contact.phone'] ?? '',
        email: cfg['contact.email'] ?? 'contact@cenkor.cn',
        bdEmail: cfg['contact.bd_email'] ?? 'bd@cenkor.cn',
        supportEmail: cfg['contact.support_email'] ?? 'support@cenkor.cn',
      }
    } catch {
      loaded = false
    }
    return contact.value
  }

  return { contact, fetchContact }
}
