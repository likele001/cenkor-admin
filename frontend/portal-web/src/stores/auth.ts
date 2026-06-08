import { defineStore } from 'pinia'

interface UserBrief {
  id: number
  username: string
  email: string
  nickname: string
  avatar: string | null
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('portal_token') || '',
    user: JSON.parse(localStorage.getItem('portal_user') || 'null') as UserBrief | null,
  }),
  getters: {
    isAuthed: (s) => !!s.token,
  },
  actions: {
    setSession(token: string, user: UserBrief) {
      this.token = token
      this.user = user
      localStorage.setItem('portal_token', token)
      localStorage.setItem('portal_user', JSON.stringify(user))
    },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('portal_token')
      localStorage.removeItem('portal_user')
    },
  },
})
