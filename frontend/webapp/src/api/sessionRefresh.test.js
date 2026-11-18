import { beforeEach, describe, expect, it, vi } from 'vitest'

import { resetRefreshQueue } from './refreshQueue'

const axiosState = vi.hoisted(() => ({
  post: vi.fn(),
}))

vi.mock('axios', () => ({
  default: {
    post: (...args) => axiosState.post(...args),
  },
}))

vi.mock('@/auth/tokenStore', () => ({
  setAccessToken: vi.fn(),
}))

describe('refreshAccessCoalesced', () => {
  beforeEach(() => {
    vi.resetModules()
    resetRefreshQueue()
    axiosState.post.mockReset()
  })

  it('issues one POST when two callers refresh at once', async () => {
    let resolvePost
    axiosState.post.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePost = () => resolve({ data: { access: 'tok' } })
        }),
    )

    const { refreshAccessCoalesced } = await import('./sessionRefresh')
    const a = refreshAccessCoalesced()
    const b = refreshAccessCoalesced()

    expect(axiosState.post).toHaveBeenCalledTimes(1)
    expect(axiosState.post.mock.calls[0][0]).toBe('/api/auth/refresh/')

    resolvePost()
    await expect(Promise.all([a, b])).resolves.toEqual(['tok', 'tok'])
  })
})