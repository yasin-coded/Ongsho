import { describe, expect, it } from 'vitest'
import { addDays, todayDhaka } from '@/lib/dates'
import { buildCreatePayload, buildPatchPayload, mapListResponse, mapSubscriptionDetail } from './plan'
describe('buildPatchPayload', () => {
  it('omits locked trial_end_date so note-only edits save', () => {
    const body = buildPatchPayload({
      planName: 'ChatGPT',
      note: 'Updated note',
      method: 'bkash',
      rarelyUsed: false,
      trialEnd: '',
      endDate: '',
      nextRenewalDate: '2026-12-15',
    })
    expect(body).toEqual({
      plan_name: 'ChatGPT',
      note: 'Updated note',
      recommended_method: 'bkash',
      rarely_used: false,
      end_date: null,
      next_renewal_date: '2026-12-15',
    })
    expect(body).not.toHaveProperty('trial_end_date')
  })

  it('skips unchanged next renewal so PATCH can carry only metadata fields', () => {
    const body = buildPatchPayload(
      { note: 'hello', nextRenewalDate: '2026-12-15' },
      { baseline: { nextRenewalDate: '2026-12-15' } },
    )
    expect(body).toEqual({ note: 'hello' })
    expect(body).not.toHaveProperty('next_renewal_date')
  })
})

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
    nextRenewalDate: '2026-03-15',
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
      confirmed_so_far: { paid: '800.00', waived: '0.00', pending: '100.00', expected: '1200.00' },
      price_now: { amount: '1200.00', currency: 'BDT', amount_bdt: '1200.00' },
    })
    expect(out.confirmedSoFar.total).toBe(120000)
    expect(out.confirmedSoFar.paid).toBe(80000)
    expect(out.confirmedSoFar.pending).toBe(10000)
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

  it('shows due when the owner seat is not paid even if members are', () => {
    const out = mapListResponse({
      results: [
        {
          id: 2,
          plan_name: 'ChatGPT Pro',
          status: 'active',
          cycle_unit: 'month',
          cycle_count: 1,
          currency: 'BDT',
          plan_mode: 'owner',
          member_count: 2,
          seats_taken: 2,
          monthly_cost: '500.00',
          price_now: { currency: 'BDT', amount_bdt: '500.00' },
          members: [
            { id: 1, user_id: 1, name: 'You', first_name: 'You', is_owner_seat: true, due_status: 'due' },
            { id: 2, user_id: 2, name: 'Guest', first_name: 'Guest', due_status: 'paid' },
          ],
        },
      ],
      count: 1,
    })
    expect(out.items[0].statusPill).toEqual({ key: 'due', label: '1 due', count: 1 })
  })

  it('solo plan status pill is due or paid, not a second Just me', () => {
    const base = {
      id: 9,
      plan_name: 'Solo Netflix',
      status: 'active',
      cycle_unit: 'month',
      cycle_count: 1,
      currency: 'BDT',
      plan_mode: 'owner',
      member_count: 1,
      seats_taken: 1,
      monthly_cost: '500.00',
      price_now: { currency: 'BDT', amount_bdt: '500.00' },
      members: [{ id: 1, user_id: 1, name: 'You', first_name: 'You', is_owner_seat: true, due_status: 'due' }],
    }
    expect(mapListResponse({ results: [base], count: 1 }).items[0].statusPill).toEqual({
      key: 'due',
      label: 'Due',
    })
    expect(mapListResponse({ results: [{ ...base, members: [{ ...base.members[0], due_status: 'paid' }] }], count: 1 }).items[0].statusPill).toEqual({
      key: 'allpaid',
      label: 'Paid',
    })
    expect(mapListResponse({ results: [base], count: 1 }).items[0].shared).toBe(false)
  })

  it('treats null due as due when the plan started and is inside the current renewal window', () => {
    const today = todayDhaka()
    const out = mapListResponse({
      results: [
        {
          id: 1,
          plan_name: 'New plan',
          status: 'active',
          start_date: today,
          next_renewal: addDays(today, 30),
          cycle_unit: 'month',
          cycle_count: 1,
          currency: 'BDT',
          plan_mode: 'reseller',
          seats_taken: 2,
          seats: 4,
          monthly_cost: '800.00',
          price_now: { currency: 'BDT', amount_bdt: '800.00' },
          members: [
            { id: 1, user_id: 10, name: 'A', first_name: 'A', due_status: null, joined_on: today },
            { id: 2, user_id: 11, name: 'B', first_name: 'B', due_status: null, joined_on: today },
          ],
        },
      ],
      count: 1,
    })
    expect(out.items[0].statusPill).toEqual({ key: 'due', label: '2 due', count: 2 })
  })

  it('shows not billed yet when members have no due on the current cycle', () => {
    const out = mapListResponse({
      results: [
        {
          id: 1,
          plan_name: 'Apple Music',
          status: 'active',
          start_date: '2099-01-01',
          next_renewal: '2099-02-01',
          cycle_unit: 'month',
          cycle_count: 1,
          currency: 'BDT',
          plan_mode: 'reseller',
          seats_taken: 2,
          seats: 4,
          monthly_cost: '800.00',
          price_now: { currency: 'BDT', amount_bdt: '800.00' },
          per_seat: '200.00',
          members: [
            { id: 1, user_id: 10, name: 'A', first_name: 'A', due_status: null },
            { id: 2, user_id: 11, name: 'B', first_name: 'B', due_status: null },
          ],
        },
      ],
      count: 1,
    })
    expect(out.items[0].statusPill).toEqual({ key: 'upcoming', label: 'Not billed yet' })
    expect(out.items[0].perSeat).toBe(20000)
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
