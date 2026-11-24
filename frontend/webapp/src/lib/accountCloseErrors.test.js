import { describe, expect, it } from 'vitest'
import { ApiError } from '@/api/http'
import { ACCOUNT_CLOSE_ERROR_MESSAGES, messageForAccountCloseError, rethrowAccountCloseError } from './accountCloseErrors'

describe('accountCloseErrors', () => {
  it('maps known backend codes', () => {
    for (const [code, text] of Object.entries(ACCOUNT_CLOSE_ERROR_MESSAGES)) {
      const err = new ApiError('raw', { code, status: 400 })
      expect(messageForAccountCloseError(err)).toBe(text)
    }
  })

  it('rethrow preserves status, code, and fields with friendly message', () => {
    const raw = new ApiError('bad', { code: 'invalid_password', status: 400, fields: { password: 'x' } })
    try {
      rethrowAccountCloseError(raw)
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError)
      expect(e.message).toBe(ACCOUNT_CLOSE_ERROR_MESSAGES.invalid_password)
      expect(e.code).toBe('invalid_password')
      expect(e.status).toBe(400)
      expect(e.fields.password).toBe(ACCOUNT_CLOSE_ERROR_MESSAGES.invalid_password)
    }
  })

  it('does not remap unrelated errors', () => {
    const raw = new ApiError('other', { code: 'something_else', status: 500 })
    try {
      rethrowAccountCloseError(raw)
    } catch (e) {
      expect(e.message).toBe('other')
    }
  })
})