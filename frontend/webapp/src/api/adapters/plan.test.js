import { describe, expect, it } from 'vitest'
import { buildCreatePayload, mapListResponse, mapSubscriptionDetail } from './plan'
import { mapOwnerTransfer } from './transfers'

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
    expect(body.renewal_type).toBe('auto')
    expect(body.invite_emails).toEqual(['friend@example.com'])
    expect(body.next_renewal_date).toBeNull()
  })

  it('sends next renewal for custom billing', () => {
    const body = buildCreatePayload(
      { ...form, cycleUnit: 'custom', nextRenewalDate: '2026-05-01', startDate: '2026-03-01' },
      1,
    )
    expect(body.cycle_unit).toBe('day')
    expect(body.next_renewal_date).toBe('2026-05-01')
  })

  it('maps USD and fixed term', () => {
    const usd = buildCreatePayload(
      { ...form, currency: 'USD', price: '9.99', rate: '122.5', renewal: 'fixed', endDate: '2027-01-01', nextRenewalDate: '', cycleUnit: 'custom' },
      1,
    )
    expect(usd.currency).toBe('USD')
    expect(usd.exchange_rate).toBe('122.50')
    expect(usd.renewal_type).toBe('fixed_term')
    expect(usd.cycle_unit).toBe('day')
    expect(usd.cycle_count).toBeGreaterThan(60)
  })
})

describe('mapSubscriptionDetail', () => {
  it('maps confirmed_so_far amounts for the progress bar', () => {
    const out = mapSubscriptionDetail({
      id: 1,
      plan_name: 'Family',
      service_name: { name: 'Spotify' },
      renewal_type: 'auto',
      confirmed_so_far: { paid: '800.00', waived: '0.00', pending: '0.00', expected: '800.00' },
      price_now: { amount: '1200.00', currency: 'BDT', amount_bdt: '1200.00' },
    })
    expect(out.confirmedSoFar.total).toBe(80000)
    expect(out.confirmedSoFar.paid).toBe(80000)
    expect(out.confirmedSoFar.pending).toBe(0)
  })

  it('maps activity timestamps for fmtWhen', () => {
    const out = mapSubscriptionDetail({
      id: 2,
      plan_name: 'Pro',
      service_name: { name: 'Netflix' },
      renewal_type: 'auto',
      activity: [{ id: 9, text: 'Plan created', tone: 'info', created_at: '2026-11-13T14:00:00+06:00' }],
    })
    expect(out.activity[0].ts).toBe('2026-11-13T14:00:00+06:00')
  })
})

describe('mapListResponse', () => {
  it('uses member rows for status pill when API member_count is stale', () => {
    const out = mapListResponse({
      results: [
        {
          id: 1,
          plan_name: 'Spotify Family',
          status: 'active',
          cycle_unit: 'month',
          cycle_count: 1,
          currency: 'BDT',
          plan_mode: 'owner',
          member_count: 1,
          seats_taken: 3,
          monthly_cost: '1200.00',
          price_now: { currency: 'BDT', amount_bdt: '1200.00' },
          members: [
            { id: 1, user_id: 1, name: 'You', first_name: 'You', due_status: 'paid' },
            { id: 2, user_id: 2, name: 'A', first_name: 'A', due_status: 'paid' },
            { id: 3, user_id: 3, name: 'B', first_name: 'B', due_status: 'paid' },
          ],
        },
      ],
      count: 1,
    })
    expect(out.items[0].statusPill).toEqual({ key: 'allpaid', label: 'All paid' })
    expect(out.items[0].shared).toBe(true)
  })

  it('maps live collection totals', () => {
    const out = mapListResponse({
      results: [],
      count: 0,
      counts: { all: 0 },
      totals: { count: 0, to_providers: '0', confirmed: '100.00', pending: '50.00', expected: '200.00', review_count: 1, review_plans: [{ id: 3, plan_name: 'Netflix', count: 1 }] },
    })
    expect(out.totals.confirmed).toBe(10000)
    expect(out.totalsMeta.memberCollections).toBe(true)
  })
})
