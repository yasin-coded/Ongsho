import { addDays, addMonthsAnchored, addYearsAnchored, dayOfMonth, diffDays } from '@/lib/dates'
import { splitExact, usdToPaisa } from '@/lib/money'

const PRESET_CYCLE_UNITS = new Set(['week', 'month', 'year'])

export function isPresetCycleUnit(unit) {
  return PRESET_CYCLE_UNITS.has(unit)
}

/** Schedule anchor for nth due dates: trial end, or plan start (start is not a renewal). */
export function scheduleFirst(plan) {
  if (plan.trialEnd) return plan.trialEnd
  return plan.startDate
}

export function renewalKStart(plan) {
  if (plan.trialEnd) return 0
  const first = scheduleFirst(plan)
  const start = plan.startDate
  const anchor = plan.anchorDay ?? dayOfMonth(plan.trialEnd ?? plan.startDate)
  const { unit, count } = plan.cycle ?? { unit: 'month', count: 1 }
  const due0 = nthDueDateFromFirst(first, anchor, unit, count, 0)
  return due0 <= start ? 1 : 0
}

/** First billable renewal on the schedule grid (matches backend first_renewal_date). */
export function firstRenewalDate(plan) {
  const first = scheduleFirst(plan)
  const anchor = plan.anchorDay ?? dayOfMonth(plan.trialEnd ?? plan.startDate)
  const { unit, count } = plan.cycle ?? { unit: 'month', count: 1 }
  return nthDueDateFromFirst(first, anchor, unit, count, renewalKStart(plan))
}

/** @deprecated Use firstRenewalDate — kept for older imports. */
export const firstBillDate = firstRenewalDate

function nthDueDateFromFirst(first, anchorDay, unit, count, k) {
  if (unit === 'month') return addMonthsAnchored(first, k * count, anchorDay)
  if (unit === 'year') return addYearsAnchored(first, k * count, anchorDay)
  if (unit === 'week') return addDays(first, k * count * 7)
  return addDays(first, k * count)
}

/** Default next-renewal field on the form when it still matches the schedule (omit from API). */
export function defaultNextRenewalForForm(form) {
  const cycle = cycleFromForm(form)
  const plan = {
    startDate: form.startDate,
    trialEnd: form.trialEnd || null,
    cycle,
    anchorDay: dayOfMonth(form.trialEnd || form.startDate),
  }
  return firstRenewalDate(plan)
}

/** Preset chips: first renewal after start (trial uses trial end as first bill; chip default is still one period after start until trial is set). */
export function presetNextRenewalFromStart(startDate, cycleUnit, trialEnd = null) {
  if (!startDate || !isPresetCycleUnit(cycleUnit)) return ''
  if (trialEnd) {
    const plan = {
      startDate,
      trialEnd,
      cycle: { unit: cycleUnit, count: 1 },
      anchorDay: dayOfMonth(trialEnd),
    }
    return nthDueDate(plan, 1)
  }
  const plan = { startDate, trialEnd: null, cycle: { unit: cycleUnit, count: 1 }, anchorDay: dayOfMonth(startDate) }
  return firstRenewalDate(plan)
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
  const first = firstRenewalDate({
    startDate: form.startDate,
    trialEnd: form.trialEnd || null,
    cycle: { unit: 'month', count: 1 },
    anchorDay: dayOfMonth(form.trialEnd || form.startDate),
  })
  const renewal = form.nextRenewalDate || form.endDate
  if (!first || !renewal) return { unit: 'day', count: 1 }
  return { unit: 'day', count: Math.max(1, diffDays(renewal, first)) }
}

/** When member billing may begin (mock plans may set billingFrom; else plan start). */
export function billingFromDate(plan) {
  return plan.billingFrom ?? plan.startDate
}

/** The k-th renewal date on the schedule (k starts at renewalKStart). */
export function nthDueDate(plan, k) {
  const first = scheduleFirst(plan)
  const anchor = plan.anchorDay ?? dayOfMonth(plan.trialEnd ?? plan.startDate)
  const { unit, count } = plan.cycle
  return nthDueDateFromFirst(first, anchor, unit, count, k)
}

/** No charge is created on or after this date (pause, cancel, fixed-term end). */
export function stopDate(plan) {
  const stops = [plan.pausedOn, plan.cancelledOn, plan.renewal === 'fixed' ? plan.endDate : null].filter(Boolean)
  return stops.length ? stops.sort()[0] : null
}

/** Billing cycles: period_start … due_date inclusive; next cycle begins due_date + 1 day. */
export function billingPeriodsBetween(plan, from, to) {
  const first = scheduleFirst(plan)
  const startK = renewalKStart(plan)
  const stop = stopDate(plan)
  const anchor = plan.anchorDay ?? dayOfMonth(plan.trialEnd ?? plan.startDate)
  const { unit, count } = plan.cycle
  const out = []
  for (let k = startK; k < 600; k += 1) {
    const due = nthDueDateFromFirst(first, anchor, unit, count, k)
    if (stop && due >= stop) break
    const periodStart = k === startK ? first : addDays(nthDueDateFromFirst(first, anchor, unit, count, k - 1), 1)
    const periodEnd = periodEndFor(plan, due)
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
  const startK = renewalKStart(plan)
  for (let k = startK; k < 600; k += 1) {
    const date = nthDueDate(plan, k)
    if (date > to) break
    if (stop && date >= stop) break
    if (date >= from && !skipped.has(date)) out.push(date)
  }
  return out
}

export function nextDueDate(plan, from) {
  const stop = stopDate(plan)
  const startK = renewalKStart(plan)
  for (let k = startK; k < 600; k += 1) {
    const date = nthDueDate(plan, k)
    if (stop && date >= stop) return null
    if (date >= from && !(plan.skipDates ?? []).includes(date)) return date
  }
  return null
}

export function periodEndFor(plan, dueDate) {
  const first = scheduleFirst(plan)
  const anchor = plan.anchorDay ?? dayOfMonth(plan.trialEnd ?? plan.startDate)
  const { unit, count } = plan.cycle
  const stop = stopDate(plan)
  for (let k = renewalKStart(plan); k < 600; k += 1) {
    const d = nthDueDateFromFirst(first, anchor, unit, count, k)
    if (d === dueDate) {
      const next = nthDueDateFromFirst(first, anchor, unit, count, k + 1)
      if (stop && next >= stop) return dueDate
      return addDays(next, -1)
    }
    if (d > dueDate) break
  }
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