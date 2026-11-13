import { passwordRules } from '@/api/accounts'
import { parseTaka } from '@/lib/money'
import { todayDhaka, diffDays } from '@/lib/dates'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export const LIMITS = {
  name: 255,
  planName: 255,
  categoryName: 40,
  note: 2000,
}

export function validateEmail(value) {
  if (!EMAIL_RE.test(String(value ?? '').trim())) return 'Enter an email address like name@example.com.'
  return null
}

export function validatePassword(value) {
  if (passwordRules(value ?? '').some((r) => !r.ok)) return 'The password does not meet the rules below.'
  return null
}

export function validatePasswordRepeat(password, repeat) {
  if (password !== repeat) return 'The two passwords do not match.'
  return null
}

export function validateName(value, { max = LIMITS.name } = {}) {
  const trimmed = String(value ?? '').trim()
  if (!trimmed) return 'Enter your name.'
  if (trimmed.length > max) return `Use at most ${max} characters.`
  return null
}

export function validatePlanName(value) {
  const trimmed = String(value ?? '').trim()
  if (!trimmed) return 'Give the plan a name, for example "Netflix Premium".'
  if (trimmed.length > LIMITS.planName) return `Use at most ${LIMITS.planName} characters.`
  return null
}

export function validateCategoryName(value) {
  const trimmed = String(value ?? '').trim().replace(/\s+/g, ' ')
  if (!trimmed) return 'Type a category name.'
  if (trimmed.length > LIMITS.categoryName) return 'Keep it under 40 characters.'
  return null
}

export function validateServiceName(value) {
  const trimmed = String(value ?? '').trim().replace(/\s+/g, ' ')
  if (!trimmed) return 'Type a service name.'
  if (trimmed.length > LIMITS.planName) return `Use at most ${LIMITS.planName} characters.`
  return null
}

export function validateRequiredPassword(value) {
  if (!String(value ?? '')) return 'Enter your password.'
  return null
}

export function validateMemberId(value) {
  if (!value) return 'Pick a member.'
  return null
}

export function validateAmount(text) {
  const paisa = parseTaka(text)
  if (paisa === null || paisa <= 0) return 'Enter the price you pay, more than 0.'
  return null
}

export function validateRate(text) {
  const paisa = parseTaka(text)
  if (paisa === null || paisa <= 0) return 'Enter the rate you are paying, for example 122.'
  return null
}

export function validateSeats(value, { minTaken = 0, mode = 'owner' } = {}) {
  const n = Number(value)
  if (!(n >= 1)) return mode === 'reseller' ? 'Enter how many buyers, 1 or more.' : 'Enter how many seats, 1 or more.'
  if (n > 20) return 'Up to 20 seats per plan.'
  if (n < minTaken) return 'Seats cannot be below the people already on the plan.'
  return null
}

export function validateInviteEmails(emails, { freeSeats }) {
  const list = emails ?? []
  const bad = list.find((e) => validateEmail(e))
  if (bad) return `"${bad}" is not an email address.`
  if (new Set(list.map((e) => e.toLowerCase())).size !== list.length) return 'Each invite email must be different.'
  if (list.length > freeSeats) return 'There are more invites than free seats. Add seats or remove an email.'
  return null
}

export function validateDateNotBeforeToday(iso, label = 'Date') {
  if (!iso) return null
  const today = todayDhaka()
  if (iso < today) return `${label} cannot be before today.`
  return null
}

export function validatePriceChangeEffective(effectiveFrom) {
  return validateDateNotBeforeToday(effectiveFrom, 'Effective date')
}

export function validateLeaveDate(leaveDate) {
  if (!leaveDate) return 'Pick a leave date.'
  const today = todayDhaka()
  if (leaveDate < today) return 'Leave date cannot be before today.'
  if (diffDays(leaveDate, today) > 90) return 'Leave date cannot be more than 90 days ahead.'
  return null
}

export function validateTid(tid) {
  const clean = String(tid ?? '').replace(/\s+/g, '').toUpperCase()
  if (clean.length < 6) return 'Enter the transaction ID from your receipt.'
  if (clean.length > 64) return 'That ID is too long. Copy the full ID from your receipt.'
  if (!/^[A-Z0-9-]+$/.test(clean)) return 'Use letters, digits and dashes only.'
  return null
}

export function validateDateOrder({ startDate, trialEnd, endDate, nextRenewal, today = todayDhaka() }) {
  const fields = {}
  if (trialEnd && startDate && trialEnd < startDate) fields.trialEnd = 'The trial cannot end before the plan starts.'
  if (endDate && startDate && endDate <= startDate) fields.endDate = 'The end date must be after the start date.'
  if (nextRenewal && nextRenewal < today) fields.nextRenewalDate = 'Next renewal cannot be before today.'
  return fields
}

export function validatePlanForm(form, { editing = false, minSeats = 0 } = {}) {
  const fields = {}
  if (!String(form.serviceName ?? '').trim()) fields.serviceName = 'Pick or type a service name.'
  const pn = validatePlanName(form.planName)
  if (pn) fields.planName = pn
  if (!form.categoryId) fields.categoryId = 'Pick a category.'
  if (!editing) {
    const amount = validateAmount(String(form.price))
    if (amount) fields.price = amount
    if (form.currency === 'USD') {
      const rate = validateRate(String(form.rate))
      if (rate) fields.rate = rate
    }
    if (!form.startDate) fields.startDate = 'Pick the start date.'
  }
  if (form.cycleUnit === 'custom' && form.renewal !== 'fixed') {
    if (!form.nextRenewalDate) fields.nextRenewalDate = 'Pick the next renewal date.'
    else {
      const first = form.trialEnd || form.startDate
      if (first && form.nextRenewalDate <= first) {
        fields.nextRenewalDate = 'Next renewal must be after the start date.'
      }
    }
  }
  Object.assign(fields, validateDateOrder({
    startDate: form.startDate,
    trialEnd: form.trialEnd || null,
    endDate: form.renewal === 'fixed' ? form.endDate : null,
    nextRenewal: form.nextRenewalDate || null,
  }))
  if (form.renewal === 'fixed' && !form.endDate) fields.endDate = 'Pick the date the plan ends.'
  const seatsErr = validateSeats(form.seats, { minTaken: minSeats, mode: form.mode })
  if (seatsErr) fields.seats = seatsErr
  const free = Math.max(0, Number(form.seats) - (form.mode === 'owner' ? 1 : 0))
  const inv = validateInviteEmails(form.invites, { freeSeats: free })
  if (inv) fields.invites = inv
  return fields
}
