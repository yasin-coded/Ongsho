import { addDays, addMonthsAnchored, addYearsAnchored, dayOfMonth } from '@/lib/dates'
import { splitExact, usdToPaisa } from '@/lib/money'

/** First billed date: the trial end when there is one, else the start date. */
export function firstBillDate(plan) {
  return plan.trialEnd ?? plan.startDate
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
  for (let k = 0; k < 600; k += 1) {
    const date = nthDueDate(plan, k)
    if (date > to) break
    if (stop && date >= stop) break
    if (date >= from && !skipped.has(date)) out.push(date)
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
