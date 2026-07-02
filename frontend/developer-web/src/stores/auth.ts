import { defineStore } from 'pinia'

interface UserBrief {
  id: number
  username: string
  email: string | null
  nickname: string
  avatar: string | null
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('portal_token') || '',
    refreshToken: localStorage.getItem('portal_refresh') || '',
    user: JSON.parse(localStorage.getItem('portal_user') || 'null') as UserBrief | null,
  }),
  getters: {
    isAuthed: (s) => !!s.token,
  },
  actions: {
    setSession(token: string, refreshToken: string, user: UserBrief) {
      this.token = token
      this.refreshToken = refreshToken
      this.user = user
      localStorage.setItem('portal_token', token)
      localStorage.setItem('portal_refresh', refreshToken)
      localStorage.setItem('portal_user', JSON.stringify(user))
    },
    logout() {
      this.token = ''
      this.refreshToken = ''
      this.user = null
      localStorage.removeItem('portal_token')
      localStorage.removeItem('portal_refresh')
      localStorage.removeItem('portal_user')
    },
  },
})
