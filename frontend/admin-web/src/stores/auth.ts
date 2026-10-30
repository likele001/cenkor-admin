import { defineStore } from 'pinia'

interface UserBrief {
  id: number
  username: string
  email: string
  nickname: string
  is_superuser: boolean
  permissions: string[]
  menus: Array<{ id: number; key: string; title: string; path: string | null; parent_id: number | null; icon: string | null }>
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('cenkor_token') || '',
    refreshToken: localStorage.getItem('cenkor_refresh') || '',
    user: JSON.parse(localStorage.getItem('cenkor_user') || 'null') as UserBrief | null,
  }),
  getters: {
    isAuthed: (s) => !!s.token,
    isSuper: (s) => !!s.user?.is_superuser,
    permissions: (s) => s.user?.permissions ?? [],
  },
  actions: {
    setToken(token: string, user: UserBrief) {
      this.token = token
      this.user = user
      localStorage.setItem('cenkor_token', token)
      localStorage.setItem('cenkor_user', JSON.stringify(user))
    },
    setRefresh(refreshToken: string) {
      this.refreshToken = refreshToken
      localStorage.setItem('cenkor_refresh', refreshToken)
    },
    /** 仅有 token 但本地 user 丢失时（清缓存/换设备），补拉一次身份，避免误判无权限 */
    async fetchMe(): Promise<boolean> {
      try {
        const { api } = await import('@/lib/api')
        const { data } = await api.get('/api/v1/auth/me')
        this.user = data as UserBrief
        localStorage.setItem('cenkor_user', JSON.stringify(data))
        return true
      } catch {
        return false
      }
    },
    hasPermission(code: string): boolean {
      if (this.isSuper) return true
      if (!this.user) return false
      // 支持通配符：cms:* 匹配 cms:product:read 等
      return this.permissions.some(p =>
        p === code ||
        (p.endsWith(':*') && code.startsWith(p.slice(0, -1)))
      )
    },
    logout() {
      this.token = ''
      this.refreshToken = ''
      this.user = null
      localStorage.removeItem('cenkor_token')
      localStorage.removeItem('cenkor_refresh')
      localStorage.removeItem('cenkor_user')
    },
  },
})
