import { describe, expect, it } from 'vitest'
import { normalizeApiError } from './errors'

describe('normalizeApiError', () => {
  it('maps backend fields to form names', () => {
    const err = normalizeApiError({
      response: {
        status: 400,
        data: { error: { code: 'validation_failed', message: 'Nope.', fields: { new_password: ['Too weak.'] } } },
      },
    })
    expect(err.fields.newPassword).toBe('Too weak.')
    expect(err.code).toBe('validation_failed')
  })
})
