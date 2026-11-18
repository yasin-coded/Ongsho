import axios from 'axios'

import { setAccessToken } from '@/auth/tokenStore'

import { onceRefresh } from './refreshQueue'

/** Same-origin `/api` when `VITE_API_URL` is empty; absolute override for tests only. */
export function apiBaseUrl() {
  const fromEnv = import.meta.env.VITE_API_URL
  if (fromEnv === '' || fromEnv == null) return ''
  return String(fromEnv).replace(/\/$/, '')
}

async function postRefresh() {
  const base = apiBaseUrl()
  const { data } = await axios.post(
    `${base}/api/auth/refresh/`,
    {},
    { withCredentials: true, headers: { 'X-Requested-With': 'Ongsho' } },
  )
  setAccessToken(data.access)
  return data.access
}

/** One in-flight POST /api/auth/refresh/ for bootstrap, StrictMode, and 401 replay. */
export function refreshAccessCoalesced() {
  return onceRefresh(() => postRefresh())
}