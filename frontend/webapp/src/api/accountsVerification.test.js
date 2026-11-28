import { describe, expect, it, vi } from 'vitest'
import * as mock from './mock/accounts'
import * as live from './live/accounts'
import { db, ME } from '@/mocks/db'

const apiRequest = vi.fn()

vi.mock('./http', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, apiRequest: (...args) => apiRequest(...args) }
})

const me = () => db.users.find((u) => u.id === ME)

describe('live verification calls', () => {
  it('rejects a missing token without contacting the server', async () => {
    await expect(live.verifyEmail({})).rejects.toMatchObject({ code: 'invalid_token' })
    await expect(live.verifyEmailChange({})).rejects.toMatchObject({ code: 'invalid_token' })
    expect(apiRequest).not.toHaveBeenCalled()
  })

  it('sends each journey to its own endpoint', async () => {
    apiRequest.mockResolvedValue({ email: 'new@example.com' })
    await live.verifyEmail({ token: 'reg' })
    await live.verifyEmailChange({ token: 'chg' })
    expect(apiRequest.mock.calls.map((c) => c[1])).toEqual(['/api/auth/verify-email/', '/api/auth/verify-email-change/'])
  })
})

describe('mock email change parity', () => {
  it('keeps the old email until verification, then swaps it once', async () => {
    await mock.cancelEmailChange()
    const original = me().email
    await expect(mock.verifyEmailChange({ token: 'x' })).rejects.toMatchObject({ code: 'email_change_stale' })

    const after = await mock.changeEmail({ email: 'brand-new@example.com', password: 'anything-1' })
    expect(after.email).toBe(original)
    expect(after.pendingEmail).toBe('brand-new@example.com')

    await expect(mock.verifyEmailChange({})).rejects.toMatchObject({ code: 'invalid_token' })
    expect(me().email).toBe(original)

    const done = await mock.verifyEmailChange({ token: 'x' })
    expect(done.email).toBe('brand-new@example.com')
    expect(me().email).toBe('brand-new@example.com')
    expect(me().pendingEmail).toBe('')

    await expect(mock.verifyEmailChange({ token: 'x' })).rejects.toMatchObject({ code: 'email_change_stale' })
  })

  it('rejects an address already used by another account', async () => {
    const other = db.users.find((u) => u.id !== ME && u.email)
    await expect(mock.changeEmail({ email: other.email, password: 'anything-1' })).rejects.toMatchObject({
      fields: { email: expect.any(String) },
    })
  })

  it('rejects a registration verification without a token', async () => {
    await expect(mock.verifyEmail({})).rejects.toMatchObject({ code: 'invalid_token' })
    await expect(mock.verifyEmail({ token: 'ok' })).resolves.toEqual({ verified: true })
  })
})
