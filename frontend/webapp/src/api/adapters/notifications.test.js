import { describe, expect, it } from 'vitest'
import { mapNotificationCounts, mapNotificationItem, mapResolved } from './notifications'

describe('notifications adapter', () => {
  it('maps action to needs_action', () => {
    const item = mapNotificationItem({
      id: 1,
      kind: 'payment_submitted',
      title: 't',
      message: 'b',
      created_at: 'x',
      read_at: null,
      group: 'payments',
      needs_action: true,
      resolved: null,
      payload: { action: { type: 'payment', payment_id: 9, plan_id: 1 } },
      link: '/app/plans/1/review',
    })
    expect(item.needsAction).toBe(true)
    expect(item.action.paymentId).toBe('9')
    expect(item.detail).toBe('b')
  })

  it('maps resolved labels', () => {
    expect(mapResolved('reversed')).toBe('Reversed')
    expect(mapResolved('unknown_x')).toBe('Done')
  })

  it('maps counts', () => {
    expect(mapNotificationCounts({ action: 2, all: 5 }).needs_action).toBe(2)
    expect(mapNotificationCounts({ action: 2, all: 5 }).action).toBe(2)
  })
})
