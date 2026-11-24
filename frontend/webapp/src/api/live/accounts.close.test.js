import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiRequest = vi.fn()
const clearAccessToken = vi.fn()

vi.mock('../http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, apiRequest: (...args) => apiRequest(...args) }
})

vi.mock('@/auth/tokenStore', () => ({
  clearAccessToken: () => clearAccessToken(),
  setAccessToken: vi.fn(),
  getAccessToken: vi.fn(),
}))

describe('closeAccount', () => {
  beforeEach(() => {
    apiRequest.mockReset()
    clearAccessToken.mockClear()
  })

  it('posts password only and handles 204', async () => {
    apiRequest.mockResolvedValue(undefined)
    const { closeAccount } = await import('./accounts')
    const result = await closeAccount({ password: 'secret123' })
    expect(apiRequest).toHaveBeenCalledWith('post', '/api/me/close/', { data: { password: 'secret123' } })
    expect(clearAccessToken).toHaveBeenCalledTimes(1)
    expect(result).toEqual({ closed: true })
  })

  it('maps duplicate-style api errors without user id in body', async () => {
    const { ApiError } = await import('../http')
    apiRequest.mockRejectedValue(new ApiError('wrong', { code: 'invalid_password', status: 400 }))
    const { closeAccount } = await import('./accounts')
    await expect(closeAccount({ password: 'bad' })).rejects.toMatchObject({
      code: 'invalid_password',
      message: 'The password you entered is incorrect.',
    })
    expect(clearAccessToken).not.toHaveBeenCalled()
  })
})