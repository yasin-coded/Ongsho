import axios from 'axios'
import { clearAccessToken, getAccessToken, setAccessToken } from '@/auth/tokenStore'
import { ApiError, normalizeApiError } from './errors'

const baseURL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

import { onceRefresh } from './refreshQueue'
let onUnauthorized = null
let onRateLimited = null
let onServerError = null

export function configureHttp({ onAuthFailure, onToast429, onToast5xx }) {
  onUnauthorized = onAuthFailure
  onRateLimited = onToast429
  onServerError = onToast5xx
}

export const http = axios.create({
  baseURL,
  withCredentials: true,
  headers: { 'X-Requested-With': 'Ongsho' },
})

http.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

async function refreshAccess() {
  const { data } = await axios.post(
    `${baseURL}/api/auth/refresh/`,
    {},
    { withCredentials: true, headers: { 'X-Requested-With': 'Ongsho' } },
  )
  setAccessToken(data.access)
  return data.access
}

function isAuthExempt(config) {
  const url = config?.url ?? ''
  return url.includes('/api/auth/login') || url.includes('/api/auth/refresh')
}

http.interceptors.response.use(
  (res) => res,
  async (error) => {
    const config = error.config
    const status = error.response?.status

    if (status === 429 && onRateLimited) {
      const retry = error.response?.headers?.['retry-after']
      onRateLimited(retry ? Number(retry) : null)
    } else if (status >= 500 && onServerError) {
      onServerError()
    }

    if (!config || config._retry || status !== 401 || isAuthExempt(config)) {
      throw normalizeApiError(error)
    }

    try {
      await onceRefresh(() =>
        refreshAccess().catch((refreshErr) => {
          clearAccessToken()
          onUnauthorized?.(refreshErr)
          throw normalizeApiError(refreshErr)
        }),
      )
    } catch (e) {
      throw e instanceof ApiError ? e : normalizeApiError(e)
    }

    config._retry = true
    config.headers.Authorization = `Bearer ${getAccessToken()}`
    try {
      return await http.request(config)
    } catch (replayErr) {
      throw normalizeApiError(replayErr)
    }
  },
)

export async function apiRequest(method, url, { data, params, ...rest } = {}) {
  try {
    const res = await http.request({ method, url, data, params, ...rest })
    return res.data
  } catch (err) {
    throw err instanceof ApiError ? err : normalizeApiError(err)
  }
}

async function blobErrorToJson(err) {
  const blob = err?.response?.data
  if (!(blob instanceof Blob)) return err
  try {
    const text = await blob.text()
    const json = JSON.parse(text)
    if (err.response) err.response.data = json
  } catch {
    /* keep blob body */
  }
  return err
}

/** GET a PDF (or other binary) and save it in the browser. */
export async function downloadFile(url, { params } = {}) {
  try {
    const res = await http.get(url, { params, responseType: 'blob' })
    const disposition = res.headers['content-disposition'] ?? ''
    const nameMatch = disposition.match(/filename="([^"]+)"/i)
    const filename = nameMatch?.[1] ?? 'ongsho-statement.pdf'
    const number = res.headers['x-statement-number'] ?? ''
    const href = URL.createObjectURL(res.data)
    const link = document.createElement('a')
    link.href = href
    link.download = filename
    link.rel = 'noopener'
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(href)
    return { number: number || filename.replace(/^ongsho-statement-|\.pdf$/gi, '') }
  } catch (err) {
    throw normalizeApiError(await blobErrorToJson(err))
  }
}

export { ApiError }
