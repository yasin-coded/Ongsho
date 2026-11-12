import { beforeEach, describe, expect, it, vi } from 'vitest'
import { resetRefreshQueue } from './refreshQueue'

const axiosState = vi.hoisted(() => ({
  onRejected: null,
  instanceRequest: vi.fn(),
  axiosPost: vi.fn(),
}))

vi.mock('axios', () => {
  const instance = {
    interceptors: {
      request: { use: () => {} },
      response: { use: (_ok, onRejected) => {
        axiosState.onRejected = onRejected
      } },
    },
    request: (...args) => axiosState.instanceRequest(...args),
  }
  return {
    default: {
      create: () => instance,
      post: (...args) => axiosState.axiosPost(...args),
    },
  }
})

const tokenState = vi.hoisted(() => ({
  token: 'access-old',
  cleared: false,
  set: vi.fn((t) => {
    tokenState.token = t
  }),
  clear: vi.fn(() => {
    tokenState.cleared = true
    tokenState.token = null
  }),
  get: vi.fn(() => tokenState.token),
}))

vi.mock('@/auth/tokenStore', () => ({
  getAccessToken: () => tokenState.get(),
  setAccessToken: (t) => tokenState.set(t),
  clearAccessToken: () => tokenState.clear(),
}))

describe('http 401 refresh interceptor', () => {
  beforeEach(async () => {
    vi.resetModules()
    resetRefreshQueue()
    tokenState.token = 'access-old'
    tokenState.cleared = false
    tokenState.get.mockClear()
    tokenState.set.mockClear()
    tokenState.clear.mockClear()
    axiosState.instanceRequest.mockReset()
    axiosState.axiosPost.mockReset()
    axiosState.onRejected = null
    await import('./http.js')
  })

  it('refreshes once and replays the request', async () => {
    axiosState.axiosPost.mockResolvedValueOnce({ data: { access: 'access-new' } })
    axiosState.instanceRequest.mockResolvedValueOnce({ data: { ok: true } })

    const err = { config: { url: '/api/me/', headers: {} }, response: { status: 401 } }
    const out = await axiosState.onRejected(err)

    expect(axiosState.axiosPost).toHaveBeenCalledTimes(1)
    expect(axiosState.instanceRequest).toHaveBeenCalledTimes(1)
    expect(axiosState.instanceRequest.mock.calls[0][0]._retry).toBe(true)
    expect(tokenState.set).toHaveBeenCalledWith('access-new')
    expect(out.data.ok).toBe(true)
  })

  it('coalesces concurrent 401 refresh calls', async () => {
    let resolveRefresh
    axiosState.axiosPost.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveRefresh = () => resolve({ data: { access: 'access-new' } })
        }),
    )
    axiosState.instanceRequest.mockResolvedValue({ data: { ok: 1 } })

    const err = { config: { url: '/api/plans/', headers: {} }, response: { status: 401 } }
    const p1 = axiosState.onRejected(err)
    const p2 = axiosState.onRejected({ ...err, config: { url: '/api/calendar/', headers: {} } })

    expect(axiosState.axiosPost).toHaveBeenCalledTimes(1)
    resolveRefresh()
    await Promise.all([p1, p2])
    expect(axiosState.instanceRequest).toHaveBeenCalledTimes(2)
  })

  it('clears session when refresh fails', async () => {
    const onAuthFailure = vi.fn()
    const { configureHttp } = await import('./http.js')
    configureHttp({ onAuthFailure, onToast429: null, onToast5xx: null })

    axiosState.axiosPost.mockRejectedValueOnce({ response: { status: 401 } })

    const err = { config: { url: '/api/me/', headers: {} }, response: { status: 401 } }
    await expect(axiosState.onRejected(err)).rejects.toBeTruthy()

    expect(tokenState.clear).toHaveBeenCalled()
    expect(onAuthFailure).toHaveBeenCalled()
  })
})
