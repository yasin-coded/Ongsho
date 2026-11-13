import { describe, expect, it } from 'vitest'
import { mapCalendarEvent, mapCalendarResponse } from './calendar'

describe('calendar adapter', () => {
  it('maps events', () => {
    const e = mapCalendarEvent({
      id: 9,
      plan_id: 2,
      plan_name: 'Netflix',
      date: '2026-03-01',
      amount: '1200.00',
      kind: 'due',
      role: 'member',
      status: 'paid',
    })
    expect(e.planId).toBe('2')
    expect(e.amount).toBe(120000)
    expect(e.role).toBe('member')
    expect(e.status).toBe('paid')
  })

  it('maps response lists', () => {
    const out = mapCalendarResponse({ events: [{ plan_id: 1, date: 'a' }], next7: [] })
    expect(out.events).toHaveLength(1)
    expect(out.next7).toHaveLength(0)
  })
})
