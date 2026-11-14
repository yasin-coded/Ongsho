import { http } from '@/api/http'

/** Dev-only: delay live API responses (VITE_DEBUG_DELAY_MS). Does not modify mock reads. */
export function installLiveDelay() {
  const ms = Number(import.meta.env.VITE_DEBUG_DELAY_MS) || 0
  if (!import.meta.env.DEV || ms <= 0) return
  http.interceptors.response.use(async (res) => {
    await new Promise((r) => setTimeout(r, ms))
    return res
  })
}
