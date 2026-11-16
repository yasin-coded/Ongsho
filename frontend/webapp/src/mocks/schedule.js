import { addDays, addMonthsAnchored, addYearsAnchored, dayOfMonth, diffDays } from '@/lib/dates'
import { splitExact, usdToPaisa } from '@/lib/money'

const PRESET_CYCLE_UNITS = new Set(['week', 'month', 'year'])

export function isPresetCycleUnit(unit) {
  return PRESET_CYCLE_UNITS.has(unit)
}

/** First renewal due date: trial end, or one full billing cycle after the start (start is not a renewal). */
export function firstBillDate(plan) {
  if (plan.trialEnd) return plan.trialEnd
  const anchor = plan.anchorDay ?? dayOfMonth(plan.startDate)
  const { unit, count } = plan.cycle ?? { unit: 'month', count: 1 }
  if (unit === 'month') return addMonthsAnchored(plan.startDate, count, anchor)
  if (unit === 'year') return addYearsAnchored(plan.startDate, count, anchor)
  if (unit === 'week') return addDays(plan.startDate, count * 7)
  return addDays(plan.startDate, count)
}

export const firstRenewalDate = firstBillDate

/** Default next-renewal field on the form when it still matches the schedule (omit from API). */
export function defaultNextRenewalForForm(form) {
  const cycle = cycleFromForm(form)
  const plan = {
    startDate: form.startDate,
    trialEnd: form.trialEnd || null,
    cycle,
    anchorDay: dayOfMonth(form.trialEnd || form.startDate),
  }
  return firstBillDate(plan)
}

/** Preset chips: first renewal after start (trial uses trial end as first bill; chip default is still one period after start until trial is set). */
export function presetNextRenewalFromStart(startDate, cycleUnit, trialEnd = null) {
  if (!startDate || !isPresetCycleUnit(cycleUnit)) return ''
  if (trialEnd) {
    const anchor = dayOfMonth(trialEnd)
    if (cycleUnit === 'week') return addDays(trialEnd, 7)
    if (cycleUnit === 'month') return addMonthsAnchored(trialEnd, 1, anchor)
    return addYearsAnchored(trialEnd, 1, anchor)
  }
  const plan = { startDate, trialEnd: null, cycle: { unit: cycleUnit, count: 1 }, anchorDay: dayOfMonth(startDate) }
  return firstBillDate(plan)
}

/** Send `next_renewal_date` only when the user aligned billing (custom or edited date). */
export function nextRenewalDateForApi(form) {
  if (form.renewal === 'fixed') return null
  const value = (form.nextRenewalDate || '').trim()
  if (!value) return null
  const auto = defaultNextRenewalForForm(form)
  if (auto && value === auto) return null
  if (isPresetCycleUnit(form.cycleUnit)) {
    const chipAuto = presetNextRenewalFromStart(form.startDate, form.cycleUnit, form.trialEnd || null)
    if (chipAuto && value === chipAuto) return null
  }
  return value
}

/** Custom billing: length in days between first renewal and the chosen next renewal. */
export function cycleFromForm(form) {
  if (form.cycleUnit !== 'custom') return { unit: form.cycleUnit, count: Number(form.cycleCount) || 1 }
  const first = firstBillDate({
    startDate: form.startDate,
    trialEnd: form.trialEnd || null,
    cycle: { unit: 'month', count: 1 },
    anchorDay: dayOfMonth(form.trialEnd || form.startDate),
  })
  const renewal = form.nextRenewalDate || form.endDate
  if (!first || !renewal) return { unit: 'day', count: 1 }
  return { unit: 'day', count: Math.max(1, diffDays(renewal, first)) }
}

/** When charge/dues generation may begin (mock plans may set billingFrom; else first renewal). */
export function billingFromDate(plan) {
  return plan.billingFrom ?? firstBillDate(plan)
}

/** The k-th due date counted from the first billed date (k = 0 is first renewal). */
export function nthDueDate(plan, k) {
  const first = firstBillDate(plan)
  const anchor = plan.anchorDay ?? dayOfMonth(plan.trialEnd ?? plan.startDate)
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

export function renewalKStart(plan) {
  return 0
}

/** Billing cycles: start … renewal (inclusive); next cycle begins the day after renewal. */
export function billingPeriodsBetween(plan, from, to) {
  const startK = renewalKStart(plan)
  const stop = stopDate(plan)
  const billFrom = billingFromDate(plan)
  const out = []
  for (let k = startK; k < 600; k += 1) {
    const due = nthDueDate(plan, k)
    if (stop && due >= stop) break
    if (due < billFrom) continue
    const first = nthDueDate(plan, startK)
    const periodStart = k === startK ? first : addDays(nthDueDate(plan, k - 1), 1)
    const periodEnd = due
    if (periodStart > to) break
    if (periodEnd >= from) out.push({ periodStart, dueDate: due, periodEnd })
  }
  return out
}

/** Renewal (cycle-end) dates in [from, to] — plan start is not a renewal. */
export function dueDatesBetween(plan, from, to) {
  const out = []
  const stop = stopDate(plan)
  const skipped = new Set(plan.skipDates ?? [])
  const billFrom = billingFromDate(plan)
  const effectiveFrom = from > billFrom ? from : billFrom
  for (let k = renewalKStart(plan); k < 600; k += 1) {
    const date = nthDueDate(plan, k)
    if (date > to) break
    if (stop && date >= stop) break
    if (date >= effectiveFrom && !skipped.has(date)) out.push(date)
  }
  return out
}

export function nextDueDate(plan, from) {
  const stop = stopDate(plan)
  for (let k = renewalKStart(plan); k < 600; k += 1) {
    const date = nthDueDate(plan, k)
    if (stop && date >= stop) return null
    if (date >= from && !(plan.skipDates ?? []).includes(date)) return date
  }
  return null
}

export function periodEndFor(_plan, dueDate) {
  return dueDate
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