import { addDays, addMonthsAnchored, addYearsAnchored, dayOfMonth, diffDays } from '@/lib/dates'
import { splitExact, usdToPaisa } from '@/lib/money'

const PRESET_CYCLE_UNITS = new Set(['week', 'month', 'year'])

export function isPresetCycleUnit(unit) {
  return PRESET_CYCLE_UNITS.has(unit)
}

/** Next renewal one full period after the start date (weekly / monthly / yearly chips). */
export function presetNextRenewalFromStart(startDate, cycleUnit) {
  if (!startDate || !isPresetCycleUnit(cycleUnit)) return ''
  const anchor = dayOfMonth(startDate)
  if (cycleUnit === 'week') return addDays(startDate, 7)
  if (cycleUnit === 'month') return addMonthsAnchored(startDate, 1, anchor)
  return addYearsAnchored(startDate, 1, anchor)
}

/** Send `next_renewal_date` only when the user aligned billing (custom or edited date). */
export function nextRenewalDateForApi(form) {
  if (form.renewal === 'fixed') return null
  const value = (form.nextRenewalDate || '').trim()
  if (!value) return null
  if (isPresetCycleUnit(form.cycleUnit)) {
    const auto = presetNextRenewalFromStart(form.startDate, form.cycleUnit)
    if (auto && value === auto) return null
  }
  return value
}

/** Custom billing: length in days between first bill date and the chosen next renewal. */
export function cycleFromForm(form) {
  if (form.cycleUnit !== 'custom') return { unit: form.cycleUnit, count: 1 }
  const first = form.trialEnd || form.startDate
  const renewal = form.nextRenewalDate || form.endDate
  if (!first || !renewal) return { unit: 'day', count: 1 }
  return { unit: 'day', count: Math.max(1, diffDays(renewal, first)) }
}

/** Anchor for the billing schedule (trial end or plan start). */
export function firstBillDate(plan) {
  return plan.trialEnd ?? plan.startDate
}

/** First renewal that may create a charge — never on plan start unless that is the trial end. */
export function billingFromDate(plan) {
  const first = firstBillDate(plan)
  if (plan.trialEnd) return first
  return nthDueDate(plan, 1)
}

/** The k-th due date counted from the first billed date. */
export function nthDueDate(plan, k) {
  const first = firstBillDate(plan)
  const anchor = plan.anchorDay ?? dayOfMonth(first)
  const { unit, count } = plan.cycle
  if (unit === 'month') return addMonthsAnchored(first, k * count, anchor)
  if (unit === 'year') return addYearsAnchored(first, k * count, anchor)
  if (unit === 'week') return addDays(first, k * count * 7)
  return addDays(first, k * count)
}

/** No charge is created on or after this date (pause, cancel, fixed-term end). */
export function stopDate(plan) {
  const stops = [plan.pausedOn, plan.cancelledOn, plan.renewal === 'fixed' ? plan.endDate : null].filter(Boolean)
  return stops.length ? stops.sort()[0] : null
}

/** Every due date in [from, to], inclusive, following the plan's rules. */
export function dueDatesBetween(plan, from, to) {
  const out = []
  const stop = stopDate(plan)
  const skipped = new Set(plan.skipDates ?? [])
  const billFrom = billingFromDate(plan)
  const effectiveFrom = from > billFrom ? from : billFrom
  for (let k = 0; k < 600; k += 1) {
    const date = nthDueDate(plan, k)
    if (date > to) break
    if (stop && date >= stop) break
    if (date >= effectiveFrom && !skipped.has(date)) out.push(date)
  }
  return out
}

export function nextDueDate(plan, from) {
  const stop = stopDate(plan)
  for (let k = 0; k < 600; k += 1) {
    const date = nthDueDate(plan, k)
    if (stop && date >= stop) return null
    if (date >= from && !(plan.skipDates ?? []).includes(date)) return date
  }
  return null
}

export function periodEndFor(plan, start) {
  for (let k = 0; k < 600; k += 1) {
    const date = nthDueDate(plan, k)
    if (date > start) return addDays(date, -1)
  }
  return start
}

/** Price in force on `date`. Later price changes never touch earlier charges. */
export function priceAt(plan, date) {
  const list = [...plan.prices].sort((a, b) => (a.effectiveFrom < b.effectiveFrom ? -1 : 1))
  let current = list[0]
  for (const p of list) if (p.effectiveFrom <= date) current = p
  if (plan.currency === 'USD') {
    return { currency: 'USD', usdCents: current.usdCents, rate: current.rate, amount: usdToPaisa(current.usdCents, current.rate) }
  }
  return { currency: 'BDT', amount: current.amount, usdCents: null, rate: null }
}

/** Monthly-equivalent cost in paisa, for comparing weekly and yearly plans. */
export function monthlyEquivalent(plan, amount) {
  const { unit, count } = plan.cycle
  if (unit === 'month') return Math.round(amount / count)
  if (unit === 'year') return Math.round(amount / (12 * count))
  if (unit === 'week') return Math.round((amount * 52) / (12 * count))
  return Math.round((amount * 365) / (12 * count))
}

export function isActiveOn(member, date) {
  return member.joinedOn <= date && (!member.leftOn || member.leftOn > date)
}

/**
 * Seat shares for one charge. Owner seat (Owner mode) is first and takes the leftover paisa.
 * Returns [{ memberId, amount }].
 */
export function splitCharge(plan, members, amount, date) {
  const seated = members
    .filter((m) => isActiveOn(m, date))
    .sort((a, b) => Number(b.isOwnerSeat) - Number(a.isOwnerSeat) || (a.joinedOn < b.joinedOn ? -1 : 1))
  if (!seated.length) return []
  if (plan.split === 'custom') {
    return seated.map((m) => ({ memberId: m.id, amount: m.customShare ?? 0 }))
  }
  const shares = splitExact(amount, seated.length, 0)
  return seated.map((m, i) => ({ memberId: m.id, amount: shares[i] }))
}

export const CYCLE_LABEL = { week: 'Weekly', month: 'Monthly', year: 'Yearly', day: 'Every day' }

export function cycleLabel(cycle) {
  if (cycle.count === 1) return CYCLE_LABEL[cycle.unit]
  return `Every ${cycle.count} ${cycle.unit}s`
}

export function perCycleLabel(cycle) {
  if (cycle.count !== 1) return `/ ${cycle.count} ${cycle.unit}s`
  return { week: '/ week', month: '/ month', year: '/ year', day: '/ day' }[cycle.unit]
}
