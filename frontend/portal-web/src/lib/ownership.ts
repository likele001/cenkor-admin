/**
 * 当前登录账号在官方门户的「已购应用」集合。
 *
 * 数据源 `GET /store/account/purchases`（后端按门户登录态过滤，客户端不做任何兜底推断）。
 * 采用模块级缓存：应用中心与详情页共用同一次请求 —— 同一账号在本次会话内只拉一次。
 *
 * 降级策略：未登录、或接口不可用（如后端尚未部署该路由）时一律视为「无已购」，
 * 页面回落到未购买时的表现，绝不阻塞商城浏览。
 */
import { ref } from 'vue'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

const ownedKeys = ref<string[]>([])
const loading = ref(false)
/** 已成功加载过数据的账号 id；用于判断是否需要重新请求 */
let loadedFor = ''

export function useOwnedApps() {
  const auth = useAuthStore()

  function currentUser(): string {
    return auth.isAuthed ? String(auth.user?.id ?? '') : ''
  }

  /** 拉取已购集合；`force` 用于「我的应用」页操作后强制刷新。 */
  async function load(force = false): Promise<void> {
    const who = currentUser()
    if (!who) {
      ownedKeys.value = []
      loadedFor = ''
      return
    }
    if (!force && loadedFor === who) return

    loading.value = true
    try {
      const { data } = await api.get('/api/v1/store/account/purchases')
      const items: any[] = Array.isArray(data?.items) ? data.items : []
      ownedKeys.value = items.map((i) => i?.app_key).filter((k): k is string => !!k)
      loadedFor = who
    } catch {
      ownedKeys.value = []
      loadedFor = ''
    } finally {
      loading.value = false
    }
  }

  function isOwned(appKey?: string | null): boolean {
    return !!appKey && ownedKeys.value.includes(appKey)
  }

  return { ownedKeys, loading, load, isOwned }
}
