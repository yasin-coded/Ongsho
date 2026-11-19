import { describe, expect, it } from 'vitest'
import { todayDhaka } from '@/lib/dates'
import { billingPeriodsBetween, firstBillDate, firstRenewalDate, nextDueDate, nthDueDate } from './schedule'

function plan(overrides) {
  return {
    startDate: '2026-01-05',
    trialEnd: null,
    cycle: { unit: 'month', count: 1 },
    anchorDay: 5,
    skipDates: [],
    pausedOn: null,
    cancelledOn: null,
    renewal: 'auto',
    endDate: null,
    ...overrides,
  }
}

describe('firstRenewalDate', () => {
  it('monthly from 2026-01-31 gives 2026-02-28', () => {
    expect(firstRenewalDate(plan({ startDate: '2026-01-31', anchorDay: 31 }))).toBe('2026-02-28')
    expect(nthDueDate(plan({ startDate: '2026-01-31', anchorDay: 31 }), 2)).toBe('2026-03-31')
  })

  it('yearly from 2028-02-29 gives 2029-02-28', () => {
    const p = plan({ startDate: '2028-02-29', anchorDay: 29, cycle: { unit: 'year', count: 1 } })
    expect(firstRenewalDate(p)).toBe('2029-02-28')
  })

  it('weekly from 2026-11-05 gives 2026-11-12', () => {
    const p = plan({ startDate: '2026-11-05', cycle: { unit: 'week', count: 1 }, anchorDay: 5 })
    expect(firstRenewalDate(p)).toBe('2026-11-12')
  })

  it('every 3 months from 2026-01-31 gives 2026-04-30', () => {
    const p = plan({ startDate: '2026-01-31', anchorDay: 31, cycle: { unit: 'month', count: 3 } })
    expect(firstRenewalDate(p)).toBe('2026-04-30')
  })

  it('trial ending 2026-11-07 gives first due on trial end then next monthly', () => {
    const p = plan({ startDate: '2026-11-01', trialEnd: '2026-11-07', anchorDay: 7 })
    expect(firstRenewalDate(p)).toBe('2026-11-07')
    expect(nthDueDate(p, 1)).toBe('2026-12-07')
  })

  it('start date of today gives one cycle from today', () => {
    const today = todayDhaka()
    const p = plan({ startDate: today, anchorDay: Number(today.slice(8, 10)) })
    expect(firstRenewalDate(p)).toBe(nextDueDate(p, today))
  })

  it('never returns the plain start when there is no trial', () => {
    const p = plan({ startDate: '2026-06-05' })
    expect(firstRenewalDate(p)).not.toBe(p.startDate)
    expect(firstRenewalDate(p)).toBe('2026-07-05')
  })

  it('first billing period starts on the plan start date', () => {
    const p = plan({ startDate: '2026-11-19', anchorDay: 19 })
    const [first] = billingPeriodsBetween(p, p.startDate, '2027-01-01')
    expect(first.periodStart).toBe('2026-11-19')
    expect(first.dueDate).toBe('2026-12-19')
  })
})

describe('firstBillDate alias', () => {
  it('matches firstRenewalDate', () => {
    expect(firstBillDate(plan())).toBe(firstRenewalDate(plan()))
  })
})