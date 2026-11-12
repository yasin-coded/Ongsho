import { describe, expect, it } from 'vitest'
import {
  validateDateOrder,
  validateEmail,
  validateInviteEmails,
  validateLeaveDate,
  validatePassword,
  validatePasswordRepeat,
  validatePlanForm,
  validateSeats,
} from './validation'
import { todayDhaka, addDays } from './dates'

describe('validateEmail', () => {
  it('accepts and rejects', () => {
    expect(validateEmail('a@b.co')).toBeNull()
    expect(validateEmail('bad')).toBeTruthy()
  })
})

describe('validatePassword', () => {
  it('requires letter and length', () => {
    expect(validatePassword('12345678')).toBeTruthy()
    expect(validatePassword('abc12345')).toBeNull()
  })
})

describe('validatePasswordRepeat', () => {
  it('matches', () => {
    expect(validatePasswordRepeat('a', 'b')).toBeTruthy()
    expect(validatePasswordRepeat('a', 'a')).toBeNull()
  })
})

describe('validateSeats', () => {
  it('bounds', () => {
    expect(validateSeats(0)).toBeTruthy()
    expect(validateSeats(21)).toBeTruthy()
    expect(validateSeats(5, { minTaken: 6 })).toBeTruthy()
    expect(validateSeats(6, { minTaken: 6 })).toBeNull()
  })
})

describe('validateInviteEmails', () => {
  it('counts free seats', () => {
    expect(validateInviteEmails(['a@b.co', 'a@b.co'], { freeSeats: 2 })).toBeTruthy()
    expect(validateInviteEmails(['a@b.co'], { freeSeats: 1 })).toBeNull()
  })
})

describe('validateDateOrder', () => {
  const today = todayDhaka()
  it('guards renewals', () => {
    const errs = validateDateOrder({ startDate: today, nextRenewal: addDays(today, -1), today })
    expect(errs.nextRenewalDate).toBeTruthy()
  })
})

describe('validateLeaveDate', () => {
  it('within 90 days', () => {
    expect(validateLeaveDate(addDays(todayDhaka(), 91))).toBeTruthy()
    expect(validateLeaveDate(addDays(todayDhaka(), 7))).toBeNull()
  })
})

describe('validatePlanForm', () => {
  const base = {
    serviceName: 'Netflix',
    planName: 'Family',
    categoryId: '1',
    price: '500',
    currency: 'BDT',
    rate: '122',
    cycleUnit: 'month',
    cycleCount: '1',
    startDate: todayDhaka(),
    trialEnd: '',
    renewal: 'auto',
    endDate: '',
    seats: '2',
    mode: 'owner',
    invites: [],
    nextRenewalDate: '',
  }
  it('BDT happy path', () => {
    expect(Object.keys(validatePlanForm(base))).toHaveLength(0)
  })
  it('USD needs rate', () => {
    const errs = validatePlanForm({ ...base, currency: 'USD', rate: '' })
    expect(errs.rate).toBeTruthy()
  })
})
