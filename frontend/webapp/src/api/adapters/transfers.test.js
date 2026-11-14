import { describe, expect, it } from 'vitest'
import { ApiError } from '../errors'
import { enrichTransferError, mapIncomingTransfer, mapOwnerTransfer } from './transfers'

describe('transfer adapter', () => {
  it('maps owner pending transfer for plan detail', () => {
    const out = mapOwnerTransfer({
      id: 12,
      status: 'pending',
      to: { id: 55, name: 'Sam', first_name: 'Sam', avatar_id: 'sage' },
      created_at: '2026-11-01T10:00:00+06:00',
    })
    expect(out.id).toBe('12')
    expect(out.toUserId).toBe('55')
    expect(out.status).toBe('pending')
  })

  it('maps incoming transfer for member plan', () => {
    const out = mapIncomingTransfer({
      id: 3,
      created_at: '2026-11-02T10:00:00+06:00',
      from: { name: 'Owner', first_name: 'Owner', avatar_id: 'coral' },
    })
    expect(out.id).toBe('3')
    expect(out.from.firstName).toBe('Owner')
  })

  it('enriches conflict codes to friendly toasts', () => {
    const err = enrichTransferError(new ApiError('raw', { code: 'transfer_closed', status: 409 }))
    expect(err.message).toBe('This transfer is no longer open.')
    const owner = enrichTransferError(new ApiError('raw', { code: 'owner_changed', status: 409 }))
    expect(owner.message).toBe('The plan owner changed. Refresh and try again.')
  })

  it('maps api member_id field to memberId', () => {
    const err = enrichTransferError(
      new ApiError('Check fields', { status: 400, fields: { member_id: 'Pick a member.' } }),
    )
    expect(err.fields.memberId).toBe('Pick a member.')
  })
})