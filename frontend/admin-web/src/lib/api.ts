import axios, { type InternalAxiosRequestConfig } from 'axios'
import { useAuthStore } from '@/stores/auth'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 15_000,
})

type RetryConfig = InternalAxiosRequestConfig & { _retry?: boolean }

let refreshPromise: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  const auth = useAuthStore()
  if (!auth.refreshToken) return null

  if (!refreshPromise) {
    refreshPromise = api
      .post('/api/v1/auth/refresh', { refresh_token: auth.refreshToken })
      .then((res) => {
        auth.setToken(res.data.access_token, res.data.user)
        auth.setRefresh(res.data.refresh_token)
        return res.data.access_token as string
      })
      .catch(() => null)
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

api.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
})

api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const status = err.response?.status
    const config = err.config as RetryConfig | undefined
    if (status !== 401 || !config || config._retry) {
      return Promise.reject(err)
    }

    const url = config.url || ''
    if (url.includes('/auth/login') || url.includes('/auth/refresh')) {
      useAuthStore().logout()
      if (!location.pathname.startsWith('/login')) {
        location.href = '/login'
      }
      return Promise.reject(err)
    }

    config._retry = true
    const newToken = await refreshAccessToken()
    if (newToken) {
      config.headers.Authorization = `Bearer ${newToken}`
      return api(config)
    }

    useAuthStore().logout()
    if (!location.pathname.startsWith('/login')) {
      location.href = '/login'
    }
    return Promise.reject(err)
  },
)
