import { describe, expect, it } from 'vitest'
import { buildCreatePayload, mapListResponse } from './plan'

describe('buildCreatePayload', () => {
  const form = {
    planName: 'Pro',
    categoryId: '3',
    mode: 'owner',
    note: '',
    currency: 'BDT',
    price: '1200',
    rate: '122',
    cycleUnit: 'month',
    cycleCount: '1',
    customUnit: 'month',
    startDate: '2026-03-01',
    trialEnd: '2026-03-15',
    renewal: 'auto',
    endDate: '',
    method: 'bkash',
    rarelyUsed: false,
    nextRenewalDate: '2026-04-01',
    seats: 2,
    split: 'equal',
    invites: ['friend@example.com'],
  }

  it('maps BDT create body', () => {
    const body = buildCreatePayload(form, 42)
    expect(body.service_name).toBe(42)
    expect(body.amount).toBe('1200.00')
    expect(body.renewal_type).toBe('ongoing')
    expect(body.invite_emails).toEqual(['friend@example.com'])
  })

  it('maps USD and fixed term', () => {
    const usd = buildCreatePayload(
      { ...form, currency: 'USD', price: '9.99', rate: '122.5', renewal: 'fixed', endDate: '2027-01-01', cycleUnit: 'custom', customUnit: 'week', cycleCount: '2' },
      1,
    )
    expect(usd.currency).toBe('USD')
    expect(usd.exchange_rate).toBe('122.50')
    expect(usd.renewal_type).toBe('fixed_term')
    expect(usd.cycle_unit).toBe('week')
    expect(usd.cycle_count).toBe(2)
  })
})

describe('mapListResponse', () => {
  it('marks TODO totals meta', () => {
    const out = mapListResponse({ results: [], count: 0, counts: { all: 0 }, totals: { count: 0, to_providers: '0' } })
    expect(out.totalsMeta.memberCollections).toBe(false)
  })
})
