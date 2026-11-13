import { describe, expect, it } from 'vitest'
import { ApiError } from '../errors'
import { enrichPaymentError, mapPaymentFields } from './payments'

describe('payments adapter', () => {
  it('maps API fields to form keys', () => {
    expect(mapPaymentFields({ transaction_id: 'x', due_ids: 'bad' })).toEqual({ tid: 'x', dues: 'bad' })
  })

  it('maps known error codes', () => {
    const err = enrichPaymentError(new ApiError('raw', { code: 'due_not_open', status: 409 }))
    expect(err.message).toMatch(/no longer open/)
  })
})
